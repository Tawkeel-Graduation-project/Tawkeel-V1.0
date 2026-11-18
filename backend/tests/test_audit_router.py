"""Route-level tests for the audit trail API (SCRUM-276)."""

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
def lawyer_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="lawyer_audit@example.com",
        role="lawyer",
        password_hash="hash",
    )


@pytest.fixture
def client_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="client_audit@example.com",
        role="client",
        password_hash="hash",
    )


@pytest.fixture
def admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="admin_audit@example.com",
        role="admin",
        password_hash="hash",
    )


class TestAuditEndpoint:
    def test_unauthenticated_returns_401(self) -> None:
        """Audit endpoint requires authentication."""
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/audit")
            assert resp.status_code == 401

    def test_admin_can_list_events(self, admin_user: User) -> None:
        """Admin should be able to list audit events."""
        db = Mock(spec=Session)
        mock_scalars = Mock()
        mock_scalars.__iter__ = Mock(return_value=iter([]))
        db.scalars.return_value = mock_scalars

        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: db

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/audit")
                assert resp.status_code == 200
                data = resp.json()
                assert "events" in data
                assert "count" in data
                assert data["count"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_lawyer_without_profile_gets_empty(self, lawyer_user: User) -> None:
        """Lawyer without a profile sees no events."""
        db = Mock(spec=Session)
        db.scalar.return_value = None  # No LawyerProfile

        app.dependency_overrides[get_current_user] = lambda: lawyer_user
        app.dependency_overrides[get_db] = lambda: db

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/audit")
                assert resp.status_code == 200
                assert resp.json()["count"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_pagination_params_accepted(self, admin_user: User) -> None:
        """Limit and offset query params should be accepted."""
        db = Mock(spec=Session)
        mock_scalars = Mock()
        mock_scalars.__iter__ = Mock(return_value=iter([]))
        db.scalars.return_value = mock_scalars

        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: db

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/audit?limit=10&offset=5")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_invalid_limit_returns_422(self, admin_user: User) -> None:
        """Limit=0 or limit=999 should be rejected."""
        db = Mock(spec=Session)
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: db

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/audit?limit=0")
                assert resp.status_code == 422
                resp = client.get("/audit?limit=999")
                assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()
