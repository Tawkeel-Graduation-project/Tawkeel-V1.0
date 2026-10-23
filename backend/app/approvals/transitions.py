"""In-memory approval decision transitions for server-defined actions.

This component records a decision for one action, target, and parameter set. It
does not persist the decision, authorize execution, or invoke an action.
"""

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.approvals.policy import (
    ApprovalPolicy,
    approval_policy,
)


class ApprovalState(StrEnum):
    """Decision state for one approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class InvalidApprovalTransitionError(ValueError):
    """Raised when a decision cannot transition from its current state."""


class ApprovalNotRequiredError(ValueError):
    """Raised when an action has no approval gate."""


class MissingApprovalActorError(ValueError):
    """Raised when an explicit decision has no authenticated actor context."""


class UnauthorizedApproverError(PermissionError):
    """Raised when the actor's role does not match the action policy."""


class ApprovalDecisionRequiredError(PermissionError):
    """Raised when there is no approved decision for the intended action."""


class ApprovalBindingMismatchError(PermissionError):
    """Raised when a decision is reused for different action input."""


@dataclass(frozen=True, slots=True)
class ApprovalActor:
    """Identity and role context adapted from the authenticated backend user."""

    user_id: uuid.UUID
    role: str

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, uuid.UUID):
            raise TypeError("approval actor user_id must be a UUID")
        if not isinstance(self.role, str):
            raise TypeError("approval actor role must be a string")


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Immutable state and binding for one approval decision."""

    action_id: str
    target_id: str
    parameters_sha256: str
    state: ApprovalState
    decided_by: uuid.UUID | None

    def __init__(
        self,
        action_id: str,
        target_id: str,
        parameters_sha256: str,
        state: ApprovalState,
        decided_by: uuid.UUID | None,
        *,
        _token: object,
    ) -> None:
        if _token is not _APPROVAL_STATE_TOKEN:
            raise TypeError("approval requests must be created by the state machine")
        object.__setattr__(self, "action_id", action_id)
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "parameters_sha256", parameters_sha256)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "decided_by", decided_by)


_APPROVAL_STATE_TOKEN = object()


def _new_approval_request(
    action_id: str,
    target_id: str,
    parameters_sha256: str,
    state: ApprovalState = ApprovalState.PENDING,
    decided_by: uuid.UUID | None = None,
) -> ApprovalRequest:
    return ApprovalRequest(
        action_id,
        target_id,
        parameters_sha256,
        state,
        decided_by,
        _token=_APPROVAL_STATE_TOKEN,
    )


def _parameters_digest(parameters: Mapping[str, Any]) -> str:
    if not isinstance(parameters, Mapping) or any(
        not isinstance(key, str) for key in parameters
    ):
        raise TypeError("action parameters must be a mapping with string keys")
    try:
        canonical_parameters = json.dumps(
            dict(parameters),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("action parameters must contain JSON-safe values") from exc
    return hashlib.sha256(canonical_parameters.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovalStateMachine:
    """Create requests and apply explicit decisions without executing actions."""

    policy: ApprovalPolicy = approval_policy

    def request(
        self,
        action_id: str,
        target_id: str,
        parameters: Mapping[str, Any],
    ) -> ApprovalRequest:
        """Start a pending approval for a known, approval-required action."""
        if not self.policy.requires_approval(action_id):
            raise ApprovalNotRequiredError(
                f"action does not require approval: {action_id}"
            )
        if not isinstance(target_id, str) or not target_id:
            raise ValueError("target_id must be a non-empty string")
        return _new_approval_request(
            action_id,
            target_id,
            _parameters_digest(parameters),
        )

    def decide(
        self,
        request: ApprovalRequest,
        destination: ApprovalState,
        actor: ApprovalActor | None,
    ) -> ApprovalRequest:
        """Apply an explicit authorized approve or reject decision."""
        if not isinstance(request, ApprovalRequest):
            raise TypeError("request must be an ApprovalRequest")
        if not isinstance(destination, ApprovalState) or destination not in (
            ApprovalState.APPROVED,
            ApprovalState.REJECTED,
        ):
            raise InvalidApprovalTransitionError(
                f"invalid approval destination: {destination}"
            )
        action = self.policy.get(request.action_id)
        if not self.policy.requires_approval(request.action_id):
            raise ApprovalNotRequiredError(
                f"action does not require approval: {request.action_id}"
            )
        if request.state is not ApprovalState.PENDING:
            raise InvalidApprovalTransitionError(
                f"cannot decide approval in state: {request.state}"
            )
        if actor is None:
            raise MissingApprovalActorError("approval decision requires an actor")
        if not isinstance(actor, ApprovalActor):
            raise TypeError("actor must be an ApprovalActor identity context")
        if actor.role != action.authorized_approver.value:
            raise UnauthorizedApproverError(
                f"role {actor.role!r} cannot approve action: {request.action_id}"
            )
        return _new_approval_request(
            request.action_id,
            request.target_id,
            request.parameters_sha256,
            state=destination,
            decided_by=actor.user_id,
        )

    def validate_approved_for(
        self,
        request: ApprovalRequest,
        action_id: str,
        target_id: str,
        parameters: Mapping[str, Any],
    ) -> ApprovalRequest:
        """Validate a decision's binding; this is not execution authorization."""
        if not self.policy.requires_approval(action_id):
            raise ApprovalNotRequiredError(
                f"action does not require approval: {action_id}"
            )
        if not isinstance(request, ApprovalRequest):
            raise TypeError("request must be an ApprovalRequest")
        if request.state is not ApprovalState.APPROVED or request.decided_by is None:
            raise ApprovalDecisionRequiredError(
                "an explicit authorized approval decision is required"
            )
        if (
            request.action_id != action_id
            or request.target_id != target_id
            or request.parameters_sha256 != _parameters_digest(parameters)
        ):
            raise ApprovalBindingMismatchError(
                "approval decision does not match the intended action and input"
            )
        return request


approval_state_machine = ApprovalStateMachine()
