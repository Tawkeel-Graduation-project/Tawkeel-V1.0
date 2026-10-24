"""FastAPI router for client endpoints with strict RBAC and ownership isolation."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_client
from app.auth.ownership import (
    verify_case_ownership,
    verify_conversation_ownership,
    verify_request_ownership,
)
from app.client.schemas import (
    ClientCaseResponse,
    ClientConversationResponse,
    ClientRequestResponse,
    CreateClientRequest,
)
from app.db.models import Case, Conversation, Request, User
from app.db.session import get_db

router = APIRouter(dependencies=[Depends(require_client)])


@router.get("/requests", response_model=list[ClientRequestResponse])
def list_client_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> list[ClientRequestResponse]:
    """Retrieve all requests submitted by the authenticated client."""
    stmt = (
        select(Request)
        .where(Request.client_id == current_user.id)
        .order_by(Request.created_at.desc())
    )
    records = db.scalars(stmt).all()
    return [ClientRequestResponse.model_validate(r) for r in records]


@router.post(
    "/requests",
    response_model=ClientRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_client_request(
    payload: CreateClientRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> ClientRequestResponse:
    """Create a new service request owned by the authenticated client."""
    new_request = Request(
        client_id=current_user.id,
        lawyer_id=payload.lawyer_id,
        niche=payload.niche,
        summary=payload.summary,
        status="pending",
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)
    return ClientRequestResponse.model_validate(new_request)


@router.get("/requests/{request_id}", response_model=ClientRequestResponse)
def get_client_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> ClientRequestResponse:
    """Retrieve a single request owned by the authenticated client."""
    req = verify_request_ownership(db, request_id, current_user)
    return ClientRequestResponse.model_validate(req)


@router.get("/cases", response_model=list[ClientCaseResponse])
def list_client_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> list[ClientCaseResponse]:
    """Retrieve all cases originating from the authenticated client's requests."""
    stmt = (
        select(Case)
        .join(Request, Case.request_id == Request.id)
        .where(Request.client_id == current_user.id)
        .order_by(Case.created_at.desc())
    )
    records = db.scalars(stmt).all()
    return [ClientCaseResponse.model_validate(c) for c in records]


@router.get("/cases/{case_id}", response_model=ClientCaseResponse)
def get_client_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> ClientCaseResponse:
    """Retrieve a case belonging to the authenticated client."""
    case_obj = verify_case_ownership(db, case_id, current_user)
    return ClientCaseResponse.model_validate(case_obj)


@router.get("/conversations", response_model=list[ClientConversationResponse])
def list_client_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> list[ClientConversationResponse]:
    """Retrieve all conversations initiated by the authenticated client."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
    )
    records = db.scalars(stmt).all()
    return [ClientConversationResponse.model_validate(c) for c in records]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ClientConversationResponse,
)
def get_client_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> ClientConversationResponse:
    """Retrieve a conversation owned by the authenticated client."""
    conv = verify_conversation_ownership(db, conversation_id, current_user)
    return ClientConversationResponse.model_validate(conv)
