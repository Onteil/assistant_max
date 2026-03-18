"""merge_heads_before_phone_change

Revision ID: 6f9a96939e72
Revises: 4c7a487d5a0c, convert_utc_to_moscow
Create Date: 2026-03-18 11:07:08.871528

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '6f9a96939e72'
down_revision: str | Sequence[str] | None = ('4c7a487d5a0c', 'convert_utc_to_moscow')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
