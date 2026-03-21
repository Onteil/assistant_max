"""add queue_notification_sent_at to tickets

Revision ID: a1b2c3d4e5f6
Revises: 75e2130f7b2f
Create Date: 2026-03-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = ('75e2130f7b2f', 'expand_telegram_file_id_to_text')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'tickets',
        sa.Column(
            'queue_notification_sent_at',
            sa.DateTime(),
            nullable=True,
            comment='Timestamp when queue notification was sent (prevents duplicate notifications)'
        )
    )


def downgrade() -> None:
    op.drop_column('tickets', 'queue_notification_sent_at')
