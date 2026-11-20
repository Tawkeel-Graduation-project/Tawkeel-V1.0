"""Persist intake turns on the workflow run (SCRUM-334).

The intake lives at ``workflow.state["intake"]`` next to the chat snapshot in
``workflow.state["context"]``, so later steps (summary, approval) read one place.
The LLM call happens without holding a row lock; the result is written only if
no other turn was saved meanwhile (optimistic check), else ``IntakeConflictError``.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Workflow
from services.audit.actions import AuditAction
from services.audit.service import log_event
from services.intake.agent import TurnOutcome, new_intake_state, run_turn
from services.llm.provider import BaseLLMProvider
from services.workflows.intake import IntakePhase
from services.workflows.service import get_run
from services.workflows.states import WorkflowKind, WorkflowStatus


class IntakeTurnError(Exception):
    """The turn can't be taken in the intake's current state (HTTP 409)."""


class IntakeConflictError(IntakeTurnError):
    """Another turn was saved while this one was being processed."""


def intake_state(run: Workflow) -> dict[str, Any]:
    """The run's intake state, or a fresh one if intake hasn't opened yet."""
    return (run.state or {}).get("intake") or new_intake_state()


def _client_chat_messages(run: Workflow) -> list[str]:
    """The client's own messages from the carried-over chat (never the answers)."""
    context = (run.state or {}).get("context") or {}
    return [
        m.get("content", "")
        for m in context.get("messages", [])
        if m.get("role") == "user"
    ]


def _ensure_open(run: Workflow) -> None:
    state = run.state or {}
    if (
        run.kind != WorkflowKind.INTAKE.value
        or run.status != WorkflowStatus.RUNNING.value
        or state.get("phase") != IntakePhase.INTAKE.value
    ):
        raise IntakeTurnError("Intake is not in progress")
    if intake_state(run).get("complete"):
        raise IntakeTurnError("Intake is already complete")


async def take_turn(
    session: Session,
    provider: BaseLLMProvider,
    run_id: uuid.UUID,
    *,
    actor_id: uuid.UUID,
    client_message: str | None,
) -> tuple[Workflow, TurnOutcome]:
    """Open the intake (``client_message=None``) or answer the agent's question."""
    run = get_run(session, run_id)
    _ensure_open(run)
    current = intake_state(run)
    seen_turns = len(current["turns"])
    if client_message is None and seen_turns:
        raise IntakeTurnError("Intake has already started")
    if client_message is not None and not seen_turns:
        raise IntakeTurnError("Intake has not started yet")
    opening_context = _client_chat_messages(run)
    session.rollback()  # end the read transaction before the slow model call

    outcome = await run_turn(
        provider, current, client_message, opening_context=opening_context
    )

    run = get_run(session, run_id, lock=True)
    try:
        _ensure_open(run)
        if len(intake_state(run)["turns"]) != seen_turns:
            raise IntakeConflictError("Another answer was saved first; reload")
    except IntakeTurnError:
        session.rollback()
        raise

    run.state = {**(run.state or {}), "intake": outcome.state}
    log_event(
        session,
        actor_id=actor_id,
        action=AuditAction.AI_PROPOSAL_GENERATED,
        workflow_id=run.id,
        after={
            "kind": "intake_turn",
            "turn": outcome.state["agent_questions"],
            "source": outcome.source,
            "model_ok": outcome.model_ok,
            "target_field": outcome.target_field,
            "changed_fields": outcome.changed_fields,
            "overrides": outcome.overrides,
            "complete": outcome.complete,
        },
    )
    session.commit()
    session.refresh(run)
    return run, outcome
