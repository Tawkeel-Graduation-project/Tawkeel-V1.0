"""Unit tests for the lawyer accepting or declining a request (SCRUM-347)."""

import json
import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from services.audit.actions import AuditAction
from services.requests.service import accept_request, decline_request
from services.requests.states import InvalidRequestTransitionError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import AuditEvent, Request, User
from app.db.session import get_db
from app.lawyer.schemas import DeclineRequestBody
from app.main import app


def _request(status: str = "sent") -> Request:
    return Request(
        id=uuid.uuid4(), client_id=uuid.uuid4(), lawyer_id=uuid.uuid4(), status=status
    )


def _event(db: Mock, action: str | None = None) -> AuditEvent:
    (event,) = [
        c.args[0]
        for c in db.add.call_args_list
        if isinstance(c.args[0], AuditEvent)
        and (action is None or c.args[0].action == action)
    ]
    return event


def test_accept_sets_status_responded_at_and_audits() -> None:
    db, req, actor = Mock(spec=Session), _request(), uuid.uuid4()

    accept_request(db, req, actor_id=actor)

    assert req.status == "accepted"
    assert req.responded_at is not None
    assert req.responded_at.utcoffset() is not None  # timezone-aware
    assert req.decline_reason is None
    event = _event(db, AuditAction.REQUEST_ACCEPTED)
    assert event.actor_id == actor
    assert event.after == {"status": "accepted"}
    db.commit.assert_not_called()


def test_decline_keeps_the_reason_out_of_the_audit_log() -> None:
    db, req = Mock(spec=Session), _request()

    decline_request(db, req, "  لا أعمل في هذا المجال  ", actor_id=uuid.uuid4())

    assert req.status == "declined"
    assert req.decline_reason == "لا أعمل في هذا المجال"
    assert req.responded_at is not None
    event = _event(db)
    assert event.action == AuditAction.REQUEST_DECLINED
    assert event.before == {"status": "sent"}
    assert event.after == {"status": "declined", "reason_given": True}
    assert "المجال" not in json.dumps([event.before, event.after], ensure_ascii=False)
    db.commit.assert_not_called()


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_decline_without_a_reason(reason) -> None:
    db, req = Mock(spec=Session), _request()
    decline_request(db, req, reason, actor_id=uuid.uuid4())
    assert req.decline_reason is None
    assert _event(db).after == {"status": "declined", "reason_given": False}


@pytest.mark.parametrize("status", ["accepted", "declined", "expired", "cancelled"])
def test_only_a_sent_request_can_be_answered(status: str) -> None:
    for respond in (
        lambda db, r: accept_request(db, r, actor_id=uuid.uuid4()),
        lambda db, r: decline_request(db, r, "x", actor_id=uuid.uuid4()),
    ):
        db, req = Mock(spec=Session), _request(status)
        with pytest.raises(InvalidRequestTransitionError):
            respond(db, req)
        assert req.status == status
        assert req.responded_at is None
        assert req.decline_reason is None
        db.add.assert_not_called()


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("", None),
        ("  \n ", None),
        ("  مشغول  ", "مشغول"),
        ("x" * 500, "x" * 500),
        ("  " + "x" * 500 + "  ", "x" * 500),  # trimmed before the length check
    ],
)
def test_decline_body_normalizes_the_reason(raw, expected) -> None:
    assert DeclineRequestBody(reason=raw).reason == expected
    assert DeclineRequestBody().reason is None


@pytest.mark.parametrize("raw", ["x" * 501, "a\x00b"])
def test_decline_body_rejects_bad_reasons(raw) -> None:
    with pytest.raises(ValidationError):
        DeclineRequestBody(reason=raw)


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_clients_cannot_answer_requests(action: str) -> None:
    client_user = User(
        id=uuid.uuid4(), email="c@example.com", role="client", password_hash="h"
    )
    app.dependency_overrides[get_current_user] = lambda: client_user
    app.dependency_overrides[get_db] = lambda: Mock(spec=Session)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(f"/lawyer/requests/{uuid.uuid4()}/{action}")
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
