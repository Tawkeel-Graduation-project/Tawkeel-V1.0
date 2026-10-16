"""Unit tests for database session dependency."""

from unittest.mock import MagicMock

import pytest

from app.db import session as db_session


def test_get_db_yields_session_and_closes_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=mock_session)
    monkeypatch.setattr(db_session, "get_session_factory", lambda: mock_factory)

    generator = db_session.get_db()
    acquired_session = next(generator)

    assert acquired_session is mock_session
    mock_session.close.assert_not_called()

    with pytest.raises(StopIteration):
        next(generator)

    mock_session.close.assert_called_once()
    mock_session.rollback.assert_not_called()


def test_get_db_rolls_back_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=mock_session)
    monkeypatch.setattr(db_session, "get_session_factory", lambda: mock_factory)

    generator = db_session.get_db()
    acquired_session = next(generator)
    assert acquired_session is mock_session

    custom_error = RuntimeError("Database operation failed")
    with pytest.raises(RuntimeError, match="Database operation failed"):
        generator.throw(custom_error)

    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()
