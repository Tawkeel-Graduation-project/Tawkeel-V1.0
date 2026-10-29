"""LLM provider abstraction layer.

Provides a unified interface for local and online large language models,
allowing feature code to remain vendor-agnostic and swappable via configuration.
"""

from services.llm.exceptions import (
    InvalidPromptError,
    LLMConfigurationError,
    LLMError,
    LLMProviderError,
    ModelNotFoundError,
    ProviderUnavailableError,
)
from services.llm.factory import (
    get_llm_provider,
    list_available_providers,
    register_provider,
)
from services.llm.models import (
    LLMMessage,
    LLMParameters,
    LLMResponse,
    LLMStreamChunk,
    MessageRole,
    TokenUsage,
)
from services.llm.provider import BaseLLMProvider
from services.llm.providers.local import LocalLLMProvider
from services.llm.providers.mock import MockLLMProvider

__all__ = [
    "BaseLLMProvider",
    "InvalidPromptError",
    "LLMConfigurationError",
    "LLMError",
    "LLMMessage",
    "LLMParameters",
    "LLMProviderError",
    "LLMResponse",
    "LLMStreamChunk",
    "LocalLLMProvider",
    "MessageRole",
    "MockLLMProvider",
    "ModelNotFoundError",
    "ProviderUnavailableError",
    "TokenUsage",
    "get_llm_provider",
    "list_available_providers",
    "register_provider",
]
