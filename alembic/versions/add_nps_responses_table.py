"""add_nps_responses_table

Revision ID: add_nps_responses_table
Revises: add_system_settings_table
Create Date: 2026-02-24 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_nps_responses_table'
down_revision: Union[str, Sequence[str], None] = '4823f153f995'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create SurveyType enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE surveytype AS ENUM (
                'loyalty',
                'service_quality'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create nps_responses table
    survey_type_enum = postgresql.ENUM(
        'loyalty',
        'service_quality',
        name='surveytype',
        create_type=False
    )
    
    op.create_table(
        'nps_responses',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('survey_type', survey_type_enum, nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('trigger_event_id', sa.Integer(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('responded_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            ondelete='CASCADE'
        )
    )
    
    # Create indexes
    op.create_index('ix_nps_responses_user_id', 'nps_responses', ['user_id'])
    op.create_index('ix_nps_responses_survey_type', 'nps_responses', ['survey_type'])
    op.create_index('ix_nps_responses_sent_at', 'nps_responses', ['sent_at'])
    op.create_index('ix_nps_responses_responded_at', 'nps_responses', ['responded_at'])
    
    # Create composite indexes for analytics queries
    op.create_index('idx_nps_user_responded', 'nps_responses', ['user_id', 'responded_at'])
    op.create_index('idx_nps_type_responded', 'nps_responses', ['survey_type', 'responded_at'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_nps_type_responded', 'nps_responses')
    op.drop_index('idx_nps_user_responded', 'nps_responses')
    op.drop_index('ix_nps_responses_responded_at', 'nps_responses')
    op.drop_index('ix_nps_responses_sent_at', 'nps_responses')
    op.drop_index('ix_nps_responses_survey_type', 'nps_responses')
    op.drop_index('ix_nps_responses_user_id', 'nps_responses')
    
    # Drop table
    op.drop_table('nps_responses')
    
    # Drop enum type
    op.execute('DROP TYPE IF EXISTS surveytype CASCADE')
