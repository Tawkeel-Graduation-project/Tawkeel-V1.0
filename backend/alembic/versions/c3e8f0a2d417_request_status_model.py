"""request status model: pending -> sent, default and CHECK constraint

SCRUM-346: canonical request statuses are sent | accepted | declined |
expired | cancelled. Values are written out here (not imported from
services.requests) so this migration stays fixed if the enum later changes.

Revision ID: c3e8f0a2d417
Revises: b7d4e2f1a9c3
Create Date: 2026-11-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e8f0a2d417"
down_revision: Union[str, Sequence[str], None] = "b7d4e2f1a9c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_CHECK = "status IN ('sent', 'accepted', 'declined', 'expired', 'cancelled')"


def upgrade() -> None:
    """Rename pending to sent, default new rows to sent, restrict the values."""
    op.execute("UPDATE requests SET status = 'sent' WHERE status = 'pending'")
    op.alter_column("requests", "status", server_default=sa.text("'sent'"))
    op.create_check_constraint("ck_requests_status", "requests", STATUS_CHECK)


def downgrade() -> None:
    """Drop the constraint and default, and turn sent back into pending."""
    op.drop_constraint("ck_requests_status", "requests", type_="check")
    op.alter_column("requests", "status", server_default=None)
    op.execute("UPDATE requests SET status = 'pending' WHERE status = 'sent'")
