"""Tests for approval gates, ownership, data scoping, and tool allowlists.

Covers:
- SCRUM-343: Enforce no-send-without-approval; test bypass attempts
- SCRUM-367: Ownership check on saved research
- SCRUM-369: Verify agent reads only authorized data
- SCRUM-376: Approval gate and artifact versioning
- SCRUM-382: Restrict scheduling agent to calendar tools only
"""

from __future__ import annotations

import uuid

import pytest
from services.security import (
    SCHEDULING_ALLOWED_TOOLS,
    ApprovalGateError,
    AuthorizedDataScope,
    OwnershipViolationError,
    UnauthorizedToolError,
    VersionedArtifact,
    verify_saved_research_ownership,
)
from services.security.guards import ToolAllowlist

from app.approvals import approval_state_machine
from app.approvals.transitions import (
    ApprovalActor,
    ApprovalBindingMismatchError,
    ApprovalDecisionRequiredError,
    ApprovalState,
    UnauthorizedApproverError,
)

# --- SCRUM-343: Enforce no-send-without-approval & bypass attempts ------------


def test_scrum_343_no_send_without_approval_blocks_bypass_attempts() -> None:
    client_actor = ApprovalActor(user_id=uuid.uuid4(), role="client")
    lawyer_actor = ApprovalActor(user_id=uuid.uuid4(), role="lawyer")
    params = {"recipient": "court-clerk", "summary": "Filing summary"}

    req = approval_state_machine.request(
        action_id="send_consequential_correspondence",
        target_id="case-123",
        parameters=params,
    )
    assert req.state is ApprovalState.PENDING

    # Bypass 1: Execute while still PENDING
    with pytest.raises(ApprovalDecisionRequiredError):
        approval_state_machine.validate_approved_for(
            req,
            action_id="send_consequential_correspondence",
            target_id="case-123",
            parameters=params,
        )

    # Bypass 2: Wrong role (client tries to approve lawyer-only send action)
    with pytest.raises(UnauthorizedApproverError):
        approval_state_machine.decide(
            req,
            destination=ApprovalState.APPROVED,
            actor=client_actor,
        )

    # Bypass 3: Rejected request cannot execute
    rejected = approval_state_machine.decide(
        req,
        destination=ApprovalState.REJECTED,
        actor=lawyer_actor,
    )
    with pytest.raises(ApprovalDecisionRequiredError):
        approval_state_machine.validate_approved_for(
            rejected,
            action_id="send_consequential_correspondence",
            target_id="case-123",
            parameters=params,
        )

    # Bypass 4: Approved for different parameters cannot execute on tampered input
    approved = approval_state_machine.decide(
        req,
        destination=ApprovalState.APPROVED,
        actor=lawyer_actor,
    )
    with pytest.raises(ApprovalBindingMismatchError):
        approval_state_machine.validate_approved_for(
            approved,
            action_id="send_consequential_correspondence",
            target_id="case-123",
            parameters={"recipient": "attacker", "summary": "TAMPERED"},
        )

    # Valid execution succeeds
    approval_state_machine.validate_approved_for(
        approved,
        action_id="send_consequential_correspondence",
        target_id="case-123",
        parameters=params,
    )


# --- SCRUM-367: Ownership check on saved research -----------------------------


def test_scrum_367_saved_research_ownership_enforced() -> None:
    verify_saved_research_ownership("lawyer-1", "lawyer-1")

    with pytest.raises(OwnershipViolationError):
        verify_saved_research_ownership("lawyer-1", "lawyer-2")

    with pytest.raises(OwnershipViolationError):
        verify_saved_research_ownership(
            "lawyer-1", "lawyer-1", artifact_type="other_type"
        )


# --- SCRUM-369: Verify agent reads only authorized data -----------------------


def test_scrum_369_agent_reads_only_authorized_data() -> None:
    records = [
        {"id": "rec-1", "user_id": "user-A", "case_id": "case-1", "text": "A1"},
        {"id": "rec-2", "user_id": "user-B", "case_id": "case-2", "text": "B1"},
        {"id": "rec-3", "user_id": "user-B", "case_id": "case-shared", "text": "S1"},
    ]
    scope = AuthorizedDataScope(
        actor_id="user-A",
        actor_role="client",
        allowed_case_ids=frozenset({"case-shared"}),
    )
    visible = scope.filter_records(records)
    assert [r["id"] for r in visible] == ["rec-1", "rec-3"]
    assert all(r["id"] != "rec-2" for r in visible)

    empty_scope = AuthorizedDataScope(actor_id="", actor_role="client")
    assert empty_scope.filter_records(records) == []


# --- SCRUM-376: Approval gate and artifact versioning -------------------------


def test_scrum_376_artifact_versioning_and_approval_binding() -> None:
    v1 = VersionedArtifact.create("art-1", "Draft case prep v1")
    assert v1.version == 1
    with pytest.raises(ApprovalGateError):
        v1.require_approved()

    v1_approved = v1.approve("lawyer-1")
    v1_approved.require_approved()

    # Creating v2 resets approval; old approval cannot apply to new version
    v2 = VersionedArtifact.create(
        "art-1", "Modified case prep v2", previous=v1_approved
    )
    assert v2.version == 2
    assert v2.approved_by is None
    with pytest.raises(ApprovalGateError):
        v2.require_approved()

    # Mismatched expected hash is rejected even on approved artifact
    with pytest.raises(ApprovalGateError):
        v1_approved.require_approved(expected_hash="deadbeef")


# --- SCRUM-382: Restrict scheduling agent to calendar tools only --------------


def test_scrum_382_scheduling_agent_restricted_to_calendar_tools() -> None:
    guard = ToolAllowlist("scheduling", SCHEDULING_ALLOWED_TOOLS)

    result = guard.execute("list_available_slots", lambda: ["10:00", "11:00"])
    assert result == ["10:00", "11:00"]

    for forbidden in (
        "read_case_files",
        "send_to_lawyer",
        "delete_audit_log",
        "sql_execute",
        "update_lawyer_fee",
    ):
        with pytest.raises(UnauthorizedToolError):
            guard.execute(forbidden, lambda: "should_not_run")
