"""Tests for the server-owned action approval policy."""

from dataclasses import FrozenInstanceError

import pytest

from app.approvals.policy import (
    ACTION_POLICIES,
    ActionPolicy,
    ActionUnavailableError,
    ApprovalPolicy,
    ApprovalRequirement,
    AuthorizedApprover,
    InvalidActionIdentifierError,
    UnknownActionError,
    UnresolvedApprovalPolicyError,
    approval_policy,
)


@pytest.mark.parametrize(
    "action_id,execution_available",
    [
        ("schedule_meeting", False),
        ("retrieve_legal_information", True),
        ("conduct_legal_research", False),
        ("prepare_intake_summary", False),
        ("analyze_contract", False),
        ("prepare_legal_draft", False),
        ("prepare_case_prep_output", False),
        ("recommend_lawyers", False),
    ],
)
def test_known_preparatory_and_autonomous_actions_do_not_require_approval(
    action_id: str, execution_available: bool
) -> None:
    action = approval_policy.get(action_id)

    assert approval_policy.requires_approval(action_id) is False
    assert action.approval_requirement is ApprovalRequirement.NOT_REQUIRED
    assert action.authorized_approver is None
    assert action.execution_available is execution_available


@pytest.mark.parametrize(
    "action_id",
    [
        "modify_case_data",
        "delete_case_data",
        "send_consequential_correspondence",
        "export_legal_draft",
        "submit_important_legal_document",
    ],
)
def test_consequential_actions_require_lawyer_approval_and_are_disabled(
    action_id: str,
) -> None:
    action = approval_policy.get(action_id)

    assert approval_policy.requires_approval(action_id) is True
    assert action.approval_requirement is ApprovalRequirement.REQUIRED
    assert action.authorized_approver is AuthorizedApprover.LAWYER
    assert action.execution_available is False
    with pytest.raises(ActionUnavailableError):
        approval_policy.require_implemented(action_id)


@pytest.mark.parametrize(
    "action_id",
    [
        "deliver_client_summary",
        "approve_case_prep_output",
        "cancel_scheduled_meeting",
    ],
)
def test_unresolved_actions_fail_closed(action_id: str) -> None:
    action = approval_policy.get(action_id)

    assert action.approval_requirement is ApprovalRequirement.UNRESOLVED
    assert action.execution_available is False
    with pytest.raises(UnresolvedApprovalPolicyError):
        approval_policy.requires_approval(action_id)
    with pytest.raises(UnresolvedApprovalPolicyError):
        approval_policy.require_implemented(action_id)


def test_unknown_action_is_not_treated_as_approval_free() -> None:
    with pytest.raises(UnknownActionError, match="unknown action"):
        approval_policy.requires_approval("unregistered_operation")


@pytest.mark.parametrize(
    "action_id",
    ["", "schedule meeting", "ScheduleMeeting", "send-email", " trailing", None],
)
def test_invalid_action_identifiers_are_rejected(action_id: object) -> None:
    with pytest.raises(InvalidActionIdentifierError):
        approval_policy.get(action_id)


def test_duplicate_or_conflicting_policy_definitions_are_rejected() -> None:
    first = ActionPolicy(
        "sample_action",
        ApprovalRequirement.NOT_REQUIRED,
        None,
        execution_available=False,
    )
    conflicting = ActionPolicy(
        "sample_action",
        ApprovalRequirement.REQUIRED,
        AuthorizedApprover.LAWYER,
        execution_available=False,
    )

    with pytest.raises(ValueError, match="conflicting approval policy"):
        ApprovalPolicy((first, conflicting))


@pytest.mark.parametrize(
    "requirement,approver",
    [
        (ApprovalRequirement.REQUIRED, None),
        (ApprovalRequirement.NOT_REQUIRED, AuthorizedApprover.LAWYER),
        (ApprovalRequirement.UNRESOLVED, AuthorizedApprover.CLIENT),
    ],
)
def test_policy_rejects_conflicting_approval_metadata(requirement, approver) -> None:
    with pytest.raises(ValueError):
        ActionPolicy(
            "sample_action",
            requirement,
            approver,
            execution_available=False,
        )


def test_policy_definitions_are_immutable_and_cannot_be_overridden_by_callers() -> None:
    action = approval_policy.get("delete_case_data")

    with pytest.raises(FrozenInstanceError):
        action.approval_requirement = ApprovalRequirement.NOT_REQUIRED
    with pytest.raises(TypeError):
        approval_policy.requires_approval("delete_case_data", approved=False)


def test_all_server_policy_entries_have_unique_identifiers() -> None:
    identifiers = [action.action_id for action in ACTION_POLICIES]

    assert len(identifiers) == len(set(identifiers))
