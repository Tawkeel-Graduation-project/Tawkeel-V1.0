"""Pydantic schemas for lawyer portal endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class LawyerRequestResponse(BaseModel):
    """Lawyer representation of an incoming client request."""

    id: uuid.UUID
    client_id: uuid.UUID
    niche: str | None
    summary: dict[str, Any] | None
    status: str
    decline_reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
