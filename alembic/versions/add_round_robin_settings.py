"""add round-robin assignment settings for support and consultation tickets

Revision ID: add_round_robin_settings
Revises: 202ab8a1f960
Create Date: 2026-04-26 12:00:00.000000

Adds two rows to system_settings that persist the round-robin state:
  - support_rr_last_staff_id       — last assigned support staff ID
  - consultation_rr_last_staff_id  — last assigned consultation specialist ID

These rows are created by the migration so they exist from the first
application start. The round_robin_service also creates them on-demand
(via _ensure_rr_setting) as a safety net.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_round_robin_settings"
down_revision: Union[str, Sequence[str], None] = "202ab8a1f960"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert round-robin state settings into system_settings."""
    now = sa.func.now()

    op.execute(
        sa.text("""
            INSERT INTO system_settings
                (key, category, value, data_type, default_value,
                 min_value, max_value, description, display_name,
                 requires_test, created_at, updated_at)
            VALUES
                (
                    'support_rr_last_staff_id',
                    'duty_support',
                    '0',
                    'integer',
                    '0',
                    0,
                    NULL,
                    'ID последнего сотрудника техподдержки, которому была назначена заявка '
                    'через круговое распределение (round-robin). '
                    'Значение 0 означает «начать с первого».',
                    'Последний назначенный (ТП)',
                    false,
                    NOW(),
                    NOW()
                ),
                (
                    'consultation_rr_last_staff_id',
                    'duty_support',
                    '0',
                    'integer',
                    '0',
                    0,
                    NULL,
                    'ID последнего сметного специалиста, которому была назначена заявка '
                    'через круговое распределение (round-robin). '
                    'Значение 0 означает «начать с первого».',
                    'Последний назначенный (Консультация)',
                    false,
                    NOW(),
                    NOW()
                )
            ON CONFLICT (key) DO NOTHING
        """)
    )


def downgrade() -> None:
    """Remove round-robin state settings."""
    op.execute(
        sa.text("""
            DELETE FROM system_settings
            WHERE key IN (
                'support_rr_last_staff_id',
                'consultation_rr_last_staff_id'
            )
        """)
    )
