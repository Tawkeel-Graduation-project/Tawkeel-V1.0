"""Unit and route tests for tool permission policy (read vs write vs delete)."""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.db.models import User
from app.main import app
from app.tools.policy import (
    OperationType,
    ToolPermissionDeniedError,
    ToolPermissionPolicy,
    UnknownToolOperationError,
    tool_permission_policy,
)
from app.tools.registry import ToolRegistry


class DummyInput(BaseModel):
    query: str


def test_operation_types_are_read_write_delete() -> None:
    assert OperationType.READ == "read"
    assert OperationType.WRITE == "write"
    assert OperationType.DELETE == "delete"


def test_default_tool_permissions_categorization() -> None:
    assert (
        tool_permission_policy.get_operation_type("retrieve_legal_information")
        is OperationType.READ
    )
    assert (
        tool_permission_policy.get_operation_type("modify_case_data")
        is OperationType.WRITE
    )
    assert (
        tool_permission_policy.get_operation_type("delete_case_data")
        is OperationType.DELETE
    )


def test_client_permitted_on_read_tools() -> None:
    assert tool_permission_policy.check_permission(
        "retrieve_legal_information", "client"
    )
    assert tool_permission_policy.check_permission("analyze_contract", "client")
    assert tool_permission_policy.check_permission("recommend_lawyers", "client")


def test_client_denied_on_destructive_delete_and_write_tools() -> None:
    with pytest.raises(ToolPermissionDeniedError, match="delete tool"):
        tool_permission_policy.check_permission("delete_case_data", "client")

    with pytest.raises(ToolPermissionDeniedError, match="write tool"):
        tool_permission_policy.check_permission("modify_case_data", "client")

    with pytest.raises(ToolPermissionDeniedError, match="write tool"):
        tool_permission_policy.check_permission("prepare_legal_draft", "client")


def test_lawyer_permitted_on_legal_work_tools() -> None:
    assert tool_permission_policy.check_permission(
        "retrieve_legal_information", "lawyer"
    )
    assert tool_permission_policy.check_permission("modify_case_data", "lawyer")
    assert tool_permission_policy.check_permission("delete_case_data", "lawyer")
    assert tool_permission_policy.check_permission("prepare_legal_draft", "lawyer")


def test_unknown_tool_fails_closed() -> None:
    with pytest.raises(UnknownToolOperationError):
        tool_permission_policy.check_permission("unregistered_tool", "admin")


def test_enforce_permission_raises_403_for_unauthorized_user() -> None:
    client_user = User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )
    with pytest.raises(HTTPException) as exc_info:
        tool_permission_policy.enforce_permission(client_user, "delete_case_data")

    assert exc_info.value.status_code == 403


def test_enforce_permission_raises_404_for_unknown_tool() -> None:
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        role="admin",
        password_hash="hash",
    )
    with pytest.raises(HTTPException) as exc_info:
        tool_permission_policy.enforce_permission(admin_user, "unknown_tool_xyz")

    assert exc_info.value.status_code == 404


def test_custom_tool_permission_policy() -> None:
    policy = ToolPermissionPolicy(
        {
            "custom_read": (OperationType.READ, ("client",)),
            "custom_delete": (OperationType.DELETE, ("admin",)),
        }
    )
    assert policy.check_permission("custom_read", "client")
    with pytest.raises(ToolPermissionDeniedError):
        policy.check_permission("custom_delete", "lawyer")


def test_tool_registry_with_permissions() -> None:
    registry = ToolRegistry()
    registry.register(
        "client_search",
        DummyInput,
        operation_type=OperationType.READ,
        allowed_roles=("client", "lawyer"),
    )
    registry.register(
        "lawyer_cleanup",
        DummyInput,
        operation_type=OperationType.DELETE,
        allowed_roles=("lawyer", "admin"),
    )

    assert registry.check_permission("client_search", "client")
    assert registry.check_permission("lawyer_cleanup", "lawyer")

    with pytest.raises(ToolPermissionDeniedError):
        registry.check_permission("lawyer_cleanup", "client")


# --- HTTP Endpoint Permission Check Tests ---


def test_http_tool_permission_check_client_allowed_read() -> None:
    client_user = User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: client_user

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/tools/retrieve_legal_information/check-permission")
            assert resp.status_code == 200
            data = resp.json()
            assert data["permitted"] is True
            assert data["operation_type"] == "read"
    finally:
        app.dependency_overrides.clear()


def test_http_tool_permission_check_client_forbidden_delete() -> None:
    client_user = User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: client_user

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/tools/delete_case_data/check-permission")
            assert resp.status_code == 403
            assert "not authorized to execute delete tool" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_http_tool_permission_check_lawyer_allowed_delete() -> None:
    lawyer_user = User(
        id=uuid.uuid4(),
        email="lawyer@example.com",
        role="lawyer",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: lawyer_user

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/tools/delete_case_data/check-permission")
            assert resp.status_code == 200
            data = resp.json()
            assert data["permitted"] is True
            assert data["operation_type"] == "delete"
    finally:
        app.dependency_overrides.clear()
