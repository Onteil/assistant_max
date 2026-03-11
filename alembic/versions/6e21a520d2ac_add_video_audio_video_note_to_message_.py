"""add_video_audio_video_note_to_message_type

Revision ID: 6e21a520d2ac
Revises: update_gs_key_format
Create Date: 2026-02-27 13:16:44.470269

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e21a520d2ac'
down_revision: Union[str, Sequence[str], None] = 'update_gs_key_format'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add VIDEO, AUDIO, VIDEO_NOTE to MessageType enum."""
    # Add new values to messagetype enum
    op.execute("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'video'")
    op.execute("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'audio'")
    op.execute("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'video_note'")


def downgrade() -> None:
    """Downgrade schema - Cannot remove enum values in PostgreSQL."""
    # PostgreSQL does not support removing enum values
    # This is a one-way migration
    pass
