"""Unit tests for authentication service edge cases."""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.schemas import UserLogin, UserRegister
from app.auth.service import authenticate_user, register_user
from app.db.models import User


def test_register_integrity_race_returns_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Mock(spec=Session)
    db.scalar.return_value = None
    db.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    monkeypatch.setattr("app.auth.service.hash_password", lambda password: "hash")

    payload = UserRegister(
        email="race@example.com",
        password="ValidRacePassword123!",
        full_name="Race User",
        role="client",
    )

    with pytest.raises(HTTPException) as error:
        register_user(db, payload)

    assert error.value.status_code == 409
    db.rollback.assert_called_once_with()


def test_services_canonicalize_email_even_for_unvalidated_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = "lookup@bücher.com"
    raw_punycode = "lookup@xn--bcher-kva.com"
    user = User(
        email=canonical,
        full_name="Canonical User",
        role="client",
        password_hash="hashed",
    )
    login_db = Mock(spec=Session)
    login_db.scalar.return_value = user
    monkeypatch.setattr(
        "app.auth.service.verify_password", lambda *_args: (True, False)
    )
    authenticate_user(
        login_db,
        UserLogin.model_construct(email=raw_punycode, password="password"),
    )
    login_query = login_db.scalar.call_args.args[0]
    assert "bücher.com" in str(login_query.compile().params.values())

    register_db = Mock(spec=Session)
    register_db.scalar.return_value = None
    monkeypatch.setattr("app.auth.service.hash_password", lambda _password: "hashed")
    payload = UserRegister.model_construct(
        email=raw_punycode,
        password="ValidPassword123!",
        full_name="Canonical User",
        role="client",
    )
    created = register_user(register_db, payload)
    register_query = register_db.scalar.call_args.args[0]
    assert "bücher.com" in str(register_query.compile().params.values())
    assert created.email == canonical
