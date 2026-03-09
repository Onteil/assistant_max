"""add_calendar_action_types_to_enum

Revision ID: f8ce6b407fd2
Revises: 7d7b1f51b56e
Create Date: 2026-02-21 13:08:52.248373

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8ce6b407fd2'
down_revision: Union[str, Sequence[str], None] = '7d7b1f51b56e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new calendar-related action types to the actiontype enum
    op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'calendar_rule_created'")
    op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'calendar_rule_deleted'")
    op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'calendar_period_cleared'")


def downgrade() -> None:
    """Downgrade schema."""
    # Note: PostgreSQL does not support removing enum values directly
    # Manual intervention required if downgrade is needed
    pass
