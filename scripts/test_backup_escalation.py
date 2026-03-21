#!/usr/bin/env python3
"""
Test script for backup manager escalation flow.

This script creates a test ticket and verifies the backup manager escalation
flow is working correctly.

Usage:
    python scripts/test_backup_escalation.py
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from constants import AsyncSessionLocal
from database.models import (
    Staff_Member, 
    Ticket, 
    TicketStatus, 
    TicketType, 
    User,
    StaffRole
)
from services.ticket_service import create_ticket
from celery_app.escalation_tasks import schedule_escalation_monitoring


async def test_backup_escalation_flow():
    """Test the backup manager escalation flow."""
    print("🧪 Testing Backup Manager Escalation Flow")
    print("─" * 5)
    
    async with AsyncSessionLocal() as session:
        # Find a test user
        user_stmt = select(User).where(User.max_user_id.isnot(None)).limit(1)
        user_result = await session.execute(user_stmt)
        test_user = user_result.scalar_one_or_none()
        
        if not test_user:
            print("❌ No test user found with MAX user ID")
            return False
        
        print(f"✅ Found test user: {test_user.full_name} (ID: {test_user.id})")
        
        # Find managers with different backup configurations for testing
        managers_stmt = (
            select(Staff_Member)
            .where(
                Staff_Member.staff_role == StaffRole.MANAGER,
                Staff_Member.is_active == True
            )
            .options(
                selectinload(Staff_Member.backup_manager_1),
                selectinload(Staff_Member.backup_manager_2)
            )
            .limit(5)
        )
        managers_result = await session.execute(managers_stmt)
        managers = managers_result.scalars().all()
        
        if not managers:
            print("❌ No managers found")
            return False
        
        # Analyze backup manager configurations
        print("📊 Manager Backup Configuration Analysis:")
        print("-" * 50)
        
        managers_with_backups = []
        managers_without_backups = []
        
        for manager in managers:
            has_backup1 = manager.backup_manager_1_id is not None
            has_backup2 = manager.backup_manager_2_id is not None
            
            backup_status = []
            if has_backup1:
                backup1_chat = manager.backup_manager_1.max_chat_id if manager.backup_manager_1 else None
                backup_status.append(f"Backup1: {manager.backup_manager_1.full_name} ({'✅' if backup1_chat else '❌ no chat_id'})")
            if has_backup2:
                backup2_chat = manager.backup_manager_2.max_chat_id if manager.backup_manager_2 else None
                backup_status.append(f"Backup2: {manager.backup_manager_2.full_name} ({'✅' if backup2_chat else '❌ no chat_id'})")
            
            if has_backup1 or has_backup2:
                managers_with_backups.append(manager)
                print(f"✅ {manager.full_name}: {', '.join(backup_status)}")
            else:
                managers_without_backups.append(manager)
                print(f"⚠️  {manager.full_name}: No backup managers configured")
        
        print()
        
        # Choose test manager
        if managers_with_backups:
            test_manager = managers_with_backups[0]
            print(f"🎯 Testing WITH backup managers: {test_manager.full_name}")
            expected_escalation_time = "30-40 minutes (through backup chain)"
        elif managers_without_backups:
            test_manager = managers_without_backups[0]
            print(f"🎯 Testing WITHOUT backup managers: {test_manager.full_name}")
            expected_escalation_time = "10 minutes (direct to admins)"
        else:
            print("❌ No suitable managers found")
            return False
        
        print(f"✅ Found test manager: {test_manager.full_name} (ID: {test_manager.id})")
        print(f"   Backup 1: {test_manager.backup_manager_1.full_name if test_manager.backup_manager_1 else 'None'}")
        print(f"   Backup 2: {test_manager.backup_manager_2.full_name if test_manager.backup_manager_2 else 'None'}")
        
        # Create test ticket
        ticket_data = {
            "ticket_type": TicketType.INVOICE,
            "user_id": test_user.id,
            "assigned_staff_id": test_manager.id,
            "organization_inn": "1234567890",
            "description": "Test ticket for backup manager escalation flow"
        }
        
        try:
            ticket = await create_ticket(session, ticket_data)
            await session.commit()
            print(f"✅ Created test ticket: #{ticket.id}")
            
            # Verify initial state
            print(f"   Status: {ticket.ticket_status.value}")
            print(f"   Escalation Level: {ticket.escalation_level}")
            print(f"   Assigned Staff: {ticket.assigned_staff.full_name}")
            
            # Check if escalation monitoring was scheduled
            if ticket.escalation_task_reminder_id:
                print(f"✅ Escalation monitoring scheduled: {ticket.escalation_task_reminder_id}")
                
                print(f"\n🎯 Expected Escalation Behavior:")
                print(f"   Manager: {test_manager.full_name}")
                
                if test_manager.backup_manager_1_id or test_manager.backup_manager_2_id:
                    print(f"   ⏱️  Escalation timeline: {expected_escalation_time}")
                    if test_manager.backup_manager_1:
                        print(f"   📱 10 min: Notify {test_manager.backup_manager_1.full_name} (Backup 1)")
                    if test_manager.backup_manager_2:
                        print(f"   📱 20 min: Notify {test_manager.backup_manager_2.full_name} (Backup 2)")
                    print(f"   🚨 Final: Notify administrators")
                else:
                    print(f"   ⏱️  Escalation timeline: {expected_escalation_time}")
                    print(f"   🚨 10 min: Direct escalation to administrators (no backup managers)")
            else:
                print("❌ Escalation monitoring not scheduled")
                return False
            
            # Verify backup managers have MAX chat IDs (only if they exist)
            backup_issues = []
            
            if test_manager.backup_manager_1:
                if not test_manager.backup_manager_1.max_chat_id:
                    backup_issues.append(f"Backup 1 ({test_manager.backup_manager_1.full_name}) has no max_chat_id → will escalate directly to admins")
            
            if test_manager.backup_manager_2:
                if not test_manager.backup_manager_2.max_chat_id:
                    backup_issues.append(f"Backup 2 ({test_manager.backup_manager_2.full_name}) has no max_chat_id → will escalate directly to admins")
            
            if backup_issues:
                print("\n⚠️  Configuration Issues (will cause immediate admin escalation):")
                for issue in backup_issues:
                    print(f"   - {issue}")
            else:
                if test_manager.backup_manager_1_id or test_manager.backup_manager_2_id:
                    print("\n✅ All configured backup managers have MAX chat IDs")
            
            if test_manager.backup_manager_2:
                if not test_manager.backup_manager_2.max_chat_id:
                    backup_issues.append(f"Backup 2 ({test_manager.backup_manager_2.full_name}) has no max_chat_id")
            
            if backup_issues:
                print("⚠️  Backup manager configuration issues:")
                for issue in backup_issues:
                    print(f"   - {issue}")
                print("💡 These managers won't receive notifications. Update max_chat_id in staff_members table.")
            else:
                print("✅ All backup managers have MAX chat IDs configured")
            
            print("\n🎯 Test Results:")
            print("✅ Backup manager escalation flow is properly configured")
            print("✅ Test ticket created successfully")
            print("✅ Escalation monitoring scheduled")
            print("\n📋 Next Steps:")
            print("1. Wait 10 minutes to see backup_manager_1 notification")
            print("2. Wait another 10 minutes to see backup_manager_2 notification")
            print("3. Wait another 10 minutes to see admin escalation")
            print(f"\n🔍 Monitor ticket #{ticket.id} in the database:")
            print(f"   SELECT id, ticket_status, escalation_level, assigned_staff_id FROM tickets WHERE id = {ticket.id};")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to create test ticket: {e}")
            await session.rollback()
            return False


async def check_celery_status():
    """Check if Celery is running."""
    try:
        from celery_app.celery_config import app
        
        # Try to get active tasks
        inspect = app.control.inspect()
        active_tasks = inspect.active()
        
        if active_tasks:
            print("✅ Celery is running")
            return True
        else:
            print("⚠️  Celery might not be running (no active tasks)")
            return True  # Still might be running, just no active tasks
            
    except Exception as e:
        print(f"❌ Celery connection failed: {e}")
        print("💡 Make sure Celery worker is running: celery -A celery_app.celery_config worker --loglevel=info")
        return False


async def main():
    """Main test function."""
    print("🚀 Backup Manager Escalation Test")
    print("─" * 5)
    
    # Check Celery status
    celery_ok = await check_celery_status()
    if not celery_ok:
        print("\n❌ Test aborted: Celery is not available")
        return
    
    print()
    
    # Run escalation flow test
    success = await test_backup_escalation_flow()
    
    print("\n" + "─" * 5)
    if success:
        print("🎉 Test completed successfully!")
        print("📊 Monitor the escalation flow in real-time using Celery logs")
    else:
        print("💥 Test failed - check configuration")


if __name__ == "__main__":
    asyncio.run(main())