"""Pydantic request and response contracts for legal chunk retrieval."""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.vector_store import (
    DEFAULT_SEARCH_LIMIT,
    EMBEDDING_DIMENSIONS,
    MAX_SEARCH_LIMIT,
    validate_embedding,
)


class RetrievalRequest(BaseModel):
    """A precomputed query embedding and bounded number of results to return."""

    embedding: list[float] = Field(
        min_length=EMBEDDING_DIMENSIONS,
        max_length=EMBEDDING_DIMENSIONS,
    )
    limit: int = Field(
        default=DEFAULT_SEARCH_LIMIT,
        strict=True,
        ge=1,
        le=MAX_SEARCH_LIMIT,
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("embedding", mode="before")
    @classmethod
    def validate_query_embedding(cls, value: object) -> list[float]:
        """Validate vector shape and values before Pydantic can coerce them."""
        try:
            vector = validate_embedding(value)
        except ValueError as error:
            raise ValueError(
                f"embedding must be a finite, non-zero vector with "
                f"{EMBEDDING_DIMENSIONS} numeric values"
            ) from error
        return vector


class RetrievedLegalChunk(BaseModel):
    """A legal text chunk and its available citation metadata."""

    id: uuid.UUID
    source_type: str
    source_name: str
    article_number: str | None
    source_date: date | None
    url: str | None
    text: str
    cosine_distance: float


class RetrievalResponse(BaseModel):
    """Search results ordered from nearest to farthest by cosine distance."""

    results: list[RetrievedLegalChunk]
