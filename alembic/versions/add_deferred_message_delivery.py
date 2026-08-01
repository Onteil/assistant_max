"""Track deferred delivery of client messages to staff.

Revision ID: deferred_message_delivery
Revises: nps_response_idempotency
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op

revision = "deferred_message_delivery"
down_revision = "nps_response_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("staff_notified_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("staff_notification_claimed_at", sa.DateTime(), nullable=True),
    )

    # Do not replay historical conversation after the first deployment.
    op.execute(
        """
        UPDATE messages
        SET staff_notified_at = sent_at
        WHERE sender_type = 'USER'
        """
    )

    op.create_index(
        "ix_messages_pending_staff_notification",
        "messages",
        ["id", "staff_notification_claimed_at"],
        unique=False,
        postgresql_where=sa.text(
            "sender_type = 'USER' AND staff_notified_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_messages_pending_staff_notification",
        table_name="messages",
    )
    op.drop_column("messages", "staff_notification_claimed_at")
    op.drop_column("messages", "staff_notified_at")
