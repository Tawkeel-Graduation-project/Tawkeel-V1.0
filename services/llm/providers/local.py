"""Local LLM provider supporting Ollama and OpenAI-compatible endpoints."""

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterator
from typing import Any

from services.llm.exceptions import (
    LLMProviderError,
    ModelNotFoundError,
    ProviderUnavailableError,
)
from services.llm.models import (
    LLMMessage,
    LLMParameters,
    LLMResponse,
    LLMStreamChunk,
    TokenUsage,
)
from services.llm.provider import BaseLLMProvider


class LocalLLMProvider(BaseLLMProvider):
    """Communicates with local Ollama or OpenAI-compatible inference daemons."""

    def __init__(
        self,
        model_name: str = "qwen2.5:7b",
        api_base: str = "http://localhost:11434",
        api_key: str | None = None,
        timeout: float = 60.0,
        provider_name: str = "local",
    ) -> None:
        self._model_name = model_name
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._provider_name = provider_name

    @property
    def name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def _chat_url(self) -> str:
        if self.api_base.endswith("/v1"):
            return f"{self.api_base}/chat/completions"
        return f"{self.api_base}/v1/chat/completions"

    def _build_request(
        self, payload: dict[str, Any], stream: bool = False
    ) -> urllib.request.Request:
        payload["stream"] = stream
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "User-Agent": "Tawkeel-LLM-Local/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return urllib.request.Request(
            self._chat_url(), data=data, headers=headers, method="POST"
        )

    def _build_payload(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> dict[str, Any]:
        self.validate_messages(messages)
        payload: dict[str, Any] = {
            "model": self._model_name,
            "messages": [
                {"role": m.role.value, "content": m.content} for m in messages
            ],
        }
        if parameters:
            if parameters.temperature is not None:
                payload["temperature"] = parameters.temperature
            if parameters.max_tokens is not None:
                payload["max_tokens"] = parameters.max_tokens
            if parameters.top_p is not None:
                payload["top_p"] = parameters.top_p
            if parameters.stop is not None:
                payload["stop"] = parameters.stop
            payload.update(parameters.extra)
        return payload

    def generate(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> LLMResponse:
        payload = self._build_payload(messages, parameters)
        req = self._build_request(payload, stream=False)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ModelNotFoundError(
                    f"Model '{self._model_name}' not found at "
                    f"{self.api_base} (HTTP 404)"
                ) from exc
            error_body = exc.read().decode("utf-8", errors="replace")
            raise LLMProviderError(
                f"Local LLM provider error: HTTP {exc.code} {exc.reason} - {error_body}"
            ) from exc
        except (
            urllib.error.URLError,
            ConnectionError,
            TimeoutError,
            OSError,
        ) as exc:
            raise ProviderUnavailableError(
                f"Could not connect to local LLM provider at {self.api_base}: {exc}"
            ) from exc

        choices = body.get("choices", [])
        if not choices:
            raise LLMProviderError("No choices returned from local LLM provider")

        choice = choices[0]
        content = choice.get("message", {}).get("content", "")
        finish_reason = choice.get("finish_reason", "stop")
        usage_dict = body.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_dict.get("prompt_tokens", 0),
            completion_tokens=usage_dict.get("completion_tokens", 0),
            total_tokens=usage_dict.get("total_tokens", 0),
        )

        return LLMResponse(
            content=content,
            model=body.get("model", self._model_name),
            provider=self.name,
            usage=usage,
            finish_reason=finish_reason,
            raw=body,
        )

    async def agenerate(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> LLMResponse:
        return await asyncio.to_thread(self.generate, messages, parameters)

    def stream(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> Iterator[LLMStreamChunk]:
        payload = self._build_payload(messages, parameters)
        req = self._build_request(payload, stream=True)

        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ModelNotFoundError(
                    f"Model '{self._model_name}' not found at "
                    f"{self.api_base} (HTTP 404)"
                ) from exc
            error_body = exc.read().decode("utf-8", errors="replace")
            raise LLMProviderError(
                f"Local LLM stream HTTP error: {exc.code} {exc.reason} - {error_body}"
            ) from exc
        except (
            urllib.error.URLError,
            ConnectionError,
            TimeoutError,
            OSError,
        ) as exc:
            raise ProviderUnavailableError(
                f"Could not connect to local LLM provider at {self.api_base}: {exc}"
            ) from exc

        finish_reason: str | None = None
        usage: TokenUsage | None = None

        with resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                else:
                    data_str = line

                if data_str == "[DONE]":
                    break

                try:
                    chunk_json = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = chunk_json.get("choices", [])
                if choices:
                    delta_content = choices[0].get("delta", {}).get("content", "")
                    if delta_content:
                        yield LLMStreamChunk(delta=delta_content, is_complete=False)
                    if choices[0].get("finish_reason"):
                        finish_reason = choices[0].get("finish_reason")

                if "usage" in chunk_json and chunk_json["usage"]:
                    usage = TokenUsage(
                        prompt_tokens=chunk_json["usage"].get("prompt_tokens", 0),
                        completion_tokens=chunk_json["usage"].get(
                            "completion_tokens", 0
                        ),
                        total_tokens=chunk_json["usage"].get("total_tokens", 0),
                    )

        yield LLMStreamChunk(
            delta="",
            is_complete=True,
            finish_reason=finish_reason or "stop",
            usage=usage,
        )

    async def astream(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        queue: asyncio.Queue[LLMStreamChunk | Exception | None] = asyncio.Queue()

        def _worker() -> None:
            try:
                for chunk in self.stream(messages, parameters):
                    queue.put_nowait(chunk)
            except Exception as exc:
                queue.put_nowait(exc)
            finally:
                queue.put_nowait(None)

        loop = asyncio.get_running_loop()
        worker_task = loop.run_in_executor(None, _worker)

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            await worker_task

    async def health_check(self) -> bool:
        def _check() -> bool:
            try:
                url = f"{self.api_base}/v1/models"
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Tawkeel-LLM/1.0"}
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    return resp.status in (200, 204)
            except Exception:
                try:
                    req = urllib.request.Request(
                        self.api_base, headers={"User-Agent": "Tawkeel-LLM/1.0"}
                    )
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        return resp.status in (200, 204)
                except Exception:
                    return False

        return await asyncio.to_thread(_check)
