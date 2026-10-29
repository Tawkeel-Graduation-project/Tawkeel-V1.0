"""Mock LLM provider for unit tests, offline development, and CI environments."""

import asyncio
from collections.abc import AsyncIterator, Iterator

from services.llm.exceptions import LLMProviderError
from services.llm.models import (
    LLMMessage,
    LLMParameters,
    LLMResponse,
    LLMStreamChunk,
    TokenUsage,
)
from services.llm.provider import BaseLLMProvider


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock provider that requires no external API or local daemon.

    Useful for offline testing, CI environments, and establishing unit test baselines.
    """

    def __init__(
        self,
        model_name: str = "mock-legal-v1",
        default_response: str = "هذا رد قانوني تجريبي مؤقت صادر من المزود التجريبي.",
        canned_responses: dict[str, str] | None = None,
        should_fail: bool = False,
        failure_error: Exception | None = None,
        healthy: bool = True,
    ) -> None:
        self._model_name = model_name
        self.default_response = default_response
        self.canned_responses = canned_responses or {}
        self.should_fail = should_fail
        self.failure_error = failure_error or LLMProviderError(
            "Simulated mock provider failure"
        )
        self._healthy = healthy
        self.recorded_calls: list[list[LLMMessage]] = []

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _resolve_response(self, messages: list[LLMMessage]) -> str:
        self.validate_messages(messages)
        if self.should_fail:
            raise self.failure_error

        self.recorded_calls.append(list(messages))
        last_user_content = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )

        for trigger, response in self.canned_responses.items():
            if trigger.lower() in last_user_content.lower():
                return response

        return self.default_response

    def generate(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> LLMResponse:
        content = self._resolve_response(messages)
        prompt_tokens = sum(len(m.content.split()) for m in messages)
        completion_tokens = len(content.split())

        return LLMResponse(
            content=content,
            model=self._model_name,
            provider=self.name,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            finish_reason="stop",
            raw={"simulated": True},
        )

    async def agenerate(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> LLMResponse:
        await asyncio.sleep(0.001)
        return self.generate(messages, parameters=parameters)

    def stream(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> Iterator[LLMStreamChunk]:
        content = self._resolve_response(messages)
        words = content.split(" ")

        for i, word in enumerate(words):
            chunk_text = word if i == len(words) - 1 else word + " "
            yield LLMStreamChunk(
                delta=chunk_text,
                is_complete=False,
            )

        yield LLMStreamChunk(
            delta="",
            is_complete=True,
            finish_reason="stop",
            usage=TokenUsage(
                prompt_tokens=sum(len(m.content.split()) for m in messages),
                completion_tokens=len(words),
                total_tokens=sum(len(m.content.split()) for m in messages) + len(words),
            ),
        )

    async def astream(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        for chunk in self.stream(messages, parameters=parameters):
            await asyncio.sleep(0.001)
            yield chunk

    async def health_check(self) -> bool:
        return self._healthy
