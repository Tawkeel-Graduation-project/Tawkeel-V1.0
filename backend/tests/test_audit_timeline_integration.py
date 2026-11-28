"""Database tests for the audit timeline and the GET /audit leak check (SCRUM-419).

Runs the real endpoints against PostgreSQL in a rolled-back transaction, with
authentication overridden to pick the acting user.
"""

import json
import os
import re
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import AuditEvent, Case, User
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

# Setup helpers shared with the SCRUM-344 send tests (same tests/ directory).
from test_request_send_integration import _intake, _lawyer, _user  # noqa: E402

NOTES = "ملاحظات المحامي السرية عن الموكل"
LIFECYCLE = [
    "request.created",
    "request.accepted",
    "case.created",
    "case.notes_updated",
]
ITEM_KEYS = {"id", "action", "actor", "created_at"}
ACTOR_KEYS = {"id", "role", "name"}
ISO_Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$")


@pytest.fixture(scope="module")
def test_engine():
    url = os.environ["TEST_DATABASE_URL"].replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url, pool_pre_ping=True)
    if "audit_events" not in inspect(engine).get_table_names():
        pytest.fail("Table 'audit_events' missing; run alembic upgrade head")
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


def _flow(api, db):
    """Intake -> declined by one lawyer -> accepted by another -> notes written.

    Returns (owner, wf, declined lawyer user, lawyer user, request id, case id).
    """
    client, act_as = api
    owner = _user(db, name="موكل تجريبي")
    wf = _intake(db, owner)
    first, second = _lawyer(db, name="أ. الأول"), _lawyer(db, name="أ. الثاني")
    first_user, lawyer = db.get(User, first.user_id), db.get(User, second.user_id)

    act_as(owner)
    declined_id = client.post(
        f"/client/intakes/{wf.id}/send", json={"lawyer_id": str(first.id)}
    ).json()["id"]
    act_as(first_user)
    assert client.post(f"/lawyer/requests/{declined_id}/decline").status_code == 200
    act_as(owner)
    request_id = client.post(
        f"/client/intakes/{wf.id}/send", json={"lawyer_id": str(second.id)}
    ).json()["id"]
    act_as(lawyer)
    case_id = client.post(f"/lawyer/requests/{request_id}/accept").json()["case_id"]
    notes = client.patch(f"/lawyer/cases/{case_id}/notes", json={"notes": NOTES})
    assert notes.status_code == 200

    # One test transaction means one now(); spread the events out in order.
    events = db.scalars(
        select(AuditEvent).where(
            or_(
                AuditEvent.request_id == uuid.UUID(request_id),
                AuditEvent.case_id == uuid.UUID(case_id),
            )
        )
    ).all()
    base = datetime(2026, 11, 28, 8, 0)
    for event in events:
        event.created_at = base + timedelta(seconds=LIFECYCLE.index(event.action))
    db.commit()
    return owner, wf, first_user, lawyer, request_id, case_id


def _timeline(client, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    resp = client.get(f"/audit/timeline?{query}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_timeline_by_request_and_by_case_is_the_same_oldest_first(api, db) -> None:
    client, act_as = api
    owner, wf, _, lawyer, request_id, case_id = _flow(api, db)
    # The intake itself has its own audit events; they must stay out.
    intake_events = db.scalars(
        select(AuditEvent.action).where(AuditEvent.workflow_id == wf.id)
    ).all()
    assert "approval.approved" in intake_events

    for user in (owner, lawyer):
        act_as(user)
        by_request = _timeline(client, request_id=request_id)
        by_case = _timeline(client, case_id=case_id)
        assert by_request == by_case
        assert [item["action"] for item in by_request] == LIFECYCLE
        times = [item["created_at"] for item in by_request]
        assert times == sorted(times)


def test_items_are_who_what_when_and_never_content(api, db) -> None:
    client, act_as = api
    owner, _, _, lawyer, request_id, case_id = _flow(api, db)

    for user in (owner, lawyer):
        act_as(user)
        for params in ({"request_id": request_id}, {"case_id": case_id}):
            resp = client.get(
                "/audit/timeline?" + "&".join(f"{k}={v}" for k, v in params.items())
            )
            items = resp.json()
            for item in items:
                assert set(item) == ITEM_KEYS
                assert set(item["actor"]) == ACTOR_KEYS
                assert ISO_Z.match(item["created_at"])
            text_out = json.dumps(items, ensure_ascii=False)
            assert NOTES not in text_out
            assert "@example.com" not in text_out

    act_as(owner)
    actors = {i["action"]: i["actor"] for i in _timeline(client, case_id=case_id)}
    assert actors["request.created"] == {
        "id": str(owner.id),
        "role": "client",
        "name": "موكل تجريبي",
    }
    for action in LIFECYCLE[1:]:
        assert actors[action] == {
            "id": str(lawyer.id),
            "role": "lawyer",
            "name": "أ. الثاني",
        }


def test_who_can_view_the_timeline(api, db) -> None:
    client, act_as = api
    owner, _, declined_lawyer, lawyer, request_id, case_id = _flow(api, db)
    admin = _user(db, role="admin")
    other_client, other_lawyer = _user(db), db.get(User, _lawyer(db).user_id)
    ids = {"request_id": request_id, "case_id": case_id}

    for user in (owner, lawyer, admin):
        act_as(user)
        for key, value in ids.items():
            assert len(_timeline(client, **{key: value})) == len(LIFECYCLE)
    # The lawyer who declined an earlier request of this intake isn't a party.
    for user in (other_client, other_lawyer, declined_lawyer):
        act_as(user)
        for key, value in ids.items():
            resp = client.get(f"/audit/timeline?{key}={value}")
            assert resp.status_code == 403, (user.role, key)

    act_as(admin)
    for key in ids:
        assert client.get(f"/audit/timeline?{key}={uuid.uuid4()}").status_code == 404
    both = f"/audit/timeline?request_id={request_id}&case_id={case_id}"
    assert client.get(both).status_code == 422
    assert client.get("/audit/timeline").status_code == 422


def test_request_without_a_case_and_other_requests_stay_out(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    profile = _lawyer(db)
    act_as(owner)
    request_id = client.post(
        f"/client/intakes/{wf.id}/send", json={"lawyer_id": str(profile.id)}
    ).json()["id"]

    items = _timeline(client, request_id=request_id)
    assert [i["action"] for i in items] == ["request.created"]
    case = select(Case).where(Case.request_id == uuid.UUID(request_id))
    assert db.scalar(case) is None


def test_limit_and_offset(api, db) -> None:
    client, act_as = api
    owner, _, _, _, request_id, _ = _flow(api, db)
    act_as(owner)
    full = _timeline(client, request_id=request_id)

    assert _timeline(client, request_id=request_id, limit=2) == full[:2]
    assert _timeline(client, request_id=request_id, limit=2, offset=2) == full[2:]
    assert _timeline(client, request_id=request_id, offset=10) == []
    assert _timeline(client, request_id=request_id, limit=500) == full
    for bad in ("limit=0", "limit=501", "offset=-1"):
        url = f"/audit/timeline?request_id={request_id}&{bad}"
        assert client.get(url).status_code == 422


def test_get_audit_never_shows_a_client_the_case_notes(api, db) -> None:
    """Leak check on the existing GET /audit (unchanged by SCRUM-419)."""
    client, act_as = api
    owner, _, _, lawyer, request_id, case_id = _flow(api, db)

    act_as(owner)
    for query in ("", f"?request_id={request_id}", f"?case_id={case_id}"):
        resp = client.get(f"/audit{query}")
        assert resp.status_code == 200
        actions = {e["action"] for e in resp.json()["events"]}
        assert "case.notes_updated" not in actions, query
        assert NOTES not in resp.text, query

    # The notes are the lawyer's own; GET /audit still shows them to that lawyer.
    act_as(lawyer)
    assert NOTES in client.get(f"/audit?case_id={case_id}").text
