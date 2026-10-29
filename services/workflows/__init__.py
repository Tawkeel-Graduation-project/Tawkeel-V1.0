"""Agentic workflows package.

Provides state machine definitions and transition services for agentic legal workflows
(intake, case preparation, scheduling, etc.).
"""

from services.workflows.service import (
    ACTIVE_STATUSES,
    WorkflowNotFoundError,
    create_run,
    get_run,
    list_resumable,
    resume,
    transition,
)
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
    "ACTIVE_STATUSES",
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "InvalidTransitionError",
    "WorkflowKind",
    "WorkflowNotFoundError",
    "WorkflowStatus",
    "allowed_targets",
    "can_transition",
    "create_run",
    "ensure_transition",
    "get_run",
    "is_terminal",
    "list_resumable",
    "next_statuses",
    "resume",
    "transition",
]
