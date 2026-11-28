"""Unit tests for the audit timeline API (SCRUM-419)."""

import json
import uuid
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from services.audit.timeline import SYSTEM_ACTOR_ID, request_timeline
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import AuditEvent, User
from app.db.session import get_db
from app.main import app

NOTES = "ملاحظات المحامي السرية"
ITEM_KEYS = {"id", "action", "actor", "created_at"}


@pytest.fixture
def api():
    admin = User(id=uuid.uuid4(), email="a@example.com", role="admin", full_name="م")
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_db] = lambda: Mock(spec=Session)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "query",
    ["", f"?request_id={uuid.uuid4()}&case_id={uuid.uuid4()}"],
)
def test_exactly_one_id_is_required(api, query: str) -> None:
    assert api.get(f"/audit/timeline{query}").status_code == 422


@pytest.mark.parametrize("bad", ["limit=0", "limit=501", "offset=-1", "case_id=x"])
def test_paging_bounds(api, bad: str) -> None:
    url = f"/audit/timeline?request_id={uuid.uuid4()}&{bad}"
    assert api.get(url).status_code == 422


def test_items_carry_who_what_when_only(api) -> None:
    lawyer = User(id=uuid.uuid4(), email="l@x.com", role="lawyer", full_name="أ. محامٍ")
    notes = AuditEvent(
        id=uuid.uuid4(),
        actor_id=lawyer.id,
        action="case.notes_updated",
        case_id=uuid.uuid4(),
        before={"notes": None},
        after={"notes": NOTES},
        created_at=datetime(2026, 11, 28, 8, 30, 0, 250000),
    )
    expired = AuditEvent(
        id=uuid.uuid4(),
        actor_id=SYSTEM_ACTOR_ID,
        action="request.expired",
        created_at=datetime(2026, 11, 28, 9, 0),
    )
    rows = [(notes, lawyer), (expired, None)]
    with patch("app.audit.router.request_timeline", return_value=rows) as timeline:
        resp = api.get(f"/audit/timeline?request_id={uuid.uuid4()}&limit=500")

    assert resp.status_code == 200
    assert timeline.call_args.kwargs == {"limit": 500, "offset": 0}
    first, second = resp.json()
    assert first == {
        "id": str(notes.id),
        "action": "case.notes_updated",
        "actor": {"id": str(lawyer.id), "role": "lawyer", "name": "أ. محامٍ"},
        "created_at": "2026-11-28T08:30:00.250000Z",
    }
    assert set(second) == ITEM_KEYS
    assert second["actor"] is None
    assert NOTES not in json.dumps(resp.json(), ensure_ascii=False)
    assert "l@x.com" not in resp.text


def test_system_and_missing_actors_are_null() -> None:
    db = Mock(spec=Session)
    person = User(id=uuid.uuid4(), role="client")
    system = User(id=SYSTEM_ACTOR_ID, role="admin")
    events = [AuditEvent(id=uuid.uuid4()) for _ in range(3)]
    db.execute.return_value.all.return_value = list(
        zip(events, [person, system, None], strict=True)
    )

    rows = request_timeline(db, uuid.uuid4())

    assert [actor for _, actor in rows] == [person, None, None]
    assert [event for event, _ in rows] == events
