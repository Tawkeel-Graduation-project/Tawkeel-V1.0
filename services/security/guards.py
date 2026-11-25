"""Execution guards for tool invocation, data scoping, and artifact versioning."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


class SecurityGuardError(PermissionError):
    """Base error raised when an agent action violates a security boundary."""


class UnauthorizedToolError(SecurityGuardError):
    """Raised when an agent attempts to invoke a tool outside its allowlist."""


class OwnershipViolationError(SecurityGuardError):
    """Raised when an actor attempts to access a resource they do not own."""


class ApprovalGateError(SecurityGuardError):
    """Raised when an action or artifact lacks a valid, matching approval."""


SCHEDULING_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "list_available_slots",
        "book_appointment",
        "reschedule_appointment",
        "cancel_appointment",
    }
)

INTAKE_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "extract_intake_fields",
        "ask_clarifying_question",
    }
)


class ToolAllowlist:
    """Enforce a strict per-agent tool allowlist (SCRUM-382)."""

    def __init__(self, agent_name: str, allowed_tools: Iterable[str]) -> None:
        self.agent_name = agent_name
        self.allowed_tools = frozenset(allowed_tools)

    def check(self, tool_name: str) -> None:
        """Raise ``UnauthorizedToolError`` if ``tool_name`` is not permitted."""
        if tool_name not in self.allowed_tools:
            raise UnauthorizedToolError(
                f"Agent {self.agent_name!r} cannot invoke tool {tool_name!r}"
            )

    def execute(
        self, tool_name: str, handler: Callable[..., T], *args: Any, **kwargs: Any
    ) -> T:
        """Check ``tool_name`` against the allowlist before invoking ``handler``."""
        self.check(tool_name)
        return handler(*args, **kwargs)


def verify_resource_ownership(actor_id: str, owner_id: str) -> None:
    """Ensure ``actor_id`` matches ``owner_id``, else raise OwnershipViolationError."""
    if not actor_id or actor_id != owner_id:
        raise OwnershipViolationError("Actor does not own the requested resource")


def verify_saved_research_ownership(
    actor_id: str, artifact_owner_id: str, *, artifact_type: str = "saved_research"
) -> None:
    """Enforce ownership on saved research artifacts (SCRUM-367)."""
    if artifact_type != "saved_research":
        raise OwnershipViolationError("Unexpected artifact type for research check")
    verify_resource_ownership(actor_id, artifact_owner_id)


@dataclass(frozen=True)
class AuthorizedDataScope:
    """Actor-scoped data access filter for agent queries (SCRUM-369)."""

    actor_id: str
    actor_role: str
    allowed_case_ids: frozenset[str] = frozenset()

    def filter_records(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        owner_key: str = "user_id",
        case_key: str = "case_id",
    ) -> list[Mapping[str, Any]]:
        """Return only records owned by ``actor_id`` or in ``allowed_case_ids``."""
        if not self.actor_id:
            return []
        visible: list[Mapping[str, Any]] = []
        for rec in records:
            owner = str(rec.get(owner_key, ""))
            case_id = str(rec.get(case_key, "")) if rec.get(case_key) else ""
            if owner == self.actor_id or (case_id and case_id in self.allowed_case_ids):
                visible.append(rec)
        return visible


@dataclass(frozen=True)
class VersionedArtifact:
    """Immutable versioned artifact bound to an explicit approval hash (SCRUM-376)."""

    artifact_id: str
    version: int
    content: str
    content_hash: str
    approved_by: str | None = None

    @classmethod
    def create(
        cls,
        artifact_id: str,
        content: str,
        *,
        previous: VersionedArtifact | None = None,
    ) -> VersionedArtifact:
        if previous is not None and previous.artifact_id != artifact_id:
            raise ValueError("previous artifact_id mismatch")
        next_version = 1 if previous is None else previous.version + 1
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(
            artifact_id=artifact_id,
            version=next_version,
            content=content,
            content_hash=digest,
            approved_by=None,
        )

    def approve(self, actor_id: str) -> VersionedArtifact:
        if not actor_id:
            raise ApprovalGateError("Approval requires a valid actor_id")
        return VersionedArtifact(
            artifact_id=self.artifact_id,
            version=self.version,
            content=self.content,
            content_hash=self.content_hash,
            approved_by=actor_id,
        )

    def require_approved(self, expected_hash: str | None = None) -> None:
        """Raise ``ApprovalGateError`` if unapproved or content hash drifted."""
        if not self.approved_by:
            raise ApprovalGateError(
                f"Artifact {self.artifact_id} v{self.version} is not approved"
            )
        current_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if current_hash != self.content_hash or (
            expected_hash is not None and expected_hash != self.content_hash
        ):
            raise ApprovalGateError(
                f"Artifact {self.artifact_id} v{self.version} hash mismatch"
            )
