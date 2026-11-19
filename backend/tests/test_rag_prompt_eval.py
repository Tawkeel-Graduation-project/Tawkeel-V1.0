"""CI checks for the SCRUM-325 prompt eval: dataset, prompt layout, and a replay of
the real model's recorded outputs through validation and grounding.

No model or network is needed: the replay reads the outputs saved by
``scripts/rag_prompt_eval.py``.
"""

import json
import uuid
from collections import Counter
from pathlib import Path

import pytest
from services.llm.exceptions import OutputValidationError
from services.llm.models import MessageRole
from services.llm.structured import validate_output
from services.rag.citations import ground_answer, make_source_validator
from services.rag.prompts import (
    QUESTION_CLOSE,
    QUESTION_OPEN,
    SOURCES_CLOSE,
    SOURCES_OPEN,
    SYSTEM_PROMPT,
    build_messages,
)
from services.rag.schemas import LegalAnswer
from services.rag.sources import SourceChunk, SourceContext

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATASET_PATH = DATA_DIR / "eval" / "prompt_eval.jsonl"
# The run whose prompt is committed in services/rag/prompts.py (baseline; the
# improved prompt was tested and reverted).
KEPT_RUN_PATH = DATA_DIR / "eval" / "results" / "baseline.json"
SMOKE_GOLD = {"4", "1", "33", "5", "37"}  # questions used by rag_smoke.py
OUTPUT_FAILURES = {"invalid_json", "schema_mismatch", "semantic_invalid"}
# Outputs accepted when the run was recorded but rejected by a later fix:
# case id -> the field the error names. neg-05's clarification question drifts
# into Chinese; the Arabic-language guard now rejects it.
REJECTED_SINCE_RECORDING = {"neg-05": "clarification_question"}


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


CASES = _load_jsonl(DATASET_PATH)
ARTICLES = {r["id"]: r for r in _load_jsonl(DATA_DIR / "labor_law.jsonl")}
QUESTIONS = _load_jsonl(DATA_DIR / "questions.jsonl")
KEPT_RUN = json.loads(KEPT_RUN_PATH.read_text(encoding="utf-8"))
RESULTS = {r["id"]: r for r in KEPT_RUN["results"]}


def _of_kind(kind: str) -> list[dict]:
    return [c for c in CASES if c["kind"] == kind]


def _context(case: dict) -> SourceContext:
    return SourceContext.from_chunks(
        SourceChunk(
            chunk_id=uuid.uuid5(uuid.NAMESPACE_URL, f"labor-law/{key}"),
            source_type="law",
            source_name=ARTICLES[key]["source_name"],
            article_number=ARTICLES[key]["article_number"],
            text=ARTICLES[key]["text"],
        )
        for key in case["source_articles"]
    )


# --- dataset integrity ----------------------------------------------------------


def test_case_counts():
    assert Counter(c["kind"] for c in CASES) == {
        "positive": 20,
        "negative": 5,
        "clarification": 3,
    }
    assert len({c["id"] for c in CASES}) == len(CASES)


def test_positive_stratification():
    assert Counter(c["style"] for c in _of_kind("positive")) == {
        "colloquial": 14,
        "scenario": 4,
        "formal": 2,
    }


def test_positives_are_distinct_real_questions_not_used_by_smoke():
    positives = _of_kind("positive")
    golds = [c["gold_article"] for c in positives]
    assert len(set(golds)) == len(golds)
    assert not set(golds) & SMOKE_GOLD
    known = {(q["question"], q["article_number"], q["style"]) for q in QUESTIONS}
    for case in positives:
        assert (case["question"], case["gold_article"], case["style"]) in known


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_sources_exist_and_are_unique(case):
    sources = case["source_articles"]
    assert len(sources) == 4
    assert len(set(sources)) == 4
    assert all(key in ARTICLES for key in sources)
    numbers = [ARTICLES[key]["article_number"] for key in sources]
    assert len(set(numbers)) == 4  # article numbers identify sources unambiguously


def test_expected_status_by_kind():
    expected = {
        "positive": "answered",
        "negative": "no_source",
        "clarification": "needs_clarification",
    }
    for case in CASES:
        assert case["expected_status"] == expected[case["kind"]]


def test_gold_present_in_positives():
    for case in _of_kind("positive"):
        assert case["gold_article"] in case["source_articles"]


def test_gold_removed_in_negatives():
    positives = {c["id"]: c for c in _of_kind("positive")}
    for case in _of_kind("negative"):
        base = positives[case["based_on"]]
        assert case["question"] == base["question"]
        assert case["gold_article"] == base["gold_article"]
        assert case["gold_article"] not in case["source_articles"]


def test_clarification_cases_have_no_gold():
    for case in _of_kind("clarification"):
        assert case["gold_article"] is None
        assert case["question"].strip()


# --- prompt layout --------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_question_and_sources_only_in_their_blocks(case):
    context = _context(case)
    system, user = build_messages(case["question"], context)
    assert system.role == MessageRole.SYSTEM and system.content == SYSTEM_PROMPT
    assert user.role == MessageRole.USER

    content = user.content
    assert content.startswith(SOURCES_OPEN) and content.endswith(QUESTION_CLOSE)
    for tag in (SOURCES_OPEN, SOURCES_CLOSE, QUESTION_OPEN, QUESTION_CLOSE):
        assert content.count(tag) == 1
    sources_block = content[: content.index(SOURCES_CLOSE)]
    question_block = content[content.index(QUESTION_OPEN) :]

    assert case["question"] in question_block
    assert case["question"] not in sources_block
    assert case["question"] not in system.content
    for source in context.sources:
        assert source.chunk.text.strip() in sources_block
        assert source.chunk.text.strip() not in question_block
        assert source.chunk.text.strip() not in system.content


def test_system_message_is_identical_across_cases():
    systems = {build_messages(c["question"], _context(c))[0].content for c in CASES}
    assert systems == {SYSTEM_PROMPT}


# --- replay of the real model's outputs -----------------------------------------


def test_kept_run_used_the_committed_prompt():
    assert KEPT_RUN["system_prompt"] == SYSTEM_PROMPT
    assert set(RESULTS) == {c["id"] for c in CASES}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_replay_recorded_output(case):
    result = RESULTS[case["id"]]
    context = _context(case)
    assert result["source_labels"] == {
        s.label: s.chunk.article_number for s in context.sources
    }
    validator = make_source_validator(context)

    if case["id"] in REJECTED_SINCE_RECORDING:
        assert result["ok"]
        with pytest.raises(OutputValidationError) as caught:
            validate_output(result["raw_outputs"][-1], LegalAnswer, validator)
        assert caught.value.kind == "semantic_invalid"
        assert any(
            e.startswith(REJECTED_SINCE_RECORDING[case["id"]]) and "non-Arabic" in e
            for e in caught.value.errors
        )
        return

    if not result["ok"]:
        assert result["failure"] in OUTPUT_FAILURES | {"timeout"}
        for raw in result["raw_outputs"]:
            with pytest.raises(OutputValidationError):
                validate_output(raw, LegalAnswer, validator)
        return

    assert 1 <= len(result["raw_outputs"]) <= result["attempts"]
    answer = validate_output(result["raw_outputs"][-1], LegalAnswer, validator)
    grounded = ground_answer(answer, context)

    assert grounded.status.value == result["status"]
    assert [c.supported for c in grounded.claims] == [
        c["supported"] for c in result["claims"]
    ]
    assert [c.article_number for c in grounded.citations] == result["cited_articles"]
    for claim in grounded.claims:
        assert all(label in context for label in claim.source_ids)
    for citation in grounded.citations:
        assert citation.label in context
        assert context.get(citation.label).article_number == citation.article_number
