"""Unit tests for cryptographic security utilities and JWT tokens."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_dummy_password,
    verify_password,
)


def test_password_hash_and_verify_round_trip() -> None:
    raw_password = "CorrectHorseBatteryStaple123!"
    hashed = hash_password(raw_password)

    is_valid, needs_rehash = verify_password(raw_password, hashed)
    assert is_valid is True
    assert needs_rehash is False

    is_wrong, _ = verify_password("WrongPassword123!", hashed)
    assert is_wrong is False


def test_password_hash_differs_from_plaintext_and_is_unique() -> None:
    raw_password = "Password123!"
    hash1 = hash_password(raw_password)
    hash2 = hash_password(raw_password)

    assert hash1.startswith("$argon2")
    assert raw_password not in hash1
    assert hash1 != hash2  # Salt ensures uniqueness across calls


def test_password_verify_handles_malformed_hashes_safely() -> None:
    assert verify_password("password", "invalid_not_a_hash") == (False, False)
    assert verify_password("password", "") == (False, False)
    assert verify_password("password", "$argon2id$v=19$malformed") == (False, False)


def test_verify_dummy_password_runs_without_error() -> None:
    # Timing mitigation check executes without throwing errors
    verify_dummy_password("any_attempted_password")


def test_token_create_and_decode_round_trip() -> None:
    subject_id = str(uuid.uuid4())
    token = create_access_token(subject=subject_id)

    payload = decode_access_token(token)
    assert payload["sub"] == subject_id
    assert "exp" in payload
    assert "iat" in payload
    assert "jti" in payload
    assert payload["exp"] > payload["iat"]


def test_expired_token_is_rejected_using_injected_time() -> None:
    subject_id = str(uuid.uuid4())
    past_now = datetime.now(timezone.utc) - timedelta(hours=2)

    # Token expires 1 hour ago
    expired_token = create_access_token(
        subject=subject_id,
        expires_delta=timedelta(hours=1),
        now=past_now,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired_token)


def test_token_with_none_algorithm_is_rejected() -> None:
    now = datetime.now(timezone.utc)
    unsigned_payload = {
        "sub": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    none_token = jwt.encode(unsigned_payload, key="", algorithm="none")

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(none_token)


def test_tampered_token_signature_is_rejected() -> None:
    token = create_access_token(subject=str(uuid.uuid4()))
    parts = token.split(".")
    # Tamper with signature part
    tampered_sig = parts[2][:-4] + "xxxx"
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(tampered_token)


def test_token_missing_exp_claim_is_rejected() -> None:
    now = datetime.now(timezone.utc)
    payload_without_exp = {
        "sub": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    # Sign with our test secret key
    from app.core.config import JWT_ALGORITHM, get_settings

    secret = get_settings().jwt_secret_key.get_secret_value()
    token = jwt.encode(payload_without_exp, secret, algorithm=JWT_ALGORITHM)

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)


def test_token_with_wrong_secret_is_rejected() -> None:
    token = create_access_token(subject=str(uuid.uuid4()))
    wrong_secret = "wrong_secret_key_at_least_32_characters_long"

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token, secret_key=wrong_secret)
