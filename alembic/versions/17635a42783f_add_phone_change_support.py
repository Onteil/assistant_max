"""add_phone_change_support

Revision ID: 17635a42783f
Revises: 6f9a96939e72
Create Date: 2026-03-18 11:07:15.741100

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '17635a42783f'
down_revision: str | Sequence[str] | None = '6f9a96939e72'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add phone change fields to tickets table
    op.add_column('tickets', sa.Column('old_phone', sa.String(20), nullable=True, comment='Old phone number for phone change requests'))
    op.add_column('tickets', sa.Column('new_phone', sa.String(20), nullable=True, comment='New phone number for phone change requests'))
    op.add_column('tickets', sa.Column('resolution_comment', sa.String(), nullable=True, comment='Resolution comment for closed tickets'))
    
    # Add PHONE_CHANGE to TicketType enum
    op.execute("ALTER TYPE tickettype ADD VALUE 'phone_change'")
    
    # Add phone change action types to ActionType enum
    op.execute("ALTER TYPE actiontype ADD VALUE 'phone_change_requested'")
    op.execute("ALTER TYPE actiontype ADD VALUE 'phone_change_approved'")
    op.execute("ALTER TYPE actiontype ADD VALUE 'phone_change_rejected'")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove phone change fields from tickets table
    op.drop_column('tickets', 'resolution_comment')
    op.drop_column('tickets', 'new_phone')
    op.drop_column('tickets', 'old_phone')
    
    # Note: Cannot remove enum values in PostgreSQL without recreating the enum
    # This would require more complex migration logic
