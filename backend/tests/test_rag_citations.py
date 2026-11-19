"""Tests for source labelling, citation attachment, and unsupported-claim marking."""

import json
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from services.llm import LLMMessage, MockLLMProvider, generate_structured
from services.rag import (
    EXCERPT_MAX_CHARS,
    MAX_SOURCES,
    AnswerStatus,
    Claim,
    GroundedAnswer,
    LegalAnswer,
    SourceChunk,
    SourceContext,
    SourceType,
    UnsupportedReason,
    ground_answer,
    make_excerpt,
    make_source_validator,
    mentioned_articles,
)

LAW = "Egyptian Labor Law 12-2003"


def _chunk(article: str | None, text: str | None = None, **overrides) -> SourceChunk:
    fields = {
        "chunk_id": uuid.uuid4(),
        "source_type": "law",
        "source_name": LAW,
        "article_number": article,
        "text": text or f"نص المادة {article}.",
    }
    fields.update(overrides)
    return SourceChunk(**fields)


@pytest.fixture
def context() -> SourceContext:
    """S1 = article 111, S2 = article 112, S3 = a ruling with no article number."""
    return SourceContext.from_chunks(
        [
            _chunk("111"),
            _chunk("112"),
            _chunk(None, source_type="ruling", source_name="نقض 1234 لسنة 80"),
        ]
    )


def _answer(*claims: tuple[str, list[str]]) -> LegalAnswer:
    return LegalAnswer(
        status=AnswerStatus.ANSWERED,
        claims=[Claim(text=text, source_ids=ids) for text, ids in claims],
    )


# --- SourceContext: labelling, dedupe, adapters ---------------------------------


def test_from_chunks_labels_in_retrieval_order_and_dedupes() -> None:
    first, second, third = _chunk("1"), _chunk("2"), _chunk("3")

    context = SourceContext.from_chunks([first, second, first, third, second])

    assert context.labels == ("S1", "S2", "S3")
    assert [context.get(label) for label in context.labels] == [first, second, third]
    assert "S2" in context and "S4" not in context and 42 not in context
    assert context.get("S9") is None and len(context) == 3


def test_from_chunks_keeps_only_the_top_ranked_sources() -> None:
    chunks = [_chunk(str(i)) for i in range(MAX_SOURCES + 5)]

    context = SourceContext.from_chunks(chunks)
    assert len(context) == MAX_SOURCES
    assert context.get(f"S{MAX_SOURCES}") == chunks[MAX_SOURCES - 1]

    assert len(SourceContext.from_chunks(chunks, max_sources=2)) == 2
    with pytest.raises(ValueError):
        SourceContext.from_chunks(chunks, max_sources=0)


def test_from_chunks_accepts_orm_rows_and_search_results() -> None:
    row = SimpleNamespace(
        id=uuid.uuid4(),
        source_type="law",
        source_name=LAW,
        article_number="69",
        source_date=date(2003, 4, 7),
        url="https://example.test/69",
        text="لا يجوز فصل العامل إلا إذا ارتكب خطأ جسيماً.",
    )

    context = SourceContext.from_chunks([(row, 0.12), row])

    chunk = context.get("S1")
    assert len(context) == 1
    assert chunk.chunk_id == row.id and chunk.source_type == SourceType.LAW
    assert chunk.article_number == "69" and chunk.source_date == date(2003, 4, 7)
    assert SourceChunk.from_legal_chunk(row) == chunk


def test_source_chunk_rejects_unknown_source_type() -> None:
    with pytest.raises(ValidationError):
        _chunk("1", source_type="legislation")


def test_empty_context() -> None:
    context = SourceContext.from_chunks([])

    assert context.labels == () and len(context) == 0


# --- make_source_validator ------------------------------------------------------


def test_validator_accepts_known_labels(context: SourceContext) -> None:
    validate = make_source_validator(context)

    assert validate(_answer(("نص", ["S1", "S3"]), ("نص آخر", ["S2"]))) == []


def test_validator_reports_unknown_ids_without_echoing_them(
    context: SourceContext,
) -> None:
    errors = make_source_validator(context)(_answer(("نص", ["S1", "S9", "UUID-X"])))

    assert errors == [
        "claims.0.source_ids.1: unknown source id; use only: S1, S2, S3",
        "claims.0.source_ids.2: unknown source id; use only: S1, S2, S3",
    ]


def test_validator_reports_duplicate_ids_within_a_claim(
    context: SourceContext,
) -> None:
    errors = make_source_validator(context)(_answer(("نص", ["S1", "S2", "S1"])))

    assert errors == ["claims.0.source_ids.2: duplicate source id in this claim"]


def test_validator_allows_same_id_across_claims(context: SourceContext) -> None:
    answer = _answer(("أ", ["S1"]), ("ب", ["S1"]))

    assert make_source_validator(context)(answer) == []


@pytest.mark.parametrize(
    "claims",
    [[("نص", [])], [("نص", []), ("نص آخر", [])], [("نص", ["S9"])]],
    ids=["one_uncited", "all_uncited", "only_unknown"],
)
def test_validator_rejects_answered_without_any_known_citation(
    context: SourceContext, claims
) -> None:
    errors = make_source_validator(context)(_answer(*claims))

    assert any("must cite at least one source" in e for e in errors)


def test_validator_does_not_reject_a_single_uncited_claim(
    context: SourceContext,
) -> None:
    answer = _answer(("نص مدعوم", ["S1"]), ("نص بلا مصدر", []))

    assert make_source_validator(context)(answer) == []


@pytest.mark.parametrize(
    "answer",
    [
        LegalAnswer(status=AnswerStatus.NO_SOURCE),
        LegalAnswer(
            status=AnswerStatus.NEEDS_CLARIFICATION,
            clarification_question="هل العقد محدد المدة؟",
        ),
    ],
    ids=["no_source", "needs_clarification"],
)
def test_validator_accepts_non_answered_statuses(answer: LegalAnswer) -> None:
    assert make_source_validator(SourceContext.from_chunks([]))(answer) == []


# --- Article mentions -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("وفقاً للمادة 111 والمادة ١١٢", {"111", "112"}),
        ("المادةُ (٦٩) من القانون", {"69"}),
        ("مادة رقم 47", {"47"}),
        ("ماده 069", {"69"}),
        ("بالمادة۱۲", {"12"}),
        ("وجود العامل تحت تأثير مادة مخدرة", set()),
        ("لا يذكر رقم مادة", set()),
    ],
)
def test_mentioned_articles(text: str, expected: set[str]) -> None:
    assert mentioned_articles(text) == expected


# --- ground_answer --------------------------------------------------------------


def test_supported_claims_get_citations(context: SourceContext) -> None:
    grounded = ground_answer(
        _answer(("يجب الإخطار قبل الإنهاء بشهرين وفقاً للمادة 111.", ["S1"])), context
    )

    assert grounded.status == AnswerStatus.ANSWERED
    assert grounded.has_unsupported_claims is False
    claim = grounded.claims[0]
    assert claim.supported and claim.unsupported_reason is None
    citation = grounded.citations[0]
    assert citation.label == "S1" and citation.article_number == "111"
    assert citation.chunk_id == context.get("S1").chunk_id
    assert citation.source_type == SourceType.LAW and citation.source_name == LAW
    assert citation.excerpt == "نص المادة 111."


def test_claim_with_empty_source_ids_is_marked(context: SourceContext) -> None:
    grounded = ground_answer(
        _answer(("حكم مدعوم.", ["S1"]), ("حكم بلا مصدر.", [])), context
    )

    assert grounded.status == AnswerStatus.ANSWERED
    assert grounded.has_unsupported_claims is True
    marked = grounded.claims[1]
    assert marked.text == "حكم بلا مصدر." and not marked.supported
    assert marked.unsupported_reason == UnsupportedReason.NO_SOURCE_CITED
    assert [c.label for c in grounded.citations] == ["S1"]


def test_claim_with_only_unknown_ids_is_marked(context: SourceContext) -> None:
    grounded = ground_answer(_answer(("أ", ["S1"]), ("ب", ["S9"])), context)

    marked = grounded.claims[1]
    assert marked.source_ids == []
    assert marked.unsupported_reason == UnsupportedReason.NO_SOURCE_CITED


@pytest.mark.parametrize(
    "text",
    ["طبقاً للمادة 69 يجوز الفصل.", "طبقاً للمادة ٦٩ يجوز الفصل."],
    ids=["western_digits", "arabic_indic_digits"],
)
def test_article_mismatch_is_marked(context: SourceContext, text: str) -> None:
    grounded = ground_answer(_answer(("أ", ["S2"]), (text, ["S1"])), context)

    mismatched = grounded.claims[1]
    assert not mismatched.supported
    assert mismatched.unsupported_reason == UnsupportedReason.ARTICLE_MISMATCH
    assert mismatched.source_ids == ["S1"]
    assert [c.label for c in grounded.citations] == ["S2"]


@pytest.mark.parametrize(
    "text",
    ["مهلة الإخطار شهران (المادة 111).", "مهلة الإخطار شهران (المادة ١١١)."],
    ids=["western_digits", "arabic_indic_digits"],
)
def test_article_match_with_either_digit_style(
    context: SourceContext, text: str
) -> None:
    grounded = ground_answer(_answer((text, ["S1"])), context)

    assert grounded.claims[0].supported


def test_source_article_number_digits_are_normalized() -> None:
    context = SourceContext.from_chunks([_chunk("٤٧")])

    grounded = ground_answer(_answer(("وفقاً للمادة 47.", ["S1"])), context)

    assert grounded.claims[0].supported


def test_multiple_sources_one_matching_article_is_supported(
    context: SourceContext,
) -> None:
    grounded = ground_answer(_answer(("وفقاً للمادة 112.", ["S1", "S2"])), context)

    assert grounded.claims[0].supported
    assert [c.label for c in grounded.citations] == ["S1", "S2"]


def test_article_mentioned_but_only_ruling_cited_is_mismatch(
    context: SourceContext,
) -> None:
    grounded = ground_answer(
        _answer(("أ", ["S1"]), ("قضت المحكمة بتطبيق المادة 111.", ["S3"])), context
    )

    assert grounded.claims[1].unsupported_reason == UnsupportedReason.ARTICLE_MISMATCH


def test_citations_deduped_in_first_cited_order(context: SourceContext) -> None:
    grounded = ground_answer(
        _answer(("أ", ["S3", "S1"]), ("ب", ["S1", "S2"]), ("ج", ["S3"])), context
    )

    assert [c.label for c in grounded.citations] == ["S3", "S1", "S2"]


def test_sources_only_cited_by_unsupported_claims_are_not_cited(
    context: SourceContext,
) -> None:
    grounded = ground_answer(
        _answer(("أ", ["S2"]), ("وفقاً للمادة 69.", ["S1", "S3"])), context
    )

    assert [c.label for c in grounded.citations] == ["S2"]


def test_duplicate_ids_in_a_claim_are_collapsed(context: SourceContext) -> None:
    grounded = ground_answer(_answer(("أ", ["S1", "S1", "S2"])), context)

    assert grounded.claims[0].source_ids == ["S1", "S2"]


@pytest.mark.parametrize(
    "claims",
    [
        [("بلا مصدر", [])],
        [("وفقاً للمادة 69.", ["S1"]), ("بلا مصدر", [])],
        [("مصدر غير معروف", ["S7"])],
    ],
    ids=["uncited", "mismatch_and_uncited", "unknown_only"],
)
def test_answered_without_supported_claims_downgrades_to_no_source(
    context: SourceContext, claims
) -> None:
    grounded = ground_answer(_answer(*claims), context)

    assert grounded == GroundedAnswer(status=AnswerStatus.NO_SOURCE)
    assert grounded.claims == [] and grounded.citations == []
    assert grounded.has_unsupported_claims is False


@pytest.mark.parametrize(
    "answer",
    [
        LegalAnswer(status=AnswerStatus.NO_SOURCE),
        LegalAnswer(
            status=AnswerStatus.NEEDS_CLARIFICATION,
            clarification_question="هل العقد محدد المدة؟",
        ),
    ],
    ids=["no_source", "needs_clarification"],
)
def test_non_answered_statuses_pass_through(
    context: SourceContext, answer: LegalAnswer
) -> None:
    grounded = ground_answer(answer, context)

    assert grounded.status == answer.status
    assert grounded.clarification_question == answer.clarification_question
    assert grounded.claims == [] and grounded.citations == []


def test_grounded_answer_rejects_inconsistent_state() -> None:
    with pytest.raises(ValidationError):
        GroundedAnswer(status=AnswerStatus.ANSWERED)
    with pytest.raises(ValidationError):
        GroundedAnswer(status=AnswerStatus.NO_SOURCE, has_unsupported_claims=True)
    with pytest.raises(ValidationError):
        GroundedAnswer(status=AnswerStatus.NEEDS_CLARIFICATION)


# --- Excerpts -------------------------------------------------------------------


def test_excerpt_keeps_short_text_and_collapses_whitespace() -> None:
    assert make_excerpt("  لا يجوز\n\nفصل   العامل  ") == "لا يجوز فصل العامل"


def test_excerpt_truncates_on_a_word_boundary() -> None:
    words = [f"كلمة{i}" for i in range(200)]
    text = " ".join(words)

    excerpt = make_excerpt(text)

    assert len(excerpt) <= EXCERPT_MAX_CHARS and excerpt.endswith("…")
    assert excerpt[:-1].split(" ") == words[: len(excerpt[:-1].split(" "))]


def test_excerpt_of_one_long_word_is_hard_cut() -> None:
    excerpt = make_excerpt("ا" * 1000, max_chars=50)

    assert len(excerpt) == 50 and excerpt.endswith("…")


def test_citation_excerpt_is_truncated(context: SourceContext) -> None:
    long_text = " ".join(["العامل يستحق أجره كاملاً"] * 100)
    context = SourceContext.from_chunks([_chunk("111", text=long_text)])

    grounded = ground_answer(_answer(("أ", ["S1"])), context)

    assert len(grounded.citations[0].excerpt) <= EXCERPT_MAX_CHARS


# --- End to end with generate_structured ----------------------------------------


@pytest.mark.anyio
async def test_unknown_id_is_repaired_then_grounded(context: SourceContext) -> None:
    def respond(source_id: str) -> str:
        return json.dumps(
            {
                "status": "answered",
                "claims": [
                    {
                        "text": "مهلة الإخطار شهران وفقاً للمادة 111.",
                        "source_ids": [source_id],
                    }
                ],
            },
            ensure_ascii=False,
        )

    provider = MockLLMProvider(response_sequence=[respond("S9"), respond("S1")])

    result = await generate_structured(
        provider,
        [LLMMessage.user("ما مهلة الإخطار؟")],
        LegalAnswer,
        semantic_validator=make_source_validator(context),
    )

    assert result.ok and result.attempts == 2
    repair_request = provider.recorded_calls[1][-1].content
    assert "unknown source id; use only: S1, S2, S3" in repair_request
    grounded = ground_answer(result.value, context)
    assert grounded.status == AnswerStatus.ANSWERED
    assert grounded.claims[0].supported
    assert [c.label for c in grounded.citations] == ["S1"]
