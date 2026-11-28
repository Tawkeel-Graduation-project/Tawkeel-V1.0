"""Client review, edit and approval of the intake summary (SCRUM-342 / SCRUM-251).

The summary is the intake field set at ``workflow.state["intake"]["fields"]``.
Phases (``services.workflows.intake.IntakePhase``):

- SUMMARY_REVIEW: the client may edit any field.
- APPROVED: a frozen snapshot is stored at ``workflow.state["summary"]`` and the
  workflow is ``completed``. Only this snapshot may ever reach a lawyer; read it
  with ``get_approved_summary``.

Nothing here commits: the caller commits once, so the state change, consent
row and audit events land together or not at all.
"""

import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Consent, Workflow
from services.audit.actions import AuditAction
from services.audit.service import log_event
from services.intake.fields import (
    ALL_FIELDS,
    REQUIRED_FIELDS,
    SUMMARY_MAX_LENGTH,
    FieldStatus,
    IntakeField,
    Urgency,
)
from services.intake.niches import Niche
from services.intake.service import intake_state
from services.workflows.intake import IntakePhase, can_advance_phase
from services.workflows.service import apply_transition, get_run
from services.workflows.states import WorkflowStatus

SHARE_SUMMARY_CONSENT_TYPE = "share_summary"
# shortcut: placeholder version until the consent text is written and
# lawyer-reviewed (PRD C13); bump it whenever that text changes.
SHARE_SUMMARY_CONSENT_VERSION = "share-summary-v1"


class SummaryError(Exception):
    """Base class for summary review errors."""


class SummaryConflictError(SummaryError):
    """The summary can't be edited/approved in its current state (HTTP 409)."""


class SummaryValidationError(SummaryError):
    """An edited value is not acceptable (HTTP 422)."""


class SummaryNotApprovedError(SummaryError):
    """The intake has no approved summary; nothing may be sent to a lawyer."""


def _phase(run: Workflow) -> str | None:
    return (run.state or {}).get("phase")


def _normalize(field: str, raw: str | None) -> str | None:
    """The stored value for one edited field; None means "not provided"."""
    try:
        f = IntakeField(field)
    except ValueError:
        raise SummaryValidationError(f"Unknown summary field: {field}") from None
    value = (raw or "").strip()
    if not value:
        return None
    if len(value) > SUMMARY_MAX_LENGTH[f] or "\x00" in value:
        raise SummaryValidationError(f"Invalid value for {f.value}")
    if f is IntakeField.NICHE and value not in {n.value for n in Niche}:
        raise SummaryValidationError("niche must be a key from the niche list")
    if f is IntakeField.URGENCY and value not in {u.value for u in Urgency}:
        raise SummaryValidationError("urgency must be urgent, soon or normal")
    return value


def _field_entry(value: str | None) -> dict[str, Any]:
    status = FieldStatus.PROVIDED if value is not None else FieldStatus.NOT_PROVIDED
    return {"status": status.value, "value": value}


def summary_values(fields: dict[str, Any]) -> dict[str, str | None]:
    """One value per field, None when not provided (as the client sees it)."""
    return {
        f.value: (
            fields[f.value]["value"]
            if fields[f.value]["status"] == FieldStatus.PROVIDED.value
            else None
        )
        for f in ALL_FIELDS
    }


def update_summary(
    db: Session,
    run_id: uuid.UUID,
    edits: dict[str, str | None],
    *,
    actor_id: uuid.UUID,
) -> Workflow:
    """Save the client's edits; empty or None means "not provided".

    Raises:
        SummaryConflictError: not in SUMMARY_REVIEW (still in intake, or approved).
        SummaryValidationError: unknown field or invalid value. Nothing is saved.
    """
    run = get_run(db, run_id, lock=True)
    if _phase(run) != IntakePhase.SUMMARY_REVIEW:
        raise SummaryConflictError("The summary can only be edited during review")
    values = {field: _normalize(field, raw) for field, raw in edits.items()}

    intake = intake_state(run)
    fields = copy.deepcopy(intake["fields"])
    changed: list[str] = []
    for field, value in values.items():
        entry = _field_entry(value)
        if fields[field] != entry:
            fields[field] = entry
            changed.append(field)

    if changed:
        run.state = {**(run.state or {}), "intake": {**intake, "fields": fields}}
        # Field names only, never values: the client controls what is shared,
        # and text they removed must not survive in an audit timeline.
        log_event(
            db,
            actor_id=actor_id,
            action=AuditAction.SUMMARY_EDITED,
            workflow_id=run.id,
            after={"changed_fields": sorted(changed)},
        )
    return run


def approve_summary(
    db: Session,
    run_id: uuid.UUID,
    submitted: dict[str, str | None],
    *,
    actor_id: uuid.UUID,
) -> Workflow:
    """Approve exactly the stored summary and freeze it.

    ``submitted`` is what the client saw; a missing key counts as None. Records
    a ``share_summary`` consent, the approval audit event, and moves the
    workflow to ``completed`` with phase APPROVED.

    Raises:
        SummaryConflictError: not in review, already approved, a required field
            is still missing, or ``submitted`` differs from the stored summary
            (including unknown keys or values that could never be stored).
    """
    run = get_run(db, run_id, lock=True)
    phase = _phase(run)
    if phase == IntakePhase.APPROVED:
        raise SummaryConflictError("The summary is already approved")
    if not can_advance_phase(phase, IntakePhase.APPROVED):
        raise SummaryConflictError("The summary is not ready for approval")
    # Only compared, never stored, so anything that isn't the stored summary is
    # a mismatch (409), not a validation error.
    seen = {field: (raw or "").strip() or None for field, raw in submitted.items()}

    fields = intake_state(run)["fields"]
    missing = [
        f.value
        for f in REQUIRED_FIELDS
        if fields[f.value]["status"] == FieldStatus.MISSING.value
    ]
    if missing:
        raise SummaryConflictError(
            f"Required fields are still missing: {', '.join(missing)}"
        )
    stored = summary_values(fields)
    if set(seen) - set(stored) or any(
        seen.get(field) != value for field, value in stored.items()
    ):
        raise SummaryConflictError("The summary changed; review it again")

    approved_at = datetime.now(UTC)
    consent = Consent(
        user_id=actor_id,
        type=SHARE_SUMMARY_CONSENT_TYPE,
        document_version=SHARE_SUMMARY_CONSENT_VERSION,
        consented_at=approved_at.replace(tzinfo=None),  # column is naive UTC
    )
    db.add(consent)
    db.flush()

    snapshot = {
        "fields": copy.deepcopy(fields),
        "approved_at": approved_at.isoformat(),
        "approved_by": str(actor_id),
        "consent_id": str(consent.id),
    }
    apply_transition(
        db,
        run,
        WorkflowStatus.COMPLETED,
        state_patch={"phase": IntakePhase.APPROVED.value, "summary": snapshot},
        actor_id=actor_id,
    )
    digest = hashlib.sha256(
        json.dumps(stored, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    log_event(
        db,
        actor_id=actor_id,
        action=AuditAction.APPROVAL_APPROVED,
        workflow_id=run.id,
        after={
            "subject": "intake_summary",
            "approved_at": snapshot["approved_at"],
            "consent_id": snapshot["consent_id"],
            "summary_sha256": digest,
        },
    )
    return run


def get_approved_summary(workflow: Workflow) -> dict[str, Any]:
    """The frozen approved summary snapshot; the only thing a lawyer may receive.

    Returns a copy of ``{"fields", "approved_at", "approved_by", "consent_id"}``.

    Raises:
        SummaryNotApprovedError: the intake has not been approved.
    """
    state = workflow.state or {}
    summary = state.get("summary")
    if (
        state.get("phase") != IntakePhase.APPROVED
        or not isinstance(summary, dict)
        or not summary.get("approved_at")
    ):
        raise SummaryNotApprovedError("The summary has not been approved")
    return copy.deepcopy(summary)
