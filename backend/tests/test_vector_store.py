"""Unit tests for vector input validation and transaction handling."""

import pytest

from app.db.models import LegalChunk
from app.db.vector_store import (
    EMBEDDING_DIMENSIONS,
    add_legal_chunk,
    validate_embedding,
)


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[LegalChunk] = []
        self.flush_calls = 0

    def add(self, instance: LegalChunk) -> None:
        self.added.append(instance)

    def flush(self) -> None:
        self.flush_calls += 1


def test_validate_embedding_returns_float_vector() -> None:
    vector = validate_embedding([1, *([0] * (EMBEDDING_DIMENSIONS - 1))])

    assert len(vector) == EMBEDDING_DIMENSIONS
    assert vector[0] == 1.0
    assert all(isinstance(value, float) for value in vector)


@pytest.mark.parametrize(
    "embedding",
    [
        [1.0] * (EMBEDDING_DIMENSIONS - 1),
        [1.0] * (EMBEDDING_DIMENSIONS + 1),
        [0.0] * EMBEDDING_DIMENSIONS,
        [float("nan")] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
        [float("inf")] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
        [10**400] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
        [True] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
        ["1"] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
    ],
)
def test_validate_embedding_rejects_invalid_vectors(embedding) -> None:
    with pytest.raises(ValueError):
        validate_embedding(embedding)


@pytest.mark.parametrize("embedding", ["not a vector", b"not a vector", None])
def test_validate_embedding_rejects_non_sequences(embedding) -> None:
    with pytest.raises(ValueError):
        validate_embedding(embedding)


def test_add_legal_chunk_validates_before_database_side_effects() -> None:
    session = RecordingSession()
    chunk = LegalChunk(source_type="law", source_name="Civil Code", text="Article")

    with pytest.raises(ValueError, match="1024"):
        add_legal_chunk(session, chunk, [1.0])

    assert session.added == []
    assert session.flush_calls == 0


def test_add_legal_chunk_flushes_without_committing() -> None:
    session = RecordingSession()
    chunk = LegalChunk(source_type="law", source_name="Civil Code", text="Article")
    embedding = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)

    result = add_legal_chunk(session, chunk, embedding)

    assert result is chunk
    assert chunk.embedding == embedding
    assert session.added == [chunk]
    assert session.flush_calls == 1
