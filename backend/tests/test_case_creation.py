"""Unit tests for opening a case on acceptance and UTC timestamps (SCRUM-359)."""

import json
import uuid
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from services.audit.actions import AuditAction
from services.requests.service import (
    CaseExistsError,
    accept_request,
    decline_request,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.schemas import AuditEventResponse
from app.auth.schemas import UserResponse
from app.client.schemas import ClientCaseResponse, ClientConversationResponse
from app.db import session as db_session
from app.db.models import AuditEvent, Case, Conversation, Request, User
from app.lawyer.schemas import LawyerCaseResponse, LawyerConversationResponse

SNAPSHOT = {
    "fields": {"facts": {"status": "provided", "value": "نص الوقائع المعتمد"}},
    "approved_at": "2026-11-28T08:00:00+00:00",
    "approved_by": str(uuid.uuid4()),
    "consent_id": str(uuid.uuid4()),
}
NAIVE = datetime(2026, 11, 28, 8, 30, 0, 250000)
Z = "2026-11-28T08:30:00.250000Z"


@pytest.fixture
def db() -> Mock:
    db = Mock(spec=Session)
    added: list = []
    db.add.side_effect = added.append

    def flush():  # give new rows their ids, as a real flush would
        for obj in added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    db.flush.side_effect = flush
    db.added = added
    return db


def _request() -> Request:
    return Request(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        lawyer_id=uuid.uuid4(),
        status="sent",
        summary=SNAPSHOT,
    )


def _added(db: Mock, kind: type) -> list:
    return [o for o in db.added if isinstance(o, kind)]


def test_accept_opens_a_case_from_the_approved_snapshot(db: Mock) -> None:
    req, actor = _request(), uuid.uuid4()

    case = accept_request(db, req, actor_id=actor)

    assert _added(db, Case) == [case]
    assert case.request_id == req.id
    assert case.lawyer_id == req.lawyer_id
    assert case.status == "open"
    assert case.notes is None
    assert case.summary == SNAPSHOT
    assert case.summary is not req.summary  # a copy, not a shared dict
    events = {e.action: e for e in _added(db, AuditEvent)}
    assert set(events) == {AuditAction.REQUEST_ACCEPTED, AuditAction.CASE_CREATED}
    created = events[AuditAction.CASE_CREATED]
    assert created.case_id == case.id
    assert created.request_id == req.id
    assert created.actor_id == actor
    assert created.after == {"status": "open"}
    logged = json.dumps([created.before, created.after], ensure_ascii=False)
    assert "الوقائع" not in logged
    db.commit.assert_not_called()


def test_decline_opens_no_case(db: Mock) -> None:
    decline_request(db, _request(), "مشغول", actor_id=uuid.uuid4())
    assert _added(db, Case) == []


def _fail_case_insert(db: Mock, message: str) -> None:
    """The flush that inserts the case fails; the audit flush before it works."""

    def flush():
        if _added(db, Case):
            raise IntegrityError("INSERT", {}, Exception(message))

    db.flush.side_effect = flush


def test_duplicate_case_is_a_conflict(db: Mock) -> None:
    _fail_case_insert(db, 'duplicate key "cases_request_id_key"')
    with pytest.raises(CaseExistsError):
        accept_request(db, _request(), actor_id=uuid.uuid4())


def test_other_case_insert_errors_are_not_hidden(db: Mock) -> None:
    _fail_case_insert(db, 'violates foreign key "cases_lawyer_id_fkey"')
    with pytest.raises(IntegrityError):
        accept_request(db, _request(), actor_id=uuid.uuid4())


def test_app_engine_pins_the_session_time_zone_to_utc() -> None:
    with patch.object(db_session, "create_engine") as create:
        db_session.create_app_engine("postgresql+psycopg://u:p@h/db")
    assert create.call_args.kwargs["connect_args"] == {"options": "-c timezone=UTC"}


@pytest.mark.parametrize(
    "schema,row",
    [
        (
            ClientCaseResponse,
            Case(id=uuid.uuid4(), request_id=uuid.uuid4(), status="open"),
        ),
        (
            LawyerCaseResponse,
            Case(
                id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                lawyer_id=uuid.uuid4(),
                status="open",
            ),
        ),
        (ClientConversationResponse, Conversation(id=uuid.uuid4(), type="qa")),
        (
            LawyerConversationResponse,
            Conversation(id=uuid.uuid4(), user_id=uuid.uuid4(), type="qa"),
        ),
        (
            AuditEventResponse,
            AuditEvent(id=uuid.uuid4(), actor_id=uuid.uuid4(), action="case.created"),
        ),
        (
            UserResponse,
            User(id=uuid.uuid4(), email="a@example.com", role="client"),
        ),
    ],
)
def test_remaining_schemas_return_z_timestamps(schema, row) -> None:
    row.created_at = NAIVE
    if hasattr(row, "updated_at"):
        row.updated_at = NAIVE
    data = schema.model_validate(row).model_dump(mode="json")
    assert data["created_at"] == Z
    if "updated_at" in data:
        assert data["updated_at"] == Z
