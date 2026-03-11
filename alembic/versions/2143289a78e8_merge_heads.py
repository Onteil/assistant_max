"""merge_heads

Revision ID: 2143289a78e8
Revises: add_nps_responses_table, add_system_settings_table
Create Date: 2026-02-26 09:43:42.381859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2143289a78e8'
down_revision: Union[str, Sequence[str], None] = ('add_nps_responses_table', 'add_system_settings_table')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
