"""Configuration loading tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_missing_database_url_has_a_clear_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "database_url" in str(error.value)
    assert "Field required" in str(error.value)
