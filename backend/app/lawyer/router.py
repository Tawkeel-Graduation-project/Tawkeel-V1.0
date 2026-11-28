"""FastAPI router for lawyer endpoints with strict RBAC and ownership isolation."""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from services.audit.actions import AuditAction
from services.audit.service import log_event
from services.requests.inbox import (
    INBOX_DEFAULT_LIMIT,
    INBOX_MAX_LIMIT,
    case_ids,
    lawyer_inbox,
)
from services.requests.service import (
    CaseExistsError,
    accept_request,
    decline_request,
)
from services.requests.states import InvalidRequestTransitionError, RequestStatus
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
    DeclineRequestBody,
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
    request_status: RequestStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=INBOX_DEFAULT_LIMIT, ge=1, le=INBOX_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> list[LawyerRequestResponse]:
    """The lawyer's inbox, newest first (SCRUM-358).

    ``?status=sent`` filters by status (422 if not a request status). Each
    item carries only the approved summary snapshot the client sent.
    """
    profile = _get_lawyer_profile(db, current_user)
    records = lawyer_inbox(
        db, profile.id, status=request_status, limit=limit, offset=offset
    )
    return _with_case_ids(db, records)


def _with_case_ids(
    db: Session, records: Sequence[Request]
) -> list[LawyerRequestResponse]:
    cases = case_ids(db, [r.id for r in records])
    return [
        LawyerRequestResponse.model_validate(r).model_copy(
            update={"case_id": cases.get(r.id)}
        )
        for r in records
    ]


@router.get("/requests/{request_id}", response_model=LawyerRequestResponse)
def get_lawyer_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> LawyerRequestResponse:
    """One request assigned to this lawyer, with the approved summary snapshot.

    403 if it is another lawyer's, 404 if it doesn't exist.
    """
    req = verify_request_ownership(db, request_id, current_user)
    return _with_case_ids(db, [req])[0]


def _not_sent(exc: InvalidRequestTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"This request is already {exc.current}",
    )


@router.post("/requests/{request_id}/accept", response_model=LawyerRequestResponse)
def accept_lawyer_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> LawyerRequestResponse:
    """Accept a request sent to this lawyer and open its case (SCRUM-347/359).

    409 unless it is sent, or if the request already has a case.
    """
    req = verify_request_ownership(db, request_id, current_user)
    try:
        case = accept_request(db, req, actor_id=current_user.id)
    except InvalidRequestTransitionError as exc:
        raise _not_sent(exc) from exc
    except CaseExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    db.commit()
    db.refresh(req)
    return LawyerRequestResponse.model_validate(req).model_copy(
        update={"case_id": case.id}
    )


@router.post("/requests/{request_id}/decline", response_model=LawyerRequestResponse)
def decline_lawyer_request(
    request_id: uuid.UUID,
    payload: DeclineRequestBody | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
) -> LawyerRequestResponse:
    """Decline a request sent to this lawyer (SCRUM-347). 409 unless it is sent.

    The optional ``reason`` is shown to the client; the client may then send
    the intake to another lawyer.
    """
    req = verify_request_ownership(db, request_id, current_user)
    reason = payload.reason if payload else None
    try:
        decline_request(db, req, reason, actor_id=current_user.id)
    except InvalidRequestTransitionError as exc:
        raise _not_sent(exc) from exc
    db.commit()
    db.refresh(req)
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
    old_notes = case_obj.notes
    case_obj.notes = payload.notes
    log_event(
        db,
        actor_id=current_user.id,
        action=AuditAction.CASE_NOTES_UPDATED,
        case_id=case_obj.id,
        before={"notes": old_notes},
        after={"notes": payload.notes},
    )
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
