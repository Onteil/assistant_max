"""
Test script to verify relationships work correctly.
"""

from database.models import (
    Base, User, Organization, GS_Key, Staff_Member, Manager_Assignment,
    Ticket, Message, File_Attachment, Action_Log, Calendar_Rule,
    Notification_Event, Broadcast, Broadcast_Delivery,
    RegistrationStatus, SubscriptionStatus, StaffRole, TicketType, TicketStatus,
    KeyConflictStatus, DeliveryMethod, SenderType, MessageType, FileType,
    UploaderType, ActionType, WorkMode, EventType, EventStatus,
    BroadcastStatus, DeliveryStatus
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import datetime

def test_relationships():
    """Test that relationships work correctly."""
    
    print("=" * 60)
    print("TESTING DATABASE RELATIONSHIPS")
    print("=" * 60)
    
    # Create in-memory database
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Test 1: Create User with Organizations
        print("\n1. Testing User-Organization many-to-many relationship...")
        user = User(
            tg_user_id=123456789,
            phone_number="+79991234567",
            username="testuser",
            first_name="Test",
            last_name="User",
            full_name="Test User",
            registration_status=RegistrationStatus.ACTIVE,
            subscription_status=SubscriptionStatus.ACTIVE
        )
        
        org1 = Organization(inn="1234567890", organization_name="Test Org 1")
        org2 = Organization(inn="9876543210", organization_name="Test Org 2")
        
        user.organizations.append(org1)
        user.organizations.append(org2)
        
        session.add(user)
        session.commit()
        
        # Verify bidirectional navigation
        assert len(user.organizations) == 2
        assert org1 in user.organizations
        assert user in org1.users
        print("   ✓ User can have multiple organizations")
        print("   ✓ Bidirectional navigation works")
        
        # Test 2: Create Staff Member with backup managers
        print("\n2. Testing Staff_Member self-referential relationships...")
        manager1 = Staff_Member(
            tg_user_id=111111111,
            full_name="Manager One",
            position="Senior Manager",
            staff_role=StaffRole.MANAGER,
            is_active=True
        )
        
        manager2 = Staff_Member(
            tg_user_id=222222222,
            full_name="Manager Two",
            position="Manager",
            staff_role=StaffRole.MANAGER,
            is_active=True,
            backup_manager_1_id=111111111
        )
        
        session.add(manager1)
        session.add(manager2)
        session.commit()
        
        # Refresh to load relationships
        session.refresh(manager2)
        session.refresh(manager1)
        
        assert manager2.backup_manager_1.tg_user_id == 111111111
        print("   ✓ Staff member can reference backup managers")
        
        # Test 3: Create GS_Key linked to User
        print("\n3. Testing User-GS_Key one-to-many relationship...")
        key1 = GS_Key(
            key_number="AB123456",
            tg_user_id=user.tg_user_id,
            conflict_status=KeyConflictStatus.NONE
        )
        key2 = GS_Key(
            key_number="CD789012",
            tg_user_id=user.tg_user_id,
            conflict_status=KeyConflictStatus.NONE
        )
        
        session.add(key1)
        session.add(key2)
        session.commit()
        
        session.refresh(user)
        assert len(user.gs_keys) == 2
        assert key1.user.tg_user_id == user.tg_user_id
        print("   ✓ User can have multiple keys")
        print("   ✓ Key references user correctly")
        
        # Test 4: Create Manager Assignment
        print("\n4. Testing Manager_Assignment relationships...")
        assignment = Manager_Assignment(
            tg_user_id=user.tg_user_id,
            organization_inn=org1.inn,
            manager_id=manager1.tg_user_id
        )
        
        session.add(assignment)
        session.commit()
        
        session.refresh(assignment)
        assert assignment.user.tg_user_id == user.tg_user_id
        assert assignment.organization.inn == org1.inn
        assert assignment.manager.tg_user_id == manager1.tg_user_id
        print("   ✓ Manager assignment links user, organization, and manager")
        
        # Test 5: Create Ticket with relationships
        print("\n5. Testing Ticket relationships...")
        ticket = Ticket(
            ticket_type=TicketType.TECHNICAL_SUPPORT,
            ticket_status=TicketStatus.NEW,
            tg_user_id=user.tg_user_id,
            assigned_staff_id=manager1.tg_user_id,
            organization_inn=org1.inn,
            description="Test ticket",
            delivery_method=DeliveryMethod.TELEGRAM,
            escalation_level=0
        )
        
        # Add keys to ticket
        ticket.gs_keys.append(key1)
        
        session.add(ticket)
        session.commit()
        
        session.refresh(ticket)
        assert ticket.user.tg_user_id == user.tg_user_id
        assert ticket.assigned_staff.tg_user_id == manager1.tg_user_id
        assert ticket.organization.inn == org1.inn
        assert len(ticket.gs_keys) == 1
        assert key1 in ticket.gs_keys
        print("   ✓ Ticket links to user, staff, organization, and keys")
        
        # Test 6: Create Message for Ticket
        print("\n6. Testing Ticket-Message relationship...")
        message = Message(
            ticket_id=ticket.id,
            sender_type=SenderType.USER,
            sender_id=user.tg_user_id,
            message_text="Test message",
            message_type=MessageType.TEXT
        )
        
        session.add(message)
        session.commit()
        
        session.refresh(ticket)
        assert len(ticket.messages) == 1
        assert ticket.messages[0].message_text == "Test message"
        assert message.ticket.id == ticket.id
        print("   ✓ Ticket can have messages")
        print("   ✓ Message references ticket")
        
        # Test 7: Create File Attachment
        print("\n7. Testing File_Attachment relationships...")
        attachment = File_Attachment(
            ticket_id=ticket.id,
            message_id=message.id,
            file_type=FileType.IMAGE,
            telegram_file_id="test_file_id_123",
            file_name="screenshot.png",
            file_size=1024,
            uploader_id=user.tg_user_id,
            uploader_type=UploaderType.USER
        )
        
        session.add(attachment)
        session.commit()
        
        session.refresh(ticket)
        session.refresh(message)
        assert len(ticket.file_attachments) == 1
        assert len(message.file_attachments) == 1
        assert attachment.ticket.id == ticket.id
        assert attachment.message.id == message.id
        print("   ✓ File attachment links to ticket and message")
        
        # Test 8: Create Action Log
        print("\n8. Testing Action_Log relationships...")
        action_log = Action_Log(
            action_type=ActionType.TICKET_CREATED,
            ticket_id=ticket.id,
            tg_user_id=user.tg_user_id,
            staff_id=manager1.tg_user_id,
            action_details={"detail": "test"}
        )
        
        session.add(action_log)
        session.commit()
        
        session.refresh(action_log)
        assert action_log.ticket.id == ticket.id
        assert action_log.user.tg_user_id == user.tg_user_id
        assert action_log.staff.tg_user_id == manager1.tg_user_id
        print("   ✓ Action log links to ticket, user, and staff")
        
        # Test 9: Create Calendar Rule
        print("\n9. Testing Calendar_Rule creation...")
        calendar_rule = Calendar_Rule(
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            work_mode=WorkMode.REGULAR,
            work_start_time=datetime.time(9, 0),
            work_end_time=datetime.time(18, 0),
            rule_priority=50
        )
        
        session.add(calendar_rule)
        session.commit()
        
        assert calendar_rule.id is not None
        print("   ✓ Calendar rule created successfully")
        
        # Test 10: Create Notification Event
        print("\n10. Testing Notification_Event relationships...")
        notification = Notification_Event(
            tg_user_id=user.tg_user_id,
            event_type=EventType.RENEWAL_REMINDER_30,
            event_status=EventStatus.SCHEDULED,
            scheduled_for=datetime.datetime.utcnow() + datetime.timedelta(days=30),
            related_ticket_id=ticket.id,
            event_data={"reminder_type": "renewal"}
        )
        
        session.add(notification)
        session.commit()
        
        session.refresh(notification)
        assert notification.user.tg_user_id == user.tg_user_id
        assert notification.related_ticket.id == ticket.id
        print("   ✓ Notification event links to user and ticket")
        
        # Test 11: Create Broadcast
        print("\n11. Testing Broadcast relationships...")
        broadcast = Broadcast(
            created_by_staff_id=manager1.tg_user_id,
            message_text="Test broadcast message",
            broadcast_status=BroadcastStatus.DRAFT,
            target_user_count=1,
            delivered_count=0
        )
        
        session.add(broadcast)
        session.commit()
        
        session.refresh(broadcast)
        assert broadcast.created_by.tg_user_id == manager1.tg_user_id
        print("   ✓ Broadcast links to staff creator")
        
        # Test 12: Create Broadcast Delivery
        print("\n12. Testing Broadcast_Delivery relationships...")
        delivery = Broadcast_Delivery(
            broadcast_id=broadcast.id,
            tg_user_id=user.tg_user_id,
            delivery_status=DeliveryStatus.PENDING
        )
        
        session.add(delivery)
        session.commit()
        
        session.refresh(broadcast)
        session.refresh(delivery)
        assert len(broadcast.deliveries) == 1
        assert delivery.broadcast.id == broadcast.id
        assert delivery.user.tg_user_id == user.tg_user_id
        print("   ✓ Broadcast delivery links to broadcast and user")
        
        # Test 13: Test cascade delete
        print("\n13. Testing cascade delete...")
        ticket_id = ticket.id
        message_count = len(ticket.messages)
        attachment_count = len(ticket.file_attachments)
        
        session.delete(ticket)
        session.commit()
        
        # Verify messages and attachments were deleted
        remaining_messages = session.query(Message).filter_by(ticket_id=ticket_id).count()
        remaining_attachments = session.query(File_Attachment).filter_by(ticket_id=ticket_id).count()
        
        assert remaining_messages == 0
        assert remaining_attachments == 0
        print(f"   ✓ Cascade delete removed {message_count} message(s)")
        print(f"   ✓ Cascade delete removed {attachment_count} attachment(s)")
        
        print("\n" + "=" * 60)
        print("ALL RELATIONSHIP TESTS PASSED ✓")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

if __name__ == "__main__":
    success = test_relationships()
    exit(0 if success else 1)
