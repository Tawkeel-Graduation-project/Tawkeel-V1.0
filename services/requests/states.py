"""Request statuses and transition rules (SCRUM-346).

This module is the single source of truth for the lawyer-request state machine.
A ``requests`` row exists only once the client has sent it to a lawyer; the
pre-send steps (summary review, approval) live in the intake workflow phase.
"""

from enum import StrEnum


class RequestStatus(StrEnum):
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


S = RequestStatus

# current status -> set of statuses it may move to. Anything not listed is forbidden.
ALLOWED_TRANSITIONS: dict[RequestStatus, frozenset[RequestStatus]] = {
    S.SENT: frozenset({S.ACCEPTED, S.DECLINED, S.EXPIRED, S.CANCELLED}),
    S.ACCEPTED: frozenset(),
    S.DECLINED: frozenset(),
    S.EXPIRED: frozenset(),
    S.CANCELLED: frozenset(),
}

TERMINAL_STATUSES = frozenset(
    s for s, targets in ALLOWED_TRANSITIONS.items() if not targets
)


class InvalidRequestTransitionError(Exception):
    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Invalid request transition: {current} -> {target}")


def can_transition(current: str, target: str) -> bool:
    """True if moving a request from `current` to `target` is permitted."""
    try:
        return RequestStatus(target) in ALLOWED_TRANSITIONS[RequestStatus(current)]
    except ValueError:
        return False


def assert_transition(current: str, target: str) -> None:
    """Raise InvalidRequestTransitionError if the move is not allowed."""
    if not can_transition(current, target):
        raise InvalidRequestTransitionError(str(current), str(target))


def is_terminal(status: str) -> bool:
    """True if this status is final and the request cannot change any more."""
    try:
        return RequestStatus(status) in TERMINAL_STATUSES
    except ValueError:
        return False
