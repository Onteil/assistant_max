"""add_middle_name_to_users

Revision ID: 75e2130f7b2f
Revises: 6e21a520d2ac
Create Date: 2026-03-04 04:10:01.912759

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75e2130f7b2f'
down_revision: Union[str, Sequence[str], None] = '6e21a520d2ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add middle_name column to users table
    op.add_column('users', sa.Column('middle_name', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove middle_name column from users table
    op.drop_column('users', 'middle_name')
