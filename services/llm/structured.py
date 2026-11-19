"""Validated structured (JSON) output from any LLM provider, with retry and fallback.

Model text is never trusted. ``generate_structured`` asks the model for JSON that
matches a Pydantic schema, parses it strictly, validates it against the schema and
an optional semantic validator, and makes at most one repair attempt. Every
failure path ends in a typed ``StructuredResult`` fallback; exceptions and model
output never reach the caller.

Retry policy:

- Invalid output (bad JSON, schema mismatch, semantic errors): up to
  ``max_attempts`` model calls in total (default 2: the original plus one repair).
- Transient provider errors (``ProviderUnavailableError``, timeouts): one retry
  after a short backoff, shared across the whole call.
- Configuration errors (``LLMConfigurationError``, ``ModelNotFoundError``,
  ``InvalidPromptError``): no retry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from services.llm.exceptions import (
    InvalidPromptError,
    LLMConfigurationError,
    LLMError,
    ModelNotFoundError,
    OutputValidationError,
    ProviderUnavailableError,
)
from services.llm.models import LLMMessage, LLMParameters, MessageRole
from services.llm.provider import BaseLLMProvider

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

SemanticValidator = Callable[[Any], list[str]]

STRUCTURED_TEMPERATURE = 0.0
DEFAULT_TRANSIENT_BACKOFF_SECONDS = 0.5

# Bounds on what is echoed back to the model in a repair prompt.
MAX_REPAIR_ERRORS = 10
MAX_ERROR_CHARS = 200
MAX_ERRORS_BLOCK_CHARS = 1500
MAX_ECHOED_OUTPUT_CHARS = 4000
# Bound on raw model output written to debug logs.
MAX_LOGGED_OUTPUT_CHARS = 500

_FENCE_RE = re.compile(r"^```(?:json)?[ \t]*\n(.*)\n[ \t]*```$", re.DOTALL | re.I)


class FailureKind(StrEnum):
    """Why a structured call fell back instead of returning a value."""

    INVALID_JSON = "invalid_json"
    SCHEMA_MISMATCH = "schema_mismatch"
    SEMANTIC_INVALID = "semantic_invalid"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    CONFIGURATION_ERROR = "configuration_error"


@dataclass(frozen=True)
class StructuredResult(Generic[T]):
    """Outcome of ``generate_structured``.

    ``ok`` is True only when ``value`` holds a validated instance of the schema.
    ``attempts`` counts every provider call made, including transient retries.
    """

    ok: bool
    value: T | None
    failure: FailureKind | None
    attempts: int

    def __post_init__(self) -> None:
        if self.ok and (self.value is None or self.failure is not None):
            raise ValueError("a successful result needs a value and no failure")
        if not self.ok and (self.value is not None or self.failure is None):
            raise ValueError("a failed result needs a failure and no value")
        if self.attempts < 0:
            raise ValueError("attempts must not be negative")

    @classmethod
    def success(cls, value: T, attempts: int) -> StructuredResult[T]:
        return cls(ok=True, value=value, failure=None, attempts=attempts)

    @classmethod
    def fallback(cls, failure: FailureKind, attempts: int) -> StructuredResult[T]:
        return cls(ok=False, value=None, failure=failure, attempts=attempts)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _reject_non_finite(constant: str) -> Any:
    raise ValueError(f"non-standard JSON constant: {constant}")


def parse_json_output(raw: str) -> Any:
    """Parse model output as strict JSON.

    Only surrounding whitespace and a single surrounding Markdown code fence
    (```json or ```) are tolerated. Raises ``OutputValidationError`` otherwise.
    """
    text = raw.strip()
    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    if not text:
        raise OutputValidationError(FailureKind.INVALID_JSON, ["Output was empty."])
    try:
        return json.loads(text, parse_constant=_reject_non_finite)
    except json.JSONDecodeError as exc:
        error = f"Output is not valid JSON: {exc.msg} (line {exc.lineno}, column "
        error += f"{exc.colno})."
        raise OutputValidationError(FailureKind.INVALID_JSON, [error]) from exc
    except ValueError as exc:
        raise OutputValidationError(
            FailureKind.INVALID_JSON, ["Output uses NaN or Infinity, not valid JSON."]
        ) from exc


def _schema_errors(exc: ValidationError) -> list[str]:
    """Describe schema errors by location and message, never by input value."""
    errors = []
    for error in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        errors.append(f"{location}: {error['msg']}")
    return errors


def validate_output(
    raw: str,
    schema: type[T],
    semantic_validator: SemanticValidator | None = None,
) -> T:
    """Parse and validate raw model output, raising ``OutputValidationError``."""
    data = parse_json_output(raw)
    try:
        value = schema.model_validate(data)
    except ValidationError as exc:
        raise OutputValidationError(
            FailureKind.SCHEMA_MISMATCH, _schema_errors(exc)
        ) from exc

    if semantic_validator is not None:
        errors = [str(e) for e in semantic_validator(value) if str(e).strip()]
        if errors:
            raise OutputValidationError(FailureKind.SEMANTIC_INVALID, errors)
    return value


def build_schema_instructions(schema: type[BaseModel]) -> str:
    """Instruction block that tells the model to answer with schema-valid JSON."""
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return (
        "Respond with a single JSON object only. Do not add any text, explanation, "
        "or Markdown before or after it. The JSON must match this JSON Schema "
        f"exactly, with no extra fields:\n{schema_json}"
    )


def _with_schema_instructions(
    messages: list[LLMMessage], schema: type[BaseModel]
) -> list[LLMMessage]:
    """Add the schema instructions to the leading system message (or create one)."""
    instructions = build_schema_instructions(schema)
    if messages and messages[0].role == MessageRole.SYSTEM:
        merged = f"{messages[0].content}\n\n{instructions}"
        return [LLMMessage.system(merged), *messages[1:]]
    return [LLMMessage.system(instructions), *messages]


def _structured_parameters(
    params: LLMParameters | None, schema: type[BaseModel]
) -> LLMParameters:
    """Low temperature plus an OpenAI-compatible ``response_format`` hint.

    Servers such as Ollama, vLLM, and llama.cpp use ``response_format`` to
    constrain decoding. It only improves the odds of valid output; the result is
    always validated regardless. A caller-provided ``response_format`` wins.
    """
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "schema": schema.model_json_schema(),
            "strict": True,
        },
    }
    if params is None:
        return LLMParameters(
            temperature=STRUCTURED_TEMPERATURE,
            extra={"response_format": response_format},
        )
    extra = {"response_format": response_format, **params.extra}
    return params.model_copy(update={"extra": extra})


def build_repair_messages(
    messages: list[LLMMessage], bad_output: str, errors: list[str]
) -> list[LLMMessage]:
    """Conversation plus the rejected output and a bounded list of its errors."""
    shown = [_truncate(e, MAX_ERROR_CHARS) for e in errors[:MAX_REPAIR_ERRORS]]
    if len(errors) > MAX_REPAIR_ERRORS:
        shown.append(f"(and {len(errors) - MAX_REPAIR_ERRORS} more errors)")
    error_block = _truncate("\n".join(f"- {e}" for e in shown), MAX_ERRORS_BLOCK_CHARS)
    echoed = _truncate(bad_output, MAX_ECHOED_OUTPUT_CHARS) or "(empty output)"
    repair_request = (
        "Your previous response was rejected for these reasons:\n"
        f"{error_block}\n\n"
        "Reply again with ONLY a valid JSON object that matches the required "
        "schema. No other text."
    )
    return [*messages, LLMMessage.assistant(echoed), LLMMessage.user(repair_request)]


def _is_timeout(exc: BaseException) -> bool:
    """True if the error, or anything in its cause chain, is a timeout."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, TimeoutError):
            return True
        reason = getattr(current, "reason", None)
        if isinstance(reason, TimeoutError):
            return True
        current = current.__cause__ or current.__context__
    return False


def _classify_provider_error(exc: BaseException) -> tuple[FailureKind, bool]:
    """Map a provider exception to (failure kind, whether it is worth retrying)."""
    if isinstance(exc, (LLMConfigurationError, ModelNotFoundError, InvalidPromptError)):
        return FailureKind.CONFIGURATION_ERROR, False
    if _is_timeout(exc):
        return FailureKind.TIMEOUT, True
    if isinstance(exc, ProviderUnavailableError):
        return FailureKind.PROVIDER_UNAVAILABLE, True
    # Other provider failures (HTTP errors, malformed bodies, unexpected bugs)
    # are not known to be transient.
    return FailureKind.PROVIDER_UNAVAILABLE, False


async def generate_structured(
    provider: BaseLLMProvider,
    messages: list[LLMMessage],
    schema: type[T],
    *,
    params: LLMParameters | None = None,
    max_attempts: int = 2,
    semantic_validator: SemanticValidator | None = None,
    transient_backoff_seconds: float = DEFAULT_TRANSIENT_BACKOFF_SECONDS,
) -> StructuredResult[T]:
    """Ask ``provider`` for JSON matching ``schema`` and return a typed result.

    Never raises for model or provider failures: it returns
    ``StructuredResult.fallback`` with a ``FailureKind`` instead.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    conversation = _with_schema_instructions(list(messages), schema)
    parameters = _structured_parameters(params, schema)
    calls = 0
    transient_retry_available = True
    output_attempt = 0

    while output_attempt < max_attempts:
        output_attempt += 1
        calls += 1
        try:
            response = await provider.agenerate(conversation, parameters)
        except Exception as exc:  # never leak provider errors to callers
            kind, transient = _classify_provider_error(exc)
            logger.warning(
                "Structured output call %d failed: %s (%s, schema=%s)",
                calls,
                kind.value,
                type(exc).__name__,
                schema.__name__,
            )
            if not isinstance(exc, LLMError):
                logger.debug("Unexpected provider exception", exc_info=True)
            if transient and transient_retry_available:
                transient_retry_available = False
                output_attempt -= 1  # a transient retry is not a repair attempt
                await asyncio.sleep(transient_backoff_seconds)
                continue
            return StructuredResult.fallback(kind, calls)

        raw = response.content or ""
        try:
            value = validate_output(raw, schema, semantic_validator)
        except OutputValidationError as exc:
            kind = FailureKind(exc.kind)
            logger.warning(
                "Structured output attempt %d/%d invalid: %s (schema=%s)",
                output_attempt,
                max_attempts,
                kind.value,
                schema.__name__,
            )
            logger.debug(
                "Rejected model output: %r", _truncate(raw, MAX_LOGGED_OUTPUT_CHARS)
            )
            if output_attempt >= max_attempts:
                return StructuredResult.fallback(kind, calls)
            conversation = build_repair_messages(conversation, raw, exc.errors)
            continue
        except Exception as exc:  # e.g. a buggy semantic validator
            logger.warning(
                "Structured output validation crashed: %s (schema=%s)",
                type(exc).__name__,
                schema.__name__,
            )
            logger.debug("Validation crash details", exc_info=True)
            return StructuredResult.fallback(FailureKind.SEMANTIC_INVALID, calls)

        return StructuredResult.success(value, calls)

    # Only reachable if the loop body never runs, which max_attempts >= 1 forbids.
    return StructuredResult.fallback(FailureKind.INVALID_JSON, calls)
