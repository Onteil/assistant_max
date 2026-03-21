"""fix keyconflictstatus enum - restore UPPER_CASE, update data

Revision ID: fix_keyconflictstatus_case
Revises: 17635a42783f
Create Date: 2026-03-20

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'fix_keyconflictstatus_case'
down_revision: str | Sequence[str] | None = '17635a42783f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Update gs_keys data from lowercase to UPPER_CASE enum values,
    then remove the lowercase variants from the enum type.
    """
    # Step 1: Update existing data to UPPER_CASE values
    op.execute("UPDATE gs_keys SET conflict_status = 'NONE'::keyconflictstatus WHERE conflict_status::text = 'none'")
    op.execute("UPDATE gs_keys SET conflict_status = 'PENDING_REVIEW'::keyconflictstatus WHERE conflict_status::text = 'pending_review'")
    op.execute("UPDATE gs_keys SET conflict_status = 'RESOLVED'::keyconflictstatus WHERE conflict_status::text = 'resolved'")

    # Step 2: Recreate the enum type with only UPPER_CASE values
    # PostgreSQL doesn't support DROP VALUE, so we recreate the type
    op.execute("ALTER TYPE keyconflictstatus RENAME TO keyconflictstatus_old")
    op.execute("CREATE TYPE keyconflictstatus AS ENUM ('NONE', 'PENDING_REVIEW', 'RESOLVED')")
    op.execute("""
        ALTER TABLE gs_keys
        ALTER COLUMN conflict_status TYPE keyconflictstatus
        USING conflict_status::text::keyconflictstatus
    """)
    op.execute("DROP TYPE keyconflictstatus_old")


def downgrade() -> None:
    """Revert: restore lowercase enum values and update data back."""
    op.execute("ALTER TYPE keyconflictstatus RENAME TO keyconflictstatus_old")
    op.execute("CREATE TYPE keyconflictstatus AS ENUM ('none', 'pending_review', 'resolved')")
    op.execute("""
        ALTER TABLE gs_keys
        ALTER COLUMN conflict_status TYPE keyconflictstatus
        USING lower(conflict_status::text)::keyconflictstatus
    """)
    op.execute("DROP TYPE keyconflictstatus_old")
