"""Authenticated API routes for legal chunk retrieval."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.db.vector_store import search_legal_chunks
from app.retrieval.schemas import (
    RetrievalRequest,
    RetrievalResponse,
    RetrievedLegalChunk,
)

router = APIRouter()


@router.post("/search", response_model=RetrievalResponse)
def retrieve_legal_chunks(
    payload: RetrievalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RetrievalResponse:
    """Search the shared legal corpus using a validated embedding."""
    results = search_legal_chunks(db, payload.embedding, limit=payload.limit)
    return RetrievalResponse(
        results=[
            RetrievedLegalChunk(
                id=chunk.id,
                source_type=chunk.source_type,
                source_name=chunk.source_name,
                article_number=chunk.article_number,
                source_date=chunk.source_date,
                url=chunk.url,
                text=chunk.text,
                cosine_distance=distance,
            )
            for chunk, distance in results
        ]
    )
