"""Pydantic schemas for client portal endpoints."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from services.intake.agent import new_intake_state
from services.intake.fields import ALL_FIELDS
from services.requests.states import RequestStatus


class ClientRequestResponse(BaseModel):
    """Client representation of a service request."""

    id: uuid.UUID
    lawyer_id: uuid.UUID
    niche: str | None
    summary: dict[str, Any] | None
    status: RequestStatus
    client_confirmed_at: datetime | None
    created_at: datetime
    # SCRUM-344: which intake it was sent from, and the lawyer's answer.
    intake_id: uuid.UUID | None
    lawyer_name: str | None = None
    responded_at: datetime | None
    decline_reason: str | None

    model_config = ConfigDict(from_attributes=True)


# --- Send to a lawyer (SCRUM-344) --------------------------------------------


class LawyerSummaryResponse(BaseModel):
    """A verified lawyer the client can send a request to."""

    id: uuid.UUID  # lawyer_profiles.id
    full_name: str | None
    niches: list[str]
    city: str | None
    fee_min: int | None
    fee_max: int | None
    years_experience: int | None
    bio: str | None


class SendRequestBody(BaseModel):
    """Send the approved summary to a lawyer; the server supplies the summary."""

    lawyer_id: uuid.UUID


class SentRequestResponse(BaseModel):
    id: uuid.UUID
    lawyer_id: uuid.UUID
    status: RequestStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntakeRequestResponse(BaseModel):
    """A request sent from an intake, as shown on the intake."""

    id: uuid.UUID
    lawyer_id: uuid.UUID
    status: RequestStatus
    created_at: datetime
    responded_at: datetime | None
    decline_reason: str | None

    model_config = ConfigDict(from_attributes=True)


class ClientCaseResponse(BaseModel):
    """Client representation of an active or closed case."""

    id: uuid.UUID
    request_id: uuid.UUID
    status: str
    summary: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientConversationResponse(BaseModel):
    """Client representation of an intake or legal Q&A conversation."""

    id: uuid.UUID
    type: str
    case_id: uuid.UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Lawyer-request intake (SCRUM-331) ---------------------------------------

MAX_INTAKE_MESSAGES = 100
MAX_MESSAGE_CHARS = 20_000
MAX_CITATIONS_PER_MESSAGE = 30


class IntakeCitation(BaseModel):
    """A citation as shown in the chat (mirrors the frontend ``Citation``)."""

    id: str = Field(max_length=200)
    source_type: str | None = Field(default=None, max_length=200, alias="sourceType")
    source_name: str | None = Field(default=None, max_length=500, alias="sourceName")
    article_number: str | None = Field(
        default=None, max_length=100, alias="articleNumber"
    )
    title: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=MAX_MESSAGE_CHARS)
    url: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class IntakeChatMessage(BaseModel):
    """One chat message carried over into the intake."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_CHARS)
    citations: list[IntakeCitation] = Field(
        default_factory=list, max_length=MAX_CITATIONS_PER_MESSAGE
    )


class StartIntakeRequest(BaseModel):
    """Start a lawyer request from a chat.

    Send ``conversation_id`` for a chat the server saved, or ``messages`` for a
    chat that only exists in the browser (stored as ``client_submitted``).
    """

    conversation_id: uuid.UUID | None = None
    messages: list[IntakeChatMessage] | None = Field(
        default=None, min_length=1, max_length=MAX_INTAKE_MESSAGES
    )

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "StartIntakeRequest":
        if (self.conversation_id is None) == (self.messages is None):
            raise ValueError("Provide exactly one of conversation_id or messages")
        return self


class IntakeContextMessage(BaseModel):
    role: str
    content: str
    citations: list[dict[str, Any]]


class IntakeFieldValue(BaseModel):
    status: Literal["missing", "provided", "not_provided"]
    value: str | None


class IntakeTurn(BaseModel):
    role: Literal["agent", "client"]
    content: str
    field: str | None


class IntakeResponse(BaseModel):
    """An intake workflow as the client sees it."""

    id: uuid.UUID
    kind: str
    status: str
    phase: str | None
    conversation_id: uuid.UUID | None
    context_source: str | None
    context_messages: list[IntakeContextMessage]
    # Intake agent progress (SCRUM-248); empty until the intake is opened.
    fields: dict[str, IntakeFieldValue]
    turns: list[IntakeTurn]
    complete: bool
    # When the client approved the summary (SCRUM-342); None until then.
    approved_at: datetime | None
    created_at: datetime
    # SCRUM-344: the latest request sent from this intake, and older ones
    # (oldest first).
    request: IntakeRequestResponse | None
    previous_requests: list[IntakeRequestResponse]

    @classmethod
    def from_workflow(cls, wf: Any, requests: Sequence[Any] = ()) -> "IntakeResponse":
        """``requests``: this intake's requests, oldest first."""
        state = wf.state or {}
        context = state.get("context") or {}
        intake = state.get("intake") or new_intake_state()
        return cls(
            id=wf.id,
            kind=wf.kind,
            status=wf.status,
            phase=state.get("phase"),
            conversation_id=wf.conversation_id,
            context_source=context.get("source"),
            context_messages=[
                IntakeContextMessage(
                    role=m.get("role", ""),
                    content=m.get("content", ""),
                    citations=m.get("citations") or [],
                )
                for m in context.get("messages", [])
            ],
            fields={
                k: IntakeFieldValue(status=v["status"], value=v.get("value"))
                for k, v in intake["fields"].items()
            },
            turns=[
                IntakeTurn(role=t["role"], content=t["content"], field=t.get("field"))
                for t in intake["turns"]
            ],
            complete=bool(intake.get("complete")),
            approved_at=(state.get("summary") or {}).get("approved_at"),
            created_at=wf.created_at,
            request=(
                IntakeRequestResponse.model_validate(requests[-1]) if requests else None
            ),
            previous_requests=[
                IntakeRequestResponse.model_validate(r) for r in requests[:-1]
            ],
        )


class IntakeTurnRequest(BaseModel):
    """Answer the intake agent, or ``content: null`` to open the intake."""

    content: str | None = Field(default=None, min_length=1, max_length=4000)


# --- Summary review and approval (SCRUM-342) --------------------------------

# One value per field; null or "" means "not provided". Keys and values are
# checked by services.intake.summary (unknown field or invalid value -> 422).
SummaryFields = dict[str, str | None]
MAX_APPROVE_FIELDS = 100


class UpdateSummaryRequest(BaseModel):
    """Edit some summary fields while the intake is in SUMMARY_REVIEW."""

    fields: SummaryFields = Field(max_length=len(ALL_FIELDS))


class ApproveSummaryRequest(BaseModel):
    """Approve the summary exactly as the client saw it (``fields``)."""

    confirmed: Literal[True]
    # Only compared with the stored summary: extra keys are a mismatch (409),
    # so the cap here just bounds the payload.
    fields: SummaryFields = Field(max_length=MAX_APPROVE_FIELDS)
