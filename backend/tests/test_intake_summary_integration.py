"""Database tests for the summary edit/approve endpoints (SCRUM-342).

Runs the real endpoints against PostgreSQL in a rolled-back transaction, with
authentication overridden to pick the acting user.
"""

import json
import os
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from services.intake.agent import new_intake_state
from services.intake.summary import SummaryNotApprovedError, get_approved_summary
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import AuditEvent, Consent, Conversation, User, Workflow
from app.db.session import get_db
from app.main import app

test_db_url = os.environ.get("TEST_DATABASE_URL")
if not test_db_url:
    if os.environ.get("CI"):
        pytest.fail(
            "TEST_DATABASE_URL is required in CI but was not set.", pytrace=False
        )
    pytest.skip(
        "TEST_DATABASE_URL is not set; skipping database integration tests.",
        allow_module_level=True,
    )

VALUES = {
    "facts": "فصلني صاحب العمل بدون إخطار",
    "niche": "labor",
    "parties": "صاحب العمل",
    "key_dates": "يناير 2026",
    "urgency": "soon",
    "city": "طنطا",
    "budget": "حوالي 3000 جنيه",
    "documents": None,
    "deadlines": None,
    "preferred_times": "بعد الخامسة",
}


@pytest.fixture(scope="module")
def test_engine():
    url = os.environ["TEST_DATABASE_URL"].replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url, pool_pre_ping=True)
    if "workflows" not in inspect(engine).get_table_names():
        pytest.fail(
            "Table 'workflows' missing; run alembic upgrade head", pytrace=False
        )
    yield engine
    engine.dispose()


@pytest.fixture
def db(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _user(db: Session, role: str = "client") -> User:
    user = User(
        role=role, email=f"{uuid.uuid4().hex[:10]}@example.com", password_hash="x"
    )
    db.add(user)
    db.commit()  # survives a request's rollback; the outer test transaction doesn't
    return user


def _intake(db: Session, owner: User, phase: str = "SUMMARY_REVIEW") -> Workflow:
    conversation = Conversation(user_id=owner.id, type="qa")
    db.add(conversation)
    db.flush()
    intake = new_intake_state()
    for f, v in VALUES.items():
        intake["fields"][f] = (
            {"status": "provided", "value": v}
            if v
            else {"status": "not_provided", "value": None}
        )
    intake["complete"] = phase != "INTAKE"
    wf = Workflow(
        kind="intake",
        status="running" if phase == "INTAKE" else "awaiting_approval",
        conversation_id=conversation.id,
        state={"phase": phase, "context": {"messages": []}, "intake": intake},
    )
    db.add(wf)
    db.commit()
    return wf


@pytest.fixture
def api(db):
    """Yields (client, act_as) using the real DB session."""
    acting: dict[str, User] = {}
    app.dependency_overrides[get_current_user] = lambda: acting["user"]

    def session():  # like app.db.session.get_db: roll back on error
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = session

    def act_as(user: User) -> None:
        acting["user"] = user

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, act_as
    finally:
        app.dependency_overrides.clear()


def _patch(client, wf, fields):
    return client.patch(f"/client/intakes/{wf.id}/summary", json={"fields": fields})


def _approve(client, wf, fields=None, confirmed=True):
    return client.post(
        f"/client/intakes/{wf.id}/approve",
        json={"confirmed": confirmed, "fields": fields or VALUES},
    )


def _events(db: Session, wf: Workflow) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.workflow_id == wf.id)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def test_edit_during_review_saves_and_audits(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)

    resp = _patch(client, wf, {"city": "القاهرة", "budget": None})

    assert resp.status_code == 200
    data = resp.json()
    assert data["phase"] == "SUMMARY_REVIEW"
    assert data["approved_at"] is None
    assert data["fields"]["city"] == {"status": "provided", "value": "القاهرة"}
    assert data["fields"]["budget"] == {"status": "not_provided", "value": None}
    db.expire_all()
    stored = db.get(Workflow, wf.id).state["intake"]["fields"]
    assert stored["city"]["value"] == "القاهرة"
    (event,) = _events(db, wf)
    assert event.action == "summary.edited"
    assert event.actor_id == owner.id
    assert event.before is None
    assert event.after == {"changed_fields": ["budget", "city"]}
    stored_event = json.dumps([event.before, event.after], ensure_ascii=False)
    for text in ("طنطا", "القاهرة", "حوالي 3000 جنيه"):  # old and new values
        assert text not in stored_event


@pytest.mark.parametrize(
    "fields",
    [{"bogus": "x"}, {"niche": "family"}, {"urgency": "now"}, {"facts": "x" * 4001}],
)
def test_edit_validation_returns_422_and_changes_nothing(api, db, fields) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)

    assert _patch(client, wf, fields).status_code == 422
    db.expire_all()
    assert db.get(Workflow, wf.id).state["intake"]["fields"]["city"]["value"] == "طنطا"
    assert _events(db, wf) == []


def test_edit_and_approve_blocked_while_intake_runs(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner, phase="INTAKE")
    act_as(owner)

    assert _patch(client, wf, {"city": "القاهرة"}).status_code == 409
    assert _approve(client, wf).status_code == 409


def test_approve_happy_path_then_frozen(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)

    resp = _approve(client, wf)

    assert resp.status_code == 200
    data = resp.json()
    assert data["phase"] == "APPROVED"
    assert data["status"] == "completed"
    assert data["approved_at"] is not None

    db.expire_all()
    stored = db.get(Workflow, wf.id)
    snapshot = get_approved_summary(stored)
    assert snapshot["fields"]["city"]["value"] == "طنطا"
    (consent,) = db.scalars(select(Consent).where(Consent.user_id == owner.id))
    assert consent.type == "share_summary"
    assert snapshot["consent_id"] == str(consent.id)
    actions = [e.action for e in _events(db, wf)]
    assert sorted(actions) == ["approval.approved", "workflow.transition"]

    # Frozen: no edits, no second approval, still one consent.
    assert _patch(client, wf, {"city": "القاهرة"}).status_code == 409
    assert _approve(client, wf).status_code == 409
    consents = db.scalars(select(Consent).where(Consent.user_id == owner.id)).all()
    assert len(consents) == 1
    assert get_approved_summary(db.get(Workflow, wf.id)) == snapshot


def test_approve_with_missing_required_field_is_409(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    state = dict(wf.state)
    state["intake"]["fields"]["facts"] = {"status": "missing", "value": None}
    wf.state = {**state}
    db.commit()
    act_as(owner)

    resp = _approve(client, wf, {**VALUES, "facts": None})

    assert resp.status_code == 409
    assert db.scalars(select(Consent).where(Consent.user_id == owner.id)).all() == []


def test_approve_stale_summary_is_409(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)

    assert _approve(client, wf, {**VALUES, "city": "القاهرة"}).status_code == 409
    with pytest.raises(SummaryNotApprovedError):
        get_approved_summary(db.get(Workflow, wf.id))


def test_approve_requires_explicit_confirmation(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)
    assert _approve(client, wf, confirmed=False).status_code == 422


def test_other_users_cannot_touch_the_summary(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)

    act_as(_user(db))  # another client: forbidden, like other owned resources
    assert _patch(client, wf, {"city": "x"}).status_code == 403
    assert _approve(client, wf).status_code == 403

    act_as(_user(db, role="lawyer"))  # client-only router
    assert _patch(client, wf, {"city": "x"}).status_code == 403
    assert _approve(client, wf).status_code == 403

    act_as(owner)
    missing = uuid.uuid4()
    resp = client.patch(f"/client/intakes/{missing}/summary", json={"fields": {}})
    assert resp.status_code == 404
    assert _events(db, wf) == []


def test_approve_is_atomic_when_audit_fails(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)

    with patch(
        "services.intake.summary.log_event", side_effect=RuntimeError("audit down")
    ):
        assert _approve(client, wf).status_code == 500

    db.expire_all()
    assert db.get(Workflow, wf.id).state["phase"] == "SUMMARY_REVIEW"
    assert db.scalars(select(Consent).where(Consent.user_id == owner.id)).all() == []
    assert _events(db, wf) == []


def test_patch_and_approve_return_the_same_shape_as_get(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)

    patched = _patch(client, wf, {"city": "القاهرة"})
    got = client.get(f"/client/intakes/{wf.id}")
    assert patched.status_code == got.status_code == 200
    assert patched.json() == got.json()
    assert "approved_at" in got.json()

    approved = _approve(client, wf, {**VALUES, "city": "القاهرة"})
    got = client.get(f"/client/intakes/{wf.id}")
    assert approved.status_code == 200
    assert approved.json() == got.json()
    assert got.json()["approved_at"] is not None


@pytest.mark.parametrize(
    "change", [{"niche": "family"}, {"bogus": "x"}], ids=["bad-value", "unknown-key"]
)
def test_approve_mismatch_is_409_not_422(api, db, change) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)
    assert _approve(client, wf, {**VALUES, **change}).status_code == 409
