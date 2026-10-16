"""Configuration loading tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_missing_database_url_has_a_clear_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "database_url" in str(error.value)
    assert "Field required" in str(error.value)


def test_missing_jwt_secret_key_has_a_clear_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "jwt_secret_key" in str(error.value)
    assert "Field required" in str(error.value)


def test_short_jwt_secret_key_fails_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", "too_short_secret_under_32_c")

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "jwt_secret_key" in str(error.value)
    assert "at least 32 characters" in str(error.value)


def test_placeholder_jwt_secret_key_fails_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", "replace_with_a_dummy_secret_key_long_enough")

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "jwt_secret_key" in str(error.value)
    assert "placeholder" in str(error.value)


def test_valid_jwt_secret_key_is_secret_str(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_secret = "c" * 32
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", valid_secret)

    settings = Settings(_env_file=None)
    assert settings.jwt_secret_key.get_secret_value() == valid_secret
    assert str(settings.jwt_secret_key) == "**********"


def test_access_token_expire_minutes_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", "d" * 32)

    # default is 30
    default_settings = Settings(_env_file=None)
    assert default_settings.access_token_expire_minutes == 30

    # < 1 fails
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "0")
    with pytest.raises(ValidationError) as err_zero:
        Settings(_env_file=None)
    assert "greater than or equal to 1" in str(err_zero.value)

    # > 1440 fails
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1441")
    with pytest.raises(ValidationError) as err_high:
        Settings(_env_file=None)
    assert "less than or equal to 1440" in str(err_high.value)

    # within bounds succeeds
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    settings = Settings(_env_file=None)
    assert settings.access_token_expire_minutes == 60


def test_sqlalchemy_database_url_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/tawkeel")
    monkeypatch.setenv("JWT_SECRET_KEY", "e" * 32)

    settings = Settings(_env_file=None)
    assert settings.sqlalchemy_database_url == (
        "postgresql+psycopg://user:pass@localhost:5432/tawkeel"
    )


def test_settings_loader_caches_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", "f" * 32)

    first_settings = get_settings()
    second_settings = get_settings()

    assert first_settings is second_settings
    get_settings.cache_clear()
