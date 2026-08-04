"""add_tech_support_knowledge

Revision ID: 9d37c2f4a8b1
Revises: deferred_message_delivery
Create Date: 2026-08-04 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d37c2f4a8b1"
down_revision: str | Sequence[str] | None = "deferred_message_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "tech_support_knowledge",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=False),
        sa.Column("solution_text", sa.Text(), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("screenshot_url", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tech_support_knowledge_active",
        "tech_support_knowledge",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_tech_support_knowledge_title",
        "tech_support_knowledge",
        ["title"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_tech_support_knowledge_title", table_name="tech_support_knowledge")
    op.drop_index("ix_tech_support_knowledge_active", table_name="tech_support_knowledge")
    op.drop_table("tech_support_knowledge")
