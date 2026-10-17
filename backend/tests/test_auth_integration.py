"""Integration tests for authentication endpoints using a real PostgreSQL database."""

import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session

from app.auth.rate_limit import InMemoryRateLimiter, get_login_rate_limiter
from app.auth.schemas import UserLogin, UserRegister
from app.auth.security import create_access_token, hash_password
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
    app.dependency_overrides[get_login_rate_limiter] = lambda: InMemoryRateLimiter()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_login_rate_limit_blocks_before_authentication_or_database(
    client: TestClient, test_engine, monkeypatch
) -> None:
    limiter = InMemoryRateLimiter(max_failures_per_email=1, max_failures_per_ip=20)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    first = client.post(
        "/auth/login", json={"email": "blocked@example.com", "password": "wrong"}
    )
    assert first.status_code == 401

    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(test_engine, "before_cursor_execute", record_statement)
    verifier_calls: list[str] = []
    monkeypatch.setattr(
        "app.auth.service.verify_password",
        lambda *_args: verifier_calls.append("password"),
    )
    monkeypatch.setattr(
        "app.auth.service.verify_dummy_password",
        lambda *_args: verifier_calls.append("dummy"),
    )
    try:
        blocked = client.post(
            "/auth/login",
            json={"email": "blocked@example.com", "password": "correct"},
        )
    finally:
        event.remove(test_engine, "before_cursor_execute", record_statement)
    assert blocked.status_code == 429
    assert blocked.headers.get("Cache-Control") == "no-store"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert statements == []
    assert verifier_calls == []


def test_exception_after_reservation_is_counted_as_failure(
    client: TestClient, monkeypatch
) -> None:
    limiter = InMemoryRateLimiter(max_failures_per_email=1, max_failures_per_ip=10)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter

    def fail_after_reservation(_db, _payload):
        raise RuntimeError("internal failure")

    monkeypatch.setattr("app.auth.router.authenticate_user", fail_after_reservation)
    payload = {"email": "exception.limit@example.com", "password": "wrong"}
    first = client.post("/auth/login", json=payload)
    assert first.status_code == 500
    assert limiter._entries["ip:testclient"].reservations == {}
    assert len(limiter._entries["ip:testclient"].failures) == 1
    assert limiter._entries["email:exception.limit@example.com"].reservations == {}
    assert len(limiter._entries["email:exception.limit@example.com"].failures) == 1
    second = client.post("/auth/login", json=payload)

    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_existing_and_unknown_email_receive_identical_block_response(
    client: TestClient, db_session: Session
) -> None:
    limiter = InMemoryRateLimiter(max_failures_per_email=1, max_failures_per_ip=20)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    password = "CorrectPassword123!"
    client.post(
        "/auth/register",
        json={
            "email": "known.limit@example.com",
            "password": password,
            "full_name": "Known",
            "role": "client",
        },
    )
    client.post(
        "/auth/login",
        json={"email": "known.limit@example.com", "password": "wrong"},
    )
    client.post(
        "/auth/login",
        json={"email": "missing.limit@example.com", "password": "wrong"},
    )
    known = client.post(
        "/auth/login",
        json={"email": "known.limit@example.com", "password": password},
    )
    unknown = client.post(
        "/auth/login",
        json={"email": "missing.limit@example.com", "password": "wrong"},
    )
    assert known.status_code == unknown.status_code == 429
    assert known.content == unknown.content
    assert known.headers["Retry-After"] == unknown.headers["Retry-After"]
    assert (
        known.headers["Cache-Control"] == unknown.headers["Cache-Control"] == "no-store"
    )


def test_another_email_can_login_while_first_email_is_blocked(
    client: TestClient,
) -> None:
    limiter = InMemoryRateLimiter(max_failures_per_email=1, max_failures_per_ip=20)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    password = "CorrectPassword123!"
    for email in ("blocked.alone@example.com", "allowed.alone@example.com"):
        assert (
            client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "full_name": "Independent Email",
                    "role": "client",
                },
            ).status_code
            == 201
        )
    assert (
        client.post(
            "/auth/login",
            json={"email": "blocked.alone@example.com", "password": "wrong"},
        ).status_code
        == 401
    )
    blocked = client.post(
        "/auth/login",
        json={"email": "blocked.alone@example.com", "password": password},
    )
    allowed = client.post(
        "/auth/login",
        json={"email": "allowed.alone@example.com", "password": password},
    )
    assert blocked.status_code == 429
    assert allowed.status_code == 200


def test_success_resets_email_but_keeps_ip_failures(client: TestClient) -> None:
    limiter = InMemoryRateLimiter(max_failures_per_email=2, max_failures_per_ip=3)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    email = "reset.limit@example.com"
    password = "CorrectPassword123!"
    assert (
        client.post(
            "/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": "Reset",
                "role": "client",
            },
        ).status_code
        == 201
    )
    bad = {"email": email, "password": "wrong"}
    assert client.post("/auth/login", json=bad).status_code == 401
    assert (
        client.post(
            "/auth/login", json={"email": email, "password": password}
        ).status_code
        == 200
    )
    assert client.post("/auth/login", json=bad).status_code == 401
    assert client.post("/auth/login", json=bad).status_code == 401
    assert client.post("/auth/login", json=bad).status_code == 429


def test_successful_login_does_not_clear_ip_counter(client: TestClient) -> None:
    limiter = InMemoryRateLimiter(max_failures_per_email=10, max_failures_per_ip=2)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    password = "CorrectPassword123!"
    for email in (
        "first.ip@example.com",
        "second.ip@example.com",
        "third.ip@example.com",
    ):
        assert (
            client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "full_name": "IP Counter",
                    "role": "client",
                },
            ).status_code
            == 201
        )
    assert (
        client.post(
            "/auth/login",
            json={"email": "first.ip@example.com", "password": "wrong"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login",
            json={"email": "second.ip@example.com", "password": password},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/auth/login",
            json={"email": "third.ip@example.com", "password": "wrong"},
        ).status_code
        == 401
    )
    blocked = client.post(
        "/auth/login",
        json={"email": "first.ip@example.com", "password": password},
    )
    assert blocked.status_code == 429


def test_missing_request_client_uses_shared_unknown_ip_key(
    client: TestClient, monkeypatch
) -> None:
    from starlette.requests import Request

    limiter = InMemoryRateLimiter(max_failures_per_email=10, max_failures_per_ip=1)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    monkeypatch.setattr(Request, "client", property(lambda _request: None))
    first = client.post(
        "/auth/login",
        json={"email": "unknown.ip.one@example.com", "password": "wrong"},
    )
    second = client.post(
        "/auth/login",
        json={"email": "unknown.ip.two@example.com", "password": "wrong"},
    )
    assert first.status_code == 401
    assert second.status_code == 429


def test_ip_limit_spans_emails_and_forwarded_headers_are_ignored(
    client: TestClient,
) -> None:
    limiter = InMemoryRateLimiter(max_failures_per_email=10, max_failures_per_ip=2)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    for email, forwarded in (
        ("one.ip@example.com", "198.51.100.1"),
        ("two.ip@example.com", "198.51.100.2"),
    ):
        response = client.post(
            "/auth/login",
            headers={"X-Forwarded-For": forwarded},
            json={"email": email, "password": "wrong"},
        )
        assert response.status_code == 401
    blocked = client.post(
        "/auth/login",
        headers={"X-Forwarded-For": "203.0.113.8"},
        json={"email": "third.ip@example.com", "password": "wrong"},
    )
    assert blocked.status_code == 429


def test_blocked_attempt_does_not_extend_the_window(client: TestClient) -> None:
    now = [100.0]
    limiter = InMemoryRateLimiter(
        max_failures_per_email=1, window_seconds=10, clock=lambda: now[0]
    )
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    bad = {"email": "clock.limit@example.com", "password": "wrong"}
    assert client.post("/auth/login", json=bad).status_code == 401
    first = client.post("/auth/login", json=bad)
    now[0] += 4
    second = client.post("/auth/login", json=bad)
    third = client.post("/auth/login", json=bad)
    assert first.status_code == second.status_code == 429
    assert third.status_code == 429
    assert first.headers["Retry-After"] == "10"
    assert second.headers["Retry-After"] == "6"
    assert third.headers["Retry-After"] == "6"


def test_register_success_response_omits_credentials(
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


def test_register_short_password_rejected(
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
    output = capsys.readouterr()
    assert payload["password"] not in output.out + output.err


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
    for response in (register_response, login_response):
        assert all(
            set(error) == {"loc", "msg", "type"} for error in response.json()["detail"]
        )

    output = capsys.readouterr()
    assert register_password not in output.out + output.err
    assert login_password not in output.out + output.err


def test_login_password_length_is_checked_before_limiter_db_and_argon(
    client: TestClient, db_session: Session, test_engine, monkeypatch
) -> None:
    email = "password.boundary@example.com"
    assert (
        client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "CorrectPassword123!",
                "full_name": "Password Boundary",
                "role": "client",
            },
        ).status_code
        == status.HTTP_201_CREATED
    )

    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    verifier_calls: list[int] = []
    monkeypatch.setattr(
        "app.auth.service.verify_password",
        lambda *_args: (verifier_calls.append(1) or False, False),
    )
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(test_engine, "before_cursor_execute", record_statement)
    try:
        accepted_length = client.post(
            "/auth/login", json={"email": email, "password": "x" * 128}
        )
        assert accepted_length.status_code == status.HTTP_401_UNAUTHORIZED
        assert len(verifier_calls) == 1
        assert limiter.tracked_key_count == 2

        statements.clear()
        for length in (129, 1024 * 1024):
            submitted = "x" * length
            started = time.perf_counter()
            response = client.post(
                "/auth/login", json={"email": email, "password": submitted}
            )
            elapsed = time.perf_counter() - started
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
            assert submitted not in response.text
            assert elapsed < 2.0
            assert statements == []
            assert len(verifier_calls) == 1
            assert limiter.tracked_key_count == 2
    finally:
        event.remove(test_engine, "before_cursor_execute", record_statement)


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


def test_lowercase_bearer_scheme_is_accepted(client: TestClient) -> None:
    password = secrets.token_urlsafe(18)
    register_response = client.post(
        "/auth/register",
        json={
            "email": "lowercase.scheme@example.com",
            "password": password,
            "full_name": "Lowercase Bearer",
            "role": "client",
        },
    )
    assert register_response.status_code == status.HTTP_201_CREATED
    login_response = client.post(
        "/auth/login",
        json={"email": "lowercase.scheme@example.com", "password": password},
    )
    assert login_response.status_code == status.HTTP_200_OK

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"bearer {login_response.json()['access_token']}"},
    )
    assert response.status_code == status.HTTP_200_OK


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


def test_login_and_me_accept_reserved_test_domain_email(
    client: TestClient,
    db_session: Session,
) -> None:
    password = secrets.token_urlsafe(18)
    email = "seeded.client@tawkeel.test"
    user = User(
        email=email,
        full_name="Seeded Client",
        role="client",
        password_hash=hash_password(password),
    )
    db_session.add(user)
    db_session.commit()

    login_response = client.post(
        "/auth/login",
        json={"email": f" {email.upper()} ", "password": password},
    )
    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["access_token"]

    me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == status.HTTP_200_OK
    assert me_response.json()["email"] == email


def test_registration_and_login_share_canonical_idn_email(
    client: TestClient, db_session: Session
) -> None:
    password = secrets.token_urlsafe(18)
    typed = "  Mixed.Puny@XN--BCHER-KVA.COM  "
    register_response = client.post(
        "/auth/register",
        json={
            "email": typed,
            "password": password,
            "full_name": "Canonical Email",
            "role": "client",
        },
    )
    assert register_response.status_code == status.HTTP_201_CREATED
    stored_email = register_response.json()["email"]
    assert stored_email == "mixed.puny@bücher.com"
    assert db_session.scalar(select(User).where(User.email == stored_email))

    equivalent_addresses = (
        typed,
        typed.strip().lower(),
        "mixed.puny@bücher.com",
    )
    for address in equivalent_addresses:
        assert (
            client.post(
                "/auth/login", json={"email": address, "password": password}
            ).status_code
            == status.HTTP_200_OK
        )
        assert UserLogin(email=address, password=password).email == stored_email

    duplicate = client.post(
        "/auth/register",
        json={
            "email": "mixed.puny@bücher.com",
            "password": password,
            "full_name": "Duplicate Canonical Email",
            "role": "client",
        },
    )
    assert duplicate.status_code == status.HTTP_409_CONFLICT


def test_registration_canonicalizes_unicode_and_surrounding_whitespace(
    client: TestClient,
) -> None:
    password = secrets.token_urlsafe(18)
    for typed, expected in (
        ("Unicode@bücher.com", "unicode@bücher.com"),
        ("  Spaced@EXAMPLE.COM  ", "spaced@example.com"),
    ):
        response = client.post(
            "/auth/register",
            json={
                "email": typed,
                "password": password,
                "full_name": "Canonical Email",
                "role": "client",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["email"] == expected
        for login_address in (typed, typed.strip().lower()):
            assert (
                client.post(
                    "/auth/login",
                    json={"email": login_address, "password": password},
                ).status_code
                == status.HTTP_200_OK
            )


def test_equivalent_email_forms_share_one_limiter_key(client: TestClient) -> None:
    limiter = InMemoryRateLimiter(max_failures_per_email=4, max_failures_per_ip=20)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    forms = (
        "shared@xn--bcher-kva.com",
        "shared@bücher.com",
        "SHARED@XN--BCHER-KVA.COM",
        " shared@bücher.com ",
    )
    for address in forms:
        response = client.post(
            "/auth/login", json={"email": address, "password": "wrong"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    assert limiter.retry_after("email:shared@bücher.com") is not None
    assert limiter.tracked_key_count == 2
    blocked = client.post(
        "/auth/login",
        json={"email": "shared@xn--bcher-kva.com", "password": "wrong"},
    )
    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_full_name_rejects_nul_and_accepts_unicode_names(
    client: TestClient,
) -> None:
    def register(full_name: str, email: str) -> int:
        response = client.post(
            "/auth/register",
            json={
                "email": email,
                "password": secrets.token_urlsafe(18),
                "full_name": full_name,
                "role": "client",
            },
        )
        return response.status_code

    assert register("A\u0000B", "nul.name@example.com") == 422
    assert register("أحمد محمد", "arabic.name@example.com") == 201
    assert register("Counselor 🧑‍⚖️", "emoji.name@example.com") == 201


def test_nul_email_is_rejected_without_database_error(client: TestClient) -> None:
    register_response = client.post(
        "/auth/register",
        json={
            "email": "nul\u0000email@example.com",
            "password": secrets.token_urlsafe(18),
            "full_name": "Nul Email",
            "role": "client",
        },
    )
    login_response = client.post(
        "/auth/login",
        json={"email": "nul\u0000email@example.com", "password": "unknown"},
    )

    assert register_response.status_code == 422
    assert login_response.status_code == 422


def test_password_with_nul_is_processed_without_server_error(
    client: TestClient,
) -> None:
    password = "Password\u0000WithNul123!"
    email = "nul.password@example.com"
    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Nul Password",
            "role": "client",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
