"""
Script to add a test escalation record to the database.

This creates:
1. A test user (if not exists)
2. A test staff member (if not exists)
3. A test ticket assigned to the staff member
4. An escalation record for that ticket
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select

from constants import get_session
from database.models import (
    User, Staff_Member, Ticket, Escalation,
    TicketType, TicketStatus, EscalationType,
    StaffRole, DeliveryMethod
)


async def create_test_escalation():
    """Create a test escalation in the database."""
    
    async with get_session() as session:
        try:
            # 1. Find or create test user
            result = await session.execute(
                select(User).where(User.tg_user_id == 999999999)
            )
            test_user = result.scalar_one_or_none()
            
            if not test_user:
                test_user = User(
                    tg_user_id=999999999,
                    full_name="Тестовый Клиент",
                    phone_number="+79991234567",
                    registration_status="ACTIVE"
                )
                session.add(test_user)
                await session.flush()
                print(f"✅ Created test user: {test_user.full_name} (ID: {test_user.id})")
            else:
                print(f"✅ Found existing test user: {test_user.full_name} (ID: {test_user.id})")
            
            # 2. Use existing staff member with ID 3
            result = await session.execute(
                select(Staff_Member).where(Staff_Member.id == 3)
            )
            test_staff = result.scalar_one_or_none()
            
            if not test_staff:
                print("❌ Staff member with ID 3 not found!")
                return
            
            print(f"✅ Using existing staff: {test_staff.full_name} (ID: {test_staff.id})")
            
            # 3. Create test ticket
            # Set created_at to 25 minutes ago to simulate escalation scenario
            created_time = datetime.now() - timedelta(minutes=25)
            
            test_ticket = Ticket(
                ticket_type=TicketType.TECHNICAL_SUPPORT,
                ticket_status=TicketStatus.IN_PROGRESS,
                user_id=test_user.id,
                assigned_staff_id=test_staff.id,
                description="Тестовая заявка для проверки функционала эскалаций",
                delivery_method=DeliveryMethod.TELEGRAM,
                is_escalated=True,
                escalation_level=1,
                escalated_at=datetime.now() - timedelta(minutes=5),
                created_at=created_time,
                updated_at=created_time
            )
            session.add(test_ticket)
            await session.flush()
            print(f"✅ Created test ticket: #{test_ticket.id}")
            print(f"   Type: {test_ticket.ticket_type.value}")
            print(f"   Status: {test_ticket.ticket_status.value}")
            print(f"   Created: {test_ticket.created_at}")
            print(f"   Assigned to: {test_staff.full_name}")
            
            # 4. Create escalation record
            escalation_time = datetime.now() - timedelta(minutes=5)
            test_escalation = Escalation(
                ticket_id=test_ticket.id,
                escalation_type=EscalationType.ESCALATION_20MIN,
                is_resolved=False,
                created_at=escalation_time,
                updated_at=escalation_time
            )
            session.add(test_escalation)
            await session.flush()
            print(f"✅ Created escalation: ID {test_escalation.id}")
            print(f"   Type: {test_escalation.escalation_type.value}")
            print(f"   Resolved: {test_escalation.is_resolved}")
            print(f"   Created: {test_escalation.created_at}")
            
            # Commit all changes
            await session.commit()
            
            print("\n" + "="*60)
            print("✅ Test escalation created successfully!")
            print("="*60)
            print(f"\nEscalation ID: {test_escalation.id}")
            print(f"Ticket ID: {test_ticket.id}")
            print(f"User: {test_user.full_name} (Telegram ID: {test_user.tg_user_id})")
            print(f"Staff: {test_staff.full_name} (Telegram ID: {test_staff.tg_user_id})")
            print(f"\nYou can now test the escalation menu in Telegram!")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error creating test escalation: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(create_test_escalation())
