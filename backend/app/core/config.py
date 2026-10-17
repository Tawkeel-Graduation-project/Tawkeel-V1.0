"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

JWT_ALGORITHM = "HS256"


class Settings(BaseSettings):
    """Settings required to start the backend."""

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str
    jwt_secret_key: SecretStr
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    login_rate_limit_ip_max_failures: int = Field(default=20, ge=1, le=100)
    login_rate_limit_email_max_failures: int = Field(default=5, ge=1, le=100)
    login_rate_limit_window_seconds: int = Field(default=900, ge=1, le=86400)
    login_rate_limit_max_tracked_keys: int = Field(default=10_000, ge=1, le=10_000)

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, v: SecretStr) -> SecretStr:
        secret = v.get_secret_value()
        if secret.startswith("replace_with"):
            raise ValueError("JWT_SECRET_KEY must not be a placeholder value")
        if len(secret.strip()) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        if secret != secret.strip():
            raise ValueError(
                "JWT_SECRET_KEY must not contain leading or trailing whitespace"
            )
        if len(set(secret)) < 8:
            raise ValueError(
                "JWT_SECRET_KEY must contain at least 8 distinct characters"
            )
        return v

    @property
    def sqlalchemy_database_url(self) -> str:
        """Convert postgresql:// URL to postgresql+psycopg:// for SQLAlchemy."""
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache
def get_settings() -> Settings:
    """Load settings from the environment and local development env file."""

    return Settings()
