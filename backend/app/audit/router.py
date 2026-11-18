"""FastAPI router for the append-only audit trail (L9, SCRUM-276)."""

import uuid

from fastapi import APIRouter, Depends, Query
from services.audit.service import list_events_for_user
from sqlalchemy.orm import Session

from app.audit.schemas import AuditEventListResponse, AuditEventResponse
from app.auth.dependencies import get_current_user
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
