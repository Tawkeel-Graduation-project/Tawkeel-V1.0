"""Unit tests for services.workflows state machine, rules, and forwarders."""

import pytest
from services.workflows import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    WorkflowKind,
    WorkflowStatus,
    allowed_targets,
    can_transition,
    ensure_transition,
    is_terminal,
    next_statuses,
)


def test_workflow_states_and_kinds_enum_values() -> None:
    assert WorkflowKind.CASE_PREP.value == "case_prep"
    assert WorkflowKind.SCHEDULING.value == "scheduling"
    assert WorkflowKind.INTAKE.value == "intake"

    assert WorkflowStatus.PENDING.value == "pending"
    assert WorkflowStatus.RUNNING.value == "running"
    assert WorkflowStatus.AWAITING_APPROVAL.value == "awaiting_approval"
    assert WorkflowStatus.COMPLETED.value == "completed"
    assert WorkflowStatus.FAILED.value == "failed"


def test_can_transition_case_prep_flow() -> None:
    assert can_transition(
        WorkflowKind.CASE_PREP,
        WorkflowStatus.PENDING,
        WorkflowStatus.RUNNING,
    )
    assert can_transition(
        WorkflowKind.CASE_PREP,
        WorkflowStatus.RUNNING,
        WorkflowStatus.AWAITING_APPROVAL,
    )
    # Cannot jump straight from PENDING to COMPLETED without approval
    assert not can_transition(
        WorkflowKind.CASE_PREP,
        WorkflowStatus.PENDING,
        WorkflowStatus.COMPLETED,
    )
    # Cannot move once completed
    assert not can_transition(
        WorkflowKind.CASE_PREP,
        WorkflowStatus.COMPLETED,
        WorkflowStatus.RUNNING,
    )


def test_can_transition_intake_direct_completion() -> None:
    # Intake can complete directly or go through awaiting_approval
    assert can_transition(
        WorkflowKind.INTAKE,
        WorkflowStatus.RUNNING,
        WorkflowStatus.COMPLETED,
    )
    assert can_transition(
        WorkflowKind.INTAKE,
        WorkflowStatus.RUNNING,
        WorkflowStatus.AWAITING_APPROVAL,
    )


def test_ensure_transition_raises_on_invalid() -> None:
    with pytest.raises(InvalidTransitionError) as exc_info:
        ensure_transition("case_prep", "pending", "completed")
    assert "Invalid transition for 'case_prep' workflow" in str(exc_info.value)

    # Valid does not raise
    ensure_transition("case_prep", "pending", "running")


def test_next_statuses_helper() -> None:
    targets = next_statuses("case_prep", "pending")
    assert targets == ["failed", "running"]

    # Unknown kind or status returns empty list
    assert next_statuses("non_existent", "pending") == []
    assert next_statuses("case_prep", "non_existent") == []


def test_is_terminal() -> None:
    assert is_terminal(WorkflowStatus.COMPLETED)
    assert not is_terminal(WorkflowStatus.RUNNING)
    assert not is_terminal(WorkflowStatus.PENDING)
    assert not is_terminal("unknown_status")


def test_allowed_transitions_coverage() -> None:
    for kind in WorkflowKind:
        assert kind in ALLOWED_TRANSITIONS
        for status in WorkflowStatus:
            assert status in ALLOWED_TRANSITIONS[kind]
            reachable = allowed_targets(kind, status)
            assert isinstance(reachable, frozenset)


def test_app_workflows_backward_compatibility() -> None:
    import services.workflows as services_wf

    import app.workflows as legacy_workflows

    assert legacy_workflows.WorkflowKind is services_wf.WorkflowKind
    assert legacy_workflows.WorkflowStatus is services_wf.WorkflowStatus
    assert legacy_workflows.can_transition is services_wf.can_transition
    assert legacy_workflows.create_run is services_wf.create_run
    assert legacy_workflows.transition is services_wf.transition
    assert legacy_workflows.get_run is services_wf.get_run
