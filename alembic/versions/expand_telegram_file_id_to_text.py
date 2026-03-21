"""expand telegram_file_id to Text

Revision ID: expand_telegram_file_id_to_text
Revises: add_max_file_url_to_attachments
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa

revision = 'expand_telegram_file_id_to_text'
down_revision = 'add_max_file_url_to_attachments'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'file_attachments',
        'telegram_file_id',
        type_=sa.Text(),
        existing_nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        'file_attachments',
        'telegram_file_id',
        type_=sa.String(256),
        existing_nullable=False
    )
