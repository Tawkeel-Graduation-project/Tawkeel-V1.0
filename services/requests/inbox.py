"""The lawyer's request inbox (SCRUM-358 / SCRUM-257)."""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Case, Request
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


def case_ids(
    db: Session, request_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """Request id -> its case id, for requests that have a case."""
    ids = set(request_ids)
    if not ids:
        return {}
    stmt = select(Case.request_id, Case.id).where(Case.request_id.in_(ids))
    return {request_id: case_id for request_id, case_id in db.execute(stmt).all()}
