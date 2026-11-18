"""Canonical action vocabulary for the append-only audit trail.

Every audit event must use one of these action identifiers. Do not invent
ad-hoc action strings outside this module.
"""

from enum import StrEnum


class AuditAction(StrEnum):
    """Defined audit event types covering AI and human actions."""

    # AI-generated proposals (case prep, drafts, intake summaries)
    AI_PROPOSAL_GENERATED = "ai.proposal_generated"

    # AI tool invocations within agentic workflows
    AI_TOOL_CALL = "ai.tool_call"

    # Human approval lifecycle
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"

    # Request state transitions (C8, C9)
    REQUEST_CREATED = "request.created"
    REQUEST_ACCEPTED = "request.accepted"
    REQUEST_DECLINED = "request.declined"
    REQUEST_CANCELLED = "request.cancelled"
    REQUEST_EXPIRED = "request.expired"

    # Case lifecycle (L6)
    CASE_CREATED = "case.created"
    CASE_NOTES_UPDATED = "case.notes_updated"
    CASE_CLOSED = "case.closed"

    # Workflow lifecycle
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_TRANSITION = "workflow.transition"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_INVALID_TRANSITION = "workflow.invalid_transition"


# Actions that may be logged by the system actor (UUID zero)
SYSTEM_ACTIONS = frozenset(
    {
        AuditAction.REQUEST_EXPIRED,
    }
)

# All valid action values as a set for quick validation
VALID_ACTIONS = frozenset(action.value for action in AuditAction)
