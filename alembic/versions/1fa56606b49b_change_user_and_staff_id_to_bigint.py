"""change_user_and_staff_id_to_bigint

Revision ID: 1fa56606b49b
Revises: 65143ee6e41d
Create Date: 2026-02-17 17:55:25.599743

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1fa56606b49b'
down_revision: Union[str, Sequence[str], None] = '65143ee6e41d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Change user_id and staff_id columns from INTEGER to BIGINT.
    
    This fixes the issue where large messenger IDs (> 2 billion) cause
    "value out of int32 range" errors in queries.
    """
    # Change users.id from INTEGER to BIGINT
    op.alter_column('users', 'id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                    autoincrement=True)
    
    # Change staff_members.id from INTEGER to BIGINT
    op.alter_column('staff_members', 'id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                    autoincrement=True)
    
    # Change foreign key references to users.id
    op.alter_column('manager_assignments', 'user_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)
    
    op.alter_column('gs_keys', 'user_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)
    
    op.alter_column('tickets', 'user_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)
    
    op.alter_column('users', 'default_manager_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)
    
    # Change foreign key references to staff_members.id
    op.alter_column('manager_assignments', 'manager_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)
    
    op.alter_column('tickets', 'assigned_staff_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)
    
    op.alter_column('staff_members', 'backup_manager_1_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)
    
    op.alter_column('staff_members', 'backup_manager_2_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)
    
    # Change user_organizations.user_id from INTEGER to BIGINT
    op.alter_column('user_organizations', 'user_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)
    
    # Change foreign key references in other tables
    op.alter_column('notification_events', 'user_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)
    
    op.alter_column('action_logs', 'user_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)
    
    op.alter_column('action_logs', 'staff_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)
    
    op.alter_column('broadcasts', 'created_by_staff_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)
    
    op.alter_column('broadcast_deliveries', 'user_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)
    
    op.alter_column('api_retry_queue', 'user_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)


def downgrade() -> None:
    """Revert BIGINT changes back to INTEGER."""
    # Revert additional foreign key references
    op.alter_column('api_retry_queue', 'user_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    
    op.alter_column('broadcast_deliveries', 'user_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
    
    op.alter_column('broadcasts', 'created_by_staff_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
    
    op.alter_column('action_logs', 'staff_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    
    op.alter_column('action_logs', 'user_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    
    op.alter_column('notification_events', 'user_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
    
    op.alter_column('user_organizations', 'user_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
    
    # Revert foreign key references to staff_members.id
    op.alter_column('staff_members', 'backup_manager_2_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    
    op.alter_column('staff_members', 'backup_manager_1_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    
    op.alter_column('tickets', 'assigned_staff_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    
    op.alter_column('manager_assignments', 'manager_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
    
    # Revert foreign key references to users.id
    op.alter_column('users', 'default_manager_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    
    op.alter_column('tickets', 'user_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
    
    op.alter_column('gs_keys', 'user_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
    
    op.alter_column('manager_assignments', 'user_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
    
    # Revert staff_members.id from BIGINT to INTEGER
    op.alter_column('staff_members', 'id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False,
                    autoincrement=True)
    
    # Revert users.id from BIGINT to INTEGER
    op.alter_column('users', 'id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False,
                    autoincrement=True)
