"""add_system_settings_table

Revision ID: add_system_settings_table
Revises: add_escalations_table
Create Date: 2026-02-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_system_settings_table'
down_revision: Union[str, Sequence[str], None] = 'add_escalations_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create enum types for system settings
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE settingdatatype AS ENUM (
                'integer',
                'json',
                'chat_id',
                'user_id'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE settingcategory AS ENUM (
                'timeouts',
                'escalation',
                'duty_support',
                'nps',
                'renewal_reminders'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Add new action types to ActionType enum
    op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'setting_changed'")
    op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'setting_reset'")
    
    # Create system_settings table
    setting_data_type_enum = postgresql.ENUM(
        'integer',
        'json',
        'chat_id',
        'user_id',
        name='settingdatatype',
        create_type=False
    )
    
    setting_category_enum = postgresql.ENUM(
        'timeouts',
        'escalation',
        'duty_support',
        'nps',
        'renewal_reminders',
        name='settingcategory',
        create_type=False
    )
    
    op.create_table(
        'system_settings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('category', setting_category_enum, nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('data_type', setting_data_type_enum, nullable=False),
        sa.Column('default_value', sa.Text(), nullable=False),
        sa.Column('min_value', sa.Integer(), nullable=True),
        sa.Column('max_value', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('requires_test', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['updated_by'],
            ['staff_members.id']
        )
    )
    
    # Create indexes
    op.create_index('ix_system_settings_key', 'system_settings', ['key'], unique=True)
    op.create_index('ix_system_settings_category', 'system_settings', ['category'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('ix_system_settings_category', 'system_settings')
    op.drop_index('ix_system_settings_key', 'system_settings')
    
    # Drop table
    op.drop_table('system_settings')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS settingcategory CASCADE')
    op.execute('DROP TYPE IF EXISTS settingdatatype CASCADE')
    
    # Note: Cannot remove values from ActionType enum in PostgreSQL
    # The setting_changed and setting_reset values will remain
