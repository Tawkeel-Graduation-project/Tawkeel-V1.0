"""Unit and route tests for resource ownership verification."""

import uuid
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.ownership import (
    verify_case_ownership,
    verify_conversation_ownership,
    verify_request_ownership,
)
from app.db.models import Case, Conversation, LawyerProfile, Request, User
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="client1@example.com",
        role="client",
        password_hash="hash",
    )


@pytest.fixture
def other_client() -> User:
    return User(
        id=uuid.uuid4(),
        email="client2@example.com",
        role="client",
        password_hash="hash",
    )


@pytest.fixture
def lawyer_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="lawyer1@example.com",
        role="lawyer",
        password_hash="hash",
    )


@pytest.fixture
def other_lawyer() -> User:
    return User(
        id=uuid.uuid4(),
        email="lawyer2@example.com",
        role="lawyer",
        password_hash="hash",
    )


@pytest.fixture
def admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="admin@example.com",
        role="admin",
        password_hash="hash",
    )


def test_client_can_access_own_request(client_user: User) -> None:
    req_id = uuid.uuid4()
    req = Request(
        id=req_id,
        client_id=client_user.id,
        lawyer_id=uuid.uuid4(),
        status="pending",
    )
    db = Mock(spec=Session)
    db.scalar.return_value = req

    result = verify_request_ownership(db, req_id, client_user)
    assert result == req


def test_client_cannot_access_other_clients_request_returns_403(
    client_user: User, other_client: User
) -> None:
    req_id = uuid.uuid4()
    req = Request(
        id=req_id,
        client_id=other_client.id,  # Owned by client 2
        lawyer_id=uuid.uuid4(),
        status="pending",
    )
    db = Mock(spec=Session)
    db.scalar.return_value = req

    with pytest.raises(HTTPException) as exc_info:
        verify_request_ownership(db, req_id, client_user)

    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.detail


def test_lawyer_can_access_assigned_request(lawyer_user: User) -> None:
    req_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    profile = LawyerProfile(id=profile_id, user_id=lawyer_user.id)
    req = Request(
        id=req_id,
        client_id=uuid.uuid4(),
        lawyer_id=profile_id,
        status="pending",
    )
    db = Mock(spec=Session)
    # First scalar returns Request, second returns LawyerProfile
    db.scalar.side_effect = [req, profile]

    result = verify_request_ownership(db, req_id, lawyer_user)
    assert result == req


def test_lawyer_cannot_access_unassigned_request_returns_403(
    lawyer_user: User,
) -> None:
    req_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    profile = LawyerProfile(id=profile_id, user_id=lawyer_user.id)
    req = Request(
        id=req_id,
        client_id=uuid.uuid4(),
        lawyer_id=uuid.uuid4(),  # Assigned to another lawyer
        status="pending",
    )
    db = Mock(spec=Session)
    db.scalar.side_effect = [req, profile]

    with pytest.raises(HTTPException) as exc_info:
        verify_request_ownership(db, req_id, lawyer_user)

    assert exc_info.value.status_code == 403


def test_nonexistent_request_returns_404(client_user: User) -> None:
    db = Mock(spec=Session)
    db.scalar.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        verify_request_ownership(db, uuid.uuid4(), client_user)

    assert exc_info.value.status_code == 404


def test_lawyer_can_access_own_case(lawyer_user: User) -> None:
    case_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    profile = LawyerProfile(id=profile_id, user_id=lawyer_user.id)
    case_obj = Case(
        id=case_id,
        request_id=uuid.uuid4(),
        lawyer_id=profile_id,
        status="open",
    )
    db = Mock(spec=Session)
    db.scalar.side_effect = [case_obj, profile]

    result = verify_case_ownership(db, case_id, lawyer_user)
    assert result == case_obj


def test_lawyer_cannot_access_other_lawyers_case_returns_403(
    lawyer_user: User,
) -> None:
    case_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    profile = LawyerProfile(id=profile_id, user_id=lawyer_user.id)
    case_obj = Case(
        id=case_id,
        request_id=uuid.uuid4(),
        lawyer_id=uuid.uuid4(),  # Different lawyer
        status="open",
    )
    db = Mock(spec=Session)
    db.scalar.side_effect = [case_obj, profile]

    with pytest.raises(HTTPException) as exc_info:
        verify_case_ownership(db, case_id, lawyer_user)

    assert exc_info.value.status_code == 403


def test_client_can_access_case_linked_to_their_request(
    client_user: User,
) -> None:
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
        client_id=client_user.id,
        lawyer_id=case_obj.lawyer_id,
        status="accepted",
    )
    db = Mock(spec=Session)
    db.scalar.side_effect = [case_obj, req]

    result = verify_case_ownership(db, case_id, client_user)
    assert result == case_obj


def test_client_cannot_access_unrelated_case_returns_403(
    client_user: User, other_client: User
) -> None:
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
        client_id=other_client.id,  # Different client
        lawyer_id=case_obj.lawyer_id,
        status="accepted",
    )
    db = Mock(spec=Session)
    db.scalar.side_effect = [case_obj, req]

    with pytest.raises(HTTPException) as exc_info:
        verify_case_ownership(db, case_id, client_user)

    assert exc_info.value.status_code == 403


def test_user_can_access_own_conversation(client_user: User) -> None:
    conv_id = uuid.uuid4()
    conv = Conversation(
        id=conv_id,
        user_id=client_user.id,
        type="qa",
    )
    db = Mock(spec=Session)
    db.scalar.return_value = conv

    result = verify_conversation_ownership(db, conv_id, client_user)
    assert result == conv


def test_user_cannot_access_other_users_conversation_returns_403(
    client_user: User, other_client: User
) -> None:
    conv_id = uuid.uuid4()
    conv = Conversation(
        id=conv_id,
        user_id=other_client.id,
        type="qa",
    )
    db = Mock(spec=Session)
    db.scalar.return_value = conv

    with pytest.raises(HTTPException) as exc_info:
        verify_conversation_ownership(db, conv_id, client_user)

    assert exc_info.value.status_code == 403


def test_admin_can_access_any_resource(admin_user: User, client_user: User) -> None:
    req_id = uuid.uuid4()
    req = Request(
        id=req_id,
        client_id=client_user.id,
        lawyer_id=uuid.uuid4(),
        status="pending",
    )
    db = Mock(spec=Session)
    db.scalar.return_value = req

    assert verify_request_ownership(db, req_id, admin_user) == req


# --- HTTP Endpoint Integration Ownership Checks ---


def test_http_client_get_request_forbidden_for_other_user(
    client_user: User, other_client: User
) -> None:
    req_id = uuid.uuid4()
    req = Request(
        id=req_id,
        client_id=other_client.id,
        lawyer_id=uuid.uuid4(),
        status="pending",
    )
    db = Mock(spec=Session)
    db.scalar.return_value = req

    app.dependency_overrides[get_current_user] = lambda: client_user
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/client/requests/{req_id}")
            assert resp.status_code == 403
            assert "permission to access this request" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_http_lawyer_get_case_forbidden_for_other_lawyer(
    lawyer_user: User,
) -> None:
    case_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    profile = LawyerProfile(id=profile_id, user_id=lawyer_user.id)
    other_case = Case(
        id=case_id,
        request_id=uuid.uuid4(),
        lawyer_id=uuid.uuid4(),  # Belongs to other lawyer
        status="open",
    )
    db = Mock(spec=Session)
    db.scalar.side_effect = [other_case, profile]

    app.dependency_overrides[get_current_user] = lambda: lawyer_user
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/lawyer/cases/{case_id}")
            assert resp.status_code == 403
            assert "permission to access this case" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()
