import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Workflow
from app.workflows.states import (
    InvalidTransitionError,
    WorkflowKind,
    WorkflowStatus,
    can_transition,
)

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = (
    WorkflowStatus.PENDING.value,
    WorkflowStatus.RUNNING.value,
    WorkflowStatus.AWAITING_APPROVAL.value,
)


class WorkflowNotFoundError(Exception):
    pass


def create_run(
    session: Session,
    kind: str,
    *,
    case_id: uuid.UUID | None = None,
    request_id: uuid.UUID | None = None,
    state: dict | None = None,
) -> Workflow:
    """Create a new workflow run in the 'pending' status."""
    kind = WorkflowKind(kind)  # raises ValueError for an unknown kind
    run = Workflow(
        kind=kind.value,
        status=WorkflowStatus.PENDING.value,
        case_id=case_id,
        request_id=request_id,
        state=state or {},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_run(session: Session, run_id: uuid.UUID, *, lock: bool = False) -> Workflow:
    stmt = select(Workflow).where(Workflow.id == run_id)
    if lock:
        # Locks the row so two processes can't change it at the same time.
        stmt = stmt.with_for_update()
    run = session.scalars(stmt).one_or_none()
    if run is None:
        raise WorkflowNotFoundError(f"Workflow run {run_id} not found")
    return run


def transition(
    session: Session,
    run_id: uuid.UUID,
    target: str,
    *,
    state_patch: dict | None = None,
    actor_id: uuid.UUID | None = None,
) -> Workflow:
    """Move a run to `target` if the rules allow it, and save it."""
    run = get_run(session, run_id, lock=True)
    current = run.status

    if not can_transition(run.kind, current, target):
        logger.warning(
            "Invalid workflow transition: run=%s kind=%s %s -> %s",
            run.id,
            run.kind,
            current,
            target,
        )
        if actor_id is not None:
            session.add(
                AuditEvent(
                    actor_id=actor_id,
                    case_id=run.case_id,
                    action="workflow.invalid_transition",
                    before={"run_id": str(run.id), "status": current},
                    after={"attempted_status": str(target)},
                )
            )
            session.commit()
        else:
            session.rollback()  # releases the row lock
        raise InvalidTransitionError(run.kind, current, str(target))

    state = dict(run.state or {})
    state.update(state_patch or {})
    state["history"] = [
        *state.get("history", []),
        {
            "from": current,
            "to": WorkflowStatus(target).value,
            "at": datetime.now(UTC).isoformat(),
        },
    ]

    run.status = WorkflowStatus(target).value
    run.state = state  # a new dict, so SQLAlchemy sees the JSONB change
    session.commit()
    session.refresh(run)
    return run


def resume(session: Session, run_id: uuid.UUID) -> Workflow:
    """Load a saved run so the agent can continue from its status and state."""
    return get_run(session, run_id)


def list_resumable(session: Session) -> list[Workflow]:
    """All unfinished runs, e.g. to pick up after a server restart."""
    stmt = select(Workflow).where(Workflow.status.in_(ACTIVE_STATUSES))
    return list(session.scalars(stmt))
