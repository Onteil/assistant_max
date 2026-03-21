"""Check ticket status and escalation tasks by ticket ID."""

import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from constants import AsyncSessionLocal
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from database.models import Ticket, Staff_Member, User, Action_Log, System_Settings
import redis
import json


async def check_ticket(ticket_id_input: str):
    """Check ticket status and escalation tasks."""
    
    async with AsyncSessionLocal() as session:
        # Parse ticket ID as integer
        try:
            ticket_id = int(ticket_id_input)
        except ValueError:
            print(f"❌ '{ticket_id_input}' is not a valid ticket ID (must be integer)")
            return
        
        # Find ticket by ID with eager loading
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.assigned_staff).selectinload(Staff_Member.backup_manager_1),
                selectinload(Ticket.assigned_staff).selectinload(Staff_Member.backup_manager_2),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys)
            )
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            print(f"❌ Ticket #{ticket_id} not found")
            return
        
        print("─" * 5)
        print(f"📋 TICKET #{ticket.id}")
        print("─" * 5)
        
        # Basic info
        print(f"\n📊 Basic Information:")
        print(f"   Type: {ticket.ticket_type.value}")
        print(f"   Status: {ticket.ticket_status.value}")
        print(f"   Escalation Level: {ticket.escalation_level}")
        print(f"   Is Escalated: {ticket.is_escalated}")
        print(f"   Created: {ticket.created_at}")
        print(f"   Updated: {ticket.updated_at}")
        
        # Calculate age
        from utils.timezone_helpers import get_moscow_now_naive
        age = get_moscow_now_naive() - ticket.created_at
        age_minutes = age.total_seconds() / 60
        print(f"   Age: {age_minutes:.1f} minutes")
        
        # User info
        if ticket.user:
            print(f"\n👤 User:")
            print(f"   Name: {ticket.user.full_name}")
            print(f"   Phone: {ticket.user.phone_number}")
            print(f"   MAX User ID: {ticket.user.max_user_id}")
        
        # Staff info
        if ticket.assigned_staff:
            print(f"\n👨‍💼 Assigned Staff:")
            print(f"   Name: {ticket.assigned_staff.full_name}")
            print(f"   Role: {ticket.assigned_staff.staff_role.value}")
            print(f"   MAX User ID: {ticket.assigned_staff.max_user_id}")
            print(f"   MAX Chat ID: {ticket.assigned_staff.max_chat_id}")
            
            # Backup managers
            if ticket.assigned_staff.backup_manager_1:
                print(f"\n   Backup Manager 1:")
                print(f"      Name: {ticket.assigned_staff.backup_manager_1.full_name}")
                print(f"      MAX Chat ID: {ticket.assigned_staff.backup_manager_1.max_chat_id}")
            else:
                print(f"\n   Backup Manager 1: Not configured")
            
            if ticket.assigned_staff.backup_manager_2:
                print(f"\n   Backup Manager 2:")
                print(f"      Name: {ticket.assigned_staff.backup_manager_2.full_name}")
                print(f"      MAX Chat ID: {ticket.assigned_staff.backup_manager_2.max_chat_id}")
            else:
                print(f"   Backup Manager 2: Not configured")
        
        # Escalation tasks
        print(f"\n⏰ Escalation Tasks:")
        print(f"   Reminder Task ID: {ticket.escalation_task_reminder_id}")
        print(f"   Escalation Task ID: {ticket.escalation_task_escalation_id}")
        
        # Check Redis for task status
        if ticket.escalation_task_reminder_id or ticket.escalation_task_escalation_id:
            print(f"\n🔍 Checking Redis for task status...")
            try:
                from constants import REDIS, CELERY_REDIS_DB_NUMBER
                redis_url = REDIS.replace('redis://', '')
                host_port = redis_url.split('/')[0]
                host, port = host_port.split(':')
                
                r = redis.Redis(
                    host=host,
                    port=int(port),
                    db=int(CELERY_REDIS_DB_NUMBER),
                    decode_responses=True
                )
                
                if ticket.escalation_task_reminder_id:
                    reminder_key = f"celery-task-meta-{ticket.escalation_task_reminder_id}"
                    if r.exists(reminder_key):
                        result_data = r.get(reminder_key)
                        data = json.loads(result_data)
                        print(f"\n   ✅ Reminder Task Status:")
                        print(f"      Status: {data.get('status')}")
                        if data.get('status') == 'SUCCESS':
                            print(f"      Result: {data.get('result')}")
                        elif data.get('status') == 'FAILURE':
                            print(f"      Error: {data.get('result', {}).get('exc_message')}")
                    else:
                        print(f"\n   ⏳ Reminder Task: Pending (not executed yet)")
                
                if ticket.escalation_task_escalation_id:
                    escalation_key = f"celery-task-meta-{ticket.escalation_task_escalation_id}"
                    if r.exists(escalation_key):
                        result_data = r.get(escalation_key)
                        data = json.loads(result_data)
                        print(f"\n   ✅ Escalation Task Status:")
                        print(f"      Status: {data.get('status')}")
                        if data.get('status') == 'SUCCESS':
                            print(f"      Result: {data.get('result')}")
                        elif data.get('status') == 'FAILURE':
                            print(f"      Error: {data.get('result', {}).get('exc_message')}")
                    else:
                        print(f"\n   ⏳ Escalation Task: Pending (not executed yet)")
                
            except Exception as e:
                print(f"\n   ❌ Error checking Redis: {e}")
        
        # Check action logs
        print(f"\n📝 Recent Action Logs:")
        stmt = (
            select(Action_Log)
            .where(Action_Log.ticket_id == ticket.id)
            .order_by(Action_Log.action_timestamp.desc())
            .limit(10)
        )
        result = await session.execute(stmt)
        logs = result.scalars().all()
        
        if logs:
            for log in logs:
                print(f"\n   {log.action_timestamp} - {log.action_type.value}")
                if log.action_details:
                    for key, value in log.action_details.items():
                        print(f"      {key}: {value}")
        else:
            print("   No action logs found")
        
        # Check system settings
        print(f"\n⚙️ Current System Settings:")
        stmt = select(System_Settings).where(
            System_Settings.key == 'manager_response_timeout'
        )
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        
        if setting:
            print(f"   Таймаут эскалации (manager_response_timeout): {setting.value} минут")
            print(f"   Применяется ко всем типам эскалации")
        else:
            print(f"   ⚠️ Настройка manager_response_timeout не найдена")
        
        print("\n" + "─" * 5)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_ticket_by_id.py <ticket_id>")
        print("Example: python check_ticket_by_id.py 79")
        sys.exit(1)
    
    ticket_id = sys.argv[1]
    asyncio.run(check_ticket(ticket_id))
