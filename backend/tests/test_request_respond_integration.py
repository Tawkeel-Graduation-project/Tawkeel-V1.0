"""Database tests for the lawyer accepting or declining a request (SCRUM-347).

Runs the real endpoints against PostgreSQL in a rolled-back transaction, with
authentication overridden to pick the acting user. The concurrency test
commits for real and cleans up after itself.
"""

import json
import os
import threading
import time
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from services.requests.service import accept_request, decline_request
from services.requests.states import InvalidRequestTransitionError
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import AuditEvent, Case, Request, User
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
from test_request_send_integration import (  # noqa: E402
    _cleanup,
    _intake,
    _lawyer,
    _user,
)

REASON = "لا أعمل في قضايا العمل حاليًا"
DECISION_KEYS = {
    "id",
    "client_id",
    "niche",
    "summary",
    "status",
    "decline_reason",
    "created_at",
    "intake_id",
    "responded_at",
    "case_id",
}


@pytest.fixture(scope="module")
def test_engine():
    url = os.environ["TEST_DATABASE_URL"].replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url, pool_pre_ping=True)
    if "requests" not in inspect(engine).get_table_names():
        pytest.fail("Table 'requests' missing; run alembic upgrade head", pytrace=False)
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


def _accept(client, request_id):
    return client.post(f"/lawyer/requests/{request_id}/accept")


def _decline(client, request_id, body=None):
    url = f"/lawyer/requests/{request_id}/decline"
    return client.post(url) if body is None else client.post(url, json=body)


def _events(db: Session, request_id: str) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.request_id == uuid.UUID(request_id))
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def _stored(db: Session, request_id: str) -> Request:
    db.expire_all()
    return db.get(Request, uuid.UUID(request_id))


def test_accept_happy_path(api, db) -> None:
    client, act_as = api
    owner, wf, lawyer, request_id = _sent(api, db)
    act_as(lawyer)

    resp = _accept(client, request_id)

    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == DECISION_KEYS
    assert data["id"] == request_id
    assert data["status"] == "accepted"
    assert data["intake_id"] == str(wf.id)
    assert data["client_id"] == str(owner.id)
    assert data["responded_at"] is not None
    assert data["decline_reason"] is None
    assert data["case_id"] is not None  # SCRUM-359 opens the case

    req = _stored(db, request_id)
    assert req.status == "accepted"
    assert req.responded_at.utcoffset() is not None
    (event,) = [e for e in _events(db, request_id) if e.action == "request.accepted"]
    assert event.actor_id == lawyer.id
    assert event.after == {"status": "accepted"}
    (case,) = db.scalars(select(Case).where(Case.request_id == req.id)).all()
    assert str(case.id) == data["case_id"]


def test_decline_with_reason_keeps_it_out_of_the_audit_log(api, db) -> None:
    client, act_as = api
    _, _, lawyer, request_id = _sent(api, db)
    act_as(lawyer)

    resp = _decline(client, request_id, {"reason": f"  {REASON}  "})

    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == DECISION_KEYS
    assert data["status"] == "declined"
    assert data["decline_reason"] == REASON
    assert data["responded_at"] is not None
    assert data["case_id"] is None
    assert _stored(db, request_id).decline_reason == REASON
    (event,) = [e for e in _events(db, request_id) if e.action == "request.declined"]
    assert event.actor_id == lawyer.id
    assert event.after == {"status": "declined", "reason_given": True}
    for e in _events(db, request_id):
        assert REASON not in json.dumps([e.before, e.after], ensure_ascii=False)


@pytest.mark.parametrize(
    "body",
    [None, {}, {"reason": None}, {"reason": ""}, {"reason": "   "}],
    ids=["no-body", "empty-body", "null", "empty", "blank"],
)
def test_decline_without_a_reason(api, db, body) -> None:
    client, act_as = api
    _, _, lawyer, request_id = _sent(api, db)
    act_as(lawyer)

    resp = _decline(client, request_id, body)

    assert resp.status_code == 200
    assert resp.json()["decline_reason"] is None
    (event,) = [e for e in _events(db, request_id) if e.action == "request.declined"]
    assert event.after == {"status": "declined", "reason_given": False}


def test_decline_reason_too_long_is_422_and_changes_nothing(api, db) -> None:
    client, act_as = api
    _, _, lawyer, request_id = _sent(api, db)
    act_as(lawyer)

    assert _decline(client, request_id, {"reason": "x" * 501}).status_code == 422
    req = _stored(db, request_id)
    assert req.status == "sent"
    assert req.responded_at is None
    assert [e.action for e in _events(db, request_id)] == ["request.created"]


@pytest.mark.parametrize("action", ["accept", "decline"])
@pytest.mark.parametrize("status", ["accepted", "declined", "expired", "cancelled"])
def test_only_a_sent_request_can_be_answered(api, db, status, action) -> None:
    client, act_as = api
    _, _, lawyer, request_id = _sent(api, db)
    _stored(db, request_id).status = status
    db.commit()
    act_as(lawyer)

    resp = client.post(f"/lawyer/requests/{request_id}/{action}")

    assert resp.status_code == 409
    assert _stored(db, request_id).status == status
    assert [e.action for e in _events(db, request_id)] == ["request.created"]


def test_ownership_and_roles(api, db) -> None:
    client, act_as = api
    owner, _, _, request_id = _sent(api, db)

    act_as(db.get(User, _lawyer(db).user_id))  # another lawyer
    assert _accept(client, request_id).status_code == 403
    assert _decline(client, request_id).status_code == 403
    act_as(owner)  # the client who sent it: lawyer-only router
    assert _accept(client, request_id).status_code == 403
    assert _decline(client, request_id).status_code == 403
    act_as(db.get(User, _lawyer(db).user_id))
    assert _accept(client, str(uuid.uuid4())).status_code == 404
    assert _decline(client, str(uuid.uuid4())).status_code == 404

    assert _stored(db, request_id).status == "sent"


def test_client_sees_the_lawyers_answer(api, db) -> None:
    client, act_as = api
    owner, wf, lawyer, request_id = _sent(api, db)
    act_as(lawyer)
    answer = _decline(client, request_id, {"reason": REASON}).json()

    act_as(owner)
    intake = client.get(f"/client/intakes/{wf.id}").json()
    assert intake["request"] == {
        "id": request_id,
        "lawyer_id": intake["request"]["lawyer_id"],
        "status": "declined",
        "created_at": answer["created_at"],
        "responded_at": answer["responded_at"],
        "decline_reason": REASON,
    }
    (item,) = client.get("/client/requests").json()
    assert item["status"] == "declined"
    assert item["responded_at"] == answer["responded_at"]
    assert item["decline_reason"] == REASON
    assert client.get(f"/client/requests/{request_id}").json() == item


def test_send_decline_resend_accept_end_to_end(api, db) -> None:
    client, act_as = api
    owner, wf, first_lawyer, first_id = _sent(api, db)
    second = _lawyer(db)

    act_as(first_lawyer)
    assert _decline(client, first_id, {"reason": REASON}).status_code == 200
    # One test transaction means one now(); make the first request older.
    _stored(db, first_id).created_at -= timedelta(minutes=5)
    db.commit()

    act_as(owner)
    resp = client.post(
        f"/client/intakes/{wf.id}/send", json={"lawyer_id": str(second.id)}
    )
    assert resp.status_code == 201
    second_id = resp.json()["id"]
    # The lawyer who declined can't get it again.
    again = client.post(
        f"/client/intakes/{wf.id}/send",
        json={"lawyer_id": str(_stored(db, first_id).lawyer_id)},
    )
    assert again.status_code == 409

    act_as(db.get(User, second.user_id))
    assert _accept(client, second_id).json()["status"] == "accepted"

    act_as(owner)
    intake = client.get(f"/client/intakes/{wf.id}").json()
    assert intake["request"]["id"] == second_id
    assert intake["request"]["status"] == "accepted"
    assert intake["request"]["responded_at"] is not None
    (previous,) = intake["previous_requests"]
    assert previous["id"] == first_id
    assert previous["status"] == "declined"
    assert previous["decline_reason"] == REASON
    statuses = {r["id"]: r["status"] for r in client.get("/client/requests").json()}
    assert statuses == {first_id: "declined", second_id: "accepted"}


def test_concurrent_accept_and_decline_exactly_one_wins(test_engine) -> None:
    with Session(test_engine, expire_on_commit=False) as setup:
        owner = _user(setup)
        wf = _intake(setup, owner)
        profile = _lawyer(setup)
        req = Request(
            client_id=owner.id,
            lawyer_id=profile.id,
            intake_id=wf.id,
            conversation_id=wf.conversation_id,
            status="sent",
        )
        setup.add(req)
        setup.commit()
    results: dict[str, str] = {}
    start = threading.Barrier(2)

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
        "accepted": lambda s, r: accept_request(s, r, actor_id=profile.user_id),
        "declined": lambda s, r: decline_request(
            s, r, REASON, actor_id=profile.user_id
        ),
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
            stored = check.get(Request, req.id)
            assert stored.status == winner
            assert stored.responded_at is not None
            actions_logged = check.scalars(
                select(AuditEvent.action).where(AuditEvent.request_id == req.id)
            ).all()
            cases = check.scalars(select(Case).where(Case.request_id == req.id)).all()
            # Accepting also opens the case in the same transaction (SCRUM-359).
            if winner == "accepted":
                assert sorted(actions_logged) == ["case.created", "request.accepted"]
                assert len(cases) == 1
            else:
                assert actions_logged == ["request.declined"]
                assert cases == []
    finally:
        _cleanup(test_engine, {owner.id, profile.user_id}, {wf.id})
