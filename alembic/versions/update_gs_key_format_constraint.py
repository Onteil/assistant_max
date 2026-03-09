"""update gs_key format constraint

Revision ID: update_gs_key_format
Revises: 7d7b1f51b56e
Create Date: 2026-02-26 15:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'update_gs_key_format'
down_revision: Union[str, None] = 'c9b462e9ebc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old constraint
    op.drop_constraint('ck_gs_keys_key_format', 'gs_keys', type_='check')
    
    # Create new constraint for format: 00001_00011 (5 digits + underscore + 5 digits)
    op.create_check_constraint(
        'ck_gs_keys_key_format',
        'gs_keys',
        "key_number ~ '^[0-9]{5}_[0-9]{5}$'"
    )


def downgrade() -> None:
    # Drop new constraint
    op.drop_constraint('ck_gs_keys_key_format', 'gs_keys', type_='check')
    
    # Restore old constraint (XX321321 format)
    op.create_check_constraint(
        'ck_gs_keys_key_format',
        'gs_keys',
        "key_number ~ '^[A-Z]{2}[0-9]{6}$'"
    )
