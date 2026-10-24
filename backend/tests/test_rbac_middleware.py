"""Unit and route tests for role-based access control (RBAC) middleware."""

import uuid
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    require_admin,
    require_client,
    require_lawyer,
    require_role,
)
from app.db.models import LawyerProfile, User
from app.db.session import get_db
from app.main import app


def test_require_role_permits_authorized_role() -> None:
    verifier = require_role("lawyer", "admin")
    lawyer_user = User(
        id=uuid.uuid4(),
        email="lawyer@example.com",
        role="lawyer",
        password_hash="hash",
    )
    result = verifier(current_user=lawyer_user)
    assert result == lawyer_user


def test_require_role_rejects_unauthorized_role_with_403() -> None:
    verifier = require_role("lawyer", "admin")
    client_user = User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )
    with pytest.raises(HTTPException) as exc_info:
        verifier(current_user=client_user)

    assert exc_info.value.status_code == 403
    assert "role 'client' is not authorized" in exc_info.value.detail


def test_require_client_permits_only_client() -> None:
    client_user = User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )
    lawyer_user = User(
        id=uuid.uuid4(),
        email="lawyer@example.com",
        role="lawyer",
        password_hash="hash",
    )

    assert require_client(current_user=client_user) == client_user

    with pytest.raises(HTTPException) as exc_info:
        require_client(current_user=lawyer_user)
    assert exc_info.value.status_code == 403


def test_require_lawyer_permits_only_lawyer() -> None:
    client_user = User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )
    lawyer_user = User(
        id=uuid.uuid4(),
        email="lawyer@example.com",
        role="lawyer",
        password_hash="hash",
    )

    assert require_lawyer(current_user=lawyer_user) == lawyer_user

    with pytest.raises(HTTPException) as exc_info:
        require_lawyer(current_user=client_user)
    assert exc_info.value.status_code == 403


def test_require_admin_permits_only_admin() -> None:
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        role="admin",
        password_hash="hash",
    )
    client_user = User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )

    assert require_admin(current_user=admin_user) == admin_user

    with pytest.raises(HTTPException) as exc_info:
        require_admin(current_user=client_user)
    assert exc_info.value.status_code == 403


# --- HTTP Route-level Separation Tests ---


@pytest.fixture
def mock_db() -> Mock:
    db = Mock(spec=Session)
    scalars_mock = Mock()
    scalars_mock.all.return_value = []
    db.scalars.return_value = scalars_mock
    db.scalar.return_value = None
    return db


def test_unauthenticated_request_to_client_routes_returns_401() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/client/requests")
        assert response.status_code == 401


def test_unauthenticated_request_to_lawyer_routes_returns_401() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/lawyer/requests")
        assert response.status_code == 401


def test_client_role_cannot_access_lawyer_requests_route(mock_db: Mock) -> None:
    client_user = User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: client_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/lawyer/requests")
            assert response.status_code == 403
            assert "role 'client' is not authorized" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_client_role_cannot_access_lawyer_cases_route(mock_db: Mock) -> None:
    client_user = User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: client_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/lawyer/cases")
            assert response.status_code == 403
            assert "role 'client' is not authorized" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_lawyer_role_cannot_access_client_requests_route(mock_db: Mock) -> None:
    lawyer_user = User(
        id=uuid.uuid4(),
        email="lawyer@example.com",
        role="lawyer",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: lawyer_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/client/requests")
            assert response.status_code == 403
            assert "role 'lawyer' is not authorized" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_client_role_can_access_client_requests(mock_db: Mock) -> None:
    client_user = User(
        id=uuid.uuid4(),
        email="client@example.com",
        role="client",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: client_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/client/requests")
            assert response.status_code == 200
            assert response.json() == []
    finally:
        app.dependency_overrides.clear()


def test_lawyer_role_can_access_lawyer_requests(mock_db: Mock) -> None:
    lawyer_id = uuid.uuid4()
    lawyer_user = User(
        id=lawyer_id,
        email="lawyer@example.com",
        role="lawyer",
        password_hash="hash",
    )
    profile = LawyerProfile(
        id=uuid.uuid4(),
        user_id=lawyer_id,
    )
    mock_db.scalar.return_value = profile

    app.dependency_overrides[get_current_user] = lambda: lawyer_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/lawyer/requests")
            assert response.status_code == 200
            assert response.json() == []
    finally:
        app.dependency_overrides.clear()
