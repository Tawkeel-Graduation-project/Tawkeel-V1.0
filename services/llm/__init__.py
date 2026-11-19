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
    OutputValidationError,
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
from services.llm.structured import (
    FailureKind,
    StructuredResult,
    generate_structured,
)
from services.llm.trial import (
    DEFAULT_LEGAL_TRIAL_PROMPTS,
    DEFAULT_SYSTEM_PROMPT,
    TrialMetrics,
    TrialResult,
    arun_trial,
    arun_trial_suite,
    export_trial_markdown_report,
    format_trial_summary,
    run_trial,
    run_trial_suite,
)

__all__ = [
    "BaseLLMProvider",
    "DEFAULT_LEGAL_TRIAL_PROMPTS",
    "DEFAULT_SYSTEM_PROMPT",
    "FailureKind",
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
    "OutputValidationError",
    "ProviderUnavailableError",
    "StructuredResult",
    "TokenUsage",
    "TrialMetrics",
    "TrialResult",
    "arun_trial",
    "arun_trial_suite",
    "export_trial_markdown_report",
    "format_trial_summary",
    "generate_structured",
    "get_llm_provider",
    "list_available_providers",
    "register_provider",
    "run_trial",
    "run_trial_suite",
]
