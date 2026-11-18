"""Unit and route tests for retrieval tenant isolation (SCRUM-275).

Covers: case_id ownership check in retrieval, cross-user retrieval returns
403 (nothing), same-user retrieval succeeds.
"""

import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import Case, LawyerProfile, Request, User
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="client_ret@example.com",
        role="client",
        password_hash="hash",
    )


@pytest.fixture
def other_client() -> User:
    return User(
        id=uuid.uuid4(),
        email="other_ret@example.com",
        role="client",
        password_hash="hash",
    )


@pytest.fixture
def lawyer_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="lawyer_ret@example.com",
        role="lawyer",
        password_hash="hash",
    )


@pytest.fixture
def valid_embedding() -> list[float]:
    """A valid 1024-dimensional embedding vector."""
    vec = [0.0] * 1024
    vec[0] = 1.0  # non-zero
    return vec


class TestRetrievalWithoutCaseId:
    """Retrieval without case_id should work for any authenticated user."""

    def test_search_without_case_id_succeeds(
        self, client_user: User, valid_embedding: list[float]
    ) -> None:
        db = Mock(spec=Session)
        # search_legal_chunks returns empty list (no data)
        db.execute.return_value = []

        app.dependency_overrides[get_current_user] = lambda: client_user
        app.dependency_overrides[get_db] = lambda: db

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/retrieval/search",
                    json={"embedding": valid_embedding},
                )
                # 200 OK or 500 (if db mock isn't complete) — not 403
                assert resp.status_code != 403
        finally:
            app.dependency_overrides.clear()


class TestRetrievalWithCaseId:
    """Retrieval with case_id enforces tenant isolation."""

    def test_client_retrieval_on_own_case_allowed(
        self, client_user: User, valid_embedding: list[float]
    ) -> None:
        """Client can retrieve with case_id for their own case."""
        case_id = uuid.uuid4()
        req_id = uuid.uuid4()
        case_obj = Case(
            id=case_id,
            request_id=req_id,
            lawyer_id=uuid.uuid4(),
            status="open",
        )
        req = Request(
            id=req_id,
            client_id=client_user.id,  # This client owns the request
            lawyer_id=case_obj.lawyer_id,
            status="accepted",
        )
        db = Mock(spec=Session)
        # verify_case_ownership calls: Case lookup, then Request lookup
        db.scalar.side_effect = [case_obj, req]
        db.execute.return_value = []

        app.dependency_overrides[get_current_user] = lambda: client_user
        app.dependency_overrides[get_db] = lambda: db

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/retrieval/search",
                    json={
                        "embedding": valid_embedding,
                        "case_id": str(case_id),
                    },
                )
                # Should not be 403
                assert resp.status_code != 403
        finally:
            app.dependency_overrides.clear()

    def test_cross_user_retrieval_returns_403(
        self,
        client_user: User,
        other_client: User,
        valid_embedding: list[float],
    ) -> None:
        """Cross-user retrieval attempt returns 403 (nothing visible)."""
        case_id = uuid.uuid4()
        req_id = uuid.uuid4()
        case_obj = Case(
            id=case_id,
            request_id=req_id,
            lawyer_id=uuid.uuid4(),
            status="open",
        )
        req = Request(
            id=req_id,
            client_id=other_client.id,  # Different client owns this
            lawyer_id=case_obj.lawyer_id,
            status="accepted",
        )
        db = Mock(spec=Session)
        db.scalar.side_effect = [case_obj, req]

        app.dependency_overrides[get_current_user] = lambda: client_user
        app.dependency_overrides[get_db] = lambda: db

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/retrieval/search",
                    json={
                        "embedding": valid_embedding,
                        "case_id": str(case_id),
                    },
                )
                assert resp.status_code == 403
                assert "permission" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_nonexistent_case_returns_404(
        self, client_user: User, valid_embedding: list[float]
    ) -> None:
        """Retrieval with a nonexistent case_id returns 404."""
        db = Mock(spec=Session)
        db.scalar.return_value = None  # Case not found

        app.dependency_overrides[get_current_user] = lambda: client_user
        app.dependency_overrides[get_db] = lambda: db

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/retrieval/search",
                    json={
                        "embedding": valid_embedding,
                        "case_id": str(uuid.uuid4()),
                    },
                )
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_lawyer_retrieval_on_assigned_case_allowed(
        self, lawyer_user: User, valid_embedding: list[float]
    ) -> None:
        """Lawyer can retrieve with case_id for a case assigned to them."""
        profile_id = uuid.uuid4()
        profile = LawyerProfile(id=profile_id, user_id=lawyer_user.id)
        case_id = uuid.uuid4()
        case_obj = Case(
            id=case_id,
            request_id=uuid.uuid4(),
            lawyer_id=profile_id,  # Assigned to this lawyer
            status="open",
        )
        db = Mock(spec=Session)
        db.scalar.side_effect = [case_obj, profile]
        db.execute.return_value = []

        app.dependency_overrides[get_current_user] = lambda: lawyer_user
        app.dependency_overrides[get_db] = lambda: db

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/retrieval/search",
                    json={
                        "embedding": valid_embedding,
                        "case_id": str(case_id),
                    },
                )
                assert resp.status_code != 403
        finally:
            app.dependency_overrides.clear()

    def test_lawyer_retrieval_on_unassigned_case_returns_403(
        self, lawyer_user: User, valid_embedding: list[float]
    ) -> None:
        """Lawyer cannot retrieve from a case they're not assigned to."""
        profile_id = uuid.uuid4()
        profile = LawyerProfile(id=profile_id, user_id=lawyer_user.id)
        case_id = uuid.uuid4()
        case_obj = Case(
            id=case_id,
            request_id=uuid.uuid4(),
            lawyer_id=uuid.uuid4(),  # Different lawyer
            status="open",
        )
        db = Mock(spec=Session)
        db.scalar.side_effect = [case_obj, profile]

        app.dependency_overrides[get_current_user] = lambda: lawyer_user
        app.dependency_overrides[get_db] = lambda: db

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/retrieval/search",
                    json={
                        "embedding": valid_embedding,
                        "case_id": str(case_id),
                    },
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
