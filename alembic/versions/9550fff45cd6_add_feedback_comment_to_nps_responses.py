"""add_feedback_comment_to_nps_responses

Revision ID: 9550fff45cd6
Revises: 64d4fc4b4662
Create Date: 2026-03-06 16:22:18.288495

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9550fff45cd6'
down_revision: str | Sequence[str] | None = '64d4fc4b4662'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add feedback_comment column to nps_responses table
    op.add_column(
        'nps_responses',
        sa.Column('feedback_comment', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove feedback_comment column from nps_responses table
    op.drop_column('nps_responses', 'feedback_comment')
