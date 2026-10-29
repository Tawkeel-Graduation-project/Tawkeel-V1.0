"""Provider registry and factory for resolving configured LLM providers."""

from collections.abc import Callable
from typing import Any, Protocol

from services.llm.exceptions import LLMConfigurationError
from services.llm.provider import BaseLLMProvider
from services.llm.providers.local import LocalLLMProvider
from services.llm.providers.mock import MockLLMProvider


class LLMSettingsProtocol(Protocol):
    """Protocol defining the configuration fields needed by LLM providers."""

    llm_provider: str
    llm_model: str
    llm_api_base: str | None
    llm_api_key: Any
    llm_temperature: float
    llm_timeout_seconds: float


ProviderFactory = Callable[[Any], BaseLLMProvider]

_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register an LLM provider factory under a canonical name.

    Names are normalized to lower-case without whitespace.
    """
    normalized = name.strip().lower()
    if not normalized:
        raise ValueError("Provider name must not be empty")
    _REGISTRY[normalized] = factory


def list_available_providers() -> list[str]:
    """Return all currently registered provider names."""
    return sorted(_REGISTRY.keys())


def _build_mock_provider(settings: Any) -> BaseLLMProvider:
    model_name = getattr(settings, "llm_model", "mock-legal-v1")
    return MockLLMProvider(
        model_name=model_name,
    )


def _build_local_provider(settings: Any) -> BaseLLMProvider:
    model_name = getattr(settings, "llm_model", "qwen2.5:7b")
    api_base = getattr(settings, "llm_api_base", None) or "http://localhost:11434"
    api_key_obj = getattr(settings, "llm_api_key", None)
    if hasattr(api_key_obj, "get_secret_value"):
        api_key = api_key_obj.get_secret_value()
    elif api_key_obj:
        api_key = str(api_key_obj)
    else:
        api_key = None

    timeout = getattr(settings, "llm_timeout_seconds", 60.0)
    provider_name = getattr(settings, "llm_provider", "local").strip().lower()

    return LocalLLMProvider(
        model_name=model_name,
        api_base=api_base,
        api_key=api_key,
        timeout=timeout,
        provider_name=provider_name,
    )


# Register baseline default providers
register_provider("mock", _build_mock_provider)
register_provider("ollama", _build_local_provider)
register_provider("local", _build_local_provider)


def get_llm_provider(settings: Any | None = None) -> BaseLLMProvider:
    """Resolve and instantiate the configured LLM provider from settings.

    Feature code should always obtain their model via this function rather than
    directly instantiating vendor-specific client classes.
    """
    if settings is None:
        try:
            from app.core.config import get_settings

            settings = get_settings()
        except ImportError as exc:
            raise LLMConfigurationError(
                "No settings object provided and app.core.config could not be imported"
            ) from exc

    provider_name = getattr(settings, "llm_provider", "mock")
    provider_key = provider_name.strip().lower()

    factory = _REGISTRY.get(provider_key)
    if factory is None:
        available = ", ".join(list_available_providers())
        raise LLMConfigurationError(
            f"Unsupported or unregistered LLM provider: '{provider_name}'. "
            f"Available providers: [{available}]. "
            f"Check LLM_PROVIDER in your environment configuration."
        )

    return factory(settings)
