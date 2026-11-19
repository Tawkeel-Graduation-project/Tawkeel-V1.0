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


class OutputValidationError(LLMError):
    """Raised internally when model output fails JSON, schema, or semantic checks.

    ``kind`` is a ``FailureKind`` value from ``services.llm.structured`` and
    ``errors`` holds short, user-safe descriptions used to build repair prompts.
    Callers of ``generate_structured`` never see this exception.
    """

    def __init__(self, kind: str, errors: list[str]) -> None:
        self.kind = kind
        self.errors = list(errors)
        super().__init__(f"{kind}: {len(self.errors)} validation error(s)")
