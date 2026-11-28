"""FastAPI router for client endpoints with strict RBAC and ownership isolation."""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Response, status
from services.intake.service import IntakeTurnError, take_turn
from services.intake.summary import (
    SummaryConflictError,
    SummaryValidationError,
    approve_summary,
    update_summary,
)
from services.llm.factory import get_llm_provider
from services.llm.provider import BaseLLMProvider
from services.requests.send import (
    LawyerUnavailableError,
    SendConflictError,
    intake_requests,
    lawyer_names,
    list_verified_lawyers,
    send_request,
)
from services.workflows.intake import (
    IntakeContextError,
    IntakePhase,
    SubmittedMessage,
    start_intake,
)
from services.workflows.states import WorkflowKind
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_client
from app.auth.ownership import (
    verify_case_ownership,
    verify_conversation_ownership,
    verify_request_ownership,
)
from app.client.schemas import (
    ApproveSummaryRequest,
    ClientCaseResponse,
    ClientConversationResponse,
    ClientRequestResponse,
    IntakeResponse,
    IntakeTurnRequest,
    LawyerSummaryResponse,
    SendRequestBody,
    SentRequestResponse,
    StartIntakeRequest,
    UpdateSummaryRequest,
)
from app.core.config import Settings, get_settings
from app.db.models import Case, Conversation, Request, User, Workflow
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
    return _with_lawyer_names(db, db.scalars(stmt).all())


def _with_lawyer_names(
    db: Session, records: Sequence[Request]
) -> list[ClientRequestResponse]:
    names = lawyer_names(db, {r.lawyer_id for r in records})
    return [
        ClientRequestResponse.model_validate(r).model_copy(
            update={"lawyer_name": names.get(r.lawyer_id)}
        )
        for r in records
    ]


@router.get("/requests/{request_id}", response_model=ClientRequestResponse)
def get_client_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> ClientRequestResponse:
    """Retrieve a single request owned by the authenticated client."""
    req = verify_request_ownership(db, request_id, current_user)
    return _with_lawyer_names(db, [req])[0]


@router.get("/lawyers", response_model=list[LawyerSummaryResponse])
def list_client_lawyers(db: Session = Depends(get_db)) -> list[LawyerSummaryResponse]:
    """Verified lawyers the client can send a request to (SCRUM-344)."""
    return [
        LawyerSummaryResponse(
            id=profile.id,
            full_name=user.full_name,
            niches=profile.niches or [],
            city=profile.city,
            fee_min=profile.fee_min,
            fee_max=profile.fee_max,
            years_experience=profile.years_experience,
            bio=profile.bio,
        )
        for profile, user in list_verified_lawyers(db)
    ]


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


@router.post(
    "/intakes",
    response_model=IntakeResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "An intake is already active for this chat"}},
)
def start_client_intake(
    payload: StartIntakeRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> IntakeResponse:
    """'Request a Lawyer': start the intake workflow from a chat (SCRUM-331).

    The chat is snapshotted into the workflow, which moves to ``running`` with
    phase ``INTAKE``. Returns 201 when started, or 200 with the existing run if
    this conversation already has an active intake.
    """
    conversation = None
    submitted = None
    if payload.conversation_id is not None:
        conversation = verify_conversation_ownership(
            db, payload.conversation_id, current_user
        )
        if conversation.type != "qa":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Only a legal Q&A conversation can start a lawyer request",
            )
    else:
        submitted = [
            SubmittedMessage(
                role=m.role,
                content=m.content,
                citations=[
                    c.model_dump(by_alias=True, exclude_none=True) for c in m.citations
                ],
            )
            for m in payload.messages or []
        ]

    try:
        result = start_intake(
            db,
            client_id=current_user.id,
            conversation=conversation,
            submitted_messages=submitted,
        )
    except IntakeContextError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    if not result.created:
        response.status_code = status.HTTP_200_OK
    return _intake_response(db, result.workflow)


def _intake_response(db: Session, wf: Workflow) -> IntakeResponse:
    # Requests exist only after approval, so skip the query before that.
    approved = (wf.state or {}).get("phase") == IntakePhase.APPROVED
    return IntakeResponse.from_workflow(
        wf, intake_requests(db, wf.id) if approved else ()
    )


def _owned_intake(db: Session, intake_id: uuid.UUID, current_user: User) -> Workflow:
    """Load an intake run the client owns (404 if missing, 403 if not theirs)."""
    wf = db.scalar(
        select(Workflow).where(
            Workflow.id == intake_id,
            Workflow.kind == WorkflowKind.INTAKE.value,
        )
    )
    if wf is None or wf.conversation_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Intake not found"
        )
    # Ownership follows the conversation the intake started from.
    verify_conversation_ownership(db, wf.conversation_id, current_user)
    return wf


@router.get("/intakes/{intake_id}", response_model=IntakeResponse)
def get_client_intake(
    intake_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> IntakeResponse:
    """Retrieve an intake workflow started by the authenticated client."""
    return _intake_response(db, _owned_intake(db, intake_id, current_user))


def get_intake_provider(settings: Settings = Depends(get_settings)) -> BaseLLMProvider:
    """LLM provider for the intake agent (overridable in tests)."""
    return get_llm_provider(settings)


@router.post("/intakes/{intake_id}/turns", response_model=IntakeResponse)
async def take_client_intake_turn(
    intake_id: uuid.UUID,
    payload: IntakeTurnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
    provider: BaseLLMProvider = Depends(get_intake_provider),
) -> IntakeResponse:
    """Talk to the intake agent (SCRUM-248).

    ``content: null`` opens the intake: the agent pre-fills fields from the
    client's chat messages and asks its first question. Afterwards each call
    sends the client's answer and returns the agent's next question, or
    ``complete: true`` once everything needed is collected or declined.
    """
    _owned_intake(db, intake_id, current_user)
    try:
        run, _ = await take_turn(
            db,
            provider,
            intake_id,
            actor_id=current_user.id,
            client_message=payload.content,
        )
    except IntakeTurnError as exc:  # includes IntakeConflictError
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return _intake_response(db, run)


def _summary_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SummaryValidationError):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=str(exc))


@router.patch("/intakes/{intake_id}/summary", response_model=IntakeResponse)
def update_client_intake_summary(
    intake_id: uuid.UUID,
    payload: UpdateSummaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> IntakeResponse:
    """Edit the intake summary while it is under review (SCRUM-342).

    ``null`` or ``""`` marks a field "not provided". 409 before the intake is
    complete or after approval; 422 for an unknown field or invalid value.
    """
    _owned_intake(db, intake_id, current_user)
    try:
        run = update_summary(db, intake_id, payload.fields, actor_id=current_user.id)
    except (SummaryConflictError, SummaryValidationError) as exc:
        raise _summary_http_error(exc) from exc
    db.commit()
    db.refresh(run)
    return _intake_response(db, run)


@router.post("/intakes/{intake_id}/approve", response_model=IntakeResponse)
def approve_client_intake_summary(
    intake_id: uuid.UUID,
    payload: ApproveSummaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> IntakeResponse:
    """Approve the summary exactly as stored; nothing reaches a lawyer before this.

    409 if not under review, already approved, a required field is missing, or
    ``fields`` differs from the stored summary. Records consent and audit.
    """
    _owned_intake(db, intake_id, current_user)
    try:
        run = approve_summary(db, intake_id, payload.fields, actor_id=current_user.id)
    except (SummaryConflictError, SummaryValidationError) as exc:
        raise _summary_http_error(exc) from exc
    db.commit()
    db.refresh(run)
    return _intake_response(db, run)


@router.post(
    "/intakes/{intake_id}/send",
    response_model=SentRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_client_intake(
    intake_id: uuid.UUID,
    payload: SendRequestBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client),
) -> SentRequestResponse:
    """Send the approved summary to a verified lawyer (SCRUM-344).

    The server copies the approved snapshot; the browser never sends it. 409 if
    not approved, a request is still sent/accepted, or this lawyer already
    declined this intake; 404 for an unknown or unverified lawyer. After a
    decline or expiry a new request is created and the old one kept.
    """
    _owned_intake(db, intake_id, current_user)
    try:
        req = send_request(db, intake_id, payload.lawyer_id, actor_id=current_user.id)
    except LawyerUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except SendConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    db.commit()
    db.refresh(req)
    return SentRequestResponse.model_validate(req)
