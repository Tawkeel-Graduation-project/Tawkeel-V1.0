"""Unit tests for the request status model and transitions (SCRUM-346)."""

import itertools
import uuid
from unittest.mock import Mock

import pytest
from services.audit.actions import AuditAction
from services.requests.service import TRANSITION_ACTIONS, transition_request
from services.requests.states import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    InvalidRequestTransitionError,
    RequestStatus,
    assert_transition,
    can_transition,
    is_terminal,
)
from sqlalchemy.orm import Session

from app.client.schemas import ClientRequestResponse
from app.db.models import AuditEvent, Request
from app.lawyer.schemas import LawyerRequestResponse

S = RequestStatus
TERMINALS = [S.ACCEPTED, S.DECLINED, S.EXPIRED, S.CANCELLED]
ALLOWED = [(S.SENT, t) for t in TERMINALS]
ILLEGAL = [
    pair for pair in itertools.product(S, S) if pair not in ALLOWED
]  # includes every self-transition and every move out of a terminal state


def test_canonical_values() -> None:
    assert [s.value for s in S] == [
        "sent",
        "accepted",
        "declined",
        "expired",
        "cancelled",
    ]
    assert set(ALLOWED_TRANSITIONS) == set(S)


@pytest.mark.parametrize(("current", "target"), ALLOWED)
def test_allowed_transitions(current: S, target: S) -> None:
    assert can_transition(current, target)
    assert_transition(current, target)  # does not raise


@pytest.mark.parametrize(("current", "target"), ILLEGAL)
def test_illegal_transitions_raise(current: S, target: S) -> None:
    assert not can_transition(current, target)
    with pytest.raises(InvalidRequestTransitionError) as exc:
        assert_transition(current, target)
    assert exc.value.current == current
    assert exc.value.target == target


@pytest.mark.parametrize("status", TERMINALS)
def test_terminal_states_have_no_exits(status: S) -> None:
    assert is_terminal(status)
    assert ALLOWED_TRANSITIONS[status] == frozenset()


def test_terminal_set_and_sent_is_not_terminal() -> None:
    assert TERMINAL_STATUSES == frozenset(TERMINALS)
    assert not is_terminal(S.SENT)


@pytest.mark.parametrize(
    ("current", "target"),
    [("pending", "accepted"), ("sent", "pending"), ("sent", "bogus"), ("", "")],
)
def test_unknown_values_are_rejected(current: str, target: str) -> None:
    assert not can_transition(current, target)
    assert not is_terminal(current)
    with pytest.raises(InvalidRequestTransitionError):
        assert_transition(current, target)


# --- transition_request ------------------------------------------------------


def _request(status: str = "sent") -> Request:
    return Request(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        lawyer_id=uuid.uuid4(),
        status=status,
    )


def test_every_target_maps_to_an_existing_audit_action() -> None:
    assert TRANSITION_ACTIONS == {
        S.ACCEPTED: AuditAction.REQUEST_ACCEPTED,
        S.DECLINED: AuditAction.REQUEST_DECLINED,
        S.EXPIRED: AuditAction.REQUEST_EXPIRED,
        S.CANCELLED: AuditAction.REQUEST_CANCELLED,
    }


@pytest.mark.parametrize("target", TERMINALS)
def test_transition_request_updates_status_and_logs(target: S) -> None:
    db = Mock(spec=Session)
    req = _request()
    actor = uuid.uuid4()

    result = transition_request(db, req, target, actor)

    assert result is req
    assert req.status == target.value
    db.refresh.assert_called_once_with(req, with_for_update=True)
    db.commit.assert_not_called()  # the caller owns the transaction
    event = db.add.call_args.args[0]
    assert isinstance(event, AuditEvent)
    assert event.action == TRANSITION_ACTIONS[target]
    assert event.actor_id == actor
    assert event.request_id == req.id
    assert event.before == {"status": "sent"}
    assert event.after == {"status": target.value}


@pytest.mark.parametrize("current", TERMINALS)
def test_transition_request_rejects_and_writes_nothing(current: S) -> None:
    db = Mock(spec=Session)
    req = _request(current.value)

    with pytest.raises(InvalidRequestTransitionError):
        transition_request(db, req, S.CANCELLED, uuid.uuid4())

    assert req.status == current.value
    db.add.assert_not_called()
    db.flush.assert_not_called()


@pytest.mark.parametrize("schema", [ClientRequestResponse, LawyerRequestResponse])
def test_response_schemas_reject_legacy_pending(schema: type) -> None:
    assert schema.model_fields["status"].annotation is RequestStatus
    with pytest.raises(ValueError):
        schema.model_fields["status"].annotation("pending")
