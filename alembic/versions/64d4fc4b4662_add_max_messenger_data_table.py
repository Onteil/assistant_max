"""add_max_messenger_data_table

Revision ID: 64d4fc4b4662
Revises: 75e2130f7b2f
Create Date: 2026-03-04 14:35:19.574827

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '64d4fc4b4662'
down_revision: str | Sequence[str] | None = '75e2130f7b2f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create max_messenger_data table
    op.create_table(
        'max_messenger_data',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('max_user_id', sa.BigInteger(), nullable=False),
        sa.Column('max_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_max_messenger_user_id'),
        sa.UniqueConstraint('max_user_id', name='uq_max_messenger_max_user_id')
    )
    
    # Create indexes
    op.create_index('ix_max_messenger_data_user_id', 'max_messenger_data', ['user_id'])
    op.create_index('ix_max_messenger_data_max_user_id', 'max_messenger_data', ['max_user_id'])
    op.create_index('ix_max_messenger_data_max_chat_id', 'max_messenger_data', ['max_chat_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('ix_max_messenger_data_max_chat_id', table_name='max_messenger_data')
    op.drop_index('ix_max_messenger_data_max_user_id', table_name='max_messenger_data')
    op.drop_index('ix_max_messenger_data_user_id', table_name='max_messenger_data')
    
    # Drop table
    op.drop_table('max_messenger_data')

