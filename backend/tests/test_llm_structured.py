"""Tests for validated structured output, repair retry, and typed fallback."""

import json
import urllib.error

import pytest
from pydantic import ValidationError
from services.llm import (
    FailureKind,
    LLMConfigurationError,
    LLMMessage,
    LLMParameters,
    MessageRole,
    MockLLMProvider,
    ModelNotFoundError,
    ProviderUnavailableError,
    StructuredResult,
    generate_structured,
)
from services.rag import AnswerStatus, Claim, LegalAnswer

VALID_ANSWER = json.dumps(
    {
        "status": "answered",
        "claims": [
            {"text": "مدة الاختبار لا تزيد على ثلاثة أشهر.", "source_ids": ["S1"]}
        ],
        "clarification_question": None,
    },
    ensure_ascii=False,
)
MESSAGES = [LLMMessage.system("أنت مساعد قانوني."), LLMMessage.user("سؤال")]


def _provider(*responses: str | Exception) -> MockLLMProvider:
    return MockLLMProvider(response_sequence=list(responses))


async def _run(provider: MockLLMProvider, **kwargs) -> StructuredResult[LegalAnswer]:
    kwargs.setdefault("transient_backoff_seconds", 0)
    return await generate_structured(provider, MESSAGES, LegalAnswer, **kwargs)


# --- generate_structured ------------------------------------------------------


@pytest.mark.anyio
async def test_valid_output_on_first_attempt() -> None:
    provider = _provider(VALID_ANSWER)

    result = await _run(provider)

    assert result.ok and result.failure is None and result.attempts == 1
    assert result.value.status == AnswerStatus.ANSWERED
    assert result.value.claims[0].source_ids == ["S1"]

    sent = provider.recorded_calls[0]
    assert sent[0].role == MessageRole.SYSTEM
    assert "JSON Schema" in sent[0].content and "أنت مساعد قانوني." in sent[0].content
    params = provider.recorded_parameters[0]
    assert params.temperature == 0.0
    assert params.extra["response_format"]["type"] == "json_schema"


@pytest.mark.anyio
async def test_json_code_fence_is_tolerated() -> None:
    result = await _run(_provider(f"  ```json\n{VALID_ANSWER}\n```  "))

    assert result.ok and result.attempts == 1


@pytest.mark.anyio
async def test_invalid_then_repaired_on_second_attempt() -> None:
    bad = "Here is the answer: " + VALID_ANSWER
    provider = _provider(bad, VALID_ANSWER)

    result = await _run(provider)

    assert result.ok and result.attempts == 2
    repair_call = provider.recorded_calls[1]
    assert repair_call[-2].role == MessageRole.ASSISTANT
    assert repair_call[-2].content == bad
    assert repair_call[-1].role == MessageRole.USER
    assert "not valid JSON" in repair_call[-1].content


@pytest.mark.anyio
async def test_invalid_twice_falls_back_with_last_failure_kind() -> None:
    schema_violation = json.dumps({"status": "answered", "claims": []})
    result = await _run(_provider("not json at all", schema_violation))

    assert not result.ok and result.value is None
    assert result.failure == FailureKind.SCHEMA_MISMATCH
    assert result.attempts == 2


@pytest.mark.anyio
async def test_invalid_json_twice_reports_invalid_json() -> None:
    result = await _run(_provider("{oops", '{"status": NaN}'))

    assert result.failure == FailureKind.INVALID_JSON and result.attempts == 2


@pytest.mark.anyio
async def test_semantic_validator_failure_triggers_repair_then_fallback() -> None:
    def cited_sources_exist(answer: LegalAnswer) -> list[str]:
        return [
            f"unknown source id {sid}"
            for claim in answer.claims
            for sid in claim.source_ids
            if sid not in {"S2"}
        ]

    provider = _provider(VALID_ANSWER, VALID_ANSWER)
    result = await _run(provider, semantic_validator=cited_sources_exist)

    assert result.failure == FailureKind.SEMANTIC_INVALID and result.attempts == 2
    assert "unknown source id S1" in provider.recorded_calls[1][-1].content


@pytest.mark.anyio
async def test_provider_unavailable_retried_once_then_succeeds() -> None:
    provider = _provider(ProviderUnavailableError("down"), VALID_ANSWER)

    result = await _run(provider)

    assert result.ok and result.attempts == 2


@pytest.mark.anyio
async def test_provider_unavailable_retried_once_then_falls_back() -> None:
    provider = _provider(
        ProviderUnavailableError("down"), ProviderUnavailableError("x")
    )

    result = await _run(provider)

    assert result.failure == FailureKind.PROVIDER_UNAVAILABLE
    assert result.attempts == 2
    assert len(provider.recorded_calls) == 2


@pytest.mark.anyio
async def test_timeout_is_classified_and_retried_once() -> None:
    timeout = ProviderUnavailableError("timed out")
    timeout.__cause__ = urllib.error.URLError(TimeoutError("timed out"))
    provider = _provider(timeout, TimeoutError("again"))

    result = await _run(provider)

    assert result.failure == FailureKind.TIMEOUT and result.attempts == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [LLMConfigurationError("bad config"), ModelNotFoundError("no such model")],
)
async def test_configuration_errors_are_not_retried(error: Exception) -> None:
    provider = _provider(error, VALID_ANSWER)

    result = await _run(provider)

    assert result.failure == FailureKind.CONFIGURATION_ERROR
    assert result.attempts == 1
    assert len(provider.recorded_calls) == 1


@pytest.mark.anyio
async def test_unexpected_exception_never_reaches_caller() -> None:
    result = await _run(_provider(RuntimeError("secret internal detail")))

    assert not result.ok and result.failure == FailureKind.PROVIDER_UNAVAILABLE
    assert result.attempts == 1


@pytest.mark.anyio
async def test_caller_parameters_are_kept() -> None:
    provider = _provider(VALID_ANSWER)

    await _run(provider, params=LLMParameters(temperature=0.1, max_tokens=256))

    params = provider.recorded_parameters[0]
    assert params.temperature == 0.1 and params.max_tokens == 256
    assert "response_format" in params.extra


def test_structured_result_rejects_inconsistent_state() -> None:
    with pytest.raises(ValueError):
        StructuredResult(ok=True, value=None, failure=None, attempts=1)
    with pytest.raises(ValueError):
        StructuredResult(ok=False, value=None, failure=None, attempts=1)


# --- LegalAnswer schema -------------------------------------------------------


def test_legal_answer_answered_requires_claims() -> None:
    with pytest.raises(ValidationError):
        LegalAnswer(status=AnswerStatus.ANSWERED, claims=[])

    answer = LegalAnswer(
        status=AnswerStatus.ANSWERED, claims=[Claim(text="نص", source_ids=["S1"])]
    )
    assert answer.claims[0].text == "نص"


def test_legal_answer_needs_clarification_rules() -> None:
    with pytest.raises(ValidationError):
        LegalAnswer(status=AnswerStatus.NEEDS_CLARIFICATION)
    with pytest.raises(ValidationError):
        LegalAnswer(status=AnswerStatus.NEEDS_CLARIFICATION, clarification_question=" ")
    with pytest.raises(ValidationError):
        LegalAnswer(
            status=AnswerStatus.NEEDS_CLARIFICATION,
            clarification_question="هل العقد محدد المدة؟",
            claims=[Claim(text="نص")],
        )

    answer = LegalAnswer(
        status=AnswerStatus.NEEDS_CLARIFICATION,
        clarification_question="هل العقد محدد المدة؟",
    )
    assert answer.claims == []


def test_legal_answer_no_source_rejects_claims() -> None:
    assert LegalAnswer(status=AnswerStatus.NO_SOURCE).claims == []
    with pytest.raises(ValidationError):
        LegalAnswer(status=AnswerStatus.NO_SOURCE, claims=[Claim(text="نص")])


def test_legal_answer_rejects_extra_fields_and_blank_claims() -> None:
    with pytest.raises(ValidationError):
        LegalAnswer.model_validate({"status": "no_source", "confidence": 0.9})
    with pytest.raises(ValidationError):
        Claim(text="   ")


# --- LocalLLMProvider malformed HTTP body ---------------------------------------


def test_local_provider_wraps_malformed_response_body(monkeypatch) -> None:
    import io

    from services.llm import LLMProviderError, LocalLLMProvider

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: _Response(b"<html>oops</html>")
    )

    with pytest.raises(LLMProviderError, match="malformed"):
        LocalLLMProvider().generate([LLMMessage.user("سؤال")])


@pytest.mark.parametrize("status", [AnswerStatus.ANSWERED, AnswerStatus.NO_SOURCE])
def test_clarification_question_only_allowed_with_needs_clarification(
    status: AnswerStatus,
) -> None:
    claims = [Claim(text="نص", source_ids=["S1"])] if status == "answered" else []

    with pytest.raises(ValidationError, match="only allowed with needs_clarification"):
        LegalAnswer(status=status, claims=claims, clarification_question="سؤال؟")
    with pytest.raises(ValidationError):
        LegalAnswer(status=status, claims=claims, clarification_question="")

    assert LegalAnswer(status=status, claims=claims).clarification_question is None
