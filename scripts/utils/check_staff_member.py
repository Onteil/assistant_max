"""Check staff member details."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from constants import get_session
from sqlalchemy import select
from database.models import Staff_Member, Ticket


async def check_staff_and_ticket():
    """Check staff member and ticket details."""
    async with get_session() as session:
        # Check staff member ID 3
        stmt = select(Staff_Member).where(Staff_Member.id == 3)
        result = await session.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if staff:
            print(f"✅ Staff Member ID 3 найден:")
            print(f"   tg_user_id: {staff.tg_user_id}")
            print(f"   staff_role: {staff.staff_role}")
            print(f"   is_active: {staff.is_active}")
            print(f"   full_name: {staff.full_name}")
        else:
            print("❌ Staff Member ID 3 не найден")
        
        print()
        
        # Check ticket #37
        stmt = select(Ticket).where(Ticket.id == 37)
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if ticket:
            print(f"✅ Ticket #37 найден:")
            print(f"   status: {ticket.ticket_status}")
            print(f"   assigned_staff_id: {ticket.assigned_staff_id}")
            print(f"   created_at: {ticket.created_at}")
            print(f"   escalation_task_reminder_id: {ticket.escalation_task_reminder_id}")
            print(f"   escalation_task_escalation_id: {ticket.escalation_task_escalation_id}")
        else:
            print("❌ Ticket #37 не найден")


if __name__ == "__main__":
    asyncio.run(check_staff_and_ticket())
