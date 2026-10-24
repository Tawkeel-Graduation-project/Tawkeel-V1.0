"""FastAPI router for tool operations with permission policy enforcement."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.db.models import User
from app.tools.policy import (
    OperationType,
    tool_permission_policy,
)

router = APIRouter()


class ToolPermissionCheckResponse(BaseModel):
    """Result of checking tool execution permission for an authenticated user."""

    tool_id: str
    operation_type: OperationType
    role: str
    permitted: bool


@router.post(
    "/{tool_id}/check-permission",
    response_model=ToolPermissionCheckResponse,
)
def check_tool_permission_endpoint(
    tool_id: str,
    current_user: User = Depends(get_current_user),
) -> ToolPermissionCheckResponse:
    """Enforce tool permission policy for the authenticated user's role.

    Raises:
        HTTPException(403): If the user's role cannot execute this tool.
        HTTPException(404): If the tool identifier is unknown.
    """
    tool_permission_policy.enforce_permission(current_user, tool_id)
    op_type = tool_permission_policy.get_operation_type(tool_id)
    return ToolPermissionCheckResponse(
        tool_id=tool_id,
        operation_type=op_type,
        role=current_user.role,
        permitted=True,
    )
