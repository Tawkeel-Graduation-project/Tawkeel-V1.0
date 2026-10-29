"""Pydantic data models and schemas for LLM provider abstraction."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(str, Enum):
    """Supported roles in a chat conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMMessage(BaseModel):
    """A single message in a chat conversation."""

    role: MessageRole
    content: str
    name: str | None = None

    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def system(cls, content: str) -> "LLMMessage":
        """Convenience constructor for a system message."""
        return cls(role=MessageRole.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str, name: str | None = None) -> "LLMMessage":
        """Convenience constructor for a user message."""
        return cls(role=MessageRole.USER, content=content, name=name)

    @classmethod
    def assistant(cls, content: str) -> "LLMMessage":
        """Convenience constructor for an assistant message."""
        return cls(role=MessageRole.ASSISTANT, content=content)


class LLMParameters(BaseModel):
    """Inference parameters for text generation."""

    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    stop: list[str] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class TokenUsage(BaseModel):
    """Token accounting for a prompt and completion."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    model_config = ConfigDict(frozen=True)


class LLMResponse(BaseModel):
    """Standardized output returned by any LLM provider."""

    content: str
    model: str
    provider: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str = "stop"
    raw: dict[str, Any] | None = None

    model_config = ConfigDict(frozen=True)


class LLMStreamChunk(BaseModel):
    """A streaming token or fragment emitted during generation."""

    delta: str
    is_complete: bool = False
    finish_reason: str | None = None
    usage: TokenUsage | None = None

    model_config = ConfigDict(frozen=True)
