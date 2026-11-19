"""Answer a legal question from retrieved sources, with citations (SCRUM-323).

``answer_question`` runs: validate question -> embed -> retrieve -> optional
distance filter -> label sources -> structured LLM call with the source-label
validator -> ground the answer. ``answer_from_sources`` is the second half, for
callers that already hold the sources (and for the live smoke test).

Nothing here raises for runtime failures: every outcome is an ``AnswerOutcome``
with a typed ``AnswerFailure`` that SCRUM-309 maps to user-facing messages.
Exception text, question text, and answer text are never put in the outcome or
logged at INFO or above.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.db.vector_store import MAX_SEARCH_LIMIT, validate_embedding
from services.llm.models import LLMParameters
from services.llm.provider import BaseLLMProvider
from services.llm.structured import FailureKind, generate_structured
from services.rag.citations import ground_answer, make_source_validator
from services.rag.prompts import build_messages
from services.rag.retrieval import QueryEmbedder, Retriever
from services.rag.schemas import AnswerStatus, GroundedAnswer, LegalAnswer
from services.rag.sources import MAX_SOURCES, LegalChunkLike, SourceChunk, SourceContext

logger = logging.getLogger(__name__)

# Long enough for a detailed scenario question, short enough to keep the prompt
# small for local models and to bound embedding cost.
MAX_QUESTION_CHARS = 2000
DEFAULT_TOP_K = MAX_SOURCES


class AnswerFailure(StrEnum):
    """Why no answer was produced. Includes every ``FailureKind`` value."""

    INVALID_QUESTION = "invalid_question"
    EMBEDDING_UNAVAILABLE = "embedding_unavailable"
    RETRIEVAL_UNAVAILABLE = "retrieval_unavailable"
    INVALID_JSON = FailureKind.INVALID_JSON.value
    SCHEMA_MISMATCH = FailureKind.SCHEMA_MISMATCH.value
    SEMANTIC_INVALID = FailureKind.SEMANTIC_INVALID.value
    PROVIDER_UNAVAILABLE = FailureKind.PROVIDER_UNAVAILABLE.value
    TIMEOUT = FailureKind.TIMEOUT.value
    CONFIGURATION_ERROR = FailureKind.CONFIGURATION_ERROR.value


@dataclass(frozen=True)
class AnswerOutcome:
    """Result of the chain.

    ``ok`` means ``answer`` holds a grounded answer (which may be ``no_source`` or
    ``needs_clarification``). ``attempts`` counts LLM calls (0 if none were made);
    ``source_count`` is the number of labelled sources shown to the model.
    """

    ok: bool
    answer: GroundedAnswer | None
    failure: AnswerFailure | None
    attempts: int = 0
    source_count: int = 0

    def __post_init__(self) -> None:
        if self.ok != (self.answer is not None) or self.ok == (
            self.failure is not None
        ):
            raise ValueError("ok must have an answer and no failure, or vice versa")

    @classmethod
    def success(
        cls, answer: GroundedAnswer, attempts: int, source_count: int
    ) -> AnswerOutcome:
        return cls(True, answer, None, attempts, source_count)

    @classmethod
    def failed(
        cls, failure: AnswerFailure, attempts: int = 0, source_count: int = 0
    ) -> AnswerOutcome:
        return cls(False, None, failure, attempts, source_count)


def normalize_question(question: object) -> str | None:
    """The stripped question, or None if it is empty, too long, or not text."""
    if not isinstance(question, str):
        return None
    text = question.strip()
    if not text or len(text) > MAX_QUESTION_CHARS or "\x00" in text:
        return None
    return text


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _within_distance(
    results: Iterable[tuple[LegalChunkLike, float]], max_distance: float | None
) -> list[tuple[LegalChunkLike, float]]:
    kept = []
    for chunk, distance in results:
        if max_distance is not None and not (
            math.isfinite(distance) and distance <= max_distance
        ):
            continue
        kept.append((chunk, distance))
    return kept


async def answer_from_sources(
    question: str,
    sources: Iterable[SourceChunk | LegalChunkLike | tuple[LegalChunkLike, float]],
    *,
    provider: BaseLLMProvider,
    params: LLMParameters | None = None,
) -> AnswerOutcome:
    """Answer ``question`` from already-retrieved sources (rank order).

    Returns ``no_source`` without calling the LLM when no valid source remains.
    """
    text = normalize_question(question)
    if text is None:
        return AnswerOutcome.failed(AnswerFailure.INVALID_QUESTION)

    context = SourceContext.from_chunks(sources)
    if not context.sources:
        logger.info("RAG answer: no sources, LLM not called")
        return AnswerOutcome.success(
            GroundedAnswer(status=AnswerStatus.NO_SOURCE), 0, 0
        )

    started = time.perf_counter()
    result = await generate_structured(
        provider,
        build_messages(text, context),
        LegalAnswer,
        params=params,
        semantic_validator=make_source_validator(context),
    )
    llm_ms = _ms(started)
    if not result.ok:
        logger.warning(
            "RAG answer failed: %s (attempts=%d sources=%d llm_ms=%d)",
            result.failure.value,
            result.attempts,
            len(context),
            llm_ms,
        )
        return AnswerOutcome.failed(
            AnswerFailure(result.failure.value), result.attempts, len(context)
        )

    try:
        grounded = ground_answer(result.value, context)
    except Exception as exc:  # never raise to the caller
        logger.warning("RAG grounding crashed: %s", type(exc).__name__)
        logger.debug("Grounding crash details", exc_info=True)
        return AnswerOutcome.failed(
            AnswerFailure.SEMANTIC_INVALID, result.attempts, len(context)
        )

    logger.info(
        "RAG answer: status=%s claims=%d unsupported=%d citations=%d "
        "attempts=%d sources=%d llm_ms=%d",
        grounded.status.value,
        len(grounded.claims),
        sum(not claim.supported for claim in grounded.claims),
        len(grounded.citations),
        result.attempts,
        len(context),
        llm_ms,
    )
    return AnswerOutcome.success(grounded, result.attempts, len(context))


async def answer_question(
    question: str,
    *,
    embedder: QueryEmbedder,
    retriever: Retriever,
    provider: BaseLLMProvider,
    top_k: int = DEFAULT_TOP_K,
    max_distance: float | None = None,
    params: LLMParameters | None = None,
) -> AnswerOutcome:
    """Answer a legal question from the corpus, with citations.

    ``top_k`` chunks are retrieved; at most ``MAX_SOURCES`` reach the model.
    Results with a cosine distance above ``max_distance`` are dropped when it is
    set. ``top_k`` outside 1..``MAX_SEARCH_LIMIT`` is a programming error and
    raises ``ValueError``.
    """
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise ValueError("top_k must be an integer")
    if not 1 <= top_k <= MAX_SEARCH_LIMIT:
        raise ValueError(f"top_k must be from 1 to {MAX_SEARCH_LIMIT}")

    text = normalize_question(question)
    if text is None:
        logger.info("RAG answer: invalid question rejected")
        return AnswerOutcome.failed(AnswerFailure.INVALID_QUESTION)

    started = time.perf_counter()
    try:
        embedding = validate_embedding(await embedder.embed_query(text))
    except Exception as exc:  # never raise to the caller
        logger.warning(
            "RAG embedding failed: %s (embed_ms=%d)", type(exc).__name__, _ms(started)
        )
        return AnswerOutcome.failed(AnswerFailure.EMBEDDING_UNAVAILABLE)
    embed_ms = _ms(started)

    started = time.perf_counter()
    try:
        results = list(await retriever.retrieve(embedding, limit=top_k))
    except Exception as exc:  # never raise to the caller
        logger.warning(
            "RAG retrieval failed: %s (retrieve_ms=%d)",
            type(exc).__name__,
            _ms(started),
        )
        return AnswerOutcome.failed(AnswerFailure.RETRIEVAL_UNAVAILABLE)
    retrieve_ms = _ms(started)

    kept = _within_distance(results, max_distance)
    logger.info(
        "RAG retrieval: retrieved=%d kept=%d embed_ms=%d retrieve_ms=%d",
        len(results),
        len(kept),
        embed_ms,
        retrieve_ms,
    )
    return await answer_from_sources(text, kept, provider=provider, params=params)
