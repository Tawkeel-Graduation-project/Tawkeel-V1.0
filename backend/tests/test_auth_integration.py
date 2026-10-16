"""Integration tests for authentication endpoints using a real PostgreSQL database."""

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.auth.schemas import UserLogin, UserRegister
from app.auth.security import create_access_token
from app.db.models import User
from app.db.session import get_db
from app.main import app

test_db_url = os.environ.get("TEST_DATABASE_URL")
if not test_db_url:
    if os.environ.get("CI"):
        pytest.fail(
            "TEST_DATABASE_URL is required in CI but was not set.",
            pytrace=False,
        )
    pytest.skip(
        "TEST_DATABASE_URL is not set; skipping database integration tests.",
        allow_module_level=True,
    )


@pytest.fixture(scope="session")
def test_engine():
    """Create a session-scoped engine for the test database."""
    raw_url = os.environ["TEST_DATABASE_URL"]
    url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, pool_pre_ping=True)

    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        pytest.fail(
            "Database table 'users' does not exist; run alembic upgrade head",
            pytrace=False,
        )

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """Provide a transactionally isolated database session that is rolled back."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """Provide a TestClient with get_db overridden to use the isolated test session."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_register_success_and_password_not_leaked(
    client: TestClient,
    db_session: Session,
) -> None:
    payload = {
        "email": "Client.Test@Example.COM ",
        "password": "SecurePassword123!",
        "full_name": "  Adham Sabry  ",
        "role": "client",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["email"] == "client.test@example.com"
    assert data["full_name"] == "Adham Sabry"
    assert data["role"] == "client"
    assert "password_hash" not in data
    assert "password" not in data
    assert "id" in data
    assert "created_at" in data

    # Verify database state
    user = db_session.scalar(
        select(User).where(User.email == "client.test@example.com")
    )
    assert user is not None
    assert user.password_hash.startswith("$argon2")
    assert "SecurePassword123!" not in user.password_hash


def test_register_duplicate_email_including_case_variation_gives_409(
    client: TestClient,
) -> None:
    first_payload = {
        "email": "unique.user@example.com",
        "password": "ValidPassword123!",
        "full_name": "First User",
        "role": "client",
    }
    response1 = client.post("/auth/register", json=first_payload)
    assert response1.status_code == status.HTTP_201_CREATED

    # Duplicate with different casing
    second_payload = {
        "email": "UNIQUE.USER@EXAMPLE.COM",
        "password": "ValidPassword123!",
        "full_name": "Second User",
        "role": "lawyer",
    }
    response2 = client.post("/auth/register", json=second_payload)
    assert response2.status_code == status.HTTP_409_CONFLICT
    assert "already exists" in response2.json()["detail"]


def test_register_admin_role_rejected(client: TestClient) -> None:
    payload = {
        "email": "admin.attempt@example.com",
        "password": "ValidPassword123!",
        "full_name": "Admin Attempt",
        "role": "admin",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_register_short_password_rejected(client: TestClient) -> None:
    password = secrets.token_urlsafe(18)
    payload = {
        "email": "short.pw@example.com",
        "password": password[:5],
        "full_name": "Short PW",
        "role": "client",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert payload["password"] not in response.text, "422 response includes password"
    assert "password" in response.text


def test_auth_validation_errors_redact_passwords_and_keep_field_details(
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    register_password = secrets.token_urlsafe(18)
    register_response = client.post(
        "/auth/register",
        json={
            "email": "missing.name@example.com",
            "password": register_password,
            "role": "client",
        },
    )
    assert register_response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert register_password not in register_response.text, (
        "register 422 leaked password"
    )
    assert "full_name" in register_response.text
    assert "msg" in register_response.text

    login_password = secrets.token_urlsafe(18)
    login_response = client.post(
        "/auth/login",
        json={"password": login_password},
    )
    assert login_response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert login_password not in login_response.text, "login 422 leaked password"
    assert "email" in login_response.text
    assert "msg" in login_response.text

    output = capsys.readouterr()
    assert register_password not in output.out + output.err
    assert login_password not in output.out + output.err


def test_auth_payload_reprs_do_not_include_passwords() -> None:
    register_password = secrets.token_urlsafe(18)
    login_password = secrets.token_urlsafe(18)
    register = UserRegister(
        email="repr.register@example.com",
        password=register_password,
        full_name="Repr Register",
        role="client",
    )
    login = UserLogin(email="repr.login@example.com", password=login_password)

    assert register_password not in repr(register)
    assert register_password not in str(register)
    assert login_password not in repr(login)
    assert login_password not in str(login)


def test_login_success_and_cache_control_no_store(client: TestClient) -> None:
    register_payload = {
        "email": "login.success@example.com",
        "password": "MySecretPassword123!",
        "full_name": "Login User",
        "role": "lawyer",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == status.HTTP_201_CREATED

    login_payload = {
        "email": "LOGIN.SUCCESS@EXAMPLE.COM",
        "password": "MySecretPassword123!",
    }
    login_response = client.post("/auth/login", json=login_payload)
    assert login_response.status_code == status.HTTP_200_OK
    assert login_response.headers.get("Cache-Control") == "no-store"

    token_data = login_response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["expires_in"] == 1800


def test_login_wrong_password_and_unknown_email_are_identical(
    client: TestClient,
) -> None:
    register_payload = {
        "email": "known.account@example.com",
        "password": "CorrectPassword123!",
        "full_name": "Known Account",
        "role": "client",
    }
    client.post("/auth/register", json=register_payload)

    # Attempt 1: known email, wrong password
    wrong_pw_response = client.post(
        "/auth/login",
        json={"email": "known.account@example.com", "password": "WrongPassword123!"},
    )

    # Attempt 2: unknown email
    unknown_email_response = client.post(
        "/auth/login",
        json={
            "email": "completely.unknown@example.com",
            "password": "AnyPassword123!",
        },
    )

    assert wrong_pw_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert unknown_email_response.status_code == status.HTTP_401_UNAUTHORIZED

    assert wrong_pw_response.json() == unknown_email_response.json()
    assert (
        wrong_pw_response.headers.get("WWW-Authenticate")
        == unknown_email_response.headers.get("WWW-Authenticate")
        == "Bearer"
    )


def test_auth_me_scenarios(client: TestClient, db_session: Session) -> None:
    # Register and login to get valid token
    register_payload = {
        "email": "me.test@example.com",
        "password": "MyPassword123!",
        "full_name": "Me Tester",
        "role": "client",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    user_id = reg_response.json()["id"]

    login_response = client.post(
        "/auth/login",
        json={"email": "me.test@example.com", "password": "MyPassword123!"},
    )
    valid_token = login_response.json()["access_token"]

    # 1. Valid token
    me_response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert me_response.status_code == status.HTTP_200_OK
    assert me_response.json()["id"] == user_id
    assert me_response.json()["email"] == "me.test@example.com"

    # 2. Expired token
    past_now = datetime.now(timezone.utc) - timedelta(hours=2)
    expired_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(minutes=10),
        now=past_now,
    )
    expired_response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert expired_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert expired_response.headers.get("WWW-Authenticate") == "Bearer"

    # 3. Malformed token
    malformed_response = client.get(
        "/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt.token"}
    )
    assert malformed_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert malformed_response.headers.get("WWW-Authenticate") == "Bearer"

    # 4. Missing token
    missing_response = client.get("/auth/me")
    assert missing_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert missing_response.headers.get("WWW-Authenticate") == "Bearer"

    # 5. Token of a deleted user
    # Generate token for a user that is then deleted
    temp_user_id = str(uuid.uuid4())
    deleted_user_token = create_access_token(subject=temp_user_id)
    deleted_response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {deleted_user_token}"}
    )
    assert deleted_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert deleted_response.headers.get("WWW-Authenticate") == "Bearer"
