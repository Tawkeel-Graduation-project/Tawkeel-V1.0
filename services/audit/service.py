"""Append-only audit event service.

This module provides the central ``log_event`` function used by all backend
components to record important actions. Events are immutable once written:
there is no update or delete API.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Case, LawyerProfile, Request
from services.audit.actions import VALID_ACTIONS

logger = logging.getLogger(__name__)


class InvalidAuditActionError(ValueError):
    """Raised when an action string is not in the defined vocabulary."""


def log_event(
    session: Session,
    *,
    actor_id: uuid.UUID,
    action: str,
    case_id: uuid.UUID | None = None,
    request_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    """Create an append-only audit event and flush it in the caller's transaction.

    Args:
        session: Active database session (the caller controls commit).
        actor_id: UUID of the user performing the action.
        action: One of the values from ``AuditAction``.
        case_id: Optional case UUID for case-scoped events.
        request_id: Optional request UUID for request-scoped events.
        workflow_id: Optional workflow UUID for workflow-scoped events.
        before: Optional JSON-serializable snapshot of state before the action.
        after: Optional JSON-serializable snapshot of state after the action.

    Returns:
        The flushed ``AuditEvent`` instance.

    Raises:
        InvalidAuditActionError: If the action string is not recognized.
    """
    if action not in VALID_ACTIONS:
        raise InvalidAuditActionError(
            f"Unknown audit action: {action!r}. "
            f"Use a value from services.audit.actions.AuditAction."
        )

    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        case_id=case_id,
        request_id=request_id,
        workflow_id=workflow_id,
        before=before,
        after=after,
    )
    session.add(event)
    session.flush()
    return event


def list_events_for_user(
    session: Session,
    user_id: uuid.UUID,
    user_role: str,
    *,
    case_id: uuid.UUID | None = None,
    request_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    """Return audit events the user is authorized to see.

    - **Lawyers** see events on cases they own and requests assigned to them.
    - **Clients** see events on requests they submitted.
    - **Admins** see all events.

    Results are ordered by ``created_at`` descending (most recent first).
    """
    stmt = select(AuditEvent)

    if user_role == "admin":
        # Admin sees everything; apply optional filters
        if case_id is not None:
            stmt = stmt.where(AuditEvent.case_id == case_id)
        if request_id is not None:
            stmt = stmt.where(AuditEvent.request_id == request_id)

    elif user_role == "lawyer":
        profile = session.scalar(
            select(LawyerProfile).where(LawyerProfile.user_id == user_id)
        )
        if profile is None:
            return []

        if case_id is not None:
            # Verify lawyer owns this case
            case_obj = session.scalar(select(Case).where(Case.id == case_id))
            if case_obj is None or case_obj.lawyer_id != profile.id:
                return []
            stmt = stmt.where(AuditEvent.case_id == case_id)
        elif request_id is not None:
            # Verify lawyer is assigned to this request
            req = session.scalar(select(Request).where(Request.id == request_id))
            if req is None or req.lawyer_id != profile.id:
                return []
            stmt = stmt.where(AuditEvent.request_id == request_id)
        else:
            # All events on lawyer's cases or assigned requests
            lawyer_case_ids = select(Case.id).where(Case.lawyer_id == profile.id)
            lawyer_request_ids = select(Request.id).where(
                Request.lawyer_id == profile.id
            )
            stmt = stmt.where(
                (AuditEvent.case_id.in_(lawyer_case_ids))
                | (AuditEvent.request_id.in_(lawyer_request_ids))
                | (AuditEvent.actor_id == user_id)
            )

    elif user_role == "client":
        if request_id is not None:
            # Verify client owns this request
            req = session.scalar(select(Request).where(Request.id == request_id))
            if req is None or req.client_id != user_id:
                return []
            stmt = stmt.where(AuditEvent.request_id == request_id)
        else:
            # All events on client's requests
            client_request_ids = select(Request.id).where(Request.client_id == user_id)
            stmt = stmt.where(AuditEvent.request_id.in_(client_request_ids))

    else:
        return []

    stmt = stmt.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit)
    return list(session.scalars(stmt))
