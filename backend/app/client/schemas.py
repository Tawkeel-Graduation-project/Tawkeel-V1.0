"""Pydantic schemas for client portal endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


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
