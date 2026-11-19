"""Tests for the user-facing reply presenter (SCRUM-309)."""

import json
import logging
import re
import uuid

import pytest
from services.llm.structured import FailureKind
from services.rag.chain import AnswerFailure, AnswerOutcome
from services.rag.presenter import (
    FAILURE_REPLY_KINDS,
    MESSAGES_AR,
    NOTICE_FLAGS,
    AssistantReply,
    ReplyKind,
    present_outcome,
)
from services.rag.schemas import (
    AnswerStatus,
    Citation,
    GroundedAnswer,
    GroundedClaim,
    UnsupportedReason,
)

ARABIC = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]")
ENGLISH_ERROR_WORDS = (
    "error",
    "exception",
    "traceback",
    "failed",
    "failure",
    "timeout",
    "invalid",
    "json",
    "schema",
    "llm",
    "provider",
)

TRANSIENT = [
    AnswerFailure.EMBEDDING_UNAVAILABLE,
    AnswerFailure.RETRIEVAL_UNAVAILABLE,
    AnswerFailure.PROVIDER_UNAVAILABLE,
    AnswerFailure.TIMEOUT,
    AnswerFailure.CONFIGURATION_ERROR,
]
OUTPUT_FAILURES = [
    AnswerFailure.INVALID_JSON,
    AnswerFailure.SCHEMA_MISMATCH,
    AnswerFailure.SEMANTIC_INVALID,
]


def _citation(label: str = "S1", article: str = "4") -> Citation:
    return Citation(
        label=label,
        chunk_id=uuid.UUID(int=1),
        source_type="law",
        source_name="قانون العمل 12 لسنة 2003",
        article_number=article,
        excerpt="نص المادة.",
    )


def _answered(*, unsupported: bool = False) -> AnswerOutcome:
    claims = [GroundedClaim(text="ادعاء مدعوم.", source_ids=["S1"], supported=True)]
    if unsupported:
        claims.append(
            GroundedClaim(
                text="ادعاء بلا سند.",
                source_ids=[],
                supported=False,
                unsupported_reason=UnsupportedReason.NO_SOURCE_CITED,
            )
        )
    answer = GroundedAnswer(
        status=AnswerStatus.ANSWERED,
        claims=claims,
        citations=[_citation()],
        has_unsupported_claims=unsupported,
    )
    return AnswerOutcome.success(answer, attempts=1, source_count=4)


def _status_only(status: AnswerStatus, question: str | None = None) -> AnswerOutcome:
    answer = GroundedAnswer(status=status, clarification_question=question)
    return AnswerOutcome.success(answer, attempts=1, source_count=2)


def _all_replies() -> list[AssistantReply]:
    outcomes = [
        _answered(),
        _answered(unsupported=True),
        _status_only(AnswerStatus.NO_SOURCE),
        _status_only(AnswerStatus.NEEDS_CLARIFICATION, "ما نوع العقد؟"),
        *(AnswerOutcome.failed(f, attempts=2, source_count=3) for f in AnswerFailure),
    ]
    return [present_outcome(outcome) for outcome in outcomes]


def _user_facing_strings(reply: AssistantReply) -> list[str]:
    strings = [reply.disclaimer_ar]
    if reply.notice is not None:
        strings.append(reply.notice.message_ar)
    return strings


# --- exhaustiveness -----------------------------------------------------------


def test_every_answer_failure_is_mapped():
    assert set(FAILURE_REPLY_KINDS) == set(AnswerFailure)


def test_answer_failure_includes_every_failure_kind():
    # A new FailureKind reaches AnswerFailure, and so this mapping test.
    assert {k.value for k in FailureKind} <= {f.value for f in AnswerFailure}


def test_every_reply_kind_has_flags_and_copy():
    assert set(NOTICE_FLAGS) == set(ReplyKind)
    for kind in ReplyKind:
        if kind != ReplyKind.ANSWERED:
            assert kind in MESSAGES_AR


# --- the mapping table --------------------------------------------------------


def test_answered_without_unsupported_claims_has_no_notice():
    reply = present_outcome(_answered())
    assert reply.kind == ReplyKind.ANSWERED
    assert reply.notice is None
    assert reply.has_unsupported_claims is False
    assert [c.supported for c in reply.claims] == [True]
    assert reply.claims[0].source_ids == ["S1"]
    assert [c.label for c in reply.citations] == ["S1"]
    assert reply.clarification_question is None


def test_answered_with_unsupported_claims_warns():
    reply = present_outcome(_answered(unsupported=True))
    assert reply.kind == ReplyKind.ANSWERED
    assert reply.has_unsupported_claims is True
    assert [c.supported for c in reply.claims] == [True, False]
    assert reply.notice is not None
    assert reply.notice.kind == ReplyKind.ANSWERED
    assert reply.notice.message_ar == MESSAGES_AR["unsupported_claims"]
    assert reply.notice.show_lawyer_cta is False


def test_needs_clarification_shows_the_model_question():
    reply = present_outcome(
        _status_only(AnswerStatus.NEEDS_CLARIFICATION, "هل العقد محدد المدة؟")
    )
    assert reply.kind == ReplyKind.CLARIFICATION
    assert reply.clarification_question == "هل العقد محدد المدة؟"
    assert reply.claims == [] and reply.citations == []
    assert reply.notice is not None
    assert reply.notice.show_lawyer_cta is False


def test_no_source():
    reply = present_outcome(_status_only(AnswerStatus.NO_SOURCE))
    assert reply.kind == ReplyKind.NO_SOURCE
    assert reply.notice is not None
    assert reply.notice.retryable is False
    assert reply.notice.show_lawyer_cta is True
    assert reply.claims == [] and reply.citations == []


def test_no_sources_at_all_is_no_source():
    # The chain's "no sources, LLM not called" path.
    outcome = AnswerOutcome.success(GroundedAnswer(status=AnswerStatus.NO_SOURCE), 0, 0)
    assert present_outcome(outcome).kind == ReplyKind.NO_SOURCE


def test_invalid_question():
    reply = present_outcome(AnswerOutcome.failed(AnswerFailure.INVALID_QUESTION))
    assert reply.kind == ReplyKind.INVALID_QUESTION
    assert reply.notice is not None
    assert reply.notice.retryable is True
    assert reply.notice.show_lawyer_cta is False


@pytest.mark.parametrize("failure", TRANSIENT)
def test_transient_failures_are_temporarily_unavailable(failure):
    reply = present_outcome(AnswerOutcome.failed(failure, attempts=2))
    assert reply.kind == ReplyKind.TEMPORARILY_UNAVAILABLE
    assert reply.notice is not None
    assert reply.notice.kind == ReplyKind.TEMPORARILY_UNAVAILABLE
    assert reply.notice.retryable is True
    assert reply.notice.show_lawyer_cta is True
    assert reply.claims == [] and reply.citations == []


@pytest.mark.parametrize("failure", OUTPUT_FAILURES)
def test_output_failures_are_answer_failed(failure):
    reply = present_outcome(AnswerOutcome.failed(failure, attempts=2))
    assert reply.kind == ReplyKind.ANSWER_FAILED
    assert reply.notice is not None
    assert reply.notice.retryable is True
    assert reply.notice.show_lawyer_cta is True


def test_table_covers_every_failure_exactly_once():
    covered = [AnswerFailure.INVALID_QUESTION, *TRANSIENT, *OUTPUT_FAILURES]
    assert sorted(covered) == sorted(AnswerFailure)


# --- safety of user-facing strings --------------------------------------------


@pytest.mark.parametrize("text", list(MESSAGES_AR.values()))
def test_every_message_is_non_empty_arabic(text):
    assert text.strip()
    assert ARABIC.search(text)
    assert not LATIN.search(text)


def test_no_reply_string_leaks_codes_or_english():
    codes = {f.value for f in AnswerFailure} | {k.value for k in ReplyKind}
    for reply in _all_replies():
        for text in _user_facing_strings(reply):
            assert ARABIC.search(text)
            assert not LATIN.search(text), text
            lowered = text.lower()
            assert not any(word in lowered for word in ENGLISH_ERROR_WORDS)
            assert not any(code in text for code in codes)


def test_notice_text_comes_only_from_the_copy_table():
    allowed = set(MESSAGES_AR.values())
    for reply in _all_replies():
        for text in _user_facing_strings(reply):
            assert text in allowed


def test_disclaimer_is_always_present():
    for reply in _all_replies():
        assert reply.disclaimer_ar == MESSAGES_AR["disclaimer"]


def test_internal_unsupported_reason_is_not_exposed():
    payload = present_outcome(_answered(unsupported=True)).model_dump(mode="json")
    assert all("unsupported_reason" not in claim for claim in payload["claims"])
    assert UnsupportedReason.NO_SOURCE_CITED.value not in json.dumps(payload)


def test_failure_reply_json_has_no_failure_code():
    for failure in AnswerFailure:
        reply = present_outcome(AnswerOutcome.failed(failure))
        payload = json.dumps(reply.model_dump(mode="json"), ensure_ascii=False)
        if failure.value not in {k.value for k in ReplyKind}:
            assert failure.value not in payload


# --- serialization and logging ------------------------------------------------


def test_reply_serializes_to_json():
    for reply in _all_replies():
        payload = json.loads(reply.model_dump_json())
        assert set(payload) == {
            "kind",
            "claims",
            "citations",
            "has_unsupported_claims",
            "clarification_question",
            "notice",
            "disclaimer_ar",
        }
        assert AssistantReply.model_validate(payload) == reply


def test_citation_serializes_with_string_uuid():
    payload = json.loads(present_outcome(_answered()).model_dump_json())
    assert payload["citations"][0]["chunk_id"] == str(uuid.UUID(int=1))


def test_reply_is_frozen():
    reply = present_outcome(_answered())
    with pytest.raises(ValueError):
        reply.kind = ReplyKind.NO_SOURCE


def test_failure_kind_is_logged_at_info_without_text(caplog):
    caplog.set_level(logging.INFO, logger="services.rag.presenter")
    present_outcome(AnswerOutcome.failed(AnswerFailure.TIMEOUT, attempts=3))
    records = [r for r in caplog.records if r.name == "services.rag.presenter"]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    message = records[0].getMessage()
    assert "kind=temporarily_unavailable" in message
    assert "failure=timeout" in message


def test_answered_log_has_no_claim_text(caplog):
    caplog.set_level(logging.INFO, logger="services.rag.presenter")
    present_outcome(_answered(unsupported=True))
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "kind=answered" in text
    assert "ادعاء" not in text
