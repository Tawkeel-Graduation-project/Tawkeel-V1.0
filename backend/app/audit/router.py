"""FastAPI router for the append-only audit trail (L9, SCRUM-276)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from services.audit.service import list_events_for_user
from services.audit.timeline import (
    TIMELINE_DEFAULT_LIMIT,
    TIMELINE_MAX_LIMIT,
    request_timeline,
)
from sqlalchemy.orm import Session

from app.audit.schemas import (
    AuditEventListResponse,
    AuditEventResponse,
    TimelineActor,
    TimelineEventResponse,
)
from app.auth.dependencies import get_current_user
from app.auth.ownership import verify_case_ownership, verify_request_ownership
from app.db.models import User
from app.db.session import get_db

router = APIRouter()


@router.get("", response_model=AuditEventListResponse)
def list_audit_events(
    case_id: uuid.UUID | None = Query(default=None),
    request_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AuditEventListResponse:
    """List audit events visible to the authenticated user.

    - Lawyers see events on their cases and assigned requests.
    - Clients see events on their submitted requests.
    - Admins see all events.

    Filtered by optional ``case_id`` or ``request_id`` query parameters.
    """
    events = list_events_for_user(
        db,
        user_id=current_user.id,
        user_role=current_user.role,
        case_id=case_id,
        request_id=request_id,
        limit=limit,
        offset=offset,
    )
    return AuditEventListResponse(
        events=[AuditEventResponse.model_validate(e) for e in events],
        count=len(events),
    )


@router.get("/timeline", response_model=list[TimelineEventResponse])
def get_audit_timeline(
    request_id: uuid.UUID | None = Query(default=None),
    case_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=TIMELINE_DEFAULT_LIMIT, ge=1, le=TIMELINE_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TimelineEventResponse]:
    """Timeline of a request and its case together, oldest first.

    Pass exactly one of ``request_id`` or ``case_id``; either gives the same
    events. Only the request's client, its lawyer and admins may view it.
    Items carry who, what and when, never the event's details.
    """
    if (request_id is None) == (case_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Pass exactly one of request_id or case_id",
        )
    if request_id is not None:
        verify_request_ownership(db, request_id, current_user)
    else:
        request_id = verify_case_ownership(db, case_id, current_user).request_id

    rows = request_timeline(db, request_id, limit=limit, offset=offset)
    return [
        TimelineEventResponse(
            id=event.id,
            action=event.action,
            actor=None
            if actor is None
            else TimelineActor(id=actor.id, role=actor.role, name=actor.full_name),
            created_at=event.created_at,
        )
        for event, actor in rows
    ]
