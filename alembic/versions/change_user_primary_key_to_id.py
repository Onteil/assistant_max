"""Change user primary key from tg_user_id to id

Revision ID: change_user_pk_to_id
Revises: add_max_messenger_support
Create Date: 2024-02-16 12:00:00.000000

Changes:
1. Add new 'id' column as autoincrement integer to users table
2. Make tg_user_id nullable, unique, and indexed (instead of primary key)
3. Update all foreign key references from tg_user_id to id
4. Migrate existing data

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'change_user_pk_to_id'
down_revision = 'add_max_messenger_support'
branch_label = None
depends_on = None


def upgrade():
    # Step 1: Add new id column to users table (temporary, not primary key yet)
    op.add_column('users', sa.Column('id', sa.Integer(), autoincrement=True, nullable=True))
    
    # Step 2: Create sequence and populate id values
    op.execute("CREATE SEQUENCE IF NOT EXISTS users_id_seq")
    op.execute("SELECT setval('users_id_seq', 1, false)")
    op.execute("UPDATE users SET id = nextval('users_id_seq')")
    
    # Step 3: Make id not nullable and set default
    op.alter_column('users', 'id', nullable=False, server_default=sa.text("nextval('users_id_seq')"))
    
    # Step 4: Add new user_id columns to related tables
    # user_organizations
    op.add_column('user_organizations', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE user_organizations uo
        SET user_id = u.id
        FROM users u
        WHERE uo.tg_user_id = u.tg_user_id
    """)
    op.alter_column('user_organizations', 'user_id', nullable=False)
    
    # gs_keys
    op.add_column('gs_keys', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE gs_keys gk
        SET user_id = u.id
        FROM users u
        WHERE gk.tg_user_id = u.tg_user_id
    """)
    op.alter_column('gs_keys', 'user_id', nullable=False)
    
    # tickets
    op.add_column('tickets', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE tickets t
        SET user_id = u.id
        FROM users u
        WHERE t.tg_user_id = u.tg_user_id
    """)
    op.alter_column('tickets', 'user_id', nullable=False)
    
    # manager_assignments
    op.add_column('manager_assignments', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE manager_assignments ma
        SET user_id = u.id
        FROM users u
        WHERE ma.tg_user_id = u.tg_user_id
    """)
    op.alter_column('manager_assignments', 'user_id', nullable=False)
    
    # notification_events
    op.add_column('notification_events', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE notification_events ne
        SET user_id = u.id
        FROM users u
        WHERE ne.tg_user_id = u.tg_user_id
    """)
    op.alter_column('notification_events', 'user_id', nullable=False)
    
    # broadcast_deliveries
    op.add_column('broadcast_deliveries', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE broadcast_deliveries bd
        SET user_id = u.id
        FROM users u
        WHERE bd.tg_user_id = u.tg_user_id
    """)
    op.alter_column('broadcast_deliveries', 'user_id', nullable=False)
    
    # action_logs (user_id can be null)
    op.add_column('action_logs', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE action_logs al
        SET user_id = u.id
        FROM users u
        WHERE al.tg_user_id = u.tg_user_id
    """)
    
    # api_retry_queue (user_id can be null)
    op.add_column('api_retry_queue', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE api_retry_queue arq
        SET user_id = u.id
        FROM users u
        WHERE arq.tg_user_id = u.tg_user_id
    """)
    
    # Step 5: Drop old foreign key constraints BEFORE changing primary key
    op.drop_constraint('user_organizations_tg_user_id_fkey', 'user_organizations', type_='foreignkey')
    op.drop_constraint('gs_keys_tg_user_id_fkey', 'gs_keys', type_='foreignkey')
    op.drop_constraint('tickets_tg_user_id_fkey', 'tickets', type_='foreignkey')
    op.drop_constraint('manager_assignments_tg_user_id_fkey', 'manager_assignments', type_='foreignkey')
    op.drop_constraint('notification_events_tg_user_id_fkey', 'notification_events', type_='foreignkey')
    op.drop_constraint('broadcast_deliveries_tg_user_id_fkey', 'broadcast_deliveries', type_='foreignkey')
    op.drop_constraint('action_logs_tg_user_id_fkey', 'action_logs', type_='foreignkey')
    op.drop_constraint('api_retry_queue_tg_user_id_fkey', 'api_retry_queue', type_='foreignkey')
    
    # Step 6: NOW change users table primary key
    op.drop_constraint('users_pkey', 'users', type_='primary')
    op.create_primary_key('users_pkey', 'users', ['id'])
    
    # Step 7: Make tg_user_id nullable, unique, and indexed
    op.alter_column('users', 'tg_user_id', nullable=True)
    op.create_unique_constraint('uq_users_tg_user_id', 'users', ['tg_user_id'])
    op.create_index('ix_users_tg_user_id', 'users', ['tg_user_id'])
    
    # Step 8: Drop old unique constraints
    op.drop_constraint('uq_user_organization', 'user_organizations', type_='unique')
    op.drop_constraint('uq_user_org_assignment', 'manager_assignments', type_='unique')
    op.drop_constraint('uq_broadcast_user_delivery', 'broadcast_deliveries', type_='unique')
    
    # Step 9: Drop old tg_user_id columns from related tables
    op.drop_column('user_organizations', 'tg_user_id')
    op.drop_column('gs_keys', 'tg_user_id')
    op.drop_column('tickets', 'tg_user_id')
    op.drop_column('manager_assignments', 'tg_user_id')
    op.drop_column('notification_events', 'tg_user_id')
    op.drop_column('broadcast_deliveries', 'tg_user_id')
    op.drop_column('action_logs', 'tg_user_id')
    op.drop_column('api_retry_queue', 'tg_user_id')
    
    # Step 10: Create new foreign key constraints (NOW users.id is primary key)
    op.create_foreign_key('user_organizations_user_id_fkey', 'user_organizations', 'users', ['user_id'], ['id'])
    op.create_foreign_key('gs_keys_user_id_fkey', 'gs_keys', 'users', ['user_id'], ['id'])
    op.create_foreign_key('tickets_user_id_fkey', 'tickets', 'users', ['user_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key('manager_assignments_user_id_fkey', 'manager_assignments', 'users', ['user_id'], ['id'])
    op.create_foreign_key('notification_events_user_id_fkey', 'notification_events', 'users', ['user_id'], ['id'])
    op.create_foreign_key('broadcast_deliveries_user_id_fkey', 'broadcast_deliveries', 'users', ['user_id'], ['id'])
    op.create_foreign_key('action_logs_user_id_fkey', 'action_logs', 'users', ['user_id'], ['id'])
    op.create_foreign_key('api_retry_queue_user_id_fkey', 'api_retry_queue', 'users', ['user_id'], ['id'])
    
    # Step 11: Create new unique constraints
    op.create_unique_constraint('uq_user_organization', 'user_organizations', ['user_id', 'organization_inn'])
    op.create_unique_constraint('uq_user_org_assignment', 'manager_assignments', ['user_id', 'organization_inn'])
    op.create_unique_constraint('uq_broadcast_user_delivery', 'broadcast_deliveries', ['broadcast_id', 'user_id'])


def downgrade():
    # This is a complex migration, downgrade should be done carefully
    # For safety, we'll keep both id and tg_user_id during downgrade
    
    # Step 1: Remove index and unique constraint from tg_user_id
    op.drop_index('ix_users_tg_user_id', 'users')
    op.drop_constraint('uq_users_tg_user_id', 'users', type_='unique')
    
    # Step 2: Make tg_user_id not nullable (ensure all records have tg_user_id)
    op.execute("UPDATE users SET tg_user_id = -id WHERE tg_user_id IS NULL")
    op.alter_column('users', 'tg_user_id', nullable=False)
    
    # Step 3: Restore tg_user_id as primary key
    op.drop_constraint('users_pkey', 'users', type_='primary')
    op.create_primary_key('users_pkey', 'users', ['tg_user_id'])
    
    # Step 4: Add back tg_user_id columns to related tables
    op.add_column('user_organizations', sa.Column('tg_user_id', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE user_organizations uo
        SET tg_user_id = u.tg_user_id
        FROM users u
        WHERE uo.user_id = u.id
    """)
    op.alter_column('user_organizations', 'tg_user_id', nullable=False)
    
    op.add_column('gs_keys', sa.Column('tg_user_id', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE gs_keys gk
        SET tg_user_id = u.tg_user_id
        FROM users u
        WHERE gk.user_id = u.id
    """)
    op.alter_column('gs_keys', 'tg_user_id', nullable=False)
    
    op.add_column('tickets', sa.Column('tg_user_id', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE tickets t
        SET tg_user_id = u.tg_user_id
        FROM users u
        WHERE t.user_id = u.id
    """)
    op.alter_column('tickets', 'tg_user_id', nullable=False)
    
    op.add_column('manager_assignments', sa.Column('tg_user_id', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE manager_assignments ma
        SET tg_user_id = u.tg_user_id
        FROM users u
        WHERE ma.user_id = u.id
    """)
    op.alter_column('manager_assignments', 'tg_user_id', nullable=False)
    
    op.add_column('notification_events', sa.Column('tg_user_id', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE notification_events ne
        SET tg_user_id = u.tg_user_id
        FROM users u
        WHERE ne.user_id = u.id
    """)
    op.alter_column('notification_events', 'tg_user_id', nullable=False)
    
    op.add_column('broadcast_deliveries', sa.Column('tg_user_id', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE broadcast_deliveries bd
        SET tg_user_id = u.tg_user_id
        FROM users u
        WHERE bd.user_id = u.id
    """)
    op.alter_column('broadcast_deliveries', 'tg_user_id', nullable=False)
    
    op.add_column('action_logs', sa.Column('tg_user_id', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE action_logs al
        SET tg_user_id = u.tg_user_id
        FROM users u
        WHERE al.user_id = u.id
    """)
    
    op.add_column('api_retry_queue', sa.Column('tg_user_id', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE api_retry_queue arq
        SET tg_user_id = u.tg_user_id
        FROM users u
        WHERE arq.user_id = u.id
    """)
    
    # Step 5: Drop new foreign key constraints
    op.drop_constraint('user_organizations_user_id_fkey', 'user_organizations', type_='foreignkey')
    op.drop_constraint('gs_keys_user_id_fkey', 'gs_keys', type_='foreignkey')
    op.drop_constraint('tickets_user_id_fkey', 'tickets', type_='foreignkey')
    op.drop_constraint('manager_assignments_user_id_fkey', 'manager_assignments', type_='foreignkey')
    op.drop_constraint('notification_events_user_id_fkey', 'notification_events', type_='foreignkey')
    op.drop_constraint('broadcast_deliveries_user_id_fkey', 'broadcast_deliveries', type_='foreignkey')
    op.drop_constraint('action_logs_user_id_fkey', 'action_logs', type_='foreignkey')
    op.drop_constraint('api_retry_queue_user_id_fkey', 'api_retry_queue', type_='foreignkey')
    
    # Step 6: Drop new unique constraints
    op.drop_constraint('uq_user_organization', 'user_organizations', type_='unique')
    op.drop_constraint('uq_user_org_assignment', 'manager_assignments', type_='unique')
    op.drop_constraint('uq_broadcast_user_delivery', 'broadcast_deliveries', type_='unique')
    
    # Step 7: Drop user_id columns
    op.drop_column('user_organizations', 'user_id')
    op.drop_column('gs_keys', 'user_id')
    op.drop_column('tickets', 'user_id')
    op.drop_column('manager_assignments', 'user_id')
    op.drop_column('notification_events', 'user_id')
    op.drop_column('broadcast_deliveries', 'user_id')
    op.drop_column('action_logs', 'user_id')
    op.drop_column('api_retry_queue', 'user_id')
    
    # Step 8: Restore old foreign key constraints
    op.create_foreign_key('user_organizations_tg_user_id_fkey', 'user_organizations', 'users', ['tg_user_id'], ['tg_user_id'])
    op.create_foreign_key('gs_keys_tg_user_id_fkey', 'gs_keys', 'users', ['tg_user_id'], ['tg_user_id'])
    op.create_foreign_key('tickets_tg_user_id_fkey', 'tickets', 'users', ['tg_user_id'], ['tg_user_id'], ondelete='RESTRICT')
    op.create_foreign_key('manager_assignments_tg_user_id_fkey', 'manager_assignments', 'users', ['tg_user_id'], ['tg_user_id'])
    op.create_foreign_key('notification_events_tg_user_id_fkey', 'notification_events', 'users', ['tg_user_id'], ['tg_user_id'])
    op.create_foreign_key('broadcast_deliveries_tg_user_id_fkey', 'broadcast_deliveries', 'users', ['tg_user_id'], ['tg_user_id'])
    op.create_foreign_key('action_logs_tg_user_id_fkey', 'action_logs', 'users', ['tg_user_id'], ['tg_user_id'])
    op.create_foreign_key('api_retry_queue_tg_user_id_fkey', 'api_retry_queue', 'users', ['tg_user_id'], ['tg_user_id'])
    
    # Step 9: Restore old unique constraints
    op.create_unique_constraint('uq_user_organization', 'user_organizations', ['tg_user_id', 'organization_inn'])
    op.create_unique_constraint('uq_user_org_assignment', 'manager_assignments', ['tg_user_id', 'organization_inn'])
    op.create_unique_constraint('uq_broadcast_user_delivery', 'broadcast_deliveries', ['broadcast_id', 'tg_user_id'])
    
    # Step 10: Drop id column from users
    op.drop_column('users', 'id')
    op.execute("DROP SEQUENCE IF EXISTS users_id_seq")
