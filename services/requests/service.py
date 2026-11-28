"""Apply request status transitions with an audit event (SCRUM-346)."""

import uuid

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
) -> Request:
    """Move `request` to `target` and log it, in the caller's transaction.

    The row is re-read under a lock first, so two concurrent decisions (e.g.
    accept and cancel) cannot both pass validation. The caller commits.

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
        after={"status": request.status},
    )
    return request
