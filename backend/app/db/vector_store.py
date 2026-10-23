"""Persistence and cosine similarity search for legal chunk embeddings."""

import math
from collections.abc import Sequence
from numbers import Real

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LegalChunk

EMBEDDING_DIMENSIONS = 1024
DEFAULT_SEARCH_LIMIT = 10


def validate_embedding(embedding: Sequence[Real]) -> list[float]:
    """Return a normalized vector after validating the persisted dimensions."""
    if isinstance(embedding, (str, bytes)) or not isinstance(embedding, Sequence):
        raise ValueError("embedding must be a sequence of numeric values")
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"embedding must contain {EMBEDDING_DIMENSIONS} values")

    vector: list[float] = []
    for value in embedding:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError("embedding values must be numeric")
        try:
            converted = float(value)
        except OverflowError as error:
            raise ValueError("embedding values must be finite") from error
        if not math.isfinite(converted):
            raise ValueError("embedding values must be finite")
        vector.append(converted)

    if not any(vector):
        raise ValueError("embedding must not be a zero vector for cosine search")
    return vector


def add_legal_chunk(
    session: Session, chunk: LegalChunk, embedding: Sequence[Real]
) -> LegalChunk:
    """Attach a precomputed embedding and flush the chunk in caller's transaction."""
    chunk.embedding = validate_embedding(embedding)
    session.add(chunk)
    session.flush()
    return chunk


def search_legal_chunks(
    session: Session,
    embedding: Sequence[Real],
    *,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[tuple[LegalChunk, float]]:
    """Return embedded chunks ordered by ascending cosine distance."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    query_embedding = validate_embedding(embedding)
    distance = LegalChunk.embedding.cosine_distance(query_embedding)
    statement = (
        select(LegalChunk, distance.label("cosine_distance"))
        .where(LegalChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    return [(chunk, float(score)) for chunk, score in session.execute(statement)]
