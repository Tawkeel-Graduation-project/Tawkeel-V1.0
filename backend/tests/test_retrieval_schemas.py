"""Unit tests for the retrieval API request contract."""

import pytest
from pydantic import ValidationError

from app.db.vector_store import (
    DEFAULT_SEARCH_LIMIT,
    EMBEDDING_DIMENSIONS,
    MAX_SEARCH_LIMIT,
)
from app.retrieval.schemas import RetrievalRequest


def valid_embedding() -> list[float]:
    return [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)


def test_retrieval_request_accepts_valid_embedding_and_default_limit() -> None:
    request = RetrievalRequest(embedding=valid_embedding())

    assert request.limit == DEFAULT_SEARCH_LIMIT
    assert request.embedding[0] == 1.0
    assert len(request.embedding) == EMBEDDING_DIMENSIONS


def test_retrieval_request_accepts_maximum_limit() -> None:
    request = RetrievalRequest(embedding=valid_embedding(), limit=MAX_SEARCH_LIMIT)

    assert request.limit == MAX_SEARCH_LIMIT


@pytest.mark.parametrize(
    "embedding",
    [
        [1.0] * (EMBEDDING_DIMENSIONS - 1),
        [1.0] * (EMBEDDING_DIMENSIONS + 1),
        [0.0] * EMBEDDING_DIMENSIONS,
        [float("nan")] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
        [float("inf")] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
        [True] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
        ["1"] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
    ],
)
def test_retrieval_request_rejects_invalid_embeddings(embedding) -> None:
    with pytest.raises(ValidationError):
        RetrievalRequest(embedding=embedding)


@pytest.mark.parametrize("limit", [0, -1, MAX_SEARCH_LIMIT + 1, True, 1.5, "2"])
def test_retrieval_request_rejects_invalid_limits(limit) -> None:
    with pytest.raises(ValidationError):
        RetrievalRequest(embedding=valid_embedding(), limit=limit)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"embedding": "not a vector"},
        {"embedding": valid_embedding(), "unexpected": "field"},
    ],
)
def test_retrieval_request_rejects_malformed_payloads(payload) -> None:
    with pytest.raises(ValidationError):
        RetrievalRequest.model_validate(payload)
