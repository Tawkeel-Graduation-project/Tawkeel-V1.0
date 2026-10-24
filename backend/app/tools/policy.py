"""Tool permission policy defining read, write, and delete operation boundaries."""

from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from fastapi import HTTPException, status

from app.db.models import User


class OperationType(StrEnum):
    """Classification of tool operations into read, write, and delete actions."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"


class ToolPermissionDeniedError(PermissionError):
    """Raised when an actor's role lacks permission for a tool operation."""


class UnknownToolOperationError(LookupError):
    """Raised when an operation/tool is unknown to the permission policy."""


# Server-owned permission policy: mapping tool IDs to (OperationType, allowed_roles)
DEFAULT_TOOL_PERMISSIONS: Mapping[str, tuple[OperationType, tuple[str, ...]]] = (
    MappingProxyType(
        {
            # READ operations - retrieving or inspecting data
            "retrieve_legal_information": (
                OperationType.READ,
                ("client", "lawyer", "admin"),
            ),
            "conduct_legal_research": (
                OperationType.READ,
                ("lawyer", "admin"),
            ),
            "analyze_contract": (
                OperationType.READ,
                ("client", "lawyer", "admin"),
            ),
            "recommend_lawyers": (
                OperationType.READ,
                ("client", "admin"),
            ),
            "export_legal_draft": (
                OperationType.READ,
                ("lawyer", "admin"),
            ),
            # WRITE operations - state modifications, draft creation, correspondence
            "schedule_meeting": (
                OperationType.WRITE,
                ("client", "lawyer", "admin"),
            ),
            "prepare_intake_summary": (
                OperationType.WRITE,
                ("client", "admin"),
            ),
            "prepare_legal_draft": (
                OperationType.WRITE,
                ("lawyer", "admin"),
            ),
            "prepare_case_prep_output": (
                OperationType.WRITE,
                ("lawyer", "admin"),
            ),
            "modify_case_data": (
                OperationType.WRITE,
                ("lawyer", "admin"),
            ),
            "send_consequential_correspondence": (
                OperationType.WRITE,
                ("lawyer", "admin"),
            ),
            "submit_important_legal_document": (
                OperationType.WRITE,
                ("lawyer", "admin"),
            ),
            # DELETE operations - destructive actions
            "delete_case_data": (
                OperationType.DELETE,
                ("lawyer", "admin"),
            ),
        }
    )
)


class ToolPermissionPolicy:
    """Immutable tool permission policy enforcing read vs write vs delete boundaries."""

    def __init__(
        self,
        permissions: Mapping[str, tuple[OperationType, tuple[str, ...]]] | None = None,
    ) -> None:
        if permissions is None:
            self._permissions = DEFAULT_TOOL_PERMISSIONS
        else:
            self._permissions = MappingProxyType(dict(permissions))

    def get_operation_type(self, tool_id: str) -> OperationType:
        """Return the OperationType (read, write, delete) for a tool identifier."""
        if tool_id not in self._permissions:
            raise UnknownToolOperationError(
                f"Unknown tool operation identifier: '{tool_id}'"
            )
        return self._permissions[tool_id][0]

    def get_allowed_roles(self, tool_id: str) -> tuple[str, ...]:
        """Return the tuple of authorized roles for this tool."""
        if tool_id not in self._permissions:
            raise UnknownToolOperationError(
                f"Unknown tool operation identifier: '{tool_id}'"
            )
        return self._permissions[tool_id][1]

    def check_permission(self, tool_id: str, role: str) -> bool:
        """Verify role has permission for tool; raises error if unauthorized."""
        allowed_roles = self.get_allowed_roles(tool_id)
        if role not in allowed_roles:
            op = self.get_operation_type(tool_id)
            raise ToolPermissionDeniedError(
                f"Role '{role}' is not authorized to execute "
                f"{op.value} tool '{tool_id}'"
            )
        return True

    def enforce_permission(self, user: User, tool_id: str) -> None:
        """Verify user permission for tool; raises HTTPException(403) if not allowed."""
        try:
            self.check_permission(tool_id, user.role)
        except UnknownToolOperationError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool '{tool_id}' not found",
            ) from None
        except ToolPermissionDeniedError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc


tool_permission_policy = ToolPermissionPolicy()
