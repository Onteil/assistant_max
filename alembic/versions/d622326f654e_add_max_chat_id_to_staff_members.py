"""add_max_chat_id_to_staff_members

Revision ID: d622326f654e
Revises: 9550fff45cd6
Create Date: 2026-03-09 20:37:23.168611

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd622326f654e'
down_revision: str | Sequence[str] | None = '9550fff45cd6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add max_chat_id column to staff_members table
    op.add_column(
        'staff_members',
        sa.Column('max_chat_id', sa.BigInteger(), nullable=True, index=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove max_chat_id column from staff_members table
    op.drop_column('staff_members', 'max_chat_id')
