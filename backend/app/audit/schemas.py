"""Pydantic schemas for audit trail API responses."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.timestamps import UTCDateTime


class AuditEventResponse(BaseModel):
    """Public representation of an audit event."""

    id: uuid.UUID
    actor_id: uuid.UUID
    action: str
    case_id: uuid.UUID | None
    request_id: uuid.UUID | None
    workflow_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True)


class AuditEventListResponse(BaseModel):
    """Paginated list of audit events."""

    events: list[AuditEventResponse]
    count: int
