"""Expand escalation_level check constraint to allow level 3 (admin escalation)

Revision ID: expand_escalation_level_constraint
Revises: add_is_working_today_to_staff
Create Date: 2026-04-30

The original constraint only allowed values 0, 1, 2.
The escalation flow uses level 3 to represent the final admin-escalation state,
so the constraint must be widened to include 3.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = 'expand_escalation_lvl_3'
down_revision = 'add_is_working_today_to_staff'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old constraint that only allows 0, 1, 2
    op.drop_constraint('ck_tickets_escalation_level', 'tickets', type_='check')

    # Re-create it allowing 0, 1, 2, 3
    op.create_check_constraint(
        'ck_tickets_escalation_level',
        'tickets',
        'escalation_level IN (0, 1, 2, 3)'
    )


def downgrade() -> None:
    op.drop_constraint('ck_tickets_escalation_level', 'tickets', type_='check')

    op.create_check_constraint(
        'ck_tickets_escalation_level',
        'tickets',
        'escalation_level IN (0, 1, 2)'
    )
