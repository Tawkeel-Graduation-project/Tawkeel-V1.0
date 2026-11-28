"""Database tests for the lawyer inbox, its privacy rule and UTC timestamps (SCRUM-358).

Runs the real endpoints against PostgreSQL in a rolled-back transaction, with
authentication overridden to pick the acting user.
"""

import json
import os
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from services.intake.summary import (
    approve_summary,
    get_approved_summary,
    update_summary,
)
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import Request, User, Workflow
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
from test_request_send_integration import VALUES, _intake, _lawyer, _user  # noqa: E402

STATUSES = ["sent", "accepted", "declined", "expired", "cancelled"]
ISO_Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$")
TIMESTAMP_KEYS = {"created_at", "responded_at", "approved_at", "client_confirmed_at"}
CHAT_TEXT = "رسالة خاصة من المحادثة لا يراها المحامي"
TURN_TEXT = "سؤال الوكيل عن تفاصيل خاصة"
OLD_CITY = VALUES["city"]  # edited away before approval
LAWYER_KEYS = {
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
FORBIDDEN_KEYS = {
    "conversation_id",
    "context",
    "messages",
    "turns",
    "intake",
    "history",
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


def _inbox(db: Session, profile, owner: User) -> list[str]:
    """One request per status, newest first; returns their ids in that order."""
    base = datetime(2026, 11, 28, 8, 0)
    ids = []
    for minutes, status in enumerate(STATUSES):
        req = Request(
            client_id=owner.id,
            lawyer_id=profile.id,
            status=status,
            summary={"fields": {}},
            created_at=base - timedelta(minutes=minutes),
        )
        db.add(req)
        db.flush()
        ids.append(str(req.id))
    db.commit()
    return ids


def _lawyer_user(db: Session, profile) -> User:
    return db.get(User, profile.user_id)


def _ids(resp) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [item["id"] for item in resp.json()]


# --- GET /lawyer/requests ---------------------------------------------------------


def test_inbox_lists_only_my_requests_newest_first(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    mine, other = _lawyer(db), _lawyer(db)
    ids = _inbox(db, mine, owner)
    _inbox(db, other, owner)
    act_as(_lawyer_user(db, mine))

    assert _ids(client.get("/lawyer/requests")) == ids


@pytest.mark.parametrize("status", STATUSES)
def test_inbox_filters_by_status(api, db, status) -> None:
    client, act_as = api
    owner = _user(db)
    mine = _lawyer(db)
    ids = dict(zip(STATUSES, _inbox(db, mine, owner), strict=True))
    _inbox(db, _lawyer(db), owner)  # another lawyer's, same statuses
    act_as(_lawyer_user(db, mine))

    resp = client.get(f"/lawyer/requests?status={status}")

    assert _ids(resp) == [ids[status]]
    assert resp.json()[0]["status"] == status


def test_inbox_limit_and_offset(api, db) -> None:
    client, act_as = api
    mine = _lawyer(db)
    ids = _inbox(db, mine, _user(db))
    act_as(_lawyer_user(db, mine))

    assert _ids(client.get("/lawyer/requests?limit=2")) == ids[:2]
    assert _ids(client.get("/lawyer/requests?limit=2&offset=2")) == ids[2:4]
    assert _ids(client.get("/lawyer/requests?limit=2&offset=4")) == ids[4:]
    assert _ids(client.get("/lawyer/requests?offset=10")) == []
    assert _ids(client.get("/lawyer/requests?limit=100")) == ids
    for bad in ("limit=0", "limit=101", "offset=-1", "status=pending"):
        assert client.get(f"/lawyer/requests?{bad}").status_code == 422


def test_inbox_is_lawyer_only(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    act_as(owner)
    assert client.get("/lawyer/requests").status_code == 403
    assert client.get("/lawyer/requests?status=sent").status_code == 403


# --- GET /lawyer/requests/{id} ----------------------------------------------------


def _private_intake(db: Session, owner: User) -> Workflow:
    """An approved intake whose chat, turns and an edit must never reach a lawyer."""
    wf = _intake(db, owner, approve=False)
    state = json.loads(json.dumps(wf.state))
    state["context"]["messages"] = [
        {"role": "user", "content": CHAT_TEXT, "citations": []}
    ]
    state["intake"]["turns"] = [{"role": "agent", "content": TURN_TEXT, "field": None}]
    wf.state = state
    db.flush()
    update_summary(db, wf.id, {"city": "القاهرة"}, actor_id=owner.id)
    approve_summary(db, wf.id, {**VALUES, "city": "القاهرة"}, actor_id=owner.id)
    db.commit()
    return wf


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_detail_has_the_approved_snapshot_and_nothing_else(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _private_intake(db, owner)
    profile = _lawyer(db)
    act_as(owner)
    sent = client.post(
        f"/client/intakes/{wf.id}/send", json={"lawyer_id": str(profile.id)}
    )
    request_id = sent.json()["id"]
    act_as(_lawyer_user(db, profile))

    detail = client.get(f"/lawyer/requests/{request_id}")
    listed = client.get("/lawyer/requests")

    assert detail.status_code == 200
    data = detail.json()
    assert set(data) == LAWYER_KEYS
    db.expire_all()
    assert data["summary"] == get_approved_summary(db.get(Workflow, wf.id))
    assert set(data["summary"]) == {
        "fields",
        "approved_at",
        "approved_by",
        "consent_id",
    }
    assert data["summary"]["fields"]["city"]["value"] == "القاهرة"
    assert listed.json() == [data]
    for body in (detail.text, listed.text):
        payload = json.loads(body)
        assert FORBIDDEN_KEYS.isdisjoint(_keys(payload))
        text_out = json.dumps(payload, ensure_ascii=False)
        for secret in (CHAT_TEXT, TURN_TEXT, OLD_CITY, str(wf.conversation_id)):
            assert secret not in text_out


def test_detail_ownership(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    mine = _lawyer(db)
    (request_id, *_) = _inbox(db, mine, owner)

    act_as(_lawyer_user(db, _lawyer(db)))
    assert client.get(f"/lawyer/requests/{request_id}").status_code == 403
    act_as(owner)
    assert client.get(f"/lawyer/requests/{request_id}").status_code == 403
    act_as(_lawyer_user(db, mine))
    assert client.get(f"/lawyer/requests/{uuid.uuid4()}").status_code == 404
    assert client.get(f"/lawyer/requests/{request_id}").status_code == 200


# --- Timestamps (step 0) ----------------------------------------------------------


def _assert_z(payload, where: str) -> int:
    """Every timestamp field (outside the stored summary) is UTC with a "Z"."""
    found = 0
    if isinstance(payload, list):
        return sum(_assert_z(item, where) for item in payload)
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "summary":  # the frozen snapshot is data, kept as approved
                continue
            if key in TIMESTAMP_KEYS and value is not None:
                assert ISO_Z.match(value), f"{where}: {key}={value!r}"
                found += 1
            else:
                found += _assert_z(value, where)
    return found


def test_every_sprint5_endpoint_returns_utc_z_timestamps(api, db) -> None:
    client, act_as = api
    owner = _user(db)
    wf = _intake(db, owner, approve=False)
    first, second = _lawyer(db), _lawyer(db)
    act_as(owner)
    responses = {
        "PATCH summary": client.patch(
            f"/client/intakes/{wf.id}/summary", json={"fields": {"city": "طنطا"}}
        ),
        "approve": client.post(
            f"/client/intakes/{wf.id}/approve",
            json={"confirmed": True, "fields": VALUES},
        ),
    }
    sent = client.post(
        f"/client/intakes/{wf.id}/send", json={"lawyer_id": str(first.id)}
    )
    responses["send"] = sent
    first_id = sent.json()["id"]

    act_as(_lawyer_user(db, first))
    responses["decline"] = client.post(f"/lawyer/requests/{first_id}/decline")
    # One test transaction means one now(); make the first request older.
    db.get(Request, uuid.UUID(first_id)).created_at -= timedelta(minutes=5)
    db.commit()
    act_as(owner)
    second_id = client.post(
        f"/client/intakes/{wf.id}/send", json={"lawyer_id": str(second.id)}
    ).json()["id"]
    act_as(_lawyer_user(db, second))
    responses["accept"] = client.post(f"/lawyer/requests/{second_id}/accept")

    # Aware columns now come back with a Cairo offset; output must still be Z.
    db.execute(text("SET TIME ZONE 'Africa/Cairo'"))
    db.expire_all()
    responses["lawyer list"] = client.get("/lawyer/requests")
    responses["lawyer detail"] = client.get(f"/lawyer/requests/{second_id}")
    act_as(owner)
    responses["intake"] = client.get(f"/client/intakes/{wf.id}")
    responses["client list"] = client.get("/client/requests")
    responses["client detail"] = client.get(f"/client/requests/{first_id}")

    for where, resp in responses.items():
        assert resp.status_code in (200, 201), f"{where}: {resp.text}"
        assert _assert_z(resp.json(), where) > 0, where

    # Same instant, whatever the session time zone.
    stored = db.get(Request, uuid.UUID(second_id)).responded_at
    shown = responses["lawyer detail"].json()["responded_at"]
    assert datetime.fromisoformat(shown) == stored
    assert datetime.fromisoformat(shown).tzinfo == UTC
    intake = responses["intake"].json()
    assert intake["previous_requests"][0]["responded_at"].endswith("Z")
    assert intake["request"]["responded_at"].endswith("Z")
