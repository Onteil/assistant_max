"""Change staff_members primary key from tg_user_id to id

Revision ID: change_staff_pk_to_id
Revises: change_user_pk_to_id
Create Date: 2024-02-16 13:00:00.000000

Changes:
1. Add new 'id' column as autoincrement integer to staff_members table
2. Make tg_user_id nullable, unique, and indexed (instead of primary key)
3. Update all foreign key references from tg_user_id to id
4. Migrate existing data

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'change_staff_pk_to_id'
down_revision = 'change_user_pk_to_id'
branch_label = None
depends_on = None


def upgrade():
    # Step 1: Add new id column to staff_members table
    op.add_column('staff_members', sa.Column('id', sa.Integer(), autoincrement=True, nullable=True))
    
    # Step 2: Create sequence and populate id values
    op.execute("CREATE SEQUENCE IF NOT EXISTS staff_members_id_seq")
    op.execute("SELECT setval('staff_members_id_seq', 1, false)")
    op.execute("UPDATE staff_members SET id = nextval('staff_members_id_seq')")
    
    # Step 3: Make id not nullable and set default
    op.alter_column('staff_members', 'id', nullable=False, server_default=sa.text("nextval('staff_members_id_seq')"))
    
    # Step 4: Add new staff_id columns to related tables
    # users.default_manager_id
    op.add_column('users', sa.Column('default_manager_id_new', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE users u
        SET default_manager_id_new = sm.id
        FROM staff_members sm
        WHERE u.default_manager_id = sm.tg_user_id
    """)
    
    # staff_members.backup_manager_1_id
    op.add_column('staff_members', sa.Column('backup_manager_1_id_new', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE staff_members sm1
        SET backup_manager_1_id_new = sm2.id
        FROM staff_members sm2
        WHERE sm1.backup_manager_1_id = sm2.tg_user_id
    """)
    
    # staff_members.backup_manager_2_id
    op.add_column('staff_members', sa.Column('backup_manager_2_id_new', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE staff_members sm1
        SET backup_manager_2_id_new = sm2.id
        FROM staff_members sm2
        WHERE sm1.backup_manager_2_id = sm2.tg_user_id
    """)
    
    # manager_assignments.manager_id
    op.add_column('manager_assignments', sa.Column('manager_id_new', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE manager_assignments ma
        SET manager_id_new = sm.id
        FROM staff_members sm
        WHERE ma.manager_id = sm.tg_user_id
    """)
    op.alter_column('manager_assignments', 'manager_id_new', nullable=False)
    
    # tickets.assigned_staff_id
    op.add_column('tickets', sa.Column('assigned_staff_id_new', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE tickets t
        SET assigned_staff_id_new = sm.id
        FROM staff_members sm
        WHERE t.assigned_staff_id = sm.tg_user_id
    """)
    
    # action_logs.staff_id
    op.add_column('action_logs', sa.Column('staff_id_new', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE action_logs al
        SET staff_id_new = sm.id
        FROM staff_members sm
        WHERE al.staff_id = sm.tg_user_id
    """)
    
    # broadcasts.created_by_staff_id
    op.add_column('broadcasts', sa.Column('created_by_staff_id_new', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE broadcasts b
        SET created_by_staff_id_new = sm.id
        FROM staff_members sm
        WHERE b.created_by_staff_id = sm.tg_user_id
    """)
    op.alter_column('broadcasts', 'created_by_staff_id_new', nullable=False)
    
    # Step 5: Drop old foreign key constraints BEFORE changing primary key
    op.drop_constraint('users_default_manager_id_fkey', 'users', type_='foreignkey')
    op.drop_constraint('staff_members_backup_manager_1_id_fkey', 'staff_members', type_='foreignkey')
    op.drop_constraint('staff_members_backup_manager_2_id_fkey', 'staff_members', type_='foreignkey')
    op.drop_constraint('manager_assignments_manager_id_fkey', 'manager_assignments', type_='foreignkey')
    op.drop_constraint('tickets_assigned_staff_id_fkey', 'tickets', type_='foreignkey')
    op.drop_constraint('action_logs_staff_id_fkey', 'action_logs', type_='foreignkey')
    op.drop_constraint('broadcasts_created_by_staff_id_fkey', 'broadcasts', type_='foreignkey')
    
    # Step 6: NOW change staff_members table primary key
    op.drop_constraint('staff_members_pkey', 'staff_members', type_='primary')
    op.create_primary_key('staff_members_pkey', 'staff_members', ['id'])
    
    # Step 7: Make tg_user_id nullable, unique, and indexed
    op.alter_column('staff_members', 'tg_user_id', nullable=True)
    op.create_unique_constraint('uq_staff_members_tg_user_id', 'staff_members', ['tg_user_id'])
    op.create_index('ix_staff_members_tg_user_id', 'staff_members', ['tg_user_id'])
    
    # Step 8: Drop old columns from related tables
    op.drop_column('users', 'default_manager_id')
    op.drop_column('staff_members', 'backup_manager_1_id')
    op.drop_column('staff_members', 'backup_manager_2_id')
    op.drop_column('manager_assignments', 'manager_id')
    op.drop_column('tickets', 'assigned_staff_id')
    op.drop_column('action_logs', 'staff_id')
    op.drop_column('broadcasts', 'created_by_staff_id')
    
    # Step 9: Rename new columns to original names
    op.alter_column('users', 'default_manager_id_new', new_column_name='default_manager_id')
    op.alter_column('staff_members', 'backup_manager_1_id_new', new_column_name='backup_manager_1_id')
    op.alter_column('staff_members', 'backup_manager_2_id_new', new_column_name='backup_manager_2_id')
    op.alter_column('manager_assignments', 'manager_id_new', new_column_name='manager_id')
    op.alter_column('tickets', 'assigned_staff_id_new', new_column_name='assigned_staff_id')
    op.alter_column('action_logs', 'staff_id_new', new_column_name='staff_id')
    op.alter_column('broadcasts', 'created_by_staff_id_new', new_column_name='created_by_staff_id')
    
    # Step 10: Create new foreign key constraints (NOW staff_members.id is primary key)
    op.create_foreign_key('users_default_manager_id_fkey', 'users', 'staff_members', ['default_manager_id'], ['id'])
    op.create_foreign_key('staff_members_backup_manager_1_id_fkey', 'staff_members', 'staff_members', ['backup_manager_1_id'], ['id'])
    op.create_foreign_key('staff_members_backup_manager_2_id_fkey', 'staff_members', 'staff_members', ['backup_manager_2_id'], ['id'])
    op.create_foreign_key('manager_assignments_manager_id_fkey', 'manager_assignments', 'staff_members', ['manager_id'], ['id'])
    op.create_foreign_key('tickets_assigned_staff_id_fkey', 'tickets', 'staff_members', ['assigned_staff_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('action_logs_staff_id_fkey', 'action_logs', 'staff_members', ['staff_id'], ['id'])
    op.create_foreign_key('broadcasts_created_by_staff_id_fkey', 'broadcasts', 'staff_members', ['created_by_staff_id'], ['id'])


def downgrade():
    # This is a complex migration, downgrade should be done carefully
    
    # Step 1: Add back tg_user_id columns to related tables
    op.add_column('users', sa.Column('default_manager_id_old', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE users u
        SET default_manager_id_old = sm.tg_user_id
        FROM staff_members sm
        WHERE u.default_manager_id = sm.id
    """)
    
    op.add_column('staff_members', sa.Column('backup_manager_1_id_old', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE staff_members sm1
        SET backup_manager_1_id_old = sm2.tg_user_id
        FROM staff_members sm2
        WHERE sm1.backup_manager_1_id = sm2.id
    """)
    
    op.add_column('staff_members', sa.Column('backup_manager_2_id_old', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE staff_members sm1
        SET backup_manager_2_id_old = sm2.tg_user_id
        FROM staff_members sm2
        WHERE sm1.backup_manager_2_id = sm2.id
    """)
    
    op.add_column('manager_assignments', sa.Column('manager_id_old', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE manager_assignments ma
        SET manager_id_old = sm.tg_user_id
        FROM staff_members sm
        WHERE ma.manager_id = sm.id
    """)
    op.alter_column('manager_assignments', 'manager_id_old', nullable=False)
    
    op.add_column('tickets', sa.Column('assigned_staff_id_old', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE tickets t
        SET assigned_staff_id_old = sm.tg_user_id
        FROM staff_members sm
        WHERE t.assigned_staff_id = sm.id
    """)
    
    op.add_column('action_logs', sa.Column('staff_id_old', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE action_logs al
        SET staff_id_old = sm.tg_user_id
        FROM staff_members sm
        WHERE al.staff_id = sm.id
    """)
    
    op.add_column('broadcasts', sa.Column('created_by_staff_id_old', sa.BigInteger(), nullable=True))
    op.execute("""
        UPDATE broadcasts b
        SET created_by_staff_id_old = sm.tg_user_id
        FROM staff_members sm
        WHERE b.created_by_staff_id = sm.id
    """)
    op.alter_column('broadcasts', 'created_by_staff_id_old', nullable=False)
    
    # Step 2: Drop new foreign key constraints
    op.drop_constraint('users_default_manager_id_fkey', 'users', type_='foreignkey')
    op.drop_constraint('staff_members_backup_manager_1_id_fkey', 'staff_members', type_='foreignkey')
    op.drop_constraint('staff_members_backup_manager_2_id_fkey', 'staff_members', type_='foreignkey')
    op.drop_constraint('manager_assignments_manager_id_fkey', 'manager_assignments', type_='foreignkey')
    op.drop_constraint('tickets_assigned_staff_id_fkey', 'tickets', type_='foreignkey')
    op.drop_constraint('action_logs_staff_id_fkey', 'action_logs', type_='foreignkey')
    op.drop_constraint('broadcasts_created_by_staff_id_fkey', 'broadcasts', type_='foreignkey')
    
    # Step 3: Drop new columns
    op.drop_column('users', 'default_manager_id')
    op.drop_column('staff_members', 'backup_manager_1_id')
    op.drop_column('staff_members', 'backup_manager_2_id')
    op.drop_column('manager_assignments', 'manager_id')
    op.drop_column('tickets', 'assigned_staff_id')
    op.drop_column('action_logs', 'staff_id')
    op.drop_column('broadcasts', 'created_by_staff_id')
    
    # Step 4: Rename old columns back
    op.alter_column('users', 'default_manager_id_old', new_column_name='default_manager_id')
    op.alter_column('staff_members', 'backup_manager_1_id_old', new_column_name='backup_manager_1_id')
    op.alter_column('staff_members', 'backup_manager_2_id_old', new_column_name='backup_manager_2_id')
    op.alter_column('manager_assignments', 'manager_id_old', new_column_name='manager_id')
    op.alter_column('tickets', 'assigned_staff_id_old', new_column_name='assigned_staff_id')
    op.alter_column('action_logs', 'staff_id_old', new_column_name='staff_id')
    op.alter_column('broadcasts', 'created_by_staff_id_old', new_column_name='created_by_staff_id')
    
    # Step 5: Restore tg_user_id as primary key
    op.drop_index('ix_staff_members_tg_user_id', 'staff_members')
    op.drop_constraint('uq_staff_members_tg_user_id', 'staff_members', type_='unique')
    
    # Make tg_user_id not nullable (ensure all records have tg_user_id)
    op.execute("UPDATE staff_members SET tg_user_id = -id WHERE tg_user_id IS NULL")
    op.alter_column('staff_members', 'tg_user_id', nullable=False)
    
    op.drop_constraint('staff_members_pkey', 'staff_members', type_='primary')
    op.create_primary_key('staff_members_pkey', 'staff_members', ['tg_user_id'])
    
    # Step 6: Restore old foreign key constraints
    op.create_foreign_key('users_default_manager_id_fkey', 'users', 'staff_members', ['default_manager_id'], ['tg_user_id'])
    op.create_foreign_key('staff_members_backup_manager_1_id_fkey', 'staff_members', 'staff_members', ['backup_manager_1_id'], ['tg_user_id'])
    op.create_foreign_key('staff_members_backup_manager_2_id_fkey', 'staff_members', 'staff_members', ['backup_manager_2_id'], ['tg_user_id'])
    op.create_foreign_key('manager_assignments_manager_id_fkey', 'manager_assignments', 'staff_members', ['manager_id'], ['tg_user_id'])
    op.create_foreign_key('tickets_assigned_staff_id_fkey', 'tickets', 'staff_members', ['assigned_staff_id'], ['tg_user_id'], ondelete='SET NULL')
    op.create_foreign_key('action_logs_staff_id_fkey', 'action_logs', 'staff_members', ['staff_id'], ['tg_user_id'])
    op.create_foreign_key('broadcasts_created_by_staff_id_fkey', 'broadcasts', 'staff_members', ['created_by_staff_id'], ['tg_user_id'])
    
    # Step 7: Drop id column from staff_members
    op.drop_column('staff_members', 'id')
    op.execute("DROP SEQUENCE IF EXISTS staff_members_id_seq")
