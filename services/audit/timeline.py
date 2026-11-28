"""Audit timeline of one request and its case (SCRUM-419 / SCRUM-280).

Only the request's own events and its case's events are included. Intake
workflow events carry neither id, so they never appear here.
"""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Case, User

TIMELINE_DEFAULT_LIMIT = 100
TIMELINE_MAX_LIMIT = 500
SYSTEM_ACTOR_ID = uuid.UUID(int=0)  # see services.audit.actions.SYSTEM_ACTIONS


def request_timeline(
    db: Session,
    request_id: uuid.UUID,
    *,
    limit: int = TIMELINE_DEFAULT_LIMIT,
    offset: int = 0,
) -> list[tuple[AuditEvent, User | None]]:
    """Events of the request and its case, oldest first, with each actor.

    The actor is ``None`` for the system actor or a missing user.
    ``id`` breaks ties so pages don't overlap when timestamps are equal.
    """
    case_ids = select(Case.id).where(Case.request_id == request_id)
    stmt = (
        select(AuditEvent, User)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(
            or_(
                AuditEvent.request_id == request_id,
                AuditEvent.case_id.in_(case_ids),
            )
        )
        .order_by(AuditEvent.created_at, AuditEvent.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        (event, None if actor is None or actor.id == SYSTEM_ACTOR_ID else actor)
        for event, actor in db.execute(stmt).all()
    ]
