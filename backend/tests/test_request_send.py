"""Unit tests for sending an approved intake to a lawyer (SCRUM-344)."""

import uuid
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from services.audit.actions import AuditAction
from services.requests.send import (
    LawyerUnavailableError,
    SendConflictError,
    list_verified_lawyers,
    send_request,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Consent, LawyerProfile, Request, Workflow

SNAPSHOT = {
    "fields": {
        "facts": {"status": "provided", "value": "فصلني صاحب العمل"},
        "niche": {"status": "provided", "value": "labor"},
    },
    "approved_at": "2026-11-28T10:00:00+02:00",
    "approved_by": str(uuid.uuid4()),
    "consent_id": str(uuid.uuid4()),
}
ACTOR = uuid.uuid4()


def _run(phase: str = "APPROVED", summary: dict | None = SNAPSHOT) -> Workflow:
    state = {"phase": phase}
    if summary is not None:
        state["summary"] = summary
    return Workflow(
        id=uuid.uuid4(),
        kind="intake",
        status="completed",
        conversation_id=uuid.uuid4(),
        state=state,
    )


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


def _lawyer() -> LawyerProfile:
    return LawyerProfile(id=uuid.uuid4(), user_id=uuid.uuid4(), verified=True)


def _send(db: Mock, run: Workflow, lawyer, history=()):
    db.scalar.return_value = lawyer
    lawyer_id = lawyer.id if lawyer else uuid.uuid4()
    with (
        patch("services.requests.send.get_run", return_value=run),
        patch("services.requests.send.intake_requests", return_value=list(history)),
        patch("services.requests.send.log_event") as log,
    ):
        return send_request(db, run.id, lawyer_id, actor_id=ACTOR), log


def _old(lawyer_id: uuid.UUID, status: str) -> Request:
    return Request(id=uuid.uuid4(), lawyer_id=lawyer_id, status=status)


def test_send_copies_the_snapshot_with_consent_and_audit(db: Mock) -> None:
    run, lawyer = _run(), _lawyer()

    req, log = _send(db, run, lawyer)

    assert req.status == "sent"
    assert req.client_id == ACTOR
    assert req.lawyer_id == lawyer.id
    assert req.intake_id == run.id
    assert req.conversation_id == run.conversation_id
    assert req.summary == SNAPSHOT
    assert req.niche == "labor"
    # approved_at, stored as naive UTC
    assert req.client_confirmed_at == datetime(2026, 11, 28, 8, 0)
    (consent,) = [o for o in db.added if isinstance(o, Consent)]
    assert consent.request_id == req.id
    assert consent.user_id == ACTOR
    assert consent.type == "share_summary"
    log.assert_called_once()
    assert log.call_args.kwargs["action"] == AuditAction.REQUEST_CREATED
    assert log.call_args.kwargs["request_id"] == req.id
    assert log.call_args.kwargs["after"]["consent_id"] == str(consent.id)
    db.commit.assert_not_called()


def test_send_without_a_provided_niche_leaves_it_empty(db: Mock) -> None:
    snapshot = {
        **SNAPSHOT,
        "fields": {"niche": {"status": "not_provided", "value": None}},
    }
    req, _ = _send(db, _run(summary=snapshot), _lawyer())
    assert req.niche is None


@pytest.mark.parametrize(
    "run",
    [_run(phase="SUMMARY_REVIEW", summary=None), _run(summary=None)],
    ids=["in-review", "no-snapshot"],
)
def test_send_before_approval_conflicts(db: Mock, run: Workflow) -> None:
    with pytest.raises(SendConflictError):
        _send(db, run, _lawyer())
    db.add.assert_not_called()


def test_send_to_unknown_or_unverified_lawyer_is_unavailable(db: Mock) -> None:
    # The lookup filters on verified, so both cases return no row.
    with pytest.raises(LawyerUnavailableError):
        _send(db, _run(), None)
    db.add.assert_not_called()


@pytest.mark.parametrize("status", ["sent", "accepted"])
def test_send_while_latest_is_active_conflicts(db: Mock, status: str) -> None:
    lawyer = _lawyer()
    history = [_old(uuid.uuid4(), "declined"), _old(uuid.uuid4(), status)]
    with pytest.raises(SendConflictError, match="active"):
        _send(db, _run(), lawyer, history)
    db.add.assert_not_called()


@pytest.mark.parametrize("status", ["declined", "expired"])
def test_resend_after_decline_or_expiry_creates_a_new_request(
    db: Mock, status: str
) -> None:
    lawyer = _lawyer()
    req, _ = _send(db, _run(), lawyer, [_old(uuid.uuid4(), status)])
    assert req.status == "sent"
    assert req.lawyer_id == lawyer.id


def test_resend_to_a_lawyer_who_declined_conflicts(db: Mock) -> None:
    lawyer = _lawyer()
    history = [_old(lawyer.id, "declined"), _old(uuid.uuid4(), "expired")]
    with pytest.raises(SendConflictError, match="declined"):
        _send(db, _run(), lawyer, history)


def test_resend_to_a_lawyer_whose_request_expired_is_allowed(db: Mock) -> None:
    lawyer = _lawyer()
    req, _ = _send(db, _run(), lawyer, [_old(lawyer.id, "expired")])
    assert req.status == "sent"


def _integrity(message: str) -> IntegrityError:
    return IntegrityError("INSERT", {}, Exception(message))


def test_active_index_violation_is_a_conflict(db: Mock) -> None:
    db.flush.side_effect = _integrity('duplicate key "uq_requests_active_intake"')
    with pytest.raises(SendConflictError):
        _send(db, _run(), _lawyer())


def test_other_integrity_errors_are_not_hidden(db: Mock) -> None:
    db.flush.side_effect = _integrity('violates foreign key "requests_client_id"')
    with pytest.raises(IntegrityError):
        _send(db, _run(), _lawyer())


def test_lawyers_list_only_selects_verified_lawyers() -> None:
    db = Mock(spec=Session)
    db.execute.return_value.all.return_value = []
    assert list_verified_lawyers(db) == []
    stmt = db.execute.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "lawyer_profiles.verified IS true" in sql
