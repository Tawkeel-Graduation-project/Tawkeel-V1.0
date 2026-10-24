"""Automated negative tests for RBAC, ownership, and input boundaries (SCRUM-399)."""

import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )


@pytest.fixture
def lawyer_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="lawyer@example.com",
        role="lawyer",
        password_hash="hash",
    )


@pytest.fixture
def mock_db() -> Mock:
    db = Mock(spec=Session)
    scalars_mock = Mock()
    scalars_mock.all.return_value = []
    db.scalars.return_value = scalars_mock
    db.scalar.return_value = None
    return db


# --- 1. Malformed Path Parameter Negative Tests ---


@pytest.mark.parametrize(
    "path",
    [
        "/client/requests/not-a-uuid",
        "/client/cases/12345",
        "/client/conversations/invalid-id-format",
        "/lawyer/requests/malformed-uuid",
        "/lawyer/cases/non-uuid",
        "/lawyer/conversations/00000-invalid",
    ],
)
def test_malformed_uuid_in_path_returns_422(
    path: str, client_user: User, lawyer_user: User, mock_db: Mock
) -> None:
    # Use matching user so role check passes and path validation is exercised
    user = client_user if path.startswith("/client") else lawyer_user
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(path)
            assert resp.status_code == 422
            data = resp.json()
            assert "detail" in data
            # Verify redacted error structure
            assert all(
                "loc" in err and "msg" in err and "type" in err
                for err in data["detail"]
            )
    finally:
        app.dependency_overrides.clear()


# --- 2. Non-existent Resource Negative Tests ---


@pytest.mark.parametrize(
    "path",
    [
        f"/client/requests/{uuid.uuid4()}",
        f"/client/cases/{uuid.uuid4()}",
        f"/client/conversations/{uuid.uuid4()}",
    ],
)
def test_nonexistent_client_resource_returns_404(
    path: str, client_user: User, mock_db: Mock
) -> None:
    mock_db.scalar.return_value = None
    app.dependency_overrides[get_current_user] = lambda: client_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(path)
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# --- 3. Invalid Request Payload Negative Tests ---


def test_create_client_request_missing_required_fields_returns_422(
    client_user: User, mock_db: Mock
) -> None:
    app.dependency_overrides[get_current_user] = lambda: client_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            # Missing lawyer_id
            resp = client.post("/client/requests", json={"niche": "criminal"})
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_create_client_request_invalid_json_body_returns_422(
    client_user: User, mock_db: Mock
) -> None:
    app.dependency_overrides[get_current_user] = lambda: client_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/client/requests",
                content="not valid json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


# --- 4. Unsupported HTTP Method Negative Tests ---


@pytest.mark.parametrize(
    "method,path",
    [
        ("delete", "/client/requests"),
        ("put", "/client/requests"),
        ("delete", "/lawyer/requests"),
        ("post", "/lawyer/requests"),
    ],
)
def test_unsupported_methods_return_405(
    method: str,
    path: str,
    client_user: User,
    lawyer_user: User,
    mock_db: Mock,
) -> None:
    user = client_user if path.startswith("/client") else lawyer_user
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            caller = getattr(client, method)
            resp = caller(path)
            assert resp.status_code == 405
    finally:
        app.dependency_overrides.clear()
