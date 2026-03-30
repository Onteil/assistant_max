"""add_consultation_ticket_type_and_estimate_specialist_flag

Revision ID: b2c3d4e5f6a1
Revises: 7019055850be
Create Date: 2026-03-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a1'
down_revision: Union[str, Sequence[str], None] = '7019055850be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add 'consultation' value to tickettype enum
    op.execute("ALTER TYPE tickettype ADD VALUE IF NOT EXISTS 'consultation'")

    # Add is_estimate_tech_specialist flag to staff_members
    op.add_column(
        'staff_members',
        sa.Column(
            'is_estimate_tech_specialist',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
            comment='Сметный тех. специалист — получает заявки типа Консультация'
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove is_estimate_tech_specialist column
    op.drop_column('staff_members', 'is_estimate_tech_specialist')

    # Note: PostgreSQL does not support removing enum values directly.
    # To fully revert, recreate the enum without 'consultation'.
