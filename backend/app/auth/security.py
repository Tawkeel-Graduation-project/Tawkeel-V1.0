"""Cryptographic security utilities for password hashing and JWT management."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import JWT_ALGORITHM, get_settings

_hasher = PasswordHasher()
# Pre-computed dummy hash using standard Argon2 parameters for timing equalization
DUMMY_ARGON2_HASH = _hasher.hash("dummy_mitigation_password_for_timing")


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2 with default library parameters."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, bool]:
    """Verify a plaintext password against an Argon2 hash.

    Returns:
        tuple[bool, bool]: (is_valid, needs_rehash)
    """
    try:
        if _hasher.verify(password_hash, password):
            needs_rehash = _hasher.check_needs_rehash(password_hash)
            return True, needs_rehash
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False, False
    except Exception:
        return False, False
    return False, False


def verify_dummy_password(password: str) -> None:
    """Run password verification against a dummy hash to equalize timing.

    Used when a user is not found in the database.
    """
    verify_password(password, DUMMY_ARGON2_HASH)


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    now: datetime | None = None,
) -> str:
    """Create a signed JWT access token.

    Claims:
        - sub: Subject identifier (typically User UUID string)
        - iat: Issued at (UTC timestamp)
        - exp: Expiration (UTC timestamp)
        - jti: Unique token identifier (UUID4 string)
    """
    settings = get_settings()
    current_time = now if now is not None else datetime.now(timezone.utc)
    if expires_delta is not None:
        expire_time = current_time + expires_delta
    else:
        expire_time = current_time + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    payload = {
        "sub": subject,
        "iat": int(current_time.timestamp()),
        "exp": int(expire_time.timestamp()),
        "jti": str(uuid.uuid4()),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(
    token: str,
    secret_key: str | None = None,
) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Pins algorithm to HS256 and requires sub, exp, and iat claims.
    Raises jwt.PyJWTError if the token is invalid, expired, or malformed.
    """
    settings = get_settings()
    secret = (
        secret_key
        if secret_key is not None
        else settings.jwt_secret_key.get_secret_value()
    )

    return jwt.decode(
        token,
        secret,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub", "iat"]},
    )
