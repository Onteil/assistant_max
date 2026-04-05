"""merge_multi_escalation_channels

Revision ID: 202ab8a1f960
Revises: b2c3d4e5f6a1, add_multi_escalation_channels
Create Date: 2026-04-05 19:09:46.359970

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '202ab8a1f960'
down_revision: str | Sequence[str] | None = ('b2c3d4e5f6a1', 'add_multi_escalation_channels')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
