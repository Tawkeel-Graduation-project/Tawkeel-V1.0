"""Backward-compatibility module forwarding to services.workflows.states."""

from services.workflows.states import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    InvalidTransitionError,
    WorkflowKind,
    WorkflowStatus,
    allowed_targets,
    can_transition,
    ensure_transition,
    is_terminal,
    next_statuses,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "InvalidTransitionError",
    "WorkflowKind",
    "WorkflowStatus",
    "allowed_targets",
    "can_transition",
    "ensure_transition",
    "is_terminal",
    "next_statuses",
]
