"""add_calendar_rules_composite_indexes

Revision ID: 7d7b1f51b56e
Revises: 1fa56606b49b
Create Date: 2026-02-19 20:00:47.599197

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d7b1f51b56e'
down_revision: Union[str, Sequence[str], None] = '1fa56606b49b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add composite index on (start_date, end_date) for efficient range queries
    # This index helps with queries like:
    # SELECT * FROM calendar_rules WHERE start_date <= ? AND end_date >= ?
    op.create_index(
        'ix_calendar_rules_date_range',
        'calendar_rules',
        ['start_date', 'end_date']
    )
    
    # Add composite index on (rule_priority DESC, created_at DESC) for ordering
    # This index helps with queries that order by priority and creation time:
    # SELECT * FROM calendar_rules ORDER BY rule_priority DESC, created_at DESC
    op.create_index(
        'ix_calendar_rules_priority_created',
        'calendar_rules',
        [sa.text('rule_priority DESC'), sa.text('created_at DESC')],
        postgresql_using='btree'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the composite indexes in reverse order
    op.drop_index('ix_calendar_rules_priority_created', 'calendar_rules')
    op.drop_index('ix_calendar_rules_date_range', 'calendar_rules')
