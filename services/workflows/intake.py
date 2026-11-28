"""Start the client intake workflow from a legal Q&A chat (SCRUM-247 / SCRUM-331).

When a client taps "Request a Lawyer" after getting an answer, we:

1. resolve the chat it came from (a saved conversation, or the transcript the
   browser sends while chat is not yet persisted server-side),
2. snapshot that chat into the workflow state, so the intake agent works from
   exactly what the client saw, even if the chat continues afterwards,
3. create an ``intake`` workflow run and move it to ``running`` with
   ``state["phase"] == "INTAKE"``.

Workflow *status* stays the shared state machine (pending/running/...). The
lawyer-request journey is tracked separately in ``state["phase"]`` so later
stories (summary review, approval) can add phases without touching the
transition table owned by the workflows module.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message, Workflow
from services.audit.actions import AuditAction
from services.audit.service import log_event
from services.workflows.service import ACTIVE_STATUSES, create_run, transition
from services.workflows.states import WorkflowKind, WorkflowStatus


class IntakePhase(StrEnum):
    """Steps of the lawyer-request journey, stored in ``workflow.state["phase"]``.

    INTAKE: the agent collects fields. SUMMARY_REVIEW: intake is complete and
    the client may edit the summary. APPROVED: the client approved it; the
    summary is frozen and may be sent to a lawyer (SCRUM-342 / SCRUM-251).
    """

    INTAKE = "INTAKE"
    SUMMARY_REVIEW = "SUMMARY_REVIEW"
    APPROVED = "APPROVED"


# current phase -> phases it may move to. Anything not listed is forbidden.
PHASE_TRANSITIONS: dict[IntakePhase, frozenset[IntakePhase]] = {
    IntakePhase.INTAKE: frozenset({IntakePhase.SUMMARY_REVIEW}),
    IntakePhase.SUMMARY_REVIEW: frozenset({IntakePhase.APPROVED}),
    IntakePhase.APPROVED: frozenset(),
}


def can_advance_phase(current: str | None, target: str) -> bool:
    """True if an intake in phase `current` may move to phase `target`."""
    try:
        return IntakePhase(target) in PHASE_TRANSITIONS[IntakePhase(current)]
    except ValueError:
        return False


class ContextSource(StrEnum):
    """Where the carried-over chat came from.

    ``server``: read from messages the backend saved itself (trusted).
    ``client_submitted``: sent by the browser; shown to lawyers as unverified.
    """

    SERVER = "server"
    CLIENT_SUBMITTED = "client_submitted"


class IntakeContextError(ValueError):
    """The chat cannot start an intake (e.g. no answer has been given yet)."""


@dataclass(frozen=True)
class SubmittedMessage:
    """One chat message as sent by the browser."""

    role: str  # "user" | "assistant"
    content: str
    citations: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class StartIntakeResult:
    workflow: Workflow
    created: bool  # False when an active intake already existed for the chat


def _has_answer(messages: list[dict[str, Any]]) -> bool:
    return any(m["role"] == "assistant" and m["content"].strip() for m in messages)


def _snapshot_from_db(session: Session, conversation: Conversation) -> list[dict]:
    rows = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at, Message.id)
    ).all()
    return [
        {
            "role": row.sender,
            "content": row.content,
            "citations": row.citations or [],
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def find_active_intake(session: Session, conversation_id: uuid.UUID) -> Workflow | None:
    """Return the newest unfinished intake run for this conversation, if any."""
    return session.scalars(
        select(Workflow)
        .where(
            Workflow.conversation_id == conversation_id,
            Workflow.kind == WorkflowKind.INTAKE.value,
            Workflow.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Workflow.created_at.desc())
        .limit(1)
    ).first()


def start_intake(
    session: Session,
    *,
    client_id: uuid.UUID,
    conversation: Conversation | None = None,
    submitted_messages: list[SubmittedMessage] | None = None,
) -> StartIntakeResult:
    """Start (or return the already-active) intake workflow for a client's chat.

    Exactly one of ``conversation`` (already ownership-checked by the caller)
    or ``submitted_messages`` must be given.

    Raises:
        ValueError: both or neither source given.
        IntakeContextError: the chat has no assistant answer yet.
    """
    if (conversation is None) == (submitted_messages is None):
        raise ValueError("Provide exactly one of conversation or submitted_messages")

    if conversation is not None:
        existing = find_active_intake(session, conversation.id)
        if existing is not None:
            return StartIntakeResult(workflow=existing, created=False)
        messages = _snapshot_from_db(session, conversation)
        source = ContextSource.SERVER
    else:
        messages = [
            {"role": m.role, "content": m.content, "citations": m.citations or []}
            for m in submitted_messages or []
        ]
        source = ContextSource.CLIENT_SUBMITTED

    if not _has_answer(messages):
        raise IntakeContextError(
            "A lawyer request can only start after the assistant has answered."
        )

    if conversation is None:
        # Persist the browser transcript so the workflow links to a real chat.
        conversation = Conversation(user_id=client_id, type="qa")
        session.add(conversation)
        session.flush()
        for m in messages:
            session.add(
                Message(
                    conversation_id=conversation.id,
                    sender=m["role"],
                    content=m["content"],
                    citations=m["citations"],
                )
            )
        session.flush()

    context = {
        "source": source.value,
        "conversation_id": str(conversation.id),
        "captured_at": datetime.now(UTC).isoformat(),
        "messages": messages,
    }
    run = create_run(
        session,
        WorkflowKind.INTAKE,
        conversation_id=conversation.id,
        state={"context": context},
    )
    log_event(
        session,
        actor_id=client_id,
        action=AuditAction.WORKFLOW_STARTED,
        workflow_id=run.id,
        after={
            "kind": WorkflowKind.INTAKE.value,
            "conversation_id": str(conversation.id),
            "context_source": source.value,
            "message_count": len(messages),
        },
    )
    run = transition(
        session,
        run.id,
        WorkflowStatus.RUNNING,
        state_patch={"phase": IntakePhase.INTAKE.value},
        actor_id=client_id,
    )
    return StartIntakeResult(workflow=run, created=True)
