"""Unit tests for intake summary review and approval (SCRUM-342)."""

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from services.audit.actions import AuditAction
from services.intake import service as intake_svc
from services.intake import summary as svc
from services.intake.agent import TurnOutcome, new_intake_state
from services.intake.fields import ALL_FIELDS, SUMMARY_MAX_LENGTH
from services.intake.summary import (
    SummaryConflictError,
    SummaryNotApprovedError,
    SummaryValidationError,
    approve_summary,
    get_approved_summary,
    update_summary,
)
from services.llm.providers.mock import MockLLMProvider
from services.workflows.intake import PHASE_TRANSITIONS, IntakePhase, can_advance_phase
from services.workflows.service import apply_transition
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Consent

VALUES = {
    "facts": "فصلني صاحب العمل بدون إخطار",
    "niche": "labor",
    "parties": "صاحب العمل",
    "key_dates": "يناير 2026",
    "urgency": "soon",
    "city": "طنطا",
    "budget": "حوالي 3000 جنيه",
    "documents": None,
    "deadlines": None,
    "preferred_times": "بعد الخامسة",
}


def complete_intake() -> dict:
    intake = new_intake_state()
    for f, v in VALUES.items():
        intake["fields"][f] = (
            {"status": "provided", "value": v}
            if v
            else {"status": "not_provided", "value": None}
        )
    intake["complete"] = True
    return intake


def run(phase: str = "SUMMARY_REVIEW", status: str = "awaiting_approval", **intake):
    data = complete_intake()
    data.update(intake)
    return SimpleNamespace(
        id=uuid.uuid4(),
        kind="intake",
        status=status,
        case_id=None,
        conversation_id=uuid.uuid4(),
        state={"phase": phase, "context": {"messages": []}, "intake": data},
        created_at=datetime.now(UTC),
    )


def added(db: Mock, kind: type) -> list:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], kind)]


@pytest.fixture
def db() -> Mock:
    return Mock(spec=Session)


# --- phase table -------------------------------------------------------------


def test_phase_order_is_intake_review_approved() -> None:
    assert PHASE_TRANSITIONS == {
        IntakePhase.INTAKE: {IntakePhase.SUMMARY_REVIEW},
        IntakePhase.SUMMARY_REVIEW: {IntakePhase.APPROVED},
        IntakePhase.APPROVED: set(),
    }
    assert can_advance_phase("SUMMARY_REVIEW", "APPROVED")
    assert not can_advance_phase("INTAKE", "APPROVED")
    assert not can_advance_phase("APPROVED", "APPROVED")
    assert not can_advance_phase(None, "SUMMARY_REVIEW")


def test_summary_limits_match_the_frontend_spec() -> None:
    assert {f.value: n for f, n in SUMMARY_MAX_LENGTH.items()} == {
        "facts": 4000,
        "parties": 1000,
        "key_dates": 1000,
        "documents": 1000,
        "deadlines": 1000,
        "preferred_times": 500,
        "city": 200,
        "budget": 200,
        "niche": 64,
        "urgency": 64,
    }
    assert set(SUMMARY_MAX_LENGTH) == set(ALL_FIELDS)


def test_apply_transition_does_not_commit(db: Mock) -> None:
    r = run(phase="INTAKE", status="running")
    apply_transition(db, r, "awaiting_approval", actor_id=uuid.uuid4())
    assert r.status == "awaiting_approval"
    db.commit.assert_not_called()


# --- completion -> SUMMARY_REVIEW ------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("complete", [True, False])
async def test_completion_opens_summary_review(db: Mock, complete: bool) -> None:
    before = new_intake_state()
    before["turns"] = [{"role": "agent", "content": "سؤال", "field": "facts"}]
    r = run(phase="INTAKE", status="running", **before)
    r.state["intake"]["complete"] = False
    after = complete_intake() if complete else before
    outcome = TurnOutcome(
        state=after,
        agent_message="...",
        target_field=None,
        complete=complete,
        source="closing",
        model_ok=True,
        changed_fields=[],
        overrides=[],
    )
    with (
        patch.object(intake_svc, "get_run", side_effect=[r, r]),
        patch.object(intake_svc, "run_turn", return_value=outcome),
    ):
        saved, _ = await intake_svc.take_turn(
            db, MockLLMProvider(), r.id, actor_id=uuid.uuid4(), client_message="x"
        )

    db.commit.assert_called_once()  # final turn + phase change in one commit
    if complete:
        assert saved.state["phase"] == "SUMMARY_REVIEW"
        assert saved.status == "awaiting_approval"
        assert saved.state["intake"]["complete"] is True
    else:
        assert saved.state["phase"] == "INTAKE"
        assert saved.status == "running"


# --- update_summary -------------------------------------------------------------


def test_edit_saves_changes_and_audits_field_names_only(db: Mock) -> None:
    r = run()
    actor = uuid.uuid4()
    with patch.object(svc, "get_run", return_value=r) as get_run:
        update_summary(
            db,
            r.id,
            {"city": "  القاهرة ", "budget": "", "documents": "عقد العمل"},
            actor_id=actor,
        )

    get_run.assert_called_once_with(db, r.id, lock=True)
    fields = r.state["intake"]["fields"]
    assert fields["city"] == {"status": "provided", "value": "القاهرة"}
    assert fields["budget"] == {"status": "not_provided", "value": None}
    assert fields["documents"] == {"status": "provided", "value": "عقد العمل"}
    db.commit.assert_not_called()
    (event,) = added(db, AuditEvent)
    assert event.action == AuditAction.SUMMARY_EDITED
    assert event.actor_id == actor
    assert event.workflow_id == r.id
    assert event.before is None
    assert event.after == {"changed_fields": ["budget", "city", "documents"]}
    # No value survives in the audit log: not the old text, not the new one.
    stored = json.dumps([event.before, event.after], ensure_ascii=False)
    for text in ("طنطا", "القاهرة", "حوالي 3000 جنيه", "عقد العمل"):
        assert text not in stored


def test_edit_with_no_change_writes_nothing(db: Mock) -> None:
    r = run()
    with patch.object(svc, "get_run", return_value=r):
        update_summary(db, r.id, {"city": "طنطا"}, actor_id=uuid.uuid4())
    db.add.assert_not_called()


@pytest.mark.parametrize("phase", ["INTAKE", "APPROVED", None])
def test_edit_blocked_outside_review(db: Mock, phase) -> None:
    r = run(phase=phase)
    with patch.object(svc, "get_run", return_value=r):
        with pytest.raises(SummaryConflictError):
            update_summary(db, r.id, {"city": "القاهرة"}, actor_id=uuid.uuid4())
    db.add.assert_not_called()


@pytest.mark.parametrize(
    "edits",
    [
        {"unknown": "x"},
        {"niche": "family"},
        {"niche": "عمل وعمال"},  # labels are display text; keys only
        {"urgency": "asap"},
        {"facts": "x" * 4001},
        {"city": "x" * 201},
        {"parties": "a\x00b"},
        {"city": "القاهرة", "bogus": "x"},  # one bad key rejects the whole edit
    ],
)
def test_edit_validation_errors_change_nothing(db: Mock, edits) -> None:
    r = run()
    before = r.state["intake"]["fields"].copy()
    with patch.object(svc, "get_run", return_value=r):
        with pytest.raises(SummaryValidationError):
            update_summary(db, r.id, edits, actor_id=uuid.uuid4())
    assert r.state["intake"]["fields"] == before
    db.add.assert_not_called()


def test_edit_accepts_every_limit_exactly(db: Mock) -> None:
    r = run()
    edits = {f.value: "ن" * n for f, n in SUMMARY_MAX_LENGTH.items()}
    edits.update(niche="unsure", urgency="urgent")
    with patch.object(svc, "get_run", return_value=r):
        update_summary(db, r.id, edits, actor_id=uuid.uuid4())
    assert r.state["intake"]["fields"]["niche"]["value"] == "unsure"


# --- approve_summary -------------------------------------------------------------


def test_approve_freezes_snapshot_records_consent_and_audit(db: Mock) -> None:
    r = run()
    actor = uuid.uuid4()
    with patch.object(svc, "get_run", return_value=r):
        approve_summary(db, r.id, dict(VALUES), actor_id=actor)

    assert r.state["phase"] == "APPROVED"
    assert r.status == "completed"
    db.commit.assert_not_called()
    (consent,) = added(db, Consent)
    assert consent.type == "share_summary"
    assert consent.user_id == actor
    assert consent.document_version == svc.SHARE_SUMMARY_CONSENT_VERSION
    snapshot = r.state["summary"]
    assert snapshot["fields"] == r.state["intake"]["fields"]
    assert snapshot["approved_by"] == str(actor)
    actions = [e.action for e in added(db, AuditEvent)]
    assert actions == [AuditAction.WORKFLOW_TRANSITION, AuditAction.APPROVAL_APPROVED]
    approval = added(db, AuditEvent)[-1]
    assert approval.after["approved_at"] == snapshot["approved_at"]
    assert len(approval.after["summary_sha256"]) == 64
    assert "طنطا" not in str(approval.after)  # the hash, not the client's words


def test_approve_treats_missing_keys_and_blanks_as_not_provided(db: Mock) -> None:
    r = run()
    submitted = {k: v for k, v in VALUES.items() if v is not None}
    submitted["documents"] = "  "
    with patch.object(svc, "get_run", return_value=r):
        approve_summary(db, r.id, submitted, actor_id=uuid.uuid4())
    assert r.state["phase"] == "APPROVED"


@pytest.mark.parametrize(
    ("phase", "message"),
    [("APPROVED", "already approved"), ("INTAKE", "not ready")],
)
def test_approve_wrong_phase_conflicts(db: Mock, phase: str, message: str) -> None:
    r = run(phase=phase)
    with patch.object(svc, "get_run", return_value=r):
        with pytest.raises(SummaryConflictError, match=message):
            approve_summary(db, r.id, dict(VALUES), actor_id=uuid.uuid4())
    db.add.assert_not_called()


def test_approve_with_missing_required_field_conflicts(db: Mock) -> None:
    r = run()
    r.state["intake"]["fields"]["budget"] = {"status": "missing", "value": None}
    with patch.object(svc, "get_run", return_value=r):
        with pytest.raises(SummaryConflictError, match="budget"):
            approve_summary(db, r.id, {**VALUES, "budget": None}, actor_id=uuid.uuid4())
    db.add.assert_not_called()


@pytest.mark.parametrize(
    "change", [{"city": "القاهرة"}, {"facts": None}, {"documents": "عقد"}]
)
def test_approve_rejects_a_different_summary(db: Mock, change: dict) -> None:
    r = run()
    with patch.object(svc, "get_run", return_value=r):
        with pytest.raises(SummaryConflictError, match="changed"):
            approve_summary(db, r.id, {**VALUES, **change}, actor_id=uuid.uuid4())
    assert r.state["phase"] == "SUMMARY_REVIEW"
    db.add.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [{"x": "y"}, {"x": None}, {"niche": "family"}, {"facts": "x" * 5000}],
    ids=["unknown-key", "unknown-null-key", "bad-niche", "too-long"],
)
def test_approve_anything_but_the_stored_summary_is_a_conflict(
    db: Mock, change: dict
) -> None:
    """Spec: approve answers 409 whenever ``fields`` != the stored summary."""
    r = run()
    with patch.object(svc, "get_run", return_value=r):
        with pytest.raises(SummaryConflictError, match="changed"):
            approve_summary(db, r.id, {**VALUES, **change}, actor_id=uuid.uuid4())
    db.add.assert_not_called()


# --- guard -------------------------------------------------------------------------


@pytest.mark.parametrize("phase", ["INTAKE", "SUMMARY_REVIEW", None])
def test_guard_raises_before_approval(phase) -> None:
    with pytest.raises(SummaryNotApprovedError):
        get_approved_summary(run(phase=phase))


def test_guard_raises_when_snapshot_is_missing() -> None:
    with pytest.raises(SummaryNotApprovedError):
        get_approved_summary(run(phase="APPROVED"))


def test_guard_returns_a_copy_of_the_approved_snapshot(db: Mock) -> None:
    r = run()
    with patch.object(svc, "get_run", return_value=r):
        approve_summary(db, r.id, dict(VALUES), actor_id=uuid.uuid4())

    snapshot = get_approved_summary(r)
    assert snapshot == r.state["summary"]
    snapshot["fields"]["city"]["value"] = "تلاعب"
    assert r.state["summary"]["fields"]["city"]["value"] == "طنطا"
