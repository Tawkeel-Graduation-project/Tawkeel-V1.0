"""Tests for retrieval eval set and metrics computation (SCRUM-423, SCRUM-424).

Validates:
- Eval set integrity: >=30 items, unique IDs, Arabic text, corpus validity.
- Metrics: Hit@1, Hit@3, Hit@5, MRR on all-hits, zero-hits, and mixed cases.
- Article number normalization.
- Handling of duplicate/tie articles in top-k results.
- Verified-only filtering.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.eval_retrieval import (
    calculate_hit_at_k,
    calculate_reciprocal_rank,
    evaluate_retrieval,
    format_console_report,
    normalize_article_number,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
EVAL_SET_PATH = BACKEND_DIR / "data" / "eval" / "retrieval_eval_set.jsonl"
CORPUS_PATH = BACKEND_DIR / "data" / "labor_law.jsonl"

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def load_corpus_articles() -> set[str]:
    """Extract set of all valid article numbers from the corpus."""
    articles = set()
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            norm = normalize_article_number(data.get("article_number"))
            if norm:
                articles.add(norm)
    return articles


def load_eval_questions() -> list[dict[str, Any]]:
    """Load evaluation questions dataset."""
    questions = []
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))
    return questions


class MockRetriever:
    """Mock retriever returning predetermined articles per question id or text."""

    def __init__(self, mapping: dict[str, list[Any]]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    async def retrieve(self, query_or_embedding: Any, *, limit: int) -> list[Any]:
        self.calls.append(str(query_or_embedding))
        # lookup by exact query text or default
        results = self.mapping.get(str(query_or_embedding), [])
        return results[:limit]


# --- SCRUM-423: Dataset Integrity Tests ---------------------------------------


def test_eval_set_minimum_count_and_uniqueness() -> None:
    questions = load_eval_questions()
    assert len(questions) >= 30, (
        f"Expected at least 30 questions, found {len(questions)}"
    )

    seen_ids = set()
    seen_questions = set()
    for q in questions:
        q_id = q.get("id")
        text = q.get("question", "").strip()

        assert q_id, "Question missing id"
        assert q_id not in seen_ids, f"Duplicate id: {q_id}"
        seen_ids.add(q_id)

        assert text, f"Empty question text for {q_id}"
        assert ARABIC_RE.search(text), f"Question {q_id} contains no Arabic"
        assert text not in seen_questions, f"Duplicate question text: {text}"
        seen_questions.add(text)


def test_eval_set_articles_exist_in_corpus() -> None:
    questions = load_eval_questions()
    corpus_articles = load_corpus_articles()

    for q in questions:
        q_id = q.get("id")
        relevant = q.get("relevant_articles", [])
        assert isinstance(relevant, list) and len(relevant) > 0, (
            f"{q_id} has no relevant_articles"
        )

        for art in relevant:
            norm = normalize_article_number(art)
            assert norm in corpus_articles, (
                f"Article '{art}' in question {q_id} does not exist in corpus"
            )


def test_eval_set_unverified_flag_and_required_fields() -> None:
    questions = load_eval_questions()
    for q in questions:
        q_id = q.get("id")
        assert q.get("lawyer_verified") is False, (
            f"Question {q_id} must have lawyer_verified=False until reviewed"
        )
        assert q.get("topic"), f"Question {q_id} missing topic"
        assert "notes" in q, f"Question {q_id} missing notes field for lawyer review"


# --- SCRUM-424: Metric Calculation Unit Tests ---------------------------------


@pytest.mark.parametrize(
    ("input_val", "expected"),
    [
        ("12", "12"),
        ("المادة 12", "12"),
        ("مادة 33", "33"),
        ("  45  ", "45"),
        ("issuance-1", "1"),
        (111, "111"),
        (None, None),
        ("", None),
    ],
)
def test_article_number_normalization(input_val: Any, expected: str | None) -> None:
    assert normalize_article_number(input_val) == expected


@pytest.mark.anyio
async def test_metrics_all_hits_perfect_score() -> None:
    questions = [
        {"id": "q1", "question": "سؤال 1", "relevant_articles": ["111"]},
        {"id": "q2", "question": "سؤال 2", "relevant_articles": ["33"]},
    ]
    mapping = {
        "سؤال 1": [
            SimpleNamespace(article_number="111"),
            SimpleNamespace(article_number="10"),
        ],
        "سؤال 2": [
            SimpleNamespace(article_number="33"),
            SimpleNamespace(article_number="40"),
        ],
    }
    retriever = MockRetriever(mapping)

    report = await evaluate_retrieval(questions, retriever, top_k=5)

    assert report["evaluated_count"] == 2
    assert report["hit_at_1"] == 1.0
    assert report["hit_at_3"] == 1.0
    assert report["hit_at_5"] == 1.0
    assert report["mrr"] == 1.0


@pytest.mark.anyio
async def test_metrics_zero_hits() -> None:
    questions = [
        {"id": "q1", "question": "سؤال 1", "relevant_articles": ["111"]},
        {"id": "q2", "question": "سؤال 2", "relevant_articles": ["33"]},
    ]
    mapping = {
        "سؤال 1": [SimpleNamespace(article_number="999")],
        "سؤال 2": [SimpleNamespace(article_number="888")],
    }
    retriever = MockRetriever(mapping)

    report = await evaluate_retrieval(questions, retriever, top_k=5)

    assert report["hit_at_1"] == 0.0
    assert report["hit_at_3"] == 0.0
    assert report["hit_at_5"] == 0.0
    assert report["mrr"] == 0.0


@pytest.mark.anyio
async def test_metrics_mixed_case_with_known_expected_values() -> None:
    """Test 4 questions with known ranks to verify exact metric mathematics:

    - Q1: Hit at rank 1 -> Hit@1=1, Hit@3=1, Hit@5=1, RR=1/1 = 1.0
    - Q2: Hit at rank 2 -> Hit@1=0, Hit@3=1, Hit@5=1, RR=1/2 = 0.5
    - Q3: Hit at rank 5 -> Hit@1=0, Hit@3=0, Hit@5=1, RR=1/5 = 0.2
    - Q4: Hit at rank 7 (outside top 5) -> Hit@1=0, Hit@3=0, Hit@5=0, RR=0.0

    Expected:
    - Hit@1: 1/4 = 0.25 (25%)
    - Hit@3: 2/4 = 0.50 (50%)
    - Hit@5: 3/4 = 0.75 (75%)
    - MRR: (1.0 + 0.5 + 0.2 + 0.0) / 4 = 1.7 / 4 = 0.425
    """
    questions = [
        {"id": "q1", "question": "س1", "relevant_articles": ["10"]},
        {"id": "q2", "question": "س2", "relevant_articles": ["20"]},
        {"id": "q3", "question": "س3", "relevant_articles": ["30"]},
        {"id": "q4", "question": "س4", "relevant_articles": ["40"]},
    ]
    mapping = {
        "س1": [
            SimpleNamespace(article_number="10"),
            SimpleNamespace(article_number="99"),
        ],
        "س2": [
            SimpleNamespace(article_number="99"),
            SimpleNamespace(article_number="20"),
        ],
        "س3": [
            SimpleNamespace(article_number="99"),
            SimpleNamespace(article_number="98"),
            SimpleNamespace(article_number="97"),
            SimpleNamespace(article_number="96"),
            SimpleNamespace(article_number="30"),
        ],
        "س4": [
            SimpleNamespace(article_number="99"),
            SimpleNamespace(article_number="98"),
            SimpleNamespace(article_number="97"),
            SimpleNamespace(article_number="96"),
            SimpleNamespace(article_number="95"),
            SimpleNamespace(article_number="94"),
            SimpleNamespace(article_number="40"),
        ],
    }
    retriever = MockRetriever(mapping)

    report = await evaluate_retrieval(questions, retriever, top_k=5)

    assert report["hit_at_1"] == 0.25
    assert report["hit_at_3"] == 0.50
    assert report["hit_at_5"] == 0.75
    assert report["mrr"] == 0.425


def test_calculate_hit_and_reciprocal_rank_duplicates_and_ties() -> None:
    # Multiple chunks with the same article number
    retrieved = ["111", "111", "112", "112", "113"]
    expected = ["112"]

    assert calculate_hit_at_k(retrieved, expected, 1) is False
    assert calculate_hit_at_k(retrieved, expected, 2) is False
    assert calculate_hit_at_k(retrieved, expected, 3) is True
    assert calculate_hit_at_k(retrieved, expected, 5) is True

    # First hit is at index 2 (rank 3)
    rr = calculate_reciprocal_rank(retrieved, expected, k=5)
    assert rr == pytest.approx(1.0 / 3.0)


@pytest.mark.anyio
async def test_verified_only_filtering() -> None:
    questions = [
        {
            "id": "q1",
            "question": "س1",
            "relevant_articles": ["10"],
            "lawyer_verified": False,
        },
        {
            "id": "q2",
            "question": "س2",
            "relevant_articles": ["20"],
            "lawyer_verified": True,
        },
        {
            "id": "q3",
            "question": "س3",
            "relevant_articles": ["30"],
            "lawyer_verified": False,
        },
        {
            "id": "q4",
            "question": "س4",
            "relevant_articles": ["40"],
            "lawyer_verified": True,
        },
    ]
    mapping = {
        "س2": [SimpleNamespace(article_number="20")],
        "س4": [SimpleNamespace(article_number="99")],
    }
    retriever = MockRetriever(mapping)

    report = await evaluate_retrieval(questions, retriever, top_k=5, verified_only=True)

    assert report["total_in_dataset"] == 4
    assert report["evaluated_count"] == 2
    assert report["verified_only"] is True
    # Q2 was hit, Q4 was not -> 1/2 = 0.50
    assert report["hit_at_5"] == 0.50
    assert report["mrr"] == 0.50


def test_console_report_format() -> None:
    sample_report = {
        "total_in_dataset": 10,
        "evaluated_count": 2,
        "verified_only": False,
        "hit_at_1": 0.5,
        "hit_at_3": 0.5,
        "hit_at_5": 1.0,
        "mrr": 0.75,
        "per_question": [
            {
                "id": "ret-01",
                "question": "سؤال تجريبي",
                "lawyer_verified": True,
                "expected_articles": ["111"],
                "retrieved_articles": ["111", "112"],
                "hit_at_5": True,
            }
        ],
    }
    formatted = format_console_report(sample_report)
    assert "Hit@5:  100.00%" in formatted
    assert "ret-01" in formatted
    assert "111" in formatted
