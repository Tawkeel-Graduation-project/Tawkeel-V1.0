"""Workflow kinds, statuses, and transition rules.

This module is the single source of truth for the workflow state machine.
Transitions that are not explicitly permitted here must be rejected by the service.
"""

from enum import StrEnum


class WorkflowKind(StrEnum):
    CASE_PREP = "case_prep"
    SCHEDULING = "scheduling"
    INTAKE = "intake"


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


S = WorkflowStatus

# For each kind: current status -> set of statuses it may move to.
# Anything not listed here is forbidden.
ALLOWED_TRANSITIONS: dict[
    WorkflowKind, dict[WorkflowStatus, frozenset[WorkflowStatus]]
] = {
    # Lawyer must approve the generated document before it completes.
    WorkflowKind.CASE_PREP: {
        S.PENDING: frozenset({S.RUNNING, S.FAILED}),
        S.RUNNING: frozenset({S.AWAITING_APPROVAL, S.FAILED}),
        S.AWAITING_APPROVAL: frozenset({S.COMPLETED, S.RUNNING, S.FAILED}),
        S.COMPLETED: frozenset(),
        S.FAILED: frozenset({S.PENDING}),  # retry
    },
    # A lawyer or client must confirm the booking before it completes.
    WorkflowKind.SCHEDULING: {
        S.PENDING: frozenset({S.RUNNING, S.FAILED}),
        S.RUNNING: frozenset({S.AWAITING_APPROVAL, S.FAILED}),
        S.AWAITING_APPROVAL: frozenset({S.COMPLETED, S.RUNNING, S.FAILED}),
        S.COMPLETED: frozenset(),
        S.FAILED: frozenset({S.PENDING}),
    },
    # Intake may finish directly, or ask the client to confirm the summary.
    WorkflowKind.INTAKE: {
        S.PENDING: frozenset({S.RUNNING, S.FAILED}),
        S.RUNNING: frozenset({S.AWAITING_APPROVAL, S.COMPLETED, S.FAILED}),
        S.AWAITING_APPROVAL: frozenset({S.COMPLETED, S.RUNNING, S.FAILED}),
        S.COMPLETED: frozenset(),
        S.FAILED: frozenset({S.PENDING}),
    },
}

TERMINAL_STATUSES = frozenset({WorkflowStatus.COMPLETED})


class InvalidTransitionError(Exception):
    def __init__(self, kind: str, current: str, target: str) -> None:
        self.kind = kind
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid transition for '{kind}' workflow: {current} -> {target}"
        )


def allowed_targets(kind: str, current: str) -> frozenset[WorkflowStatus]:
    """Return the set of statuses `current` can move to for this kind."""
    try:
        return ALLOWED_TRANSITIONS[WorkflowKind(kind)][WorkflowStatus(current)]
    except (ValueError, KeyError):
        return frozenset()


def can_transition(kind: str, current: str, target: str) -> bool:
    """True if moving from `current` to `target` is permitted."""
    try:
        target_status = WorkflowStatus(target)
        return target_status in allowed_targets(kind, current)
    except ValueError:
        return False


def ensure_transition(kind: str, current: str, target: str) -> None:
    """Raise InvalidTransitionError if the move is not allowed."""
    if not can_transition(kind, current, target):
        raise InvalidTransitionError(kind, current, target)


def next_statuses(kind: str, current: str) -> list[str]:
    """User-facing helper: string list of valid next statuses, sorted for stability."""
    return sorted(s.value for s in allowed_targets(kind, current))


def is_terminal(status: str) -> bool:
    """True if this status is final and the run cannot be modified further."""
    try:
        return WorkflowStatus(status) in TERMINAL_STATUSES
    except ValueError:
        return False

