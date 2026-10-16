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

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, v: SecretStr) -> SecretStr:
        secret = v.get_secret_value()
        if secret.startswith("replace_with"):
            raise ValueError("JWT_SECRET_KEY must not be a placeholder value")
        if len(secret) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return v

    @property
    def sqlalchemy_database_url(self) -> str:
        """Convert postgresql:// URL to postgresql+psycopg:// for SQLAlchemy."""
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache
def get_settings() -> Settings:
    """Load settings from the environment and local development env file."""

    return Settings()
