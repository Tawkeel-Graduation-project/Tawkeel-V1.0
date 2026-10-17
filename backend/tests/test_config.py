"""Configuration loading tests."""

import secrets

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def _valid_secret() -> str:
    return secrets.token_urlsafe(48)


def test_missing_database_url_has_a_clear_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", _valid_secret())

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
    secret = "too_short_secret_under_32_c"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "jwt_secret_key" in str(error.value)
    assert "at least 32 characters" in str(error.value)
    assert secret not in str(error.value)


def test_31_character_jwt_secret_fails_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "AbcdefghijKLMNOPQRSTuvwxyz01234"
    assert len(secret) == 31
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "at least 32 characters" in str(error.value)
    assert secret not in str(error.value)


def test_placeholder_jwt_secret_key_fails_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    secret = "replace_with_a_dummy_secret_key_long_enough"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "jwt_secret_key" in str(error.value)
    assert "placeholder" in str(error.value)
    assert secret not in str(error.value)


def test_valid_jwt_secret_key_is_secret_str(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_secret = _valid_secret()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", valid_secret)

    settings = Settings(_env_file=None)
    assert settings.jwt_secret_key.get_secret_value() == valid_secret
    assert str(settings.jwt_secret_key) == "**********"


@pytest.mark.parametrize("secret", [" " * 32, " " * 40, "x" * 32])
def test_weak_jwt_secrets_fail_validation(
    monkeypatch: pytest.MonkeyPatch,
    secret: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "jwt_secret_key" in str(error.value)
    assert secret not in str(error.value)


def test_jwt_secret_with_surrounding_whitespace_fails_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = " " + _valid_secret()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "whitespace" in str(error.value)
    assert secret not in str(error.value)


def test_32_character_jwt_secret_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "AbcdefghijKLMNOPQRSTuvwxyz012345"
    assert len(secret) == 32
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    settings = Settings(_env_file=None)

    assert settings.jwt_secret_key.get_secret_value() == secret


def test_generated_jwt_secret_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = secrets.token_urlsafe(48)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    settings = Settings(_env_file=None)

    assert settings.jwt_secret_key.get_secret_value() == secret


def test_access_token_expire_minutes_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", _valid_secret())

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


def test_login_rate_limit_defaults_and_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", _valid_secret())
    for key in (
        "LOGIN_RATE_LIMIT_IP_MAX_FAILURES",
        "LOGIN_RATE_LIMIT_EMAIL_MAX_FAILURES",
        "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
        "LOGIN_RATE_LIMIT_MAX_TRACKED_KEYS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)
    assert settings.login_rate_limit_ip_max_failures == 20
    assert settings.login_rate_limit_email_max_failures == 5
    assert settings.login_rate_limit_window_seconds == 900
    assert settings.login_rate_limit_max_tracked_keys == 10_000

    monkeypatch.setenv("LOGIN_RATE_LIMIT_EMAIL_MAX_FAILURES", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("LOGIN_RATE_LIMIT_EMAIL_MAX_FAILURES", "101")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("LOGIN_RATE_LIMIT_EMAIL_MAX_FAILURES", "7")
    configured = Settings(_env_file=None)
    assert configured.login_rate_limit_email_max_failures == 7


@pytest.mark.parametrize(
    ("setting", "invalid_value"),
    [
        ("LOGIN_RATE_LIMIT_IP_MAX_FAILURES", "0"),
        ("LOGIN_RATE_LIMIT_IP_MAX_FAILURES", "101"),
        ("LOGIN_RATE_LIMIT_EMAIL_MAX_FAILURES", "0"),
        ("LOGIN_RATE_LIMIT_EMAIL_MAX_FAILURES", "101"),
        ("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "0"),
        ("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "86401"),
        ("LOGIN_RATE_LIMIT_MAX_TRACKED_KEYS", "0"),
        ("LOGIN_RATE_LIMIT_MAX_TRACKED_KEYS", "10001"),
    ],
)
def test_login_rate_limit_setting_rejects_out_of_bounds_values(
    monkeypatch: pytest.MonkeyPatch,
    setting: str,
    invalid_value: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", _valid_secret())
    monkeypatch.setenv(setting, invalid_value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_sqlalchemy_database_url_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/tawkeel")
    monkeypatch.setenv("JWT_SECRET_KEY", _valid_secret())

    settings = Settings(_env_file=None)
    assert settings.sqlalchemy_database_url == (
        "postgresql+psycopg://user:pass@localhost:5432/tawkeel"
    )


def test_settings_loader_caches_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", _valid_secret())

    first_settings = get_settings()
    second_settings = get_settings()

    assert first_settings is second_settings
    get_settings.cache_clear()
