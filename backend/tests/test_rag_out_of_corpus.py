"""Out-of-corpus test set and retrieval confidence threshold tests.

SCRUM-326, SCRUM-327.

Acceptance criteria:
- Low retrieval confidence triggers a clear refusal (no model call, empty citations).
- Tested on at least 20 out-of-corpus questions across diverse domains.
- In-corpus questions with high retrieval confidence are answered with citations.
- Boundary conditions for the threshold (just below, equal, just above).
- No fabricated citations: the response never cites unretrieved articles.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from services.llm import MockLLMProvider
from services.rag.chain import answer_question
from services.rag.presenter import MESSAGES_AR, ReplyKind, present_outcome
from services.rag.schemas import AnswerStatus

DATA_FILE = Path(__file__).parent / "data" / "out_of_corpus_questions.jsonl"

IN_CORPUS_QUESTION = "ما هي مهلة الإخطار قبل إنهاء عقد العمل غير محدد المدة؟"


def load_out_of_corpus_questions() -> list[dict[str, str]]:
    """Load out-of-corpus Arabic questions from JSONL test dataset."""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _chunk(
    article: str | None,
    text: str = (
        "يجب أن يتم الإخطار قبل الإنهاء بشهرين "
        "إذا كانت مدة خدمة العامل أقل من عشر سنوات."
    ),
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        source_type="law",
        source_name="قانون العمل 12 لسنة 2003",
        article_number=article,
        source_date=None,
        url=None,
        text=text,
    )


class FakeEmbedder:
    """Mock embedder returning a fixed vector."""

    async def embed_query(self, text: str) -> list[float]:
        return [0.01] * 1024


class FakeRetriever:
    """Mock retriever returning fixed (chunk, score) results."""

    def __init__(self, results: list | None = None) -> None:
        self.results = results or []
        self.calls: list[int] = []

    async def retrieve(self, embedding, *, limit: int):
        self.calls.append(limit)
        return self.results[:limit]


def _llm_response(article_number: str = "111", source_id: str = "S1") -> str:
    return json.dumps(
        {
            "status": "answered",
            "claims": [
                {
                    "text": f"مدة الإخطار هي شهران وفقاً للمادة {article_number}.",
                    "source_ids": [source_id],
                }
            ],
        },
        ensure_ascii=False,
    )


# --- Dataset Integrity --------------------------------------------------------


def test_out_of_corpus_dataset_integrity() -> None:
    questions = load_out_of_corpus_questions()
    assert len(questions) >= 20, f"Expected at least 20 questions, got {len(questions)}"

    seen_ids = set()
    categories = set()
    for item in questions:
        assert "id" in item and item["id"]
        assert "question" in item and item["question"].strip()
        assert "category" in item and item["category"]
        assert item["id"] not in seen_ids, f"Duplicate ID: {item['id']}"
        seen_ids.add(item["id"])
        categories.add(item["category"])

    expected_categories = {
        "criminal_law",
        "family_law",
        "tax_law",
        "foreign_law",
        "cooking",
        "weather",
        "sports",
        "chit_chat",
        "near_miss",
    }
    assert expected_categories <= categories


# --- Out-of-Corpus Refusal: Low Scores & Empty Results -------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    "case",
    load_out_of_corpus_questions(),
    ids=[c["id"] for c in load_out_of_corpus_questions()],
)
async def test_out_of_corpus_low_score_triggers_refusal(case: dict[str, str]) -> None:
    """Every out-of-corpus question with low score is refused without LLM call."""
    retriever = FakeRetriever(results=[(_chunk("111"), 0.20)])  # below default 0.50
    provider = MockLLMProvider(response_sequence=[_llm_response()])

    outcome = await answer_question(
        case["question"],
        embedder=FakeEmbedder(),
        retriever=retriever,
        provider=provider,
    )

    assert outcome.ok
    assert outcome.answer is not None
    assert outcome.answer.status == AnswerStatus.NO_SOURCE
    assert outcome.attempts == 0
    assert outcome.source_count == 0
    assert provider.recorded_calls == []

    reply = present_outcome(outcome)
    assert reply.kind == ReplyKind.NO_SOURCE
    assert reply.notice is not None
    assert reply.notice.message_ar == MESSAGES_AR[ReplyKind.NO_SOURCE]
    assert reply.citations == []
    assert reply.claims == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "case",
    load_out_of_corpus_questions()[:5],
    ids=[c["id"] for c in load_out_of_corpus_questions()[:5]],
)
async def test_out_of_corpus_empty_results_triggers_refusal(
    case: dict[str, str],
) -> None:
    """Empty retrieval results trigger immediate refusal without calling LLM."""
    retriever = FakeRetriever(results=[])
    provider = MockLLMProvider(response_sequence=[_llm_response()])

    outcome = await answer_question(
        case["question"],
        embedder=FakeEmbedder(),
        retriever=retriever,
        provider=provider,
    )

    assert outcome.ok
    assert outcome.answer is not None
    assert outcome.answer.status == AnswerStatus.NO_SOURCE
    assert outcome.attempts == 0
    assert provider.recorded_calls == []

    reply = present_outcome(outcome)
    assert reply.kind == ReplyKind.NO_SOURCE
    assert reply.citations == []
    assert reply.claims == []
    assert reply.notice is not None
    assert reply.notice.message_ar == MESSAGES_AR[ReplyKind.NO_SOURCE]


# --- In-Corpus High Score: Answered with Citations ----------------------------


@pytest.mark.anyio
async def test_in_corpus_high_score_is_answered_with_citations() -> None:
    """In-corpus question with score above threshold is answered with citations."""
    chunk = _chunk("111")
    retriever = FakeRetriever(results=[(chunk, 0.85)])  # well above 0.50
    provider = MockLLMProvider(response_sequence=[_llm_response("111")])

    outcome = await answer_question(
        IN_CORPUS_QUESTION,
        embedder=FakeEmbedder(),
        retriever=retriever,
        provider=provider,
    )

    assert outcome.ok
    assert outcome.answer is not None
    assert outcome.answer.status == AnswerStatus.ANSWERED
    assert outcome.attempts == 1
    assert len(provider.recorded_calls) == 1

    reply = present_outcome(outcome)
    assert reply.kind == ReplyKind.ANSWERED
    assert len(reply.citations) == 1
    assert reply.citations[0].article_number == "111"
    assert reply.citations[0].chunk_id == chunk.id
    assert len(reply.claims) == 1
    assert reply.claims[0].supported is True


# --- Boundary Tests (Just Below, Equal, Just Above) ---------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("score", "threshold", "expected_status", "should_call_llm"),
    [
        (0.49, 0.50, AnswerStatus.NO_SOURCE, False),  # just below: refused
        (0.50, 0.50, AnswerStatus.ANSWERED, True),  # equal: accepted
        (0.51, 0.50, AnswerStatus.ANSWERED, True),  # just above: accepted
    ],
    ids=["just_below_refused", "equal_accepted", "just_above_accepted"],
)
async def test_threshold_boundary_cases(
    score: float,
    threshold: float,
    expected_status: AnswerStatus,
    should_call_llm: bool,
) -> None:
    chunk = _chunk("111")
    retriever = FakeRetriever(results=[(chunk, score)])
    provider = MockLLMProvider(response_sequence=[_llm_response("111")])

    outcome = await answer_question(
        IN_CORPUS_QUESTION,
        embedder=FakeEmbedder(),
        retriever=retriever,
        provider=provider,
        min_score=threshold,
    )

    assert outcome.ok
    assert outcome.answer is not None
    assert outcome.answer.status == expected_status
    if should_call_llm:
        assert outcome.attempts == 1
        assert len(provider.recorded_calls) == 1
        reply = present_outcome(outcome)
        assert reply.kind == ReplyKind.ANSWERED
        assert len(reply.citations) == 1
    else:
        assert outcome.attempts == 0
        assert provider.recorded_calls == []
        reply = present_outcome(outcome)
        assert reply.kind == ReplyKind.NO_SOURCE
        assert reply.citations == []


# --- Edge Cases: None Scores, Mixed, Zero Threshold ---------------------------


@pytest.mark.anyio
async def test_edge_case_none_scores_refuses() -> None:
    chunk = _chunk("111")
    retriever = FakeRetriever(results=[(chunk, None)])
    provider = MockLLMProvider(response_sequence=[_llm_response()])

    outcome = await answer_question(
        IN_CORPUS_QUESTION,
        embedder=FakeEmbedder(),
        retriever=retriever,
        provider=provider,
        min_score=0.5,
    )

    assert outcome.ok
    assert outcome.answer.status == AnswerStatus.NO_SOURCE
    assert outcome.attempts == 0
    assert provider.recorded_calls == []
    reply = present_outcome(outcome)
    assert reply.kind == ReplyKind.NO_SOURCE
    assert reply.citations == []


@pytest.mark.anyio
async def test_edge_case_mixed_none_and_low_score_refuses() -> None:
    c1, c2 = _chunk("111"), _chunk("112")
    retriever = FakeRetriever(results=[(c1, None), (c2, 0.30)])
    provider = MockLLMProvider(response_sequence=[_llm_response()])

    outcome = await answer_question(
        IN_CORPUS_QUESTION,
        embedder=FakeEmbedder(),
        retriever=retriever,
        provider=provider,
        min_score=0.5,
    )

    assert outcome.answer.status == AnswerStatus.NO_SOURCE
    assert provider.recorded_calls == []


@pytest.mark.anyio
async def test_edge_case_mixed_none_and_high_score_accepted() -> None:
    c1, c2 = _chunk("111"), _chunk("112")
    retriever = FakeRetriever(results=[(c1, None), (c2, 0.80)])
    provider = MockLLMProvider(response_sequence=[_llm_response("112", source_id="S2")])

    outcome = await answer_question(
        IN_CORPUS_QUESTION,
        embedder=FakeEmbedder(),
        retriever=retriever,
        provider=provider,
        min_score=0.5,
    )

    assert outcome.answer.status == AnswerStatus.ANSWERED
    assert outcome.attempts == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("score", "accepted"),
    [
        (0.0, True),  # equal = accepted
        (-0.1, False),  # below = refused
        (0.1, True),  # above = accepted
    ],
    ids=["zero_equal_accepted", "negative_refused", "positive_accepted"],
)
async def test_edge_case_zero_threshold(score: float, accepted: bool) -> None:
    chunk = _chunk("111")
    retriever = FakeRetriever(results=[(chunk, score)])
    provider = MockLLMProvider(response_sequence=[_llm_response("111")])

    outcome = await answer_question(
        IN_CORPUS_QUESTION,
        embedder=FakeEmbedder(),
        retriever=retriever,
        provider=provider,
        min_score=0.0,
    )

    if accepted:
        assert outcome.answer.status == AnswerStatus.ANSWERED
        assert len(provider.recorded_calls) == 1
    else:
        assert outcome.answer.status == AnswerStatus.NO_SOURCE
        assert provider.recorded_calls == []


# --- No Fabricated Citations --------------------------------------------------


@pytest.mark.anyio
async def test_no_fabricated_citations_in_reply() -> None:
    """Citations in the assistant reply only reference chunks actually retrieved."""
    retrieved_chunk = _chunk("111")
    retriever = FakeRetriever(results=[(retrieved_chunk, 0.90)])

    # Model claims cite S1 (valid) and try to mention unretrieved articles
    hallucinated_model_response = json.dumps(
        {
            "status": "answered",
            "claims": [
                {
                    "text": "يجب الإخطار بشهرين وفقاً للمادة 111.",
                    "source_ids": ["S1"],
                },
                {
                    "text": "كما تنص المادة 999 غير الموجودة على حكم إضافي.",
                    "source_ids": ["S1"],
                },
            ],
        },
        ensure_ascii=False,
    )
    provider = MockLLMProvider(response_sequence=[hallucinated_model_response])

    outcome = await answer_question(
        IN_CORPUS_QUESTION,
        embedder=FakeEmbedder(),
        retriever=retriever,
        provider=provider,
        min_score=0.50,
    )

    reply = present_outcome(outcome)
    assert reply.kind == ReplyKind.ANSWERED

    # Every citation article_number must come from retrieved chunks
    retrieved_articles = {retrieved_chunk.article_number}
    cited_articles = {c.article_number for c in reply.citations}
    assert cited_articles <= retrieved_articles
    assert "999" not in cited_articles
    assert "50" not in cited_articles

    # Claim mentioning unretrieved article 999 must be marked unsupported
    unsupported_claims = [c for c in reply.claims if not c.supported]
    assert len(unsupported_claims) == 1
    assert "999" in unsupported_claims[0].text
