"""add request_id and workflow_id to audit_events

Revision ID: a1b2c3d4e5f6
Revises: 9a0c317c9f11
Create Date: 2026-11-18 20:24:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9a0c317c9f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add request_id and workflow_id columns to audit_events."""
    op.add_column(
        "audit_events",
        sa.Column("request_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_events_request_id",
        "audit_events",
        "requests",
        ["request_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_audit_events_workflow_id",
        "audit_events",
        "workflows",
        ["workflow_id"],
        ["id"],
    )


def downgrade() -> None:
    """Remove request_id and workflow_id columns from audit_events."""
    op.drop_constraint(
        "fk_audit_events_workflow_id", "audit_events", type_="foreignkey"
    )
    op.drop_constraint("fk_audit_events_request_id", "audit_events", type_="foreignkey")
    op.drop_column("audit_events", "workflow_id")
    op.drop_column("audit_events", "request_id")
