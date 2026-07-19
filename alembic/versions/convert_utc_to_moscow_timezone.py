"""Convert existing UTC timestamps to Moscow time.

Revision ID: convert_utc_to_moscow
Revises:
Create Date: 2024-03-12 15:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "convert_utc_to_moscow"
down_revision = None
branch_labels = None
depends_on = None


TABLES_AND_COLUMNS = {
    "users": ("created_at", "updated_at"),
    "tickets": ("created_at", "updated_at", "closed_at", "escalated_at"),
    "messages": ("created_at",),
    "action_logs": ("created_at", "action_timestamp"),
    "escalations": ("created_at", "escalated_at", "resolved_at"),
    "broadcasts": ("created_at", "sent_at"),
    "broadcast_deliveries": ("created_at", "delivered_at"),
    "nps_responses": ("created_at", "response_date"),
    "notification_events": ("created_at", "scheduled_at", "sent_at"),
    "api_retry_queue": ("created_at", "last_attempt_at"),
    "system_settings": ("created_at", "updated_at"),
    "file_attachments": ("created_at",),
    "calendar_rules": ("created_at", "updated_at"),
    "manager_assignments": ("added_at",),
    "staff_actions": ("action_timestamp",),
}


def _shift_existing_timestamps(hours: int) -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = set(inspector.get_table_names(schema="public"))
    preparer = connection.dialect.identifier_preparer

    for table_name, configured_columns in TABLES_AND_COLUMNS.items():
        if table_name not in existing_tables:
            print(f"Table public.{table_name} does not exist, skipping")
            continue

        existing_columns = {
            column["name"]
            for column in inspector.get_columns(table_name, schema="public")
        }
        quoted_table = (
            f"{preparer.quote_schema('public')}.{preparer.quote(table_name)}"
        )

        for column_name in configured_columns:
            if column_name not in existing_columns:
                print(
                    f"Column public.{table_name}.{column_name} "
                    "does not exist, skipping"
                )
                continue

            quoted_column = preparer.quote(column_name)
            statement = sa.text(
                f"UPDATE {quoted_table} "
                f"SET {quoted_column} = "
                f"{quoted_column} + (:hours * INTERVAL '1 hour') "
                f"WHERE {quoted_column} IS NOT NULL"
            )
            result = connection.execute(statement, {"hours": hours})
            print(
                f"Shifted {result.rowcount} rows in "
                f"public.{table_name}.{column_name} by {hours} hours"
            )


def upgrade() -> None:
    # Missing legacy tables/columns are expected on a fresh database. Any SQL
    # failure for an existing column must abort the migration.
    _shift_existing_timestamps(hours=3)


def downgrade() -> None:
    _shift_existing_timestamps(hours=-3)
