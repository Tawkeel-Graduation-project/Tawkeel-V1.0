"""Embedding and retrieval dependencies of the answer chain, as interfaces.

The chain depends only on the two protocols below, so it can be tested with
fakes and the real embedder can arrive in its own story.

``QueryEmbedder``: the embedding story provides the implementation. The model
recommended in ``docs/embedding-model-comparison.md`` is
``Snowflake/snowflake-arctic-embed-l-v2.0`` (1024 dimensions, cosine). Queries
need the ``"query: "`` prefix and passages none; the same Arabic normalization
must be applied to queries and passages. Changing the model means re-embedding
every stored passage.

``Retriever``: ``PgVectorRetriever`` wraps the existing
``app.db.vector_store.search_legal_chunks`` (pgvector cosine distance, HNSW
index). It does not duplicate the SQL.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.orm import Session

from app.db.vector_store import EMBEDDING_DIMENSIONS, search_legal_chunks
from services.rag.sources import LegalChunkLike

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "PgVectorRetriever",
    "QueryEmbedder",
    "Retriever",
]


class QueryEmbedder(Protocol):
    """Turns a user question into a query embedding of ``EMBEDDING_DIMENSIONS``."""

    async def embed_query(self, text: str) -> list[float]:
        """Return the query vector; implementations add any model-specific prefix."""
        ...


class Retriever(Protocol):
    """Finds the legal chunks nearest to a query embedding."""

    async def retrieve(
        self, embedding: Sequence[float], *, limit: int
    ) -> list[tuple[LegalChunkLike, float]]:
        """Return ``(chunk, cosine_distance)`` pairs, nearest first."""
        ...


class PgVectorRetriever:
    """``Retriever`` over ``legal_chunks`` using the caller's SQLAlchemy session.

    The search runs in a worker thread because the session is synchronous. The
    session must not be used by anything else while ``retrieve`` is running.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    async def retrieve(
        self, embedding: Sequence[float], *, limit: int
    ) -> list[tuple[LegalChunkLike, float]]:
        return await asyncio.to_thread(
            search_legal_chunks, self._session, embedding, limit=limit
        )
