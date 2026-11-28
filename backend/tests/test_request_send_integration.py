"""Database tests for sending an approved intake to a lawyer (SCRUM-344).

Runs the real endpoints against PostgreSQL in a rolled-back transaction, with
authentication overridden to pick the acting user. The concurrency and
migration tests commit for real and clean up after themselves.
"""

import os
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from services.intake.agent import new_intake_state
from services.intake.summary import approve_summary, get_approved_summary
from services.requests.send import SendConflictError, send_request
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from alembic import command
from app.auth.dependencies import get_current_user
from app.db.models import (
    AuditEvent,
    Consent,
    Conversation,
    LawyerProfile,
    Request,
    User,
    Workflow,
)
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

MIGRATION = "d5a1c9e7b203"
PREVIOUS = "c3e8f0a2d417"

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


def _user(db: Session, role: str = "client", name: str | None = None) -> User:
    user = User(
        role=role,
        email=f"{uuid.uuid4().hex[:10]}@example.com",
        password_hash="x",
        full_name=name,
    )
    db.add(user)
    db.commit()  # survives a request's rollback; the outer test transaction doesn't
    return user


def _lawyer(db: Session, verified: bool = True, name: str = "أ. محامٍ") -> LawyerProfile:
    user = _user(db, role="lawyer", name=name)
    profile = LawyerProfile(
        user_id=user.id,
        niches=["labor", "family"],
        city="طنطا",
        fee_min=500,
        fee_max=1500,
        years_experience=7,
        bio="محامٍ عمالي",
        verified=verified,
    )
    db.add(profile)
    db.commit()
    return profile


def _intake(db: Session, owner: User, approve: bool = True) -> Workflow:
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
    intake["complete"] = True
    wf = Workflow(
        kind="intake",
        status="awaiting_approval",
        conversation_id=conversation.id,
        state={
            "phase": "SUMMARY_REVIEW",
            "context": {"messages": []},
            "intake": intake,
        },
    )
    db.add(wf)
    db.flush()
    if approve:
        approve_summary(db, wf.id, dict(VALUES), actor_id=owner.id)
    db.commit()
    return wf


def _finish(
    db: Session, request_id: str, status: str, age: int = 5, **extra
) -> Request:
    """Close a request as the lawyer/expiry job would, and make it older.

    Everything here runs in one transaction, so ``now()`` is the same for every
    row; ageing the closed request keeps "oldest first" well defined.
    """
    req = db.get(Request, uuid.UUID(request_id))
    req.status = status
    req.created_at = req.created_at - timedelta(minutes=age)
    for key, value in extra.items():
        setattr(req, key, value)
    db.commit()
    return req


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


def _send(client, wf, lawyer, **body):
    return client.post(
        f"/client/intakes/{wf.id}/send", json={"lawyer_id": str(lawyer.id), **body}
    )


def _requests(db: Session, wf: Workflow) -> list[Request]:
    db.expire_all()
    return list(db.scalars(select(Request).where(Request.intake_id == wf.id)))


# --- GET /client/lawyers ---------------------------------------------------------


def test_lawyers_list_shows_only_verified_lawyers(api, db) -> None:
    client, act_as = api
    verified = _lawyer(db, name="أ. سارة")
    hidden = _lawyer(db, verified=False, name="أ. عمر")
    act_as(_user(db))

    resp = client.get("/client/lawyers")

    assert resp.status_code == 200
    by_id = {item["id"]: item for item in resp.json()}
    assert str(hidden.id) not in by_id
    assert by_id[str(verified.id)] == {
        "id": str(verified.id),
        "full_name": "أ. سارة",
        "niches": ["labor", "family"],
        "city": "طنطا",
        "fee_min": 500,
        "fee_max": 1500,
        "years_experience": 7,
        "bio": "محامٍ عمالي",
    }

    act_as(_user(db, role="lawyer"))
    assert client.get("/client/lawyers").status_code == 403


# --- POST /client/intakes/{id}/send ----------------------------------------------


def test_send_happy_path_copies_snapshot_with_consent_and_audit(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    lawyer = _lawyer(db)
    act_as(owner)

    # The browser can't supply the summary: extra keys are ignored.
    resp = _send(client, wf, lawyer, summary={"facts": "نص مزور"})

    assert resp.status_code == 201
    data = resp.json()
    assert set(data) == {"id", "lawyer_id", "status", "created_at"}
    assert data["lawyer_id"] == str(lawyer.id)
    assert data["status"] == "sent"

    (req,) = _requests(db, wf)
    snapshot = get_approved_summary(db.get(Workflow, wf.id))
    assert str(req.id) == data["id"]
    assert req.summary == snapshot
    assert req.client_id == owner.id
    assert req.conversation_id == wf.conversation_id
    assert req.niche == "labor"
    approved_at = datetime.fromisoformat(snapshot["approved_at"])
    assert req.client_confirmed_at == approved_at.astimezone(UTC).replace(tzinfo=None)

    (consent,) = db.scalars(select(Consent).where(Consent.request_id == req.id))
    assert consent.type == "share_summary"
    assert consent.user_id == owner.id
    (event,) = db.scalars(select(AuditEvent).where(AuditEvent.request_id == req.id))
    assert event.action == "request.created"
    assert event.actor_id == owner.id
    assert event.workflow_id == wf.id
    assert event.after["consent_id"] == str(consent.id)


def test_send_before_approval_is_409(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner, approve=False)
    act_as(owner)
    assert _send(client, wf, _lawyer(db)).status_code == 409
    assert _requests(db, wf) == []


def test_send_to_unknown_or_unverified_lawyer_is_404(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)

    unknown = client.post(
        f"/client/intakes/{wf.id}/send", json={"lawyer_id": str(uuid.uuid4())}
    )
    assert unknown.status_code == 404
    assert _send(client, wf, _lawyer(db, verified=False)).status_code == 404
    assert _requests(db, wf) == []


def test_send_to_another_clients_intake_is_forbidden(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    lawyer = _lawyer(db)

    act_as(_user(db))
    assert _send(client, wf, lawyer).status_code == 403
    act_as(_user(db, role="lawyer"))
    assert _send(client, wf, lawyer).status_code == 403
    act_as(owner)
    missing = client.post(
        f"/client/intakes/{uuid.uuid4()}/send", json={"lawyer_id": str(lawyer.id)}
    )
    assert missing.status_code == 404
    assert _requests(db, wf) == []


@pytest.mark.parametrize("status", ["sent", "accepted"])
def test_send_while_latest_is_active_is_409(api, db, status) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)
    first = _send(client, wf, _lawyer(db)).json()
    if status != "sent":
        _finish(db, first["id"], status)

    assert _send(client, wf, _lawyer(db)).status_code == 409
    assert len(_requests(db, wf)) == 1


@pytest.mark.parametrize("status", ["declined", "expired"])
def test_resend_after_decline_or_expiry_keeps_history(api, db, status) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    first_lawyer, second_lawyer = _lawyer(db), _lawyer(db)
    act_as(owner)
    first = _send(client, wf, first_lawyer).json()
    _finish(db, first["id"], status)

    resp = _send(client, wf, second_lawyer)

    assert resp.status_code == 201
    statuses = {str(r.id): r.status for r in _requests(db, wf)}
    assert statuses == {first["id"]: status, resp.json()["id"]: "sent"}
    consents = db.scalars(
        select(Consent).where(Consent.request_id.in_(statuses.keys()))
    ).all()
    assert len(consents) == 2  # one per send


def test_resend_to_a_lawyer_who_declined_is_409(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    lawyer = _lawyer(db)
    act_as(owner)
    first = _send(client, wf, lawyer).json()
    _finish(db, first["id"], "declined")

    assert _send(client, wf, lawyer).status_code == 409
    assert len(_requests(db, wf)) == 1


def test_race_on_the_unique_index_is_409_not_500(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    act_as(owner)
    assert _send(client, wf, _lawyer(db)).status_code == 201

    # A send that missed the first one (as in a race) hits the partial index.
    with patch("services.requests.send.intake_requests", return_value=[]):
        resp = _send(client, wf, _lawyer(db))

    assert resp.status_code == 409
    assert len(_requests(db, wf)) == 1


# --- Intake response and GET /client/requests --------------------------------------


def test_intake_response_shows_latest_and_previous_requests(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    lawyers = [_lawyer(db) for _ in range(3)]
    act_as(owner)

    got = client.get(f"/client/intakes/{wf.id}").json()
    assert got["request"] is None
    assert got["previous_requests"] == []

    first = _send(client, wf, lawyers[0]).json()
    _finish(db, first["id"], "declined", age=10, decline_reason="مشغول")
    second = _send(client, wf, lawyers[1]).json()
    _finish(db, second["id"], "expired")
    third = _send(client, wf, lawyers[2]).json()

    got = client.get(f"/client/intakes/{wf.id}").json()
    assert got["request"]["id"] == third["id"]
    assert got["request"]["status"] == "sent"
    assert set(got["request"]) == {
        "id",
        "lawyer_id",
        "status",
        "created_at",
        "responded_at",
        "decline_reason",
    }
    assert [r["id"] for r in got["previous_requests"]] == [first["id"], second["id"]]
    assert got["previous_requests"][0]["decline_reason"] == "مشغول"


def test_client_requests_list_includes_old_requests_and_new_fields(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    declined_by = _lawyer(db, name="أ. خالد")
    act_as(owner)
    first = _send(client, wf, declined_by).json()
    responded = datetime(2026, 11, 28, 9, 30, tzinfo=UTC)
    _finish(db, first["id"], "declined", decline_reason="خارج تخصصي")
    db.get(Request, uuid.UUID(first["id"])).responded_at = responded
    db.commit()
    second = _send(client, wf, _lawyer(db, name="أ. منى")).json()

    resp = client.get("/client/requests")

    assert resp.status_code == 200
    items = {item["id"]: item for item in resp.json()}
    assert set(items) == {first["id"], second["id"]}
    old = items[first["id"]]
    assert old["status"] == "declined"
    assert old["intake_id"] == str(wf.id)
    assert old["lawyer_name"] == "أ. خالد"
    assert old["decline_reason"] == "خارج تخصصي"
    assert datetime.fromisoformat(old["responded_at"]) == responded
    assert items[second["id"]]["lawyer_name"] == "أ. منى"
    assert items[second["id"]]["responded_at"] is None

    single = client.get(f"/client/requests/{first['id']}").json()
    assert single == old


def test_post_client_requests_no_longer_exists(api, db) -> None:
    client, act_as = api
    act_as(_user(db))
    resp = client.post("/client/requests", json={"lawyer_id": str(uuid.uuid4())})
    assert resp.status_code == 405


# --- Concurrency (real commits) ------------------------------------------------------


def _cleanup(engine, user_ids, workflow_ids) -> None:
    with engine.begin() as conn:
        params = {"u": list(user_ids), "w": list(workflow_ids)}
        conn.execute(
            text(
                "DELETE FROM audit_events WHERE actor_id = ANY(:u) "
                "OR workflow_id = ANY(:w)"
            ),
            params,
        )
        conn.execute(text("DELETE FROM consents WHERE user_id = ANY(:u)"), params)
        conn.execute(text("DELETE FROM requests WHERE client_id = ANY(:u)"), params)
        conn.execute(text("DELETE FROM workflows WHERE id = ANY(:w)"), params)
        conn.execute(text("DELETE FROM conversations WHERE user_id = ANY(:u)"), params)
        conn.execute(
            text("DELETE FROM lawyer_profiles WHERE user_id = ANY(:u)"), params
        )
        conn.execute(text("DELETE FROM users WHERE id = ANY(:u)"), params)


def test_concurrent_double_send_creates_exactly_one_request(test_engine) -> None:
    with Session(test_engine, expire_on_commit=False) as setup:
        owner = _user(setup)
        wf = _intake(setup, owner)
        lawyers = [_lawyer(setup), _lawyer(setup)]
    user_ids = {owner.id, *(lw.user_id for lw in lawyers)}
    results: list[str] = []
    start = threading.Barrier(2)

    def worker(lawyer: LawyerProfile) -> None:
        with Session(test_engine) as session:
            start.wait()
            try:
                send_request(session, wf.id, lawyer.id, actor_id=owner.id)
                time.sleep(0.3)  # hold the intake lock while the other send waits
                session.commit()
                results.append("sent")
            except SendConflictError:
                session.rollback()
                results.append("conflict")

    try:
        threads = [threading.Thread(target=worker, args=(lw,)) for lw in lawyers]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert sorted(results) == ["conflict", "sent"]
        with Session(test_engine) as check:
            rows = check.scalars(select(Request).where(Request.intake_id == wf.id))
            assert len(rows.all()) == 1
    finally:
        _cleanup(test_engine, user_ids, {wf.id})


# --- Migration --------------------------------------------------------------------


def test_migration_down_up_down_up(test_engine, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    config = Config("alembic.ini")

    def shape() -> tuple[set[str], set[str], set[str]]:
        insp = inspect(test_engine)
        columns = {c["name"] for c in insp.get_columns("requests")}
        indexes = {i["name"] for i in insp.get_indexes("requests")}
        fks = {f["name"] for f in insp.get_foreign_keys("requests")}
        return columns, indexes, fks

    with test_engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == (
            MIGRATION
        )
    try:
        for _ in range(2):
            command.downgrade(config, PREVIOUS)
            columns, indexes, fks = shape()
            assert {"intake_id", "responded_at"}.isdisjoint(columns)
            assert "decline_reason" in columns  # pre-existing, kept
            assert {"ix_requests_intake_id", "uq_requests_active_intake"}.isdisjoint(
                indexes
            )
            assert "fk_requests_intake_id" not in fks

            command.upgrade(config, "head")
            columns, indexes, fks = shape()
            assert {"intake_id", "responded_at"} <= columns
            assert {"ix_requests_intake_id", "uq_requests_active_intake"} <= indexes
            assert "fk_requests_intake_id" in fks
    finally:
        command.upgrade(config, "head")
