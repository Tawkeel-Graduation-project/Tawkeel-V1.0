"""Pydantic schemas for authentication and user payloads."""

import unicodedata
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.auth.email import normalize_email

MAX_PASSWORD_LENGTH = 128


class UserRegister(BaseModel):
    """Payload for registering a new client or lawyer user."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_LENGTH, repr=False)
    full_name: str = Field(min_length=1, max_length=200)
    role: Literal["client", "lawyer"]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: Any) -> Any:
        if isinstance(v, str):
            return normalize_email(v)
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        if any(unicodedata.category(character) == "Cc" for character in v):
            raise ValueError("full_name must not contain control characters")
        stripped = v.strip()
        if not stripped:
            raise ValueError("full_name must not be empty or whitespace only")
        return stripped


class UserLogin(BaseModel):
    """Payload for user login."""

    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH, repr=False)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: Any) -> Any:
        if isinstance(v, str):
            normalized = normalize_email(v, allow_special_use=True)
            if any(unicodedata.category(character) == "Cc" for character in normalized):
                raise ValueError("email must not contain control characters")
            return normalized
        return v


class TokenResponse(BaseModel):
    """Response returned upon successful authentication."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """Public representation of an authenticated user."""

    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
