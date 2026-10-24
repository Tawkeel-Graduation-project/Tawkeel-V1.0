"""Security bypass tests (SCRUM-402).

Verifies that unauthorized access attempts, vertical privilege escalations,
horizontal privilege escalations (IDOR), and tool authorization bypasses
are strictly blocked with HTTP 403 Forbidden or 401 Unauthorized.
"""

import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import Case, Conversation, LawyerProfile, Request, User
from app.db.session import get_db
from app.main import app


@pytest.fixture
def mock_db() -> Mock:
    db = Mock(spec=Session)
    scalars_mock = Mock()
    scalars_mock.all.return_value = []
    db.scalars.return_value = scalars_mock
    db.scalar.return_value = None
    return db


# --- 1. Unauthenticated Bypass Attempts ---


@pytest.mark.parametrize(
    "path",
    [
        "/client/requests",
        "/client/cases",
        "/client/conversations",
        "/lawyer/requests",
        "/lawyer/cases",
        "/lawyer/conversations",
        f"/client/requests/{uuid.uuid4()}",
        f"/lawyer/cases/{uuid.uuid4()}",
    ],
)
def test_unauthenticated_bypass_attempt_is_rejected_with_401(
    path: str,
) -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(path)
        assert resp.status_code == 401
        assert "Could not validate credentials" in resp.json()["detail"]


def test_tampered_bearer_token_bypass_returns_401() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(
            "/client/requests",
            headers={"Authorization": "Bearer forged.token.signature"},
        )
        assert resp.status_code == 401


# --- 2. Vertical Privilege Escalation Bypass (Role Bypasses) ---


def test_vertical_escalation_client_hitting_lawyer_routes_returns_403(
    mock_db: Mock,
) -> None:
    client_user = User(
        id=uuid.uuid4(),
        email="attacker_client@example.com",
        role="client",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: client_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            # Client trying to view lawyer inbox
            resp1 = client.get("/lawyer/requests")
            assert resp1.status_code == 403
            assert "role 'client' is not authorized" in resp1.json()["detail"]

            # Client trying to view lawyer active cases
            resp2 = client.get("/lawyer/cases")
            assert resp2.status_code == 403

            # Client trying to view lawyer internal case conversations
            resp3 = client.get("/lawyer/conversations")
            assert resp3.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_vertical_escalation_lawyer_hitting_client_routes_returns_403(
    mock_db: Mock,
) -> None:
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
            resp = client.get("/client/requests")
            assert resp.status_code == 403
            assert "role 'lawyer' is not authorized" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_unknown_or_tampered_role_returns_403(mock_db: Mock) -> None:
    unknown_role_user = User(
        id=uuid.uuid4(),
        email="intruder@example.com",
        role="attacker",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: unknown_role_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp1 = client.get("/client/requests")
            assert resp1.status_code == 403

            resp2 = client.get("/lawyer/requests")
            assert resp2.status_code == 403
    finally:
        app.dependency_overrides.clear()


# --- 3. Horizontal Privilege Escalation Bypass (IDOR / Cross-Tenant) ---


def test_horizontal_escalation_client_cannot_access_other_client_request(
    mock_db: Mock,
) -> None:
    victim_client_id = uuid.uuid4()
    attacker_client = User(
        id=uuid.uuid4(),
        email="attacker@example.com",
        role="client",
        password_hash="hash",
    )
    stolen_request_id = uuid.uuid4()
    victim_request = Request(
        id=stolen_request_id,
        client_id=victim_client_id,
        lawyer_id=uuid.uuid4(),
        status="pending",
    )

    mock_db.scalar.return_value = victim_request
    app.dependency_overrides[get_current_user] = lambda: attacker_client
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/client/requests/{stolen_request_id}")
            assert resp.status_code == 403
            assert "permission to access this request" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_horizontal_escalation_lawyer_cannot_access_other_lawyer_case(
    mock_db: Mock,
) -> None:
    attacker_lawyer = User(
        id=uuid.uuid4(),
        email="attacker_lawyer@example.com",
        role="lawyer",
        password_hash="hash",
    )
    attacker_profile = LawyerProfile(
        id=uuid.uuid4(),
        user_id=attacker_lawyer.id,
    )
    stolen_case_id = uuid.uuid4()
    victim_case = Case(
        id=stolen_case_id,
        request_id=uuid.uuid4(),
        lawyer_id=uuid.uuid4(),  # Different lawyer's profile ID
        status="open",
    )

    mock_db.scalar.side_effect = [
        victim_case,
        attacker_profile,
    ]
    app.dependency_overrides[get_current_user] = lambda: attacker_lawyer
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/lawyer/cases/{stolen_case_id}")
            assert resp.status_code == 403
            assert "permission to access this case" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_horizontal_escalation_lawyer_cannot_modify_other_lawyer_notes(
    mock_db: Mock,
) -> None:
    attacker_lawyer = User(
        id=uuid.uuid4(),
        email="attacker_lawyer@example.com",
        role="lawyer",
        password_hash="hash",
    )
    attacker_profile = LawyerProfile(
        id=uuid.uuid4(),
        user_id=attacker_lawyer.id,
    )
    stolen_case_id = uuid.uuid4()
    victim_case = Case(
        id=stolen_case_id,
        request_id=uuid.uuid4(),
        lawyer_id=uuid.uuid4(),  # Different lawyer
        status="open",
        notes="Confidential client strategy notes",
    )

    mock_db.scalar.side_effect = [
        victim_case,
        attacker_profile,
    ]
    app.dependency_overrides[get_current_user] = lambda: attacker_lawyer
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                f"/lawyer/cases/{stolen_case_id}/notes",
                json={"notes": "Overwritten by attacker!"},
            )
            assert resp.status_code == 403
            assert victim_case.notes == "Confidential client strategy notes"
    finally:
        app.dependency_overrides.clear()


def test_horizontal_escalation_cannot_access_other_user_conversation(
    mock_db: Mock,
) -> None:
    attacker = User(
        id=uuid.uuid4(),
        email="attacker@example.com",
        role="client",
        password_hash="hash",
    )
    stolen_conv_id = uuid.uuid4()
    victim_conv = Conversation(
        id=stolen_conv_id,
        user_id=uuid.uuid4(),  # Different user
        type="qa",
    )

    mock_db.scalar.return_value = victim_conv
    app.dependency_overrides[get_current_user] = lambda: attacker
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/client/conversations/{stolen_conv_id}")
            assert resp.status_code == 403
            assert "permission to access this conversation" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# --- 4. Tool Execution Escalation Bypass ---


def test_tool_bypass_client_cannot_execute_delete_case_data() -> None:
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
