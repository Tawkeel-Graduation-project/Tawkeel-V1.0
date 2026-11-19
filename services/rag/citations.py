"""Check cited source labels, mark unsupported claims, and attach citations.

Two steps run after the model answers:

1. ``make_source_validator(context)`` is passed to ``generate_structured`` as its
   semantic validator, so unknown or duplicate labels trigger a repair attempt.
   A claim with no labels is *not* rejected here; it is marked instead.
2. ``ground_answer(answer, context)`` marks each claim supported or unsupported
   and attaches citations for the sources that supported claims cite.

A claim is unsupported when it cites no known source, or when it names an
article ("مادة 69", "المادة ١١١", "للمادة (47)") whose number is not the
``article_number`` of any source it cites. Only the singular forms مادة/ماده are
recognised; dual and plural forms (المادتين، المواد) are not checked.

The validator also rejects claim text and ``clarification_question`` that are
not Arabic (see ``language_problem``), since that text is shown to the user.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable

from services.rag.schemas import (
    AnswerStatus,
    Citation,
    GroundedAnswer,
    GroundedClaim,
    LegalAnswer,
    UnsupportedReason,
)
from services.rag.sources import SourceChunk, SourceContext

logger = logging.getLogger(__name__)

EXCERPT_MAX_CHARS = 300
ELLIPSIS = "…"

# Arabic-Indic (U+0660..U+0669) and Extended Arabic-Indic (U+06F0..U+06F9) digits.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# Harakat, superscript alef, and tatweel, which can sit between letters.
_DIACRITICS_RE = re.compile(r"[ً-ْٰـ]")
_ARTICLE_RE = re.compile(r"ماد[ةه]\s*(?:رقم\s*)?[(\[]?\s*(\d+)")
_LEADING_NUMBER_RE = re.compile(r"\d+")

# Of all letters in a text, at least this share must be Arabic. Latin letters
# are allowed only for short tokens such as source labels ("S1") or law names;
# letters of any other script (CJK, Cyrillic, ...) are always rejected.
# Digits (Western or Arabic-Indic), punctuation, and diacritics are not letters.
MIN_ARABIC_LETTER_RATIO = 0.7


def _letter_script(char: str) -> str:
    """'arabic', 'latin', or 'other' for a letter character."""
    name = unicodedata.name(char, "")
    if name.startswith("ARABIC"):
        return "arabic"
    if name.startswith("LATIN"):
        return "latin"
    return "other"


def language_problem(text: str) -> str | None:
    """Why ``text`` is not acceptable Arabic, or None if it is.

    The reason never quotes the text, so it is safe to send back to the model.
    """
    counts = {"arabic": 0, "latin": 0, "other": 0}
    for char in text:
        if char.isalpha():
            counts[_letter_script(char)] += 1
    if counts["other"]:
        return "contains letters from a non-Arabic script"
    if counts["arabic"] == 0:
        return "contains no Arabic text"
    ratio = counts["arabic"] / (counts["arabic"] + counts["latin"])
    if ratio < MIN_ARABIC_LETTER_RATIO:
        return "is mostly in a non-Arabic language"
    return None


def normalize_digits(text: str) -> str:
    """Replace Arabic-Indic digits with Western digits."""
    return text.translate(_DIGITS)


def _article_key(number: str) -> str:
    """Compare article numbers without leading zeros ("069" == "69")."""
    return number.lstrip("0") or "0"


def mentioned_articles(text: str) -> set[str]:
    """Article numbers a claim names with مادة/المادة, digits normalized."""
    cleaned = normalize_digits(_DIACRITICS_RE.sub("", text))
    return {_article_key(m.group(1)) for m in _ARTICLE_RE.finditer(cleaned)}


def _source_article(chunk: SourceChunk) -> str | None:
    if chunk.article_number is None:
        return None
    match = _LEADING_NUMBER_RE.search(normalize_digits(chunk.article_number))
    return _article_key(match.group(0)) if match else None


def make_source_validator(
    context: SourceContext,
) -> Callable[[LegalAnswer], list[str]]:
    """Semantic validator for ``generate_structured`` that checks source labels.

    Errors name locations only (never the model's own label or text) and list
    the allowed labels so the model can repair its answer. Claim text and the
    clarification question must be Arabic (``language_problem``).
    """
    allowed = ", ".join(context.labels) or "(none)"

    def validate(answer: LegalAnswer) -> list[str]:
        errors: list[str] = []
        cites_known_source = False
        for i, claim in enumerate(answer.claims):
            problem = language_problem(claim.text)
            if problem:
                errors.append(f"claims.{i}.text: {problem}; write it in Arabic only")
            seen: set[str] = set()
            for j, source_id in enumerate(claim.source_ids):
                location = f"claims.{i}.source_ids.{j}"
                if source_id in seen:
                    errors.append(f"{location}: duplicate source id in this claim")
                    continue
                seen.add(source_id)
                if source_id in context:
                    cites_known_source = True
                else:
                    errors.append(f"{location}: unknown source id; use only: {allowed}")
        if answer.clarification_question is not None:
            problem = language_problem(answer.clarification_question)
            if problem:
                errors.append(
                    f"clarification_question: {problem}; write it in Arabic only"
                )
        if answer.status == AnswerStatus.ANSWERED and not cites_known_source:
            errors.append(
                "claims: an answered answer must cite at least one source "
                "(or use status no_source)"
            )
        return errors

    return validate


def make_excerpt(text: str, max_chars: int = EXCERPT_MAX_CHARS) -> str:
    """Whitespace-collapsed excerpt of at most ``max_chars``, cut between words."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    cut = collapsed[: max_chars - len(ELLIPSIS)]
    space = cut.rfind(" ")
    if space > 0:
        cut = cut[:space]
    return cut.rstrip() + ELLIPSIS


def _citation(label: str, chunk: SourceChunk) -> Citation:
    return Citation(
        label=label,
        chunk_id=chunk.chunk_id,
        source_type=chunk.source_type,
        source_name=chunk.source_name,
        article_number=chunk.article_number,
        source_date=chunk.source_date,
        url=chunk.url,
        excerpt=make_excerpt(chunk.text),
    )


def _ground_claim(
    text: str, source_ids: list[str], context: SourceContext
) -> GroundedClaim:
    known = list(dict.fromkeys(sid for sid in source_ids if sid in context))
    if not known:
        return GroundedClaim(
            text=text,
            source_ids=[],
            supported=False,
            unsupported_reason=UnsupportedReason.NO_SOURCE_CITED,
        )
    cited_articles = {_source_article(context.get(sid)) for sid in known}
    if not mentioned_articles(text) <= cited_articles:
        return GroundedClaim(
            text=text,
            source_ids=known,
            supported=False,
            unsupported_reason=UnsupportedReason.ARTICLE_MISMATCH,
        )
    return GroundedClaim(text=text, source_ids=known, supported=True)


def ground_answer(answer: LegalAnswer, context: SourceContext) -> GroundedAnswer:
    """Mark each claim and attach citations for sources behind supported claims.

    ``source_ids`` on a grounded claim keeps only labels found in ``context``,
    de-duplicated in order. An ``answered`` answer with no supported claim is
    downgraded to ``no_source`` with no claims and no citations.
    """
    if answer.status != AnswerStatus.ANSWERED:
        return GroundedAnswer(
            status=answer.status,
            clarification_question=answer.clarification_question,
        )

    claims = [
        _ground_claim(claim.text, claim.source_ids, context) for claim in answer.claims
    ]
    citations: dict[str, Citation] = {}
    for claim in claims:
        if not claim.supported:
            continue
        for label in claim.source_ids:
            if label not in citations:
                citations[label] = _citation(label, context.get(label))

    if not citations:
        logger.info(
            "Answer downgraded to no_source: none of %d claims is supported",
            len(claims),
        )
        return GroundedAnswer(status=AnswerStatus.NO_SOURCE)

    return GroundedAnswer(
        status=AnswerStatus.ANSWERED,
        claims=claims,
        citations=list(citations.values()),
        has_unsupported_claims=any(not claim.supported for claim in claims),
    )
