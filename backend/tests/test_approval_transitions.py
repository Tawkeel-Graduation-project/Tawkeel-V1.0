"""Tests for approval decision transitions and action binding."""

import uuid

import pytest

from app.approvals.policy import (
    ActionUnavailableError,
    UnknownActionError,
    UnresolvedApprovalPolicyError,
    approval_policy,
)
from app.approvals.transitions import (
    ApprovalActor,
    ApprovalBindingMismatchError,
    ApprovalDecisionRequiredError,
    ApprovalNotRequiredError,
    ApprovalRequest,
    ApprovalState,
    ApprovalStateMachine,
    InvalidApprovalTransitionError,
    MissingApprovalActorError,
    UnauthorizedApproverError,
)


@pytest.fixture
def state_machine() -> ApprovalStateMachine:
    return ApprovalStateMachine()


@pytest.fixture
def pending_request(state_machine: ApprovalStateMachine) -> ApprovalRequest:
    return state_machine.request(
        "send_consequential_correspondence",
        "case-123",
        {"recipient": "client@example.test", "body": "Draft"},
    )


@pytest.fixture
def lawyer_actor() -> ApprovalActor:
    return ApprovalActor(user_id=uuid.uuid4(), role="lawyer")


@pytest.mark.parametrize(
    ("decision", "expected_state"),
    [
        (ApprovalState.APPROVED, ApprovalState.APPROVED),
        (ApprovalState.REJECTED, ApprovalState.REJECTED),
    ],
)
def test_lawyer_can_make_explicit_approval_decision(
    state_machine: ApprovalStateMachine,
    pending_request: ApprovalRequest,
    lawyer_actor: ApprovalActor,
    decision: ApprovalState,
    expected_state: ApprovalState,
) -> None:
    decided = state_machine.decide(pending_request, decision, lawyer_actor)

    assert decided.state is expected_state
    assert decided.decided_by == lawyer_actor.user_id
    assert pending_request.state is ApprovalState.PENDING
    assert pending_request.decided_by is None


def test_approval_must_be_explicit_and_actor_context_is_required(
    state_machine: ApprovalStateMachine,
    pending_request: ApprovalRequest,
) -> None:
    with pytest.raises(MissingApprovalActorError):
        state_machine.decide(pending_request, ApprovalState.APPROVED, None)
    with pytest.raises(TypeError, match="ApprovalActor"):
        state_machine.decide(pending_request, ApprovalState.APPROVED, True)
    with pytest.raises(TypeError, match="user_id must be a UUID"):
        ApprovalActor(user_id="not-a-uuid", role="lawyer")
    assert pending_request.state is ApprovalState.PENDING
    assert pending_request.decided_by is None


@pytest.mark.parametrize("destination", [ApprovalState.PENDING, "approved", True])
def test_only_explicit_approval_decision_states_are_valid_destinations(
    state_machine: ApprovalStateMachine,
    pending_request: ApprovalRequest,
    lawyer_actor: ApprovalActor,
    destination: object,
) -> None:
    with pytest.raises(InvalidApprovalTransitionError):
        state_machine.decide(pending_request, destination, lawyer_actor)
    assert pending_request.state is ApprovalState.PENDING


@pytest.mark.parametrize("role", ["client", "admin", "agent", ""])
def test_only_the_policy_authorized_lawyer_can_decide(
    state_machine: ApprovalStateMachine,
    pending_request: ApprovalRequest,
    role: str,
) -> None:
    actor = ApprovalActor(user_id=uuid.uuid4(), role=role)

    with pytest.raises(UnauthorizedApproverError):
        state_machine.decide(pending_request, ApprovalState.APPROVED, actor)
    assert pending_request.state is ApprovalState.PENDING
    assert pending_request.decided_by is None


@pytest.mark.parametrize(
    ("current_state", "destination"),
    [
        (ApprovalState.PENDING, ApprovalState.PENDING),
        (ApprovalState.APPROVED, ApprovalState.APPROVED),
        (ApprovalState.APPROVED, ApprovalState.REJECTED),
        (ApprovalState.REJECTED, ApprovalState.REJECTED),
        (ApprovalState.REJECTED, ApprovalState.APPROVED),
    ],
)
def test_invalid_source_destination_transitions_are_rejected_without_mutation(
    state_machine: ApprovalStateMachine,
    current_state: ApprovalState,
    destination: ApprovalState,
) -> None:
    request = state_machine.request("delete_case_data", "case-456", {"field": "notes"})
    if current_state is not ApprovalState.PENDING:
        request = state_machine.decide(
            request,
            current_state,
            ApprovalActor(user_id=uuid.uuid4(), role="lawyer"),
        )
    original_decided_by = request.decided_by

    with pytest.raises(InvalidApprovalTransitionError):
        state_machine.decide(
            request,
            destination,
            ApprovalActor(user_id=uuid.uuid4(), role="lawyer"),
        )
    assert request.state is current_state
    assert request.decided_by == original_decided_by


def test_unknown_and_unresolved_actions_cannot_enter_approval_flow(
    state_machine: ApprovalStateMachine,
) -> None:
    with pytest.raises(UnknownActionError):
        state_machine.request("unregistered_operation", "case-1", {})
    with pytest.raises(UnresolvedApprovalPolicyError):
        state_machine.request("deliver_client_summary", "request-1", {})


def test_autonomous_action_is_not_forced_through_approval(
    state_machine: ApprovalStateMachine,
) -> None:
    with pytest.raises(ApprovalNotRequiredError):
        state_machine.request("schedule_meeting", "request-1", {"slot": "10:00"})


def test_pending_or_rejected_decision_cannot_validate_as_approved(
    state_machine: ApprovalStateMachine,
    pending_request: ApprovalRequest,
    lawyer_actor: ApprovalActor,
) -> None:
    parameters = {"recipient": "client@example.test", "body": "Draft"}
    with pytest.raises(ApprovalDecisionRequiredError):
        state_machine.validate_approved_for(
            pending_request,
            pending_request.action_id,
            pending_request.target_id,
            parameters,
        )

    rejected = state_machine.decide(
        pending_request, ApprovalState.REJECTED, lawyer_actor
    )
    with pytest.raises(ApprovalDecisionRequiredError):
        state_machine.validate_approved_for(
            rejected, rejected.action_id, rejected.target_id, parameters
        )


@pytest.mark.parametrize(
    ("action_id", "target_id", "parameters"),
    [
        (
            "delete_case_data",
            "case-123",
            {"recipient": "client@example.test", "body": "Draft"},
        ),
        (
            "send_consequential_correspondence",
            "case-999",
            {"recipient": "client@example.test", "body": "Draft"},
        ),
        (
            "send_consequential_correspondence",
            "case-123",
            {"recipient": "other@example.test", "body": "Draft"},
        ),
        (
            "send_consequential_correspondence",
            "case-123",
            {"recipient": "client@example.test", "body": "Changed"},
        ),
        (
            "send_consequential_correspondence",
            "case-123",
            {
                "recipient": "client@example.test",
                "body": "Draft",
                "cc": "lawyer@example.test",
            },
        ),
        (
            "send_consequential_correspondence",
            "case-123",
            {"body": "Draft"},
        ),
    ],
)
def test_approval_cannot_be_reused_for_other_action_target_or_parameters(
    state_machine: ApprovalStateMachine,
    pending_request: ApprovalRequest,
    lawyer_actor: ApprovalActor,
    action_id: str,
    target_id: str,
    parameters: dict[str, str],
) -> None:
    approved = state_machine.decide(
        pending_request, ApprovalState.APPROVED, lawyer_actor
    )

    with pytest.raises(ApprovalBindingMismatchError):
        state_machine.validate_approved_for(approved, action_id, target_id, parameters)
    assert approved.state is ApprovalState.APPROVED
    assert approved.decided_by == lawyer_actor.user_id


def test_parameter_order_does_not_change_approval_binding(
    state_machine: ApprovalStateMachine,
    lawyer_actor: ApprovalActor,
) -> None:
    request = state_machine.request(
        "modify_case_data", "case-123", {"a": 1, "b": {"x": True, "y": 2}}
    )
    approved = state_machine.decide(request, ApprovalState.APPROVED, lawyer_actor)

    assert (
        state_machine.validate_approved_for(
            approved,
            "modify_case_data",
            "case-123",
            {"b": {"y": 2, "x": True}, "a": 1},
        )
        is approved
    )


def test_approval_decision_does_not_enable_a_disabled_action(
    state_machine: ApprovalStateMachine,
    lawyer_actor: ApprovalActor,
) -> None:
    request = state_machine.request(
        "submit_important_legal_document", "case-123", {"document_id": "doc-1"}
    )
    approved = state_machine.decide(request, ApprovalState.APPROVED, lawyer_actor)

    with pytest.raises(ActionUnavailableError):
        approval_policy.require_implemented(approved.action_id)


def test_untrusted_callers_cannot_construct_approved_request_directly() -> None:
    with pytest.raises(TypeError, match="_token"):
        ApprovalRequest(
            action_id="delete_case_data",
            target_id="case-123",
            parameters_sha256="0" * 64,
            state=ApprovalState.APPROVED,
            decided_by=uuid.uuid4(),
        )


@pytest.mark.parametrize(
    ("target_id", "parameters"),
    [
        ("", {}),
        ("case-1", {1: "non-string key"}),
        ("case-1", {"not_json": object()}),
    ],
)
def test_invalid_target_or_parameters_cannot_start_approval(
    state_machine: ApprovalStateMachine,
    target_id: str,
    parameters: dict,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        state_machine.request("delete_case_data", target_id, parameters)
