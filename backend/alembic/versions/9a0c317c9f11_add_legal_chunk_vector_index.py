"""add cosine HNSW index for legal chunk embeddings

Revision ID: 9a0c317c9f11
Revises: 52e9881421c6
Create Date: 2026-10-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a0c317c9f11"
down_revision: Union[str, Sequence[str], None] = "52e9881421c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add an approximate cosine index for populated embeddings."""
    op.create_index(
        "ix_legal_chunks_embedding_hnsw_cosine",
        "legal_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=sa.text("embedding IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove the legal chunk cosine index."""
    op.drop_index("ix_legal_chunks_embedding_hnsw_cosine", table_name="legal_chunks")
