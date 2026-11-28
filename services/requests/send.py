"""Send an approved intake summary to a lawyer (SCRUM-344 / SCRUM-252).

A ``requests`` row is created only here. The summary is always the frozen
snapshot from ``get_approved_summary``; the browser never sends it. Nothing
here commits: the caller commits once, so the request, its consent row and its
audit event land together or not at all.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Consent, LawyerProfile, Request, User
from services.audit.actions import AuditAction
from services.audit.service import log_event
from services.intake.fields import FieldStatus, IntakeField
from services.intake.summary import (
    SHARE_SUMMARY_CONSENT_TYPE,
    SHARE_SUMMARY_CONSENT_VERSION,
    SummaryNotApprovedError,
    get_approved_summary,
)
from services.requests.states import RequestStatus
from services.workflows.service import get_run

ACTIVE_STATUSES = frozenset({RequestStatus.SENT, RequestStatus.ACCEPTED})
ACTIVE_INDEX = "uq_requests_active_intake"


class SendError(Exception):
    """Base class for send errors."""


class SendConflictError(SendError):
    """The intake can't be sent right now (HTTP 409)."""


class LawyerUnavailableError(SendError):
    """The lawyer doesn't exist or isn't verified (HTTP 404)."""


def list_verified_lawyers(db: Session) -> list[tuple[LawyerProfile, User]]:
    """Verified lawyers with their user rows, by name. Unverified are never listed."""
    stmt = (
        select(LawyerProfile, User)
        .join(User, LawyerProfile.user_id == User.id)
        .where(LawyerProfile.verified.is_(True))
        .order_by(User.full_name, LawyerProfile.id)
    )
    return [(profile, user) for profile, user in db.execute(stmt).all()]


def intake_requests(db: Session, intake_id: uuid.UUID) -> list[Request]:
    """Every request sent from this intake, oldest first (the last is the latest)."""
    stmt = (
        select(Request)
        .where(Request.intake_id == intake_id)
        .order_by(Request.created_at, Request.id)
    )
    return list(db.scalars(stmt).all())


def lawyer_names(
    db: Session, lawyer_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    """Lawyer profile id -> the lawyer's full name."""
    ids = set(lawyer_ids)
    if not ids:
        return {}
    stmt = (
        select(LawyerProfile.id, User.full_name)
        .join(User, LawyerProfile.user_id == User.id)
        .where(LawyerProfile.id.in_(ids))
    )
    return {profile_id: name for profile_id, name in db.execute(stmt).all()}


def send_request(
    db: Session,
    intake_id: uuid.UUID,
    lawyer_id: uuid.UUID,
    *,
    actor_id: uuid.UUID,
) -> Request:
    """Create a ``sent`` request carrying the approved summary snapshot.

    The intake row is locked first, so two concurrent sends for one intake run
    one after the other and the second sees the first; the partial unique index
    is the last line of defence.

    Raises:
        SendConflictError: summary not approved, the latest request is still
            sent/accepted, or this lawyer already declined this intake.
        LawyerUnavailableError: unknown or unverified lawyer.
    """
    run = get_run(db, intake_id, lock=True)
    try:
        snapshot = get_approved_summary(run)
    except SummaryNotApprovedError as exc:
        raise SendConflictError("The summary has not been approved") from exc

    lawyer = db.scalar(
        select(LawyerProfile).where(
            LawyerProfile.id == lawyer_id, LawyerProfile.verified.is_(True)
        )
    )
    if lawyer is None:
        raise LawyerUnavailableError("Lawyer not found")

    history = intake_requests(db, run.id)
    if history and history[-1].status in ACTIVE_STATUSES:
        raise SendConflictError("This intake already has an active request")
    if any(
        r.lawyer_id == lawyer.id and r.status == RequestStatus.DECLINED for r in history
    ):
        raise SendConflictError("This lawyer already declined this request")

    niche = snapshot["fields"].get(IntakeField.NICHE.value) or {}
    approved_at = datetime.fromisoformat(snapshot["approved_at"])
    request = Request(
        client_id=actor_id,
        lawyer_id=lawyer.id,
        conversation_id=run.conversation_id,
        intake_id=run.id,
        niche=(
            niche.get("value")
            if niche.get("status") == FieldStatus.PROVIDED.value
            else None
        ),
        summary=snapshot,
        status=RequestStatus.SENT.value,
        # The column is naive UTC, like the rest of the schema.
        client_confirmed_at=approved_at.astimezone(UTC).replace(tzinfo=None),
    )
    db.add(request)
    try:
        db.flush()
    except IntegrityError as exc:
        if ACTIVE_INDEX in str(exc.orig):
            raise SendConflictError(
                "This intake already has an active request"
            ) from exc
        raise

    consent = Consent(
        user_id=actor_id,
        request_id=request.id,
        type=SHARE_SUMMARY_CONSENT_TYPE,
        document_version=SHARE_SUMMARY_CONSENT_VERSION,
    )
    db.add(consent)
    db.flush()
    log_event(
        db,
        actor_id=actor_id,
        action=AuditAction.REQUEST_CREATED,
        request_id=request.id,
        workflow_id=run.id,
        after={
            "status": request.status,
            "lawyer_id": str(lawyer.id),
            "intake_id": str(run.id),
            "consent_id": str(consent.id),
        },
    )
    return request
