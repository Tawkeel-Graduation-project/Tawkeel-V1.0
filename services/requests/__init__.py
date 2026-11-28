"""Lawyer-request status model and transitions (SCRUM-346).

``transition_request`` lives in ``services.requests.service``; it is not
re-exported here because ``app.db.models`` imports this package's states.
"""

from services.requests.states import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    InvalidRequestTransitionError,
    RequestStatus,
    assert_transition,
    can_transition,
    is_terminal,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "InvalidRequestTransitionError",
    "RequestStatus",
    "assert_transition",
    "can_transition",
    "is_terminal",
]
