"""Retrieval-augmented legal answering: grounded, cited answers."""

from services.rag.citations import (
    EXCERPT_MAX_CHARS,
    MIN_ARABIC_LETTER_RATIO,
    ground_answer,
    language_problem,
    make_excerpt,
    make_source_validator,
    mentioned_articles,
    normalize_digits,
)
from services.rag.schemas import (
    AnswerStatus,
    Citation,
    Claim,
    GroundedAnswer,
    GroundedClaim,
    LegalAnswer,
    UnsupportedReason,
)
from services.rag.sources import (
    MAX_SOURCES,
    LabeledSource,
    SourceChunk,
    SourceContext,
    SourceType,
)

__all__ = [
    "EXCERPT_MAX_CHARS",
    "MAX_SOURCES",
    "MIN_ARABIC_LETTER_RATIO",
    "AnswerStatus",
    "Citation",
    "Claim",
    "GroundedAnswer",
    "GroundedClaim",
    "LabeledSource",
    "LegalAnswer",
    "SourceChunk",
    "SourceContext",
    "SourceType",
    "UnsupportedReason",
    "ground_answer",
    "language_problem",
    "make_excerpt",
    "make_source_validator",
    "mentioned_articles",
    "normalize_digits",
]
