"""add max_file_url to file_attachments

Revision ID: add_max_file_url_to_attachments
Revises: 9550fff45cd6
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_max_file_url_to_attachments'
down_revision = 'fix_keyconflictstatus_case'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'file_attachments',
        sa.Column('max_file_url', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('file_attachments', 'max_file_url')
