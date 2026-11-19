"""Malformed LLM output must never crash the system or leak to the user (SCRUM-310).

Every case runs through ``generate_structured`` with ``LegalAnswer`` as the schema
and a scripted ``MockLLMProvider``. Groups:

A. invalid JSON            -> invalid_json
B. valid JSON, bad shape   -> schema_mismatch
C. valid shape, bad sense  -> semantic_invalid
D. valid edge cases        -> success
E. repair retry behaviour
F. provider failures
G. no leaks (result fields, logs, repair messages)
"""

import dataclasses
import io
import json
import logging

import pytest
from services.llm import (
    FailureKind,
    LLMConfigurationError,
    LLMMessage,
    LocalLLMProvider,
    MessageRole,
    MockLLMProvider,
    ModelNotFoundError,
    ProviderUnavailableError,
    StructuredResult,
    generate_structured,
)
from services.llm.structured import (
    MAX_ECHOED_OUTPUT_CHARS,
    MAX_ERROR_CHARS,
    MAX_ERRORS_BLOCK_CHARS,
    MAX_LOGGED_OUTPUT_CHARS,
    MAX_REPAIR_ERRORS,
    parse_json_output,
)
from services.rag import AnswerStatus, LegalAnswer

MESSAGES = [LLMMessage.system("أنت مساعد قانوني."), LLMMessage.user("سؤال")]
ALLOWED_SOURCES = {"S1", "S2"}
REPAIR_HEADER = "Your previous response was rejected for these reasons:\n"
REPAIR_FOOTER = "\n\nReply again with ONLY"


def _json(**fields) -> str:
    return json.dumps(fields, ensure_ascii=False)


def _answer(*source_ids: str, text: str = "يجب الإخطار قبل الإنهاء بشهرين.") -> str:
    return _json(
        status="answered", claims=[{"text": text, "source_ids": list(source_ids)}]
    )


VALID = _answer("S1")


def _sources_exist(answer: LegalAnswer) -> list[str]:
    return [
        f"claim {i}: unknown source id {source_id}"
        for i, claim in enumerate(answer.claims)
        for source_id in claim.source_ids
        if source_id not in ALLOWED_SOURCES
    ]


async def _run(
    *responses: str | Exception, provider: MockLLMProvider | None = None, **kwargs
) -> tuple[StructuredResult[LegalAnswer], MockLLMProvider]:
    provider = provider or MockLLMProvider(response_sequence=list(responses))
    kwargs.setdefault("transient_backoff_seconds", 0)
    result = await generate_structured(provider, MESSAGES, LegalAnswer, **kwargs)
    return result, provider


def _repair_errors(provider: MockLLMProvider, call: int = 1) -> str:
    """The error block of the repair request sent on the given (0-based) call."""
    content = provider.recorded_calls[call][-1].content
    assert content.startswith(REPAIR_HEADER)
    return content[len(REPAIR_HEADER) : content.index(REPAIR_FOOTER)]


# --- A. Invalid JSON -> invalid_json -------------------------------------------

INVALID_JSON_CASES = {
    "empty": "",
    "whitespace_only": "  \n\t  ",
    "arabic_prose": "مدة الإخطار شهران وفقاً للمادة 111.",
    "prose_before_json": "إليك الإجابة: " + VALID,
    "prose_after_json": VALID + "\nأتمنى أن يكون هذا مفيداً.",
    "truncated_mid_string": VALID[:40],
    "truncated_mid_array": '{"status": "answered", "claims": [{"text": "نص", "source',
    "two_objects": VALID + VALID,
    "trailing_comma": '{"status": "no_source",}',
    "single_quotes": "{'status': 'no_source'}",
    "unclosed_fence": f"```json\n{VALID}",
    "non_json_fence_tag": f"```python\n{VALID}\n```",
    "fence_without_newline": f"```json {VALID}```",
    "nan": '{"status": NaN}',
    "infinity": '{"status": Infinity}',
    "negative_infinity": '{"status": -Infinity}',
    "extra_text_inside_fence": f"```json\nالإجابة:\n{VALID}\n```",
    "two_fences": f"```json\n{VALID}\n```\n```json\n{VALID}\n```",
    "huge_integer": '{"status": ' + "9" * 5000 + "}",
    "deeply_nested": "[" * 100_000 + "]" * 100_000,
    "raw_control_char_in_string": '{"status": "no_source", "note": "a' + "\t" + 'b"}',
}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "raw", INVALID_JSON_CASES.values(), ids=INVALID_JSON_CASES.keys()
)
async def test_invalid_json_falls_back(raw: str) -> None:
    result, provider = await _run(raw, raw)

    assert not result.ok and result.value is None
    assert result.failure == FailureKind.INVALID_JSON
    assert result.attempts == 2 and len(provider.recorded_calls) == 2


# --- B. Valid JSON, wrong shape -> schema_mismatch ------------------------------

SCHEMA_MISMATCH_CASES = {
    "empty_array": "[]",
    "array_of_answers": f"[{VALID}]",
    "bare_string": '"answered"',
    "bare_number": "42",
    "null": "null",
    "boolean": "true",
    "empty_object": "{}",
    "missing_status": '{"claims": []}',
    "unknown_status": _json(status="maybe"),
    "status_wrong_case": _json(status="ANSWERED", claims=[{"text": "نص"}]),
    "status_as_number": _json(status=1),
    "claims_as_string": _json(status="answered", claims="المادة 111"),
    "claims_as_object": _json(status="answered", claims={"text": "نص"}),
    "source_ids_as_string": _json(
        status="answered", claims=[{"text": "نص", "source_ids": "S1"}]
    ),
    "source_id_as_number": _json(
        status="answered", claims=[{"text": "نص", "source_ids": [1]}]
    ),
    "text_as_number": _json(status="answered", claims=[{"text": 111}]),
    "text_missing": _json(status="answered", claims=[{"source_ids": ["S1"]}]),
    "extra_top_level_field": _json(status="no_source", confidence=0.9),
    "extra_claim_field": _json(
        status="answered", claims=[{"text": "نص", "source_ids": [], "page": 3}]
    ),
    "empty_claim_text": _json(status="answered", claims=[{"text": ""}]),
    "whitespace_claim_text": _json(status="answered", claims=[{"text": " \n "}]),
    "nul_in_claim_text": _json(status="answered", claims=[{"text": "a\u0000b"}]),
    "lone_surrogate_in_text": '{"status": "answered", "claims": [{"text": "\\ud800"}]}',
    "answered_without_claims": _json(status="answered", claims=[]),
    "no_source_with_claims": _json(status="no_source", claims=[{"text": "نص"}]),
    "clarification_without_question": _json(status="needs_clarification"),
    "clarification_blank_question": _json(
        status="needs_clarification", clarification_question="  "
    ),
    "clarification_with_claims": _json(
        status="needs_clarification",
        clarification_question="هل العقد محدد المدة؟",
        claims=[{"text": "نص"}],
    ),
    "question_with_answered": _json(
        status="answered",
        claims=[{"text": "نص", "source_ids": ["S1"]}],
        clarification_question="هل العقد محدد المدة؟",
    ),
    "question_with_no_source": _json(
        status="no_source", clarification_question="هل العقد محدد المدة؟"
    ),
}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "raw", SCHEMA_MISMATCH_CASES.values(), ids=SCHEMA_MISMATCH_CASES.keys()
)
async def test_wrong_shape_falls_back(raw: str) -> None:
    result, provider = await _run(raw, raw)

    assert not result.ok and result.value is None
    assert result.failure == FailureKind.SCHEMA_MISMATCH
    assert result.attempts == 2 and len(provider.recorded_calls) == 2


# --- C. Valid shape, semantic failure -> semantic_invalid -----------------------

SEMANTIC_CASES = {
    "unknown_label": _answer("S9"),
    "db_uuid_instead_of_label": _answer("3f2b8c1e-0d4a-4c47-9a5e-1b2c3d4e5f60"),
    "article_number_instead_of_label": _answer("المادة 111"),
    "one_valid_one_unknown": _answer("S1", "S3"),
}


@pytest.mark.anyio
@pytest.mark.parametrize("raw", SEMANTIC_CASES.values(), ids=SEMANTIC_CASES.keys())
async def test_semantic_failure_falls_back(raw: str) -> None:
    result, provider = await _run(raw, raw, semantic_validator=_sources_exist)

    assert not result.ok and result.failure == FailureKind.SEMANTIC_INVALID
    assert result.attempts == 2 and len(provider.recorded_calls) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("bad_return", ["raise", "none", "int"])
async def test_broken_semantic_validator_falls_back_without_repair(
    bad_return: str,
) -> None:
    def broken(answer: LegalAnswer):
        if bad_return == "raise":
            raise KeyError("validator bug")
        return None if bad_return == "none" else 7

    result, provider = await _run(VALID, VALID, semantic_validator=broken)

    assert result.failure == FailureKind.SEMANTIC_INVALID
    assert result.attempts == 1 and len(provider.recorded_calls) == 1


# --- D. Valid edge cases must succeed -------------------------------------------

LONG_ANSWER = _json(
    status="answered",
    claims=[
        {"text": f"الحكم رقم {i}: " + "نص قانوني طويل " * 40, "source_ids": ["S1"]}
        for i in range(200)
    ],
)
VALID_CASES = {
    "diacritics_and_arabic_indic_digits": _answer(
        "S1", "S2", text="يُخْطَرُ العاملُ قبل الإنهاء بشهرين وفقاً للمادة ١١١."
    ),
    "json_fence": f"```json\n{VALID}\n```",
    "uppercase_json_fence": f"```JSON\n{VALID}\n```",
    "bare_fence": f"```\n{VALID}\n```",
    "surrounding_whitespace": f"\n\n   {VALID}   \n\t",
    "fence_with_surrounding_whitespace": f"  \n```json\n  {VALID}  \n```\n ",
    "pretty_printed": json.dumps(json.loads(VALID), ensure_ascii=False, indent=2),
    "escaped_unicode": json.dumps(json.loads(VALID)),
    "very_long_answer": LONG_ANSWER,
    "no_source": _json(status="no_source", claims=[]),
    "needs_clarification": _json(
        status="needs_clarification",
        clarification_question="هل عقد العمل محدد المدة أم غير محدد المدة؟",
    ),
}


@pytest.mark.anyio
@pytest.mark.parametrize("raw", VALID_CASES.values(), ids=VALID_CASES.keys())
async def test_valid_edge_cases_succeed(raw: str) -> None:
    result, provider = await _run(raw, semantic_validator=_sources_exist)

    assert result.ok and result.failure is None and result.attempts == 1
    assert isinstance(result.value, LegalAnswer)
    assert len(provider.recorded_calls) == 1


@pytest.mark.anyio
async def test_arabic_text_is_preserved_exactly() -> None:
    text = "يُخْطَرُ العاملُ قبل الإنهاء بشهرين وفقاً للمادة ١١١."

    result, _ = await _run(_answer("S1", text=text))

    assert result.value.claims[0].text == text
    assert result.value.status == AnswerStatus.ANSWERED


# --- E. Retry behaviour -------------------------------------------------------

REPRESENTATIVE = {
    "invalid_json": (FailureKind.INVALID_JSON, "not json", None),
    "schema_mismatch": (FailureKind.SCHEMA_MISMATCH, _json(status="maybe"), None),
    "semantic_invalid": (FailureKind.SEMANTIC_INVALID, _answer("S9"), _sources_exist),
}


@pytest.mark.anyio
@pytest.mark.parametrize("case", REPRESENTATIVE.values(), ids=REPRESENTATIVE.keys())
async def test_bad_then_good_succeeds_on_second_attempt(case) -> None:
    _, bad, validator = case

    result, provider = await _run(bad, VALID, semantic_validator=validator)

    assert result.ok and result.attempts == 2
    repair = provider.recorded_calls[1]
    assert repair[-2].role == MessageRole.ASSISTANT and repair[-2].content == bad
    assert repair[-1].role == MessageRole.USER
    assert _repair_errors(provider).startswith("- ")


@pytest.mark.anyio
@pytest.mark.parametrize("case", REPRESENTATIVE.values(), ids=REPRESENTATIVE.keys())
async def test_bad_then_bad_falls_back_after_two_attempts(case) -> None:
    kind, bad, validator = case

    result, provider = await _run(bad, bad, VALID, semantic_validator=validator)

    assert result.failure == kind and result.attempts == 2
    assert len(provider.recorded_calls) == 2  # the third (valid) item is never used


@pytest.mark.anyio
async def test_repair_message_respects_length_limits() -> None:
    long_key = "k" * 1000
    bad = json.dumps(
        {
            long_key: "x" * 20_000,
            "status": "answered",
            "claims": [{"text": 1, "source_ids": "S1"} for _ in range(60)],
        }
    )

    result, provider = await _run(bad, VALID)

    assert result.ok and result.attempts == 2
    errors = _repair_errors(provider)
    lines = errors.splitlines()
    assert len(errors) <= MAX_ERRORS_BLOCK_CHARS
    assert len(lines) <= MAX_REPAIR_ERRORS + 1
    assert lines[-1].startswith("- (and ") and lines[-1].endswith("more errors)")
    assert all(len(line) <= MAX_ERROR_CHARS + 2 for line in lines)
    echoed = provider.recorded_calls[1][-2].content
    assert len(echoed) <= MAX_ECHOED_OUTPUT_CHARS


@pytest.mark.anyio
async def test_repair_echoes_placeholder_for_empty_output() -> None:
    _, provider = await _run("", VALID)

    assert provider.recorded_calls[1][-2].content == "(empty output)"


# --- F. Provider failures -----------------------------------------------------


@pytest.mark.anyio
async def test_timeout_then_success() -> None:
    result, provider = await _run(TimeoutError("read timed out"), VALID)

    assert result.ok and result.attempts == 2 and len(provider.recorded_calls) == 2


@pytest.mark.anyio
async def test_timeout_twice_falls_back() -> None:
    result, provider = await _run(TimeoutError("t1"), TimeoutError("t2"), VALID)

    assert result.failure == FailureKind.TIMEOUT and result.attempts == 2
    assert len(provider.recorded_calls) == 2


@pytest.mark.anyio
async def test_unavailable_then_malformed_then_valid_respects_caps() -> None:
    down = ProviderUnavailableError("connection refused")

    result, provider = await _run(down, "not json", VALID)

    assert result.ok and result.attempts == 3  # 1 transient retry + 2 output tries


@pytest.mark.anyio
async def test_unavailable_then_malformed_twice_stops_at_attempt_cap() -> None:
    down = ProviderUnavailableError("connection refused")

    result, provider = await _run(down, "not json", "still not json", VALID)

    assert result.failure == FailureKind.INVALID_JSON and result.attempts == 3
    assert len(provider.recorded_calls) == 3


@pytest.mark.anyio
async def test_transient_retry_is_used_only_once() -> None:
    down = ProviderUnavailableError("down")

    result, provider = await _run(down, "not json", down, VALID)

    assert result.failure == FailureKind.PROVIDER_UNAVAILABLE
    assert result.attempts == 3 and len(provider.recorded_calls) == 3


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [LLMConfigurationError("bad config"), ModelNotFoundError("missing model")],
    ids=["configuration", "model_not_found"],
)
async def test_configuration_errors_are_not_retried(error: Exception) -> None:
    result, provider = await _run(error, VALID)

    assert result.failure == FailureKind.CONFIGURATION_ERROR
    assert result.attempts == 1 and len(provider.recorded_calls) == 1


def _patch_urlopen(monkeypatch, *bodies: bytes) -> list[int]:
    calls: list[int] = []
    queue = list(bodies)

    def fake_urlopen(*args, **kwargs):
        calls.append(1)
        return io.BytesIO(queue.pop(0))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return calls


def _chat_body(content: str) -> bytes:
    return json.dumps(
        {"model": "m", "choices": [{"message": {"content": content}}]}
    ).encode()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [b"<html>502 Bad Gateway</html>", b"\xff\xfe\x00garbage", b"[1, 2, 3]", b"{}"],
    ids=["html", "invalid_utf8", "json_array", "no_choices"],
)
async def test_local_provider_malformed_http_body_falls_back(
    monkeypatch, body: bytes
) -> None:
    calls = _patch_urlopen(monkeypatch, body, _chat_body(VALID))

    result = await generate_structured(
        LocalLLMProvider(), MESSAGES, LegalAnswer, transient_backoff_seconds=0
    )

    assert result.failure == FailureKind.PROVIDER_UNAVAILABLE
    assert result.attempts == 1 and len(calls) == 1


@pytest.mark.anyio
async def test_local_provider_malformed_content_goes_through_repair(
    monkeypatch,
) -> None:
    calls = _patch_urlopen(monkeypatch, _chat_body("```json\n{"), _chat_body(VALID))

    result = await generate_structured(LocalLLMProvider(), MESSAGES, LegalAnswer)

    assert result.ok and result.attempts == 2 and len(calls) == 2


# --- G. No leaks --------------------------------------------------------------

OUTPUT_MARKER = "RAW-OUTPUT-MARKER"
EXCEPTION_MARKER = "EXCEPTION-TEXT-MARKER"


def _assert_result_has_no(result: StructuredResult, *markers: str) -> None:
    for field in dataclasses.fields(result):
        value = getattr(result, field.name)
        assert value is None or isinstance(value, (bool, int, FailureKind))
    for marker in markers:
        assert marker not in repr(result)


LEAKY_SEQUENCES = {
    "invalid_json": [f"{OUTPUT_MARKER} prose", f"{OUTPUT_MARKER} again"],
    "schema_mismatch": [_json(status=OUTPUT_MARKER), _json(status=OUTPUT_MARKER)],
    "provider_error": [
        ProviderUnavailableError(EXCEPTION_MARKER),
        ProviderUnavailableError(EXCEPTION_MARKER),
    ],
    "unexpected_error": [RuntimeError(EXCEPTION_MARKER)],
    "configuration_error": [LLMConfigurationError(EXCEPTION_MARKER)],
}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "sequence", LEAKY_SEQUENCES.values(), ids=LEAKY_SEQUENCES.keys()
)
async def test_fallback_and_warning_logs_never_contain_output_or_exception_text(
    sequence, caplog
) -> None:
    caplog.set_level(logging.DEBUG, logger="services.llm.structured")

    result, _ = await _run(*sequence)

    assert not result.ok
    _assert_result_has_no(result, OUTPUT_MARKER, EXCEPTION_MARKER)
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings
    for record in warnings:
        text = record.getMessage() + (record.exc_text or "")
        assert OUTPUT_MARKER not in text and EXCEPTION_MARKER not in text
        assert record.exc_info is None


@pytest.mark.anyio
async def test_raw_output_logged_only_at_debug_and_truncated(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="services.llm.structured")
    tail_marker = "TAIL-MARKER"
    raw = OUTPUT_MARKER + ("ن" * 5000) + tail_marker

    await _run(raw, raw)

    debug = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    with_output = [message for message in debug if OUTPUT_MARKER in message]
    assert with_output
    for message in with_output:
        assert tail_marker not in message
        assert len(message) <= MAX_LOGGED_OUTPUT_CHARS + 100
    for record in caplog.records:
        if record.levelno > logging.DEBUG:
            assert OUTPUT_MARKER not in record.getMessage()


@pytest.mark.anyio
async def test_warning_logs_stay_clean_at_default_level(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="services.llm.structured")

    await _run(f"{OUTPUT_MARKER} not json", f"{OUTPUT_MARKER} still not json")

    assert caplog.records
    assert all(OUTPUT_MARKER not in r.getMessage() for r in caplog.records)


VALUE_LEAK_CASES = {
    "bad_status_value": _json(status="VALUE-MARKER-STATUS"),
    "claims_as_string": _json(status="answered", claims="VALUE-MARKER-CLAIMS"),
    "source_ids_as_string": _json(
        status="answered", claims=[{"text": "نص", "source_ids": "VALUE-MARKER-IDS"}]
    ),
    "extra_field_value": _json(status="no_source", note="VALUE-MARKER-EXTRA"),
    "wrong_type_number": _json(status="answered", claims=[{"text": 987654321}]),
}


@pytest.mark.anyio
@pytest.mark.parametrize("bad", VALUE_LEAK_CASES.values(), ids=VALUE_LEAK_CASES.keys())
async def test_repair_errors_never_echo_invalid_values(bad: str) -> None:
    _, provider = await _run(bad, VALID)

    errors = _repair_errors(provider)
    assert "VALUE-MARKER" not in errors and "987654321" not in errors
    assert ":" in errors  # "location: message" lines are still present


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"status": ' + "9" * 5000 + "}", "out-of-range number"),
        ("[" * 100_000 + "]" * 100_000, "nested too deeply"),
        ("{oops", "not valid JSON"),
        ("", "Output was empty"),
    ],
    ids=["huge_integer", "deeply_nested", "syntax_error", "empty"],
)
async def test_invalid_json_repair_hint_names_the_problem(raw, expected) -> None:
    _, provider = await _run(raw, VALID)

    assert expected in _repair_errors(provider)


# --- A (hardening). Duplicate keys and overflowing numbers -> invalid_json ------

DUPLICATE_KEY_CASES = {
    "top_level": '{"status": "answered", "status": "no_source"}',
    "same_value_twice": '{"status": "no_source", "status": "no_source"}',
    "inside_claim": (
        '{"status": "answered", "claims": [{"text": "أ", "text": "ب", '
        '"source_ids": ["S1"]}]}'
    ),
    "deeply_nested": '{"status": "no_source", "x": [[{"a": {"k": 1, "k": 2}}]]}',
}
OVERFLOW_CASES = {
    "top_level": '{"status": 1e999}',
    "negative": '{"status": -1e999}',
    "inside_claim_array": '{"status": "answered", "claims": [{"text": 1E400}]}',
    "deeply_nested": '{"status": "no_source", "x": [[{"a": [2.5e10000]}]]}',
}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "raw", DUPLICATE_KEY_CASES.values(), ids=DUPLICATE_KEY_CASES.keys()
)
async def test_duplicate_keys_are_invalid_json(raw: str) -> None:
    result, provider = await _run(raw, raw)

    assert result.failure == FailureKind.INVALID_JSON and result.attempts == 2
    assert "repeats a key" in _repair_errors(provider)


@pytest.mark.anyio
@pytest.mark.parametrize("raw", OVERFLOW_CASES.values(), ids=OVERFLOW_CASES.keys())
async def test_overflowing_numbers_are_invalid_json(raw: str) -> None:
    result, provider = await _run(raw, raw)

    assert result.failure == FailureKind.INVALID_JSON and result.attempts == 2
    assert "NaN, Infinity, or an out-of-range number" in _repair_errors(provider)


def test_finite_numbers_and_distinct_keys_still_parse() -> None:
    parsed = parse_json_output('{"a": 1.5e308, "b": {"a": -2.0}, "c": [{"a": 0}]}')

    assert parsed == {"a": 1.5e308, "b": {"a": -2.0}, "c": [{"a": 0}]}
