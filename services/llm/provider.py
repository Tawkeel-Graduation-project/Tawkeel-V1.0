"""Abstract Base Class for LLM providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator

from services.llm.exceptions import InvalidPromptError
from services.llm.models import (
    LLMMessage,
    LLMParameters,
    LLMResponse,
    LLMStreamChunk,
)


class BaseLLMProvider(ABC):
    """Abstract interface that every LLM provider (local or online) must implement.

    Feature code (chat, contract review, lawyer intake, research) must depend solely
    on this interface, ensuring the underlying provider can be swapped via configuration
    without modifying application logic.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The canonical name of the provider (e.g. 'ollama', 'openai', 'mock')."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The active model identifier used by this provider instance."""

    @abstractmethod
    def generate(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> LLMResponse:
        """Synchronously generate a completion for the provided chat messages."""

    @abstractmethod
    async def agenerate(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> LLMResponse:
        """Asynchronously generate a completion for the provided chat messages."""

    @abstractmethod
    def stream(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> Iterator[LLMStreamChunk]:
        """Synchronously stream response chunks as they are generated."""

    @abstractmethod
    async def astream(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Asynchronously stream response chunks as they are generated."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider endpoint and model are reachable and operational."""

    @staticmethod
    def validate_messages(messages: list[LLMMessage]) -> None:
        """Ensure the message list is non-empty and correctly formed."""
        if not messages:
            raise InvalidPromptError("messages list cannot be empty")
        for i, msg in enumerate(messages):
            if not isinstance(msg, LLMMessage):
                raise InvalidPromptError(
                    f"message at index {i} must be an instance of LLMMessage"
                )
            if not isinstance(msg.content, str):
                raise InvalidPromptError(
                    f"message content at index {i} must be a string"
                )
