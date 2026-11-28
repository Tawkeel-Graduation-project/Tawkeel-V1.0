"""Pydantic schemas for lawyer portal endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from services.requests.service import DECLINE_REASON_MAX_LENGTH
from services.requests.states import RequestStatus

from app.core.timestamps import UTCDateTime


class LawyerRequestResponse(BaseModel):
    """Lawyer representation of an incoming client request.

    Privacy (SCRUM-358): a lawyer sees only the approved summary snapshot
    (``summary``), never the intake transcript, chat messages, edit history or
    anything from before approval. Don't add conversation_id or similar here.
    """

    id: uuid.UUID
    client_id: uuid.UUID
    niche: str | None
    summary: dict[str, Any] | None
    status: RequestStatus
    decline_reason: str | None
    created_at: UTCDateTime
    # SCRUM-347
    intake_id: uuid.UUID | None
    responded_at: UTCDateTime | None

    model_config = ConfigDict(from_attributes=True)


class LawyerDecisionResponse(LawyerRequestResponse):
    """The request after the lawyer accepted or declined it (SCRUM-347)."""

    # shortcut: always null until SCRUM-359 creates a case on acceptance.
    case_id: uuid.UUID | None = None


class DeclineRequestBody(BaseModel):
    """Optional reason shown to the client; blank means no reason."""

    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def _clean_reason(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if len(value) > DECLINE_REASON_MAX_LENGTH:
            raise ValueError(
                f"reason must be at most {DECLINE_REASON_MAX_LENGTH} characters"
            )
        if "\x00" in value:
            raise ValueError("reason contains an invalid character")
        return value or None


class LawyerCaseResponse(BaseModel):
    """Lawyer representation of an assigned case."""

    id: uuid.UUID
    request_id: uuid.UUID
    lawyer_id: uuid.UUID
    status: str
    summary: dict[str, Any] | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LawyerConversationResponse(BaseModel):
    """Lawyer representation of a conversation linked to case work."""

    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    case_id: uuid.UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateCaseNotesRequest(BaseModel):
    """Payload for updating notes on a case."""

    notes: str
