"""Convert UTC timestamps to Moscow timezone

Revision ID: convert_utc_to_moscow
Revises: [latest_revision]
Create Date: 2024-03-12 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone, timedelta

# revision identifiers, used by Alembic.
revision = 'convert_utc_to_moscow'
down_revision = None  # Set this to the latest revision ID
branch_labels = None
depends_on = None

# Moscow timezone offset (UTC+3)
MOSCOW_OFFSET = timedelta(hours=3)


def upgrade() -> None:
    """
    Convert all UTC timestamps to Moscow timezone.
    
    This migration converts existing UTC timestamps in the database
    to Moscow time by adding 3 hours to all datetime fields.
    
    Tables affected:
    - users (created_at, updated_at)
    - tickets (created_at, updated_at, closed_at, escalated_at)
    - messages (created_at)
    - action_logs (created_at, action_timestamp)
    - escalations (created_at, escalated_at, resolved_at)
    - broadcasts (created_at, sent_at)
    - broadcast_deliveries (created_at, delivered_at)
    - nps_responses (created_at, response_date)
    - notification_events (created_at, scheduled_at, sent_at)
    - api_retry_queue (created_at, last_attempt_at)
    - system_settings (created_at, updated_at)
    - file_attachments (created_at)
    - calendar_rules (created_at, updated_at)
    - manager_assignments (added_at)
    - staff_actions (action_timestamp)
    """
    
    # Get database connection
    connection = op.get_bind()
    
    # List of tables and their datetime columns
    tables_and_columns = [
        ('users', ['created_at', 'updated_at']),
        ('tickets', ['created_at', 'updated_at', 'closed_at', 'escalated_at']),
        ('messages', ['created_at']),
        ('action_logs', ['created_at', 'action_timestamp']),
        ('escalations', ['created_at', 'escalated_at', 'resolved_at']),
        ('broadcasts', ['created_at', 'sent_at']),
        ('broadcast_deliveries', ['created_at', 'delivered_at']),
        ('nps_responses', ['created_at', 'response_date']),
        ('notification_events', ['created_at', 'scheduled_at', 'sent_at']),
        ('api_retry_queue', ['created_at', 'last_attempt_at']),
        ('system_settings', ['created_at', 'updated_at']),
        ('file_attachments', ['created_at']),
        ('calendar_rules', ['created_at', 'updated_at']),
        ('manager_assignments', ['added_at']),
        ('staff_actions', ['action_timestamp']),
    ]
    
    print("Converting UTC timestamps to Moscow timezone...")
    
    for table_name, columns in tables_and_columns:
        for column_name in columns:
            try:
                # Check if table and column exist
                result = connection.execute(sa.text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}' 
                    AND column_name = '{column_name}'
                """))
                
                if result.fetchone():
                    # Update timestamps by adding 3 hours (Moscow offset)
                    update_sql = f"""
                        UPDATE {table_name} 
                        SET {column_name} = {column_name} + INTERVAL '3 hours'
                        WHERE {column_name} IS NOT NULL
                    """
                    
                    result = connection.execute(sa.text(update_sql))
                    rows_affected = result.rowcount
                    print(f"Updated {rows_affected} rows in {table_name}.{column_name}")
                else:
                    print(f"Column {table_name}.{column_name} does not exist, skipping")
                    
            except Exception as e:
                print(f"Error updating {table_name}.{column_name}: {e}")
                # Continue with other columns
                continue
    
    print("Timezone conversion completed!")


def downgrade() -> None:
    """
    Convert Moscow timestamps back to UTC.
    
    This reverses the upgrade by subtracting 3 hours from all datetime fields.
    """
    
    # Get database connection
    connection = op.get_bind()
    
    # List of tables and their datetime columns (same as upgrade)
    tables_and_columns = [
        ('users', ['created_at', 'updated_at']),
        ('tickets', ['created_at', 'updated_at', 'closed_at', 'escalated_at']),
        ('messages', ['created_at']),
        ('action_logs', ['created_at', 'action_timestamp']),
        ('escalations', ['created_at', 'escalated_at', 'resolved_at']),
        ('broadcasts', ['created_at', 'sent_at']),
        ('broadcast_deliveries', ['created_at', 'delivered_at']),
        ('nps_responses', ['created_at', 'response_date']),
        ('notification_events', ['created_at', 'scheduled_at', 'sent_at']),
        ('api_retry_queue', ['created_at', 'last_attempt_at']),
        ('system_settings', ['created_at', 'updated_at']),
        ('file_attachments', ['created_at']),
        ('calendar_rules', ['created_at', 'updated_at']),
        ('manager_assignments', ['added_at']),
        ('staff_actions', ['action_timestamp']),
    ]
    
    print("Converting Moscow timestamps back to UTC...")
    
    for table_name, columns in tables_and_columns:
        for column_name in columns:
            try:
                # Check if table and column exist
                result = connection.execute(sa.text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}' 
                    AND column_name = '{column_name}'
                """))
                
                if result.fetchone():
                    # Update timestamps by subtracting 3 hours (reverse Moscow offset)
                    update_sql = f"""
                        UPDATE {table_name} 
                        SET {column_name} = {column_name} - INTERVAL '3 hours'
                        WHERE {column_name} IS NOT NULL
                    """
                    
                    result = connection.execute(sa.text(update_sql))
                    rows_affected = result.rowcount
                    print(f"Reverted {rows_affected} rows in {table_name}.{column_name}")
                else:
                    print(f"Column {table_name}.{column_name} does not exist, skipping")
                    
            except Exception as e:
                print(f"Error reverting {table_name}.{column_name}: {e}")
                # Continue with other columns
                continue
    
    print("Timezone reversion completed!")