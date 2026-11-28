"""Database tests for opening a case when a lawyer accepts (SCRUM-359).

Runs the real endpoints against PostgreSQL in a rolled-back transaction, with
authentication overridden to pick the acting user. The concurrency and time
zone tests commit or connect for real and clean up after themselves.
"""

import json
import os
import re
import threading
import time
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.intake.summary import get_approved_summary
from services.requests.service import accept_request, decline_request
from services.requests.states import InvalidRequestTransitionError
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import AuditEvent, Case, Conversation, Request, User, Workflow
from app.db.session import create_app_engine, get_db
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
from test_request_send_integration import (  # noqa: E402
    VALUES,
    _cleanup,
    _intake,
    _lawyer,
    _user,
)

ISO_Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$")
INTAKE_ACTIONS = re.compile(r"^(workflow|ai|summary|approval)\.")


@pytest.fixture(scope="module")
def test_engine():
    url = os.environ["TEST_DATABASE_URL"].replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url, pool_pre_ping=True)
    if "cases" not in inspect(engine).get_table_names():
        pytest.fail("Table 'cases' missing; run alembic upgrade head", pytrace=False)
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


def _sent(api, db):
    """An approved intake sent to a lawyer: (owner, intake, lawyer user, request id)."""
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner)
    profile = _lawyer(db)
    act_as(owner)
    resp = client.post(
        f"/client/intakes/{wf.id}/send", json={"lawyer_id": str(profile.id)}
    )
    assert resp.status_code == 201
    return owner, wf, db.get(User, profile.user_id), resp.json()["id"]


def _cases(db: Session, request_id: str) -> list[Case]:
    db.expire_all()
    return list(
        db.scalars(select(Case).where(Case.request_id == uuid.UUID(request_id)))
    )


def _actions(db: Session, request_id: str) -> list[str]:
    return list(
        db.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.request_id == uuid.UUID(request_id))
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


# --- Acceptance opens the case ----------------------------------------------------


def test_accept_creates_one_case_from_the_approved_snapshot(api, db) -> None:
    client, act_as = api
    owner, wf, lawyer, request_id = _sent(api, db)
    act_as(lawyer)

    resp = client.post(f"/lawyer/requests/{request_id}/accept")

    assert resp.status_code == 200
    data = resp.json()
    (case,) = _cases(db, request_id)
    assert data["case_id"] == str(case.id)
    req = db.get(Request, uuid.UUID(request_id))
    assert case.lawyer_id == req.lawyer_id
    assert case.status == "open"
    assert case.notes is None
    snapshot = get_approved_summary(db.get(Workflow, wf.id))
    assert case.summary == snapshot == req.summary == data["summary"]

    (event,) = db.scalars(select(AuditEvent).where(AuditEvent.case_id == case.id))
    assert event.action == "case.created"
    assert event.request_id == req.id
    assert event.actor_id == lawyer.id
    assert event.after == {"status": "open"}
    logged = json.dumps([event.before, event.after], ensure_ascii=False)
    for value in VALUES.values():
        if value:
            assert value not in logged

    # The lawyer's list and detail link to the case; so does the client's view.
    listed = client.get("/lawyer/requests").json()
    assert [item["case_id"] for item in listed] == [str(case.id)]
    detail = client.get(f"/lawyer/requests/{request_id}").json()
    assert detail == listed[0]
    assert detail["case_id"] == str(case.id)


def test_case_id_is_null_until_accepted(api, db) -> None:
    client, act_as = api
    _, _, lawyer, request_id = _sent(api, db)
    act_as(lawyer)
    assert client.get(f"/lawyer/requests/{request_id}").json()["case_id"] is None
    assert client.get("/lawyer/requests").json()[0]["case_id"] is None


def test_decline_creates_no_case(api, db) -> None:
    client, act_as = api
    _, _, lawyer, request_id = _sent(api, db)
    act_as(lawyer)

    resp = client.post(f"/lawyer/requests/{request_id}/decline")

    assert resp.status_code == 200
    assert resp.json()["case_id"] is None
    assert _cases(db, request_id) == []
    assert "case.created" not in _actions(db, request_id)


def test_case_creation_failure_rolls_back_the_acceptance(api, db) -> None:
    client, act_as = api
    _, _, lawyer, request_id = _sent(api, db)
    req = db.get(Request, uuid.UUID(request_id))
    # A stray case for this still-"sent" request makes the insert collide.
    stray = Case(request_id=req.id, lawyer_id=req.lawyer_id, status="open")
    db.add(stray)
    db.commit()
    act_as(lawyer)

    resp = client.post(f"/lawyer/requests/{request_id}/accept")

    assert resp.status_code == 409
    db.expire_all()
    req = db.get(Request, uuid.UUID(request_id))
    assert req.status == "sent"
    assert req.responded_at is None
    assert [c.id for c in _cases(db, request_id)] == [stray.id]
    assert _actions(db, request_id) == ["request.created"]


# --- Who can see the case ---------------------------------------------------------


def test_case_visibility(api, db) -> None:
    client, act_as = api
    owner, _, lawyer, request_id = _sent(api, db)
    act_as(lawyer)
    case_id = client.post(f"/lawyer/requests/{request_id}/accept").json()["case_id"]

    resp = client.get(f"/lawyer/cases/{case_id}")
    assert resp.status_code == 200
    assert resp.json()["request_id"] == request_id
    assert resp.json()["summary"] == db.get(Request, uuid.UUID(request_id)).summary
    assert [c["id"] for c in client.get("/lawyer/cases").json()] == [case_id]

    act_as(db.get(User, _lawyer(db).user_id))
    assert client.get(f"/lawyer/cases/{case_id}").status_code == 403
    assert client.get("/lawyer/cases").json() == []

    act_as(owner)
    resp = client.get(f"/client/cases/{case_id}")
    assert resp.status_code == 200
    assert resp.json()["request_id"] == request_id
    assert [c["id"] for c in client.get("/client/cases").json()] == [case_id]

    act_as(_user(db))
    assert client.get(f"/client/cases/{case_id}").status_code == 403


# --- Privacy: the case doesn't open the intake to the lawyer -----------------------


def test_lawyer_cannot_reach_the_intake_after_acceptance(api, db) -> None:
    client, act_as = api
    owner, wf, lawyer, request_id = _sent(api, db)
    act_as(lawyer)
    case_id = client.post(f"/lawyer/requests/{request_id}/accept").json()["case_id"]

    db.expire_all()
    req = db.get(Request, uuid.UUID(request_id))
    conversation = db.get(Conversation, wf.conversation_id)
    # Linked only through case -> request -> request.conversation_id.
    assert req.conversation_id == conversation.id
    assert conversation.case_id is None
    assert db.get(Workflow, wf.id).case_id is None

    listed = client.get("/lawyer/conversations")
    assert listed.status_code == 200
    assert str(conversation.id) not in {c["id"] for c in listed.json()}
    assert client.get(f"/lawyer/conversations/{conversation.id}").status_code == 403

    # The intake run has its own audit trail (started, turns, edits, approval).
    intake_events = db.scalars(
        select(AuditEvent.action).where(AuditEvent.workflow_id == wf.id)
    ).all()
    assert any(INTAKE_ACTIONS.match(a) for a in intake_events)
    for query in ("", f"?case_id={case_id}", f"?request_id={request_id}"):
        resp = client.get(f"/audit{query}")
        assert resp.status_code == 200
        actions = {e["action"] for e in resp.json()["events"]}
        assert actions <= {"request.created", "request.accepted", "case.created"}
        assert not any(INTAKE_ACTIONS.match(a) for a in actions)
    by_case = client.get(f"/audit?case_id={case_id}").json()["events"]
    assert [e["action"] for e in by_case] == ["case.created"]


# --- Concurrency (real commits) ------------------------------------------------------


def test_concurrent_accept_and_decline_open_at_most_one_case(test_engine) -> None:
    with Session(test_engine, expire_on_commit=False) as setup:
        owner = _user(setup)
        wf = _intake(setup, owner)
        profile = _lawyer(setup)
        req = Request(
            client_id=owner.id,
            lawyer_id=profile.id,
            intake_id=wf.id,
            conversation_id=wf.conversation_id,
            summary=get_approved_summary(wf),
            status="sent",
        )
        setup.add(req)
        setup.commit()
    results: dict[str, str] = {}
    start = threading.Barrier(2)
    actor = profile.user_id

    def worker(name: str, respond) -> None:
        with Session(test_engine) as session:
            row = session.get(Request, req.id)
            start.wait()
            try:
                respond(session, row)
                time.sleep(0.3)  # hold the row lock while the other one waits
                session.commit()
                results[name] = "won"
            except InvalidRequestTransitionError:
                session.rollback()
                results[name] = "conflict"

    actions = {
        "accepted": lambda s, r: accept_request(s, r, actor_id=actor),
        "declined": lambda s, r: decline_request(s, r, None, actor_id=actor),
    }
    try:
        threads = [
            threading.Thread(target=worker, args=(name, fn))
            for name, fn in actions.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert sorted(results.values()) == ["conflict", "won"]
        winner = next(name for name, r in results.items() if r == "won")
        with Session(test_engine) as check:
            assert check.get(Request, req.id).status == winner
            cases = check.scalars(select(Case).where(Case.request_id == req.id)).all()
            assert len(cases) == (1 if winner == "accepted" else 0)
    finally:
        with test_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM audit_events WHERE request_id = :r"), {"r": req.id}
            )
            conn.execute(text("DELETE FROM cases WHERE request_id = :r"), {"r": req.id})
        _cleanup(test_engine, {owner.id, profile.user_id}, {wf.id})


# --- Time zone and timestamp format ---------------------------------------------------


def test_app_engine_keeps_utc_when_the_database_default_is_cairo(test_engine) -> None:
    with test_engine.connect() as conn:
        name = conn.scalar(text("SELECT quote_ident(current_database())"))
    url = test_engine.url.render_as_string(hide_password=False)
    with test_engine.begin() as conn:
        conn.execute(text(f"ALTER DATABASE {name} SET timezone TO 'Africa/Cairo'"))
    plain, app_engine = create_engine(url), create_app_engine(url)
    try:
        utc_now = datetime.now(UTC).replace(tzinfo=None)
        with plain.connect() as conn:  # proves the database default is Cairo
            assert conn.scalar(text("SHOW timezone")) == "Africa/Cairo"
            local = conn.scalar(text("SELECT now()::timestamp"))
            assert abs((local - utc_now).total_seconds()) > 3600
        with app_engine.connect() as conn:
            assert conn.scalar(text("SHOW timezone")) == "UTC"
            # What now() writes into a naive column is UTC.
            stored = conn.scalar(text("SELECT now()::timestamp"))
            assert abs((stored - utc_now).total_seconds()) < 60
    finally:
        plain.dispose()
        app_engine.dispose()
        with test_engine.begin() as conn:
            conn.execute(text(f"ALTER DATABASE {name} RESET timezone"))


def _all_z(payload) -> int:
    found = 0
    if isinstance(payload, list):
        return sum(_all_z(item) for item in payload)
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "summary":  # the frozen snapshot is data, kept as approved
                continue
            if key.endswith("_at") and value is not None:
                assert ISO_Z.match(value), f"{key}={value!r}"
                found += 1
            else:
                found += _all_z(value)
    return found


def test_converted_schemas_return_z_timestamps(api, db) -> None:
    client, act_as = api
    owner, _, lawyer, request_id = _sent(api, db)
    act_as(lawyer)
    case_id = client.post(f"/lawyer/requests/{request_id}/accept").json()["case_id"]
    db.add(Conversation(user_id=lawyer.id, type="case_research"))
    db.commit()

    paths = {
        lawyer: [
            f"/lawyer/cases/{case_id}",
            "/lawyer/cases",
            "/lawyer/conversations",
            "/audit",
            "/auth/me",
        ],
        owner: [
            f"/client/cases/{case_id}",
            "/client/cases",
            "/client/conversations",
            "/audit",
            "/auth/me",
        ],
    }
    for user, urls in paths.items():
        act_as(user)
        for url in urls:
            resp = client.get(url)
            assert resp.status_code == 200, f"{url}: {resp.text}"
            assert _all_z(resp.json()) > 0, url
