"""Pydantic schemas for client portal endpoints."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClientRequestResponse(BaseModel):
    """Client representation of a service request."""

    id: uuid.UUID
    lawyer_id: uuid.UUID
    niche: str | None
    summary: dict[str, Any] | None
    status: str
    client_confirmed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateClientRequest(BaseModel):
    """Payload for submitting a new client request to a lawyer."""

    lawyer_id: uuid.UUID
    niche: str | None = None
    summary: dict[str, Any] | None = None


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


class IntakeResponse(BaseModel):
    """An intake workflow as the client sees it."""

    id: uuid.UUID
    kind: str
    status: str
    phase: str | None
    conversation_id: uuid.UUID | None
    context_source: str | None
    context_messages: list[IntakeContextMessage]
    created_at: datetime

    @classmethod
    def from_workflow(cls, wf: Any) -> "IntakeResponse":
        state = wf.state or {}
        context = state.get("context") or {}
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
            created_at=wf.created_at,
        )
