"""Domain exceptions for LLM provider abstraction."""


class LLMError(Exception):
    """Base exception for all LLM-related failures."""


class LLMConfigurationError(LLMError):
    """Raised when the provider config is invalid or missing credentials."""


class LLMProviderError(LLMError):
    """Raised when an LLM provider encounters an execution or runtime error."""


class ModelNotFoundError(LLMProviderError):
    """Raised when the requested model is not found or not supported."""


class ProviderUnavailableError(LLMProviderError):
    """Raised when the provider endpoint is unreachable or timed out."""


class InvalidPromptError(LLMError):
    """Raised when the prompt or message list is empty or malformed."""
