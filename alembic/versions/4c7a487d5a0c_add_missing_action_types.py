"""add_missing_action_types

Revision ID: 4c7a487d5a0c
Revises: d622326f654e
Create Date: 2026-03-09 21:39:35.653991

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4c7a487d5a0c'
down_revision: str | Sequence[str] | None = 'd622326f654e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add missing enum values to actiontype
    # PostgreSQL requires ALTER TYPE ... ADD VALUE for each new value
    op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'reminder_sent'")
    op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'escalated'")
    op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'clients_transferred'")


def downgrade() -> None:
    """Downgrade schema."""
    # Note: PostgreSQL does not support removing enum values
    # This would require recreating the enum type
    pass
