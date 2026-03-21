"""convert_message_timestamps_to_moscow_timezone

Revision ID: 7019055850be
Revises: a1b2c3d4e5f6
Create Date: 2026-03-21 13:20:38.858078

Converts all message timestamps from UTC to Moscow timezone (UTC+3).
This migration adds 3 hours to all existing sent_at timestamps in the messages table.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7019055850be'
down_revision: str | Sequence[str] | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Convert message timestamps from UTC to Moscow timezone.
    
    Adds 3 hours to all sent_at timestamps in messages table.
    """
    # Add 3 hours to all message timestamps (UTC -> MSK)
    op.execute("""
        UPDATE messages
        SET sent_at = sent_at + INTERVAL '3 hours'
        WHERE sent_at IS NOT NULL
    """)


def downgrade() -> None:
    """
    Revert message timestamps from Moscow timezone to UTC.
    
    Subtracts 3 hours from all sent_at timestamps in messages table.
    """
    # Subtract 3 hours from all message timestamps (MSK -> UTC)
    op.execute("""
        UPDATE messages
        SET sent_at = sent_at - INTERVAL '3 hours'
        WHERE sent_at IS NOT NULL
    """)

