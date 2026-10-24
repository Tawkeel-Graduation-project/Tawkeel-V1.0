"""FastAPI router for lawyer endpoints with strict RBAC and ownership isolation."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_lawyer
from app.auth.ownership import (
    verify_case_ownership,
    verify_conversation_ownership,
    verify_request_ownership,
)
from app.db.models import Case, Conversation, LawyerProfile, Request, User
from app.db.session import get_db
from app.lawyer.schemas import (
    LawyerCaseResponse,
    LawyerConversationResponse,
    LawyerRequestResponse,
    UpdateCaseNotesRequest,
)

router = APIRouter(dependencies=[Depends(require_lawyer)])


def _get_lawyer_profile(db: Session, user: User) -> LawyerProfile:
    """Helper to retrieve lawyer profile or raise 404."""
    profile = db.scalar(select(LawyerProfile).where(LawyerProfile.user_id == user.id))
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found for authenticated user",
        )
    return profile


@router.get("/requests", response_model=list[LawyerRequestResponse])
def list_lawyer_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> list[LawyerRequestResponse]:
    """Retrieve all requests assigned to the authenticated lawyer."""
    profile = _get_lawyer_profile(db, current_user)
    stmt = (
        select(Request)
        .where(Request.lawyer_id == profile.id)
        .order_by(Request.created_at.desc())
    )
    records = db.scalars(stmt).all()
    return [LawyerRequestResponse.model_validate(r) for r in records]


@router.get("/requests/{request_id}", response_model=LawyerRequestResponse)
def get_lawyer_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> LawyerRequestResponse:
    """Retrieve a single request assigned to the authenticated lawyer."""
    req = verify_request_ownership(db, request_id, current_user)
    return LawyerRequestResponse.model_validate(req)


@router.get("/cases", response_model=list[LawyerCaseResponse])
def list_lawyer_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> list[LawyerCaseResponse]:
    """Retrieve all cases assigned to the authenticated lawyer."""
    profile = _get_lawyer_profile(db, current_user)
    stmt = (
        select(Case)
        .where(Case.lawyer_id == profile.id)
        .order_by(Case.created_at.desc())
    )
    records = db.scalars(stmt).all()
    return [LawyerCaseResponse.model_validate(c) for c in records]


@router.get("/cases/{case_id}", response_model=LawyerCaseResponse)
def get_lawyer_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> LawyerCaseResponse:
    """Retrieve an assigned case for the authenticated lawyer."""
    case_obj = verify_case_ownership(db, case_id, current_user)
    return LawyerCaseResponse.model_validate(case_obj)


@router.patch("/cases/{case_id}/notes", response_model=LawyerCaseResponse)
def update_case_notes(
    case_id: uuid.UUID,
    payload: UpdateCaseNotesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> LawyerCaseResponse:
    """Update notes on an assigned case for the authenticated lawyer."""
    case_obj = verify_case_ownership(db, case_id, current_user)
    case_obj.notes = payload.notes
    db.commit()
    db.refresh(case_obj)
    return LawyerCaseResponse.model_validate(case_obj)


@router.get("/conversations", response_model=list[LawyerConversationResponse])
def list_lawyer_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> list[LawyerConversationResponse]:
    """Retrieve conversations accessible to the authenticated lawyer."""
    profile = _get_lawyer_profile(db, current_user)
    # Find conversations created by lawyer or linked to cases managed by lawyer
    stmt = (
        select(Conversation)
        .outerjoin(Case, Conversation.case_id == Case.id)
        .where(
            (Conversation.user_id == current_user.id) | (Case.lawyer_id == profile.id)
        )
        .order_by(Conversation.created_at.desc())
    )
    records = db.scalars(stmt).all()
    return [LawyerConversationResponse.model_validate(c) for c in records]


@router.get(
    "/conversations/{conversation_id}",
    response_model=LawyerConversationResponse,
)
def get_lawyer_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> LawyerConversationResponse:
    """Retrieve a conversation accessible to the authenticated lawyer."""
    conv = verify_conversation_ownership(db, conversation_id, current_user)
    return LawyerConversationResponse.model_validate(conv)
