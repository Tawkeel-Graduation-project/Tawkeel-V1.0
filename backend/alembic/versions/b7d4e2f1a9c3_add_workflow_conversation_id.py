"""add conversation_id to workflows

Links a workflow run to the chat it started from (SCRUM-331: the intake
workflow carries over the client's Q&A conversation).

Revision ID: b7d4e2f1a9c3
Revises: a1b2c3d4e5f6
Create Date: 2026-11-20 00:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d4e2f1a9c3"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a nullable conversation_id foreign key (indexed) to workflows."""
    op.add_column(
        "workflows",
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_workflows_conversation_id",
        "workflows",
        "conversations",
        ["conversation_id"],
        ["id"],
    )
    op.create_index("ix_workflows_conversation_id", "workflows", ["conversation_id"])


def downgrade() -> None:
    """Remove conversation_id from workflows."""
    op.drop_index("ix_workflows_conversation_id", table_name="workflows")
    op.drop_constraint("fk_workflows_conversation_id", "workflows", type_="foreignkey")
    op.drop_column("workflows", "conversation_id")
