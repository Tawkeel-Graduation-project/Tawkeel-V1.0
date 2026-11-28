"""The lawyer's request inbox (SCRUM-358 / SCRUM-257)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Request
from services.requests.states import RequestStatus

INBOX_DEFAULT_LIMIT = 50
INBOX_MAX_LIMIT = 100


def lawyer_inbox(
    db: Session,
    lawyer_id: uuid.UUID,
    *,
    status: RequestStatus | None = None,
    limit: int = INBOX_DEFAULT_LIMIT,
    offset: int = 0,
) -> list[Request]:
    """This lawyer's requests (``lawyer_profiles.id``), newest first.

    ``id`` breaks ties so pages don't overlap when timestamps are equal.
    """
    stmt = select(Request).where(Request.lawyer_id == lawyer_id)
    if status is not None:
        stmt = stmt.where(Request.status == RequestStatus(status).value)
    stmt = (
        stmt.order_by(Request.created_at.desc(), Request.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())
