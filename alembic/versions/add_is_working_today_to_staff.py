"""add_is_working_today_to_staff

Revision ID: add_is_working_today_to_staff
Revises: add_round_robin_settings
Create Date: 2026-04-28 12:00:00.000000

Adds is_working_today flag to staff_members table.
Allows employees to mark themselves as temporarily unavailable
(sick, day off, etc.) so they don't receive new ticket assignments.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_is_working_today_to_staff'
down_revision: Union[str, Sequence[str], None] = 'add_round_robin_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_working_today column to staff_members table."""
    op.add_column(
        'staff_members',
        sa.Column(
            'is_working_today',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true'),
            comment='Сотрудник доступен сегодня — если False, не получает новые заявки'
        )
    )


def downgrade() -> None:
    """Remove is_working_today column from staff_members table."""
    op.drop_column('staff_members', 'is_working_today')
