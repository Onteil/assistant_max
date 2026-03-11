"""add_email_to_users

Revision ID: c9b462e9ebc4
Revises: 2143289a78e8
Create Date: 2026-02-26 09:43:49.283324

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9b462e9ebc4'
down_revision: Union[str, Sequence[str], None] = '2143289a78e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add email column to users table
    op.add_column('users', sa.Column('email', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove email column from users table
    op.drop_column('users', 'email')
