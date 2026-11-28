"""request intake link: intake_id, responded_at, one active request per intake

SCRUM-344: a request is created when the client sends an approved intake
summary to a lawyer. ``intake_id`` points at the intake workflow row (the
``id`` the intake API returns). At most one request per intake may be active
(sent or accepted); declined/expired ones stay as history. ``decline_reason``
already exists, so only ``responded_at`` is added (set by SCRUM-347).

Revision ID: d5a1c9e7b203
Revises: c3e8f0a2d417
Create Date: 2026-11-28 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5a1c9e7b203"
down_revision: Union[str, Sequence[str], None] = "c3e8f0a2d417"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add intake_id (FK, indexed), responded_at, and the active-request index."""
    op.add_column("requests", sa.Column("intake_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_requests_intake_id", "requests", "workflows", ["intake_id"], ["id"]
    )
    op.create_index("ix_requests_intake_id", "requests", ["intake_id"])
    op.add_column(
        "requests",
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_requests_active_intake",
        "requests",
        ["intake_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('sent', 'accepted')"),
    )


def downgrade() -> None:
    """Remove the active-request index, responded_at and intake_id."""
    op.drop_index("uq_requests_active_intake", table_name="requests")
    op.drop_column("requests", "responded_at")
    op.drop_index("ix_requests_intake_id", table_name="requests")
    op.drop_constraint("fk_requests_intake_id", "requests", type_="foreignkey")
    op.drop_column("requests", "intake_id")
