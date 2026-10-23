"""Immutable approval classifications for server-defined AI action identifiers.

This catalog is policy metadata, not an execution authorizer. Future execution
integrations must check availability, resolve required approvals, and enforce
those approvals before invoking an action.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Iterable, Mapping


class ApprovalRequirement(StrEnum):
    """Whether policy resolves an additional human approval requirement."""

    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    UNRESOLVED = "unresolved"


class AuthorizedApprover(StrEnum):
    """Product roles documented as approval actors."""

    CLIENT = "client"
    LAWYER = "lawyer"


class InvalidActionIdentifierError(ValueError):
    """Raised when an action identifier is not a canonical lowercase name."""


class UnknownActionError(LookupError):
    """Raised instead of assigning a default policy to an unknown action."""


class UnresolvedApprovalPolicyError(RuntimeError):
    """Raised when product requirements do not resolve an action's policy."""


class ActionUnavailableError(RuntimeError):
    """Raised when the backend has no implemented operation for an action."""


_ACTION_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    """Server-owned approval metadata for one action identifier."""

    action_id: str
    approval_requirement: ApprovalRequirement
    authorized_approver: AuthorizedApprover | None
    execution_available: bool

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not _ACTION_IDENTIFIER.fullmatch(
            self.action_id
        ):
            raise InvalidActionIdentifierError(
                "action identifier must use lowercase snake_case"
            )
        if not isinstance(self.approval_requirement, ApprovalRequirement):
            raise TypeError("approval_requirement must be an ApprovalRequirement")
        if self.authorized_approver is not None and not isinstance(
            self.authorized_approver, AuthorizedApprover
        ):
            raise TypeError("authorized_approver must be a known approver role")
        if not isinstance(self.execution_available, bool):
            raise TypeError("execution_available must be a boolean")

        if self.approval_requirement is ApprovalRequirement.REQUIRED:
            if self.authorized_approver is None:
                raise ValueError(
                    "approval-required actions need an authorized approver"
                )
        elif self.authorized_approver is not None:
            raise ValueError(
                "actions without a resolved approval requirement "
                "cannot name an approver"
            )


@dataclass(frozen=True, slots=True, init=False)
class ApprovalPolicy:
    """Immutable catalog with explicit lookup and fail-closed helpers."""

    _actions: Mapping[str, ActionPolicy]

    def __init__(self, actions: Iterable[ActionPolicy]) -> None:
        definitions: dict[str, ActionPolicy] = {}
        for action in actions:
            if not isinstance(action, ActionPolicy):
                raise TypeError("approval policy entries must be ActionPolicy values")
            if action.action_id in definitions:
                raise ValueError(
                    f"conflicting approval policy for action: {action.action_id}"
                )
            definitions[action.action_id] = action
        object.__setattr__(self, "_actions", MappingProxyType(definitions))

    def get(self, action_id: str) -> ActionPolicy:
        """Return a known action policy; malformed and unknown IDs are errors."""
        if not isinstance(action_id, str) or not _ACTION_IDENTIFIER.fullmatch(
            action_id
        ):
            raise InvalidActionIdentifierError(
                "action identifier must use lowercase snake_case"
            )
        try:
            return self._actions[action_id]
        except KeyError:
            raise UnknownActionError(
                f"unknown action identifier: {action_id}"
            ) from None

    def requires_approval(self, action_id: str) -> bool:
        """Resolve the approval requirement or reject unresolved policies."""
        action = self.get(action_id)
        if action.approval_requirement is ApprovalRequirement.UNRESOLVED:
            raise UnresolvedApprovalPolicyError(
                f"approval policy is unresolved for action: {action_id}"
            )
        return action.approval_requirement is ApprovalRequirement.REQUIRED

    def require_implemented(self, action_id: str) -> ActionPolicy:
        """Reject unresolved or unavailable operations.

        This verifies that a backend operation exists; it does not authorize
        execution or confirm that a required human approval has occurred.
        """
        action = self.get(action_id)
        if action.approval_requirement is ApprovalRequirement.UNRESOLVED:
            raise UnresolvedApprovalPolicyError(
                f"approval policy is unresolved for action: {action_id}"
            )
        if not action.execution_available:
            raise ActionUnavailableError(
                f"action is not implemented for execution: {action_id}"
            )
        return action

    @property
    def action_ids(self) -> tuple[str, ...]:
        """Return the known action IDs in policy definition order."""
        return tuple(self._actions)


ACTION_POLICIES = (
    ActionPolicy(
        "schedule_meeting",
        ApprovalRequirement.NOT_REQUIRED,
        None,
        execution_available=False,
    ),
    ActionPolicy(
        "retrieve_legal_information",
        ApprovalRequirement.NOT_REQUIRED,
        None,
        execution_available=True,
    ),
    ActionPolicy(
        "conduct_legal_research",
        ApprovalRequirement.NOT_REQUIRED,
        None,
        execution_available=False,
    ),
    ActionPolicy(
        "prepare_intake_summary",
        ApprovalRequirement.NOT_REQUIRED,
        None,
        execution_available=False,
    ),
    ActionPolicy(
        "analyze_contract",
        ApprovalRequirement.NOT_REQUIRED,
        None,
        execution_available=False,
    ),
    ActionPolicy(
        "prepare_legal_draft",
        ApprovalRequirement.NOT_REQUIRED,
        None,
        execution_available=False,
    ),
    ActionPolicy(
        "prepare_case_prep_output",
        ApprovalRequirement.NOT_REQUIRED,
        None,
        execution_available=False,
    ),
    ActionPolicy(
        "recommend_lawyers",
        ApprovalRequirement.NOT_REQUIRED,
        None,
        execution_available=False,
    ),
    ActionPolicy(
        "modify_case_data",
        ApprovalRequirement.REQUIRED,
        AuthorizedApprover.LAWYER,
        execution_available=False,
    ),
    ActionPolicy(
        "delete_case_data",
        ApprovalRequirement.REQUIRED,
        AuthorizedApprover.LAWYER,
        execution_available=False,
    ),
    ActionPolicy(
        "send_consequential_correspondence",
        ApprovalRequirement.REQUIRED,
        AuthorizedApprover.LAWYER,
        execution_available=False,
    ),
    ActionPolicy(
        "export_legal_draft",
        ApprovalRequirement.REQUIRED,
        AuthorizedApprover.LAWYER,
        execution_available=False,
    ),
    ActionPolicy(
        "submit_important_legal_document",
        ApprovalRequirement.REQUIRED,
        AuthorizedApprover.LAWYER,
        execution_available=False,
    ),
    ActionPolicy(
        "deliver_client_summary",
        ApprovalRequirement.UNRESOLVED,
        None,
        execution_available=False,
    ),
    ActionPolicy(
        "approve_case_prep_output",
        ApprovalRequirement.UNRESOLVED,
        None,
        execution_available=False,
    ),
    ActionPolicy(
        "cancel_scheduled_meeting",
        ApprovalRequirement.UNRESOLVED,
        None,
        execution_available=False,
    ),
)

approval_policy = ApprovalPolicy(ACTION_POLICIES)
