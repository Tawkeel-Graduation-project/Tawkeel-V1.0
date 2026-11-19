"""Retrieved legal sources and the labelled context the model cites from.

``SourceChunk`` is a plain, frozen copy of a retrieved ``legal_chunks`` row, so
grounding code never depends on FastAPI or a live SQLAlchemy session.
``SourceContext`` deduplicates chunks, keeps retrieval order, and labels them
``S1``..``Sn``. The prompt builder (SCRUM-323) shows the model those labels, and
the model cites them in ``Claim.source_ids``.

At most ``MAX_SOURCES`` chunks are kept (the highest-ranked ones). A Labor Law
article can run to a few thousand characters, and small local models degrade
with long contexts and many labels, so 8 is the default ceiling.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

MAX_SOURCES = 8
LABEL_PREFIX = "S"


class SourceType(StrEnum):
    """Kinds of legal source, matching ``legal_chunks.source_type``."""

    LAW = "law"
    RULING = "ruling"


class LegalChunkLike(Protocol):
    """The attributes of ``app.db.models.LegalChunk`` that grounding needs."""

    id: uuid.UUID
    source_type: str
    source_name: str
    article_number: str | None
    source_date: date | None
    url: str | None
    text: str


class SourceChunk(BaseModel):
    """A retrieved legal passage with its citation metadata."""

    chunk_id: uuid.UUID
    source_type: SourceType
    source_name: str
    article_number: str | None = None
    source_date: date | None = None
    url: str | None = None
    text: str

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def from_legal_chunk(cls, chunk: LegalChunkLike) -> SourceChunk:
        """Copy a ``LegalChunk`` row (or anything shaped like one)."""
        return cls(
            chunk_id=chunk.id,
            source_type=chunk.source_type,
            source_name=chunk.source_name,
            article_number=chunk.article_number,
            source_date=chunk.source_date,
            url=chunk.url,
            text=chunk.text,
        )

    @classmethod
    def from_search_result(cls, result: tuple[LegalChunkLike, float]) -> SourceChunk:
        """Copy one ``(LegalChunk, cosine_distance)`` from ``search_legal_chunks``."""
        chunk, _distance = result
        return cls.from_legal_chunk(chunk)


class LabeledSource(BaseModel):
    """A source and the short label the model uses to cite it."""

    label: str
    chunk: SourceChunk

    model_config = ConfigDict(extra="forbid", frozen=True)


def _to_source_chunk(item: Any) -> SourceChunk:
    if isinstance(item, SourceChunk):
        return item
    if isinstance(item, tuple):
        return SourceChunk.from_search_result(item)
    return SourceChunk.from_legal_chunk(item)


def _row_id(item: Any) -> Any:
    """Best-effort chunk id of a row that failed conversion, for logging only."""
    row = item[0] if isinstance(item, tuple) and item else item
    return getattr(row, "id", None)


class SourceContext(BaseModel):
    """Labelled sources in retrieval order. Build it with ``from_chunks``."""

    sources: tuple[LabeledSource, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def from_chunks(
        cls,
        chunks: Iterable[SourceChunk | LegalChunkLike | tuple[LegalChunkLike, float]],
        *,
        max_sources: int = MAX_SOURCES,
    ) -> SourceContext:
        """Deduplicate by ``chunk_id``, keep the first ``max_sources``, label S1..Sn.

        Accepts ``SourceChunk`` objects, ``LegalChunk`` rows, or the
        ``(LegalChunk, distance)`` tuples returned by ``search_legal_chunks``.
        Input order is treated as rank order. A row that cannot be converted
        (for example an unknown ``source_type``) is skipped with a warning that
        names only its chunk id, so one bad row never fails the whole request.
        Constructing ``SourceChunk`` directly stays strict.
        """
        if max_sources < 1:
            raise ValueError("max_sources must be at least 1")
        seen: set[uuid.UUID] = set()
        labelled: list[LabeledSource] = []
        for item in chunks:
            try:
                chunk = _to_source_chunk(item)
            except (ValueError, TypeError, AttributeError) as exc:
                logger.warning(
                    "Skipping invalid source row chunk_id=%s (%s)",
                    _row_id(item),
                    type(exc).__name__,
                )
                continue
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            label = f"{LABEL_PREFIX}{len(labelled) + 1}"
            labelled.append(LabeledSource(label=label, chunk=chunk))
            if len(labelled) == max_sources:
                break
        return cls(sources=tuple(labelled))

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(source.label for source in self.sources)

    def get(self, label: str) -> SourceChunk | None:
        """The source for ``label``, or None if the label is not in the context."""
        for source in self.sources:
            if source.label == label:
                return source.chunk
        return None

    def __contains__(self, label: object) -> bool:
        return isinstance(label, str) and self.get(label) is not None

    def __len__(self) -> int:
        return len(self.sources)
