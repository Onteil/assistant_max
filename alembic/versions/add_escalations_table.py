"""add_escalations_table

Revision ID: add_escalations_table
Revises: f8ce6b407fd2
Create Date: 2026-02-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_escalations_table'
down_revision: Union[str, Sequence[str], None] = 'f8ce6b407fd2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create enum types for escalation (with IF NOT EXISTS check)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE escalationtype AS ENUM (
                'reminder_10min',
                'escalation_20min'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE resolutionaction AS ENUM (
                'reassigned',
                'taken_over',
                'contacted',
                'auto_resolved'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create escalations table using postgresql.ENUM with create_type=False
    escalation_type_enum = postgresql.ENUM(
        'reminder_10min',
        'escalation_20min',
        name='escalationtype',
        create_type=False
    )
    
    resolution_action_enum = postgresql.ENUM(
        'reassigned',
        'taken_over',
        'contacted',
        'auto_resolved',
        name='resolutionaction',
        create_type=False
    )
    
    op.create_table(
        'escalations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('escalation_type', escalation_type_enum, nullable=False),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by_staff_id', sa.BigInteger(), nullable=True),
        sa.Column('resolution_action', resolution_action_enum, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['ticket_id'],
            ['tickets.id'],
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['resolved_by_staff_id'],
            ['staff_members.id'],
            ondelete='SET NULL'
        )
    )
    
    # Create indexes
    op.create_index('ix_escalations_ticket_id', 'escalations', ['ticket_id'])
    op.create_index('ix_escalations_is_resolved', 'escalations', ['is_resolved'])
    op.create_index(
        'ix_escalations_is_resolved_created_at',
        'escalations',
        ['is_resolved', 'created_at']
    )
    
    # Add new columns to tickets table
    op.add_column(
        'tickets',
        sa.Column(
            'escalation_task_reminder_id',
            sa.String(255),
            nullable=True,
            comment='ID Celery задачи напоминания'
        )
    )
    op.add_column(
        'tickets',
        sa.Column(
            'escalation_task_escalation_id',
            sa.String(255),
            nullable=True,
            comment='ID Celery задачи эскалации'
        )
    )
    op.add_column(
        'tickets',
        sa.Column(
            'is_escalated',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='Флаг эскалированной заявки'
        )
    )
    
    # Create index on is_escalated
    op.create_index('ix_tickets_is_escalated', 'tickets', ['is_escalated'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop index on tickets.is_escalated
    op.drop_index('ix_tickets_is_escalated', 'tickets')
    
    # Drop columns from tickets table
    op.drop_column('tickets', 'is_escalated')
    op.drop_column('tickets', 'escalation_task_escalation_id')
    op.drop_column('tickets', 'escalation_task_reminder_id')
    
    # Drop indexes
    op.drop_index('ix_escalations_is_resolved_created_at', 'escalations')
    op.drop_index('ix_escalations_is_resolved', 'escalations')
    op.drop_index('ix_escalations_ticket_id', 'escalations')
    
    # Drop table
    op.drop_table('escalations')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS resolutionaction CASCADE')
    op.execute('DROP TYPE IF EXISTS escalationtype CASCADE')
