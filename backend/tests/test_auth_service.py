"""Unit tests for authentication service edge cases."""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.schemas import UserRegister
from app.auth.service import register_user


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
