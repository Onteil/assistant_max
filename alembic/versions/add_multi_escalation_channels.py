"""add_multi_escalation_channels

Converts escalation channel settings from single chat_id to JSON arrays,
and adds escalation_consultant_channel setting.

Revision ID: add_multi_escalation_channels
Revises: add_system_settings_table
Create Date: 2026-04-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_multi_escalation_channels'
down_revision: Union[str, Sequence[str], None] = 'add_system_settings_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    1. Convert escalation_manager_channel and escalation_duty_channel
       from chat_id type to json type (value becomes JSON array).
    2. Insert escalation_consultant_channel setting.
    """
    conn = op.get_bind()

    # Migrate existing single chat_id values to JSON arrays
    for key in ('escalation_manager_channel', 'escalation_duty_channel'):
        row = conn.execute(
            sa.text("SELECT value, data_type FROM system_settings WHERE key = :key"),
            {"key": key}
        ).fetchone()

        if row is None:
            continue

        current_value, current_type = row

        # Convert value: None/"" → "[]", existing chat_id → "[\"<id>\"]"
        if current_value and current_value.strip() not in ('', '[]'):
            import json
            new_value = json.dumps([current_value.strip()])
        else:
            new_value = '[]'

        conn.execute(
            sa.text(
                "UPDATE system_settings "
                "SET value = :value, data_type = 'json', "
                "    default_value = '[]', "
                "    display_name = REPLACE(display_name, 'Канал', 'Каналы'), "
                "    requires_test = false "
                "WHERE key = :key"
            ),
            {"value": new_value, "key": key}
        )

    # Insert escalation_consultant_channel if not present
    existing = conn.execute(
        sa.text("SELECT id FROM system_settings WHERE key = 'escalation_consultant_channel'")
    ).fetchone()

    if existing is None:
        from datetime import datetime
        now = datetime.utcnow()
        conn.execute(
            sa.text(
                "INSERT INTO system_settings "
                "(key, category, value, data_type, default_value, "
                " description, display_name, requires_test, created_at, updated_at) "
                "VALUES "
                "('escalation_consultant_channel', 'escalation', '[]', 'json', '[]', "
                " 'Список MAX чатов для уведомлений об эскалации сметных консультантов (JSON массив)', "
                " 'Каналы эскалации консультантов', false, :now, :now)"
            ),
            {"now": now}
        )


def downgrade() -> None:
    """
    Revert JSON arrays back to single chat_id strings and remove consultant channel.
    """
    conn = op.get_bind()

    for key in ('escalation_manager_channel', 'escalation_duty_channel'):
        row = conn.execute(
            sa.text("SELECT value FROM system_settings WHERE key = :key"),
            {"key": key}
        ).fetchone()

        if row is None:
            continue

        current_value = row[0]

        # Convert JSON array back to single value (take first element or None)
        import json
        try:
            arr = json.loads(current_value) if current_value else []
            single_value = arr[0] if arr else None
        except (json.JSONDecodeError, IndexError):
            single_value = None

        conn.execute(
            sa.text(
                "UPDATE system_settings "
                "SET value = :value, data_type = 'chat_id', "
                "    default_value = '', requires_test = true "
                "WHERE key = :key"
            ),
            {"value": single_value, "key": key}
        )

    # Remove consultant channel
    conn.execute(
        sa.text("DELETE FROM system_settings WHERE key = 'escalation_consultant_channel'")
    )
