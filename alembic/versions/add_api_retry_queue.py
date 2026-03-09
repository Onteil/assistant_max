"""add api retry queue

Revision ID: add_api_retry_queue
Revises: 4c1aba65e0c8
Create Date: 2026-02-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_api_retry_queue'
down_revision: Union[str, None] = '4c1aba65e0c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create retry_status enum only if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE retrystatus AS ENUM ('pending', 'success', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create api_retry_queue table
    retry_status_enum = postgresql.ENUM('pending', 'success', 'failed', name='retrystatus', create_type=False)
    op.create_table(
        'api_retry_queue',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('operation', sa.String(length=100), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('tg_user_id', sa.BigInteger(), nullable=True),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', retry_status_enum, nullable=False, server_default='pending'),
        sa.Column('next_retry_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['tg_user_id'], ['users.tg_user_id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create index on status and next_retry_at for efficient retry processing
    op.create_index(
        'ix_api_retry_queue_status_next_retry',
        'api_retry_queue',
        ['status', 'next_retry_at']
    )
    
    # Add API_RETRY_FAILED to ActionType enum
    op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'api_retry_failed'")


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_api_retry_queue_status_next_retry', table_name='api_retry_queue')
    
    # Drop table
    op.drop_table('api_retry_queue')
    
    # Drop enum
    retry_status_enum = postgresql.ENUM('pending', 'success', 'failed', name='retrystatus')
    retry_status_enum.drop(op.get_bind())
    
    # Note: Cannot remove value from ActionType enum in PostgreSQL
    # Manual intervention required if downgrade is needed
