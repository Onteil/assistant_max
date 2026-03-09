"""add max messenger support

Revision ID: add_max_messenger_support
Revises: add_api_retry_queue
Create Date: 2026-02-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_max_messenger_support'
down_revision: Union[str, None] = 'add_api_retry_queue'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add support for MAX messenger alongside Telegram.
    
    Changes:
    1. Add max_user_id column to users table
    2. Add user_id column (computed, for API compatibility)
    3. Update foreign key references in related tables
    4. Add indexes for performance
    """
    
    # Add max_user_id to users table
    op.add_column('users', sa.Column('max_user_id', sa.BigInteger(), nullable=True))
    
    # Add user_id as a computed column (defaults to tg_user_id for backward compatibility)
    # This will be used for API calls - handlers will set it based on active messenger
    op.add_column('users', sa.Column('user_id', sa.BigInteger(), nullable=True))
    
    # Create unique index on max_user_id (sparse index - only non-null values)
    op.create_index('ix_users_max_user_id', 'users', ['max_user_id'], unique=True, 
                    postgresql_where=sa.text('max_user_id IS NOT NULL'))
    
    # Add messenger_type column to track primary messenger
    op.add_column('users', sa.Column('messenger_type', sa.String(20), nullable=True, server_default='telegram'))
    
    # Update existing rows: set user_id = tg_user_id for existing users
    op.execute('UPDATE users SET user_id = tg_user_id WHERE user_id IS NULL')
    
    # Add max_user_id to staff_members table
    op.add_column('staff_members', sa.Column('max_user_id', sa.BigInteger(), nullable=True))
    op.create_index('ix_staff_members_max_user_id', 'staff_members', ['max_user_id'], unique=True,
                    postgresql_where=sa.text('max_user_id IS NOT NULL'))
    
    # Add comment to clarify usage
    op.execute("COMMENT ON COLUMN users.tg_user_id IS 'Telegram user ID (primary key for backward compatibility)'")
    op.execute("COMMENT ON COLUMN users.max_user_id IS 'MAX messenger user ID (optional)'")
    op.execute("COMMENT ON COLUMN users.user_id IS 'Active messenger user ID (used for API calls)'")
    op.execute("COMMENT ON COLUMN users.messenger_type IS 'Primary messenger: telegram or max'")


def downgrade() -> None:
    """
    Remove MAX messenger support.
    """
    
    # Drop indexes
    op.drop_index('ix_users_max_user_id', table_name='users')
    op.drop_index('ix_staff_members_max_user_id', table_name='staff_members')
    
    # Drop columns from users
    op.drop_column('users', 'max_user_id')
    op.drop_column('users', 'user_id')
    op.drop_column('users', 'messenger_type')
    
    # Drop columns from staff_members
    op.drop_column('staff_members', 'max_user_id')
