"""Configuration loading tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_missing_database_url_has_a_clear_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "database_url" in str(error.value)
    assert "Field required" in str(error.value)


def test_settings_loader_caches_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")

    first_settings = get_settings()
    second_settings = get_settings()

    assert first_settings is second_settings
    get_settings.cache_clear()
