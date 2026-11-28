"""Request status transitions with an audit event (SCRUM-346, SCRUM-347)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Request
from services.audit.actions import AuditAction
from services.audit.service import log_event
from services.requests.states import RequestStatus, assert_transition

TRANSITION_ACTIONS: dict[RequestStatus, AuditAction] = {
    RequestStatus.ACCEPTED: AuditAction.REQUEST_ACCEPTED,
    RequestStatus.DECLINED: AuditAction.REQUEST_DECLINED,
    RequestStatus.EXPIRED: AuditAction.REQUEST_EXPIRED,
    RequestStatus.CANCELLED: AuditAction.REQUEST_CANCELLED,
}


def transition_request(
    db: Session,
    request: Request,
    target: str,
    actor_id: uuid.UUID,
    *,
    details: dict[str, Any] | None = None,
) -> Request:
    """Move `request` to `target` and log it, in the caller's transaction.

    The row is re-read under a lock first, so two concurrent decisions (e.g.
    accept and cancel) cannot both pass validation. ``details`` is added to the
    audit event's ``after``; never put user free text in it. The caller commits.

    Raises:
        InvalidRequestTransitionError: the move is not allowed.
    """
    db.refresh(request, with_for_update=True)
    current = request.status
    assert_transition(current, target)

    request.status = RequestStatus(target).value
    log_event(
        db,
        actor_id=actor_id,
        action=TRANSITION_ACTIONS[RequestStatus(target)],
        request_id=request.id,
        before={"status": current},
        after={"status": request.status, **(details or {})},
    )
    return request


# --- Lawyer response (SCRUM-347) ---------------------------------------------

DECLINE_REASON_MAX_LENGTH = 500


def accept_request(db: Session, request: Request, *, actor_id: uuid.UUID) -> Request:
    """The lawyer accepts a ``sent`` request. The caller commits.

    Raises:
        InvalidRequestTransitionError: the request is no longer ``sent``.
    """
    transition_request(db, request, RequestStatus.ACCEPTED, actor_id)
    request.responded_at = datetime.now(UTC)
    return request


def decline_request(
    db: Session,
    request: Request,
    reason: str | None,
    *,
    actor_id: uuid.UUID,
) -> Request:
    """The lawyer declines a ``sent`` request, optionally with a reason.

    The reason is shown to the client but kept out of the audit log, which
    only records whether one was given. The caller commits.

    Raises:
        InvalidRequestTransitionError: the request is no longer ``sent``.
    """
    reason = (reason or "").strip() or None
    transition_request(
        db,
        request,
        RequestStatus.DECLINED,
        actor_id,
        details={"reason_given": reason is not None},
    )
    request.responded_at = datetime.now(UTC)
    request.decline_reason = reason
    return request
