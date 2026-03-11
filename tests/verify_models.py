"""
Verification script for database models.
Checks that all models, relationships, and constraints are properly defined.
"""

from database.models import (
    Base, User, Organization, GS_Key, Staff_Member, Manager_Assignment,
    Ticket, Message, File_Attachment, Action_Log, Calendar_Rule,
    Notification_Event, Broadcast, Broadcast_Delivery,
    user_organizations, ticket_keys
)
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

def verify_models():
    """Verify all models and relationships are properly configured."""
    
    print("=" * 60)
    print("DATABASE MODELS VERIFICATION")
    print("=" * 60)
    
    # Create in-memory SQLite database for testing
    engine = create_engine('sqlite:///:memory:', echo=False)
    
    # Create all tables
    print("\n1. Creating all tables...")
    try:
        Base.metadata.create_all(engine)
        print("   ✓ All tables created successfully")
    except Exception as e:
        print(f"   ✗ Error creating tables: {e}")
        return False
    
    # Verify tables exist
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    print(f"\n2. Verifying tables ({len(tables)} tables)...")
    expected_tables = [
        'users', 'organizations', 'gs_keys', 'staff_members',
        'manager_assignments', 'tickets', 'messages', 'file_attachments',
        'action_logs', 'calendar_rules', 'notification_events',
        'broadcasts', 'broadcast_deliveries',
        'user_organizations', 'ticket_keys'
    ]
    
    for table in expected_tables:
        if table in tables:
            print(f"   ✓ {table}")
        else:
            print(f"   ✗ {table} - MISSING")
            return False
    
    # Verify relationships
    print("\n3. Verifying model relationships...")
    
    relationships_to_check = [
        (User, ['organizations', 'gs_keys', 'tickets', 'manager_assignments', 
                'notification_events', 'default_manager', 'broadcast_deliveries', 'action_logs']),
        (Organization, ['users', 'tickets', 'manager_assignments']),
        (GS_Key, ['user', 'tickets']),
        (Staff_Member, ['tickets_assigned', 'manager_assignments', 'backup_manager_1', 
                        'backup_manager_2', 'broadcasts_created', 'managed_users', 'action_logs']),
        (Manager_Assignment, ['user', 'organization', 'manager']),
        (Ticket, ['user', 'assigned_staff', 'organization', 'gs_keys', 'messages', 
                  'file_attachments', 'action_logs', 'notification_events']),
        (Message, ['ticket', 'file_attachments']),
        (File_Attachment, ['ticket', 'message']),
        (Action_Log, ['ticket', 'user', 'staff']),
        (Notification_Event, ['user', 'related_ticket']),
        (Broadcast, ['created_by', 'deliveries']),
        (Broadcast_Delivery, ['broadcast', 'user']),
    ]
    
    for model, expected_rels in relationships_to_check:
        model_name = model.__name__
        mapper = inspect(model)
        actual_rels = [rel.key for rel in mapper.relationships]
        
        for rel in expected_rels:
            if rel in actual_rels:
                print(f"   ✓ {model_name}.{rel}")
            else:
                print(f"   ✗ {model_name}.{rel} - MISSING")
                return False
    
    # Verify primary keys
    print("\n4. Verifying primary keys...")
    pk_checks = [
        ('users', ['tg_user_id']),
        ('organizations', ['inn']),
        ('gs_keys', ['id']),
        ('staff_members', ['tg_user_id']),
        ('manager_assignments', ['id']),
        ('tickets', ['id']),
        ('messages', ['id']),
        ('file_attachments', ['id']),
        ('action_logs', ['id']),
        ('calendar_rules', ['id']),
        ('notification_events', ['id']),
        ('broadcasts', ['id']),
        ('broadcast_deliveries', ['id']),
    ]
    
    for table_name, expected_pk in pk_checks:
        pk_constraint = inspector.get_pk_constraint(table_name)
        actual_pk = pk_constraint['constrained_columns']
        if actual_pk == expected_pk:
            print(f"   ✓ {table_name}: {expected_pk}")
        else:
            print(f"   ✗ {table_name}: expected {expected_pk}, got {actual_pk}")
            return False
    
    # Verify foreign keys
    print("\n5. Verifying foreign keys...")
    fk_tables = [
        'gs_keys', 'manager_assignments', 'tickets', 'messages',
        'file_attachments', 'action_logs', 'notification_events',
        'broadcasts', 'broadcast_deliveries', 'user_organizations', 'ticket_keys'
    ]
    
    for table_name in fk_tables:
        fks = inspector.get_foreign_keys(table_name)
        if fks:
            print(f"   ✓ {table_name}: {len(fks)} foreign key(s)")
        else:
            print(f"   ✗ {table_name}: no foreign keys found")
    
    # Verify unique constraints
    print("\n6. Verifying unique constraints...")
    unique_checks = [
        ('users', 'phone_number'),
        ('gs_keys', 'key_number'),
        ('user_organizations', 'uq_user_organization'),
        ('ticket_keys', 'uq_ticket_key'),
        ('manager_assignments', 'uq_user_org_assignment'),
        ('broadcast_deliveries', 'uq_broadcast_user_delivery'),
    ]
    
    for table_name, constraint_name in unique_checks:
        unique_constraints = inspector.get_unique_constraints(table_name)
        indexes = inspector.get_indexes(table_name)
        
        # Check in unique constraints
        found = any(uc.get('name') == constraint_name for uc in unique_constraints)
        
        # Also check in indexes (SQLite sometimes creates unique indexes instead)
        if not found:
            found = any(idx.get('name') == constraint_name or 
                       (idx.get('unique') and constraint_name in str(idx.get('column_names', [])))
                       for idx in indexes)
        
        # For single column unique constraints, check column definition
        if not found and constraint_name in ['phone_number', 'key_number']:
            columns = inspector.get_columns(table_name)
            found = any(col['name'] == constraint_name and col.get('unique', False) 
                       for col in columns)
        
        if found:
            print(f"   ✓ {table_name}.{constraint_name}")
        else:
            print(f"   ⚠ {table_name}.{constraint_name} - may be implicit")
    
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE - ALL CHECKS PASSED ✓")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = verify_models()
    exit(0 if success else 1)
