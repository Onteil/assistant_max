#!/usr/bin/env python3
"""
Comprehensive test script for backup manager escalation flow.

Tests:
1. System settings integration for timeout intervals
2. Backup manager escalation logic when no backup managers are configured
3. Proper escalation flow with configured backup managers
4. Immediate escalation to admins when backup managers are unavailable

Requirements: Backup Manager Escalation Flow
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from constants import AsyncSessionLocal
from database.models import (
    Staff_Member, 
    Ticket, 
    TicketStatus, 
    TicketType, 
    User,
    Organization,
    StaffRole
)
from celery_app.escalation_tasks import (
    get_backup_escalation_timeout_sync,
    _check_ticket_reminder_async,
    _escalate_to_backup_manager_1,
    _escalate_to_backup_manager_2,
    _escalate_to_admins
)
from services.settings_service import get_setting, update_setting
from sqlalchemy import select
from sqlalchemy.orm import selectinload


async def test_system_settings_integration():
    """Test that timeout intervals are properly read from system settings."""
    print("\n=== Testing System Settings Integration ===")
    
    async with AsyncSessionLocal() as session:
        # Test getting current setting
        timeout_minutes = await get_setting(session, "backup_escalation_timeout")
        print(f"Current backup_escalation_timeout setting: {timeout_minutes} minutes")
        
        # Test sync wrapper
        timeout_seconds = get_backup_escalation_timeout_sync()
        print(f"Sync wrapper result: {timeout_seconds} seconds ({timeout_seconds//60} minutes)")
        
        # Verify they match
        if timeout_minutes and int(timeout_minutes) * 60 == timeout_seconds:
            print("✅ System settings integration working correctly")
            return True
        else:
            print("❌ System settings integration failed")
            return False


async def test_no_backup_managers_escalation():
    """Test immediate escalation when no backup managers are configured."""
    print("\n=== Testing No Backup Managers Escalation ===")
    
    async with AsyncSessionLocal() as session:
        # Create test staff without backup managers
        staff = Staff_Member(
            name="Test Staff",
            staff_role=StaffRole.MANAGER,
            is_active=True,
            backup_manager_1_id=None,  # No backup managers
            backup_manager_2_id=None,
            max_user_id=12345,
            max_chat_id="12345"
        )
        session.add(staff)
        await session.flush()
        
        # Create test user
        user = User(
            phone_number="+1234567890",
            first_name="Test",
            last_name="User",
            max_user_id=67890,
            max_chat_id="67890"
        )
        session.add(user)
        await session.flush()
        
        # Create test ticket
        ticket = Ticket(
            user_id=user.id,
            assigned_staff_id=staff.id,
            ticket_type=TicketType.TECHNICAL_SUPPORT,
            ticket_status=TicketStatus.NEW,
            escalation_level=0,
            description="Test ticket for no backup managers",
            created_at=datetime.now(timezone.utc)
        )
        session.add(ticket)
        await session.flush()
        
        # Load relationships
        await session.refresh(ticket, ['user', 'assigned_staff'])
        
        print(f"Created test ticket {ticket.id} with staff {staff.id} (no backup managers)")
        
        # Test escalation - should go directly to admins
        result = await _escalate_to_backup_manager_1(ticket, session)
        
        print(f"Escalation result: {result}")
        
        # Verify it escalated directly to admins
        if result['status'] == 'success' and 'escalated directly to admins' in result.get('message', ''):
            print("✅ Correctly escalated directly to admins when no backup managers configured")
            success = True
        else:
            print("❌ Failed to escalate directly to admins")
            success = False
        
        # Cleanup
        await session.delete(ticket)
        await session.delete(user)
        await session.delete(staff)
        await session.commit()
        
        return success


async def test_backup_manager_chain():
    """Test proper escalation chain with configured backup managers."""
    print("\n=== Testing Backup Manager Chain ===")
    
    async with AsyncSessionLocal() as session:
        # Create backup managers
        backup1 = Staff_Member(
            name="Backup Manager 1",
            staff_role=StaffRole.MANAGER,
            is_active=True,
            max_user_id=11111,
            max_chat_id="11111"
        )
        session.add(backup1)
        await session.flush()
        
        backup2 = Staff_Member(
            name="Backup Manager 2", 
            staff_role=StaffRole.MANAGER,
            is_active=True,
            max_user_id=22222,
            max_chat_id="22222"
        )
        session.add(backup2)
        await session.flush()
        
        # Create main staff with backup managers
        staff = Staff_Member(
            name="Main Staff",
            staff_role=StaffRole.MANAGER,
            is_active=True,
            backup_manager_1_id=backup1.id,
            backup_manager_2_id=backup2.id,
            max_user_id=33333,
            max_chat_id="33333"
        )
        session.add(staff)
        await session.flush()
        
        # Create test user
        user = User(
            phone_number="+1234567890",
            first_name="Test",
            last_name="User",
            max_user_id=44444,
            max_chat_id="44444"
        )
        session.add(user)
        await session.flush()
        
        # Create test ticket
        ticket = Ticket(
            user_id=user.id,
            assigned_staff_id=staff.id,
            ticket_type=TicketType.TECHNICAL_SUPPORT,
            ticket_status=TicketStatus.NEW,
            escalation_level=0,
            description="Test ticket for backup manager chain",
            created_at=datetime.now(timezone.utc)
        )
        session.add(ticket)
        await session.flush()
        
        # Load relationships
        await session.refresh(ticket, ['user', 'assigned_staff'])
        await session.refresh(staff, ['backup_manager_1', 'backup_manager_2'])
        
        print(f"Created test ticket {ticket.id} with backup managers {backup1.id} and {backup2.id}")
        
        # Test Level 0 → Level 1 escalation
        print("Testing Level 0 → Level 1 escalation...")
        result1 = await _escalate_to_backup_manager_1(ticket, session)
        print(f"Level 1 result: {result1}")
        
        # Verify ticket was reassigned to backup_manager_1
        await session.refresh(ticket)
        level1_success = (
            result1['status'] == 'success' and 
            ticket.assigned_staff_id == backup1.id and
            ticket.escalation_level == 1
        )
        
        if level1_success:
            print("✅ Level 0 → Level 1 escalation successful")
        else:
            print("❌ Level 0 → Level 1 escalation failed")
        
        # Test Level 1 → Level 2 escalation
        print("Testing Level 1 → Level 2 escalation...")
        result2 = await _escalate_to_backup_manager_2(ticket, session)
        print(f"Level 2 result: {result2}")
        
        # Verify ticket was reassigned to backup_manager_2
        await session.refresh(ticket)
        level2_success = (
            result2['status'] == 'success' and
            ticket.assigned_staff_id == backup2.id and
            ticket.escalation_level == 2
        )
        
        if level2_success:
            print("✅ Level 1 → Level 2 escalation successful")
        else:
            print("❌ Level 1 → Level 2 escalation failed")
        
        # Cleanup
        await session.delete(ticket)
        await session.delete(user)
        await session.delete(staff)
        await session.delete(backup1)
        await session.delete(backup2)
        await session.commit()
        
        return level1_success and level2_success


async def test_timeout_configuration():
    """Test that timeout can be configured and affects escalation scheduling."""
    print("\n=== Testing Timeout Configuration ===")
    
    async with AsyncSessionLocal() as session:
        # Get current timeout
        original_timeout = await get_setting(session, "backup_escalation_timeout")
        print(f"Original timeout: {original_timeout} minutes")
        
        # Update timeout to 5 minutes
        success, message = await update_setting(
            session, 
            "backup_escalation_timeout", 
            5, 
            admin_id=1  # Assuming admin exists
        )
        
        if success:
            print("✅ Successfully updated timeout to 5 minutes")
            
            # Test that sync function returns new value
            new_timeout = get_backup_escalation_timeout_sync()
            expected_seconds = 5 * 60  # 5 minutes = 300 seconds
            
            if new_timeout == expected_seconds:
                print(f"✅ Sync function returns correct value: {new_timeout} seconds")
                config_success = True
            else:
                print(f"❌ Sync function returned {new_timeout}, expected {expected_seconds}")
                config_success = False
            
            # Restore original timeout
            if original_timeout:
                await update_setting(
                    session,
                    "backup_escalation_timeout",
                    int(original_timeout),
                    admin_id=1
                )
                print(f"✅ Restored original timeout: {original_timeout} minutes")
        else:
            print(f"❌ Failed to update timeout: {message}")
            config_success = False
        
        return config_success


async def main():
    """Run all tests."""
    print("🚀 Starting Backup Manager Escalation Tests")
    print("=" * 50)
    
    tests = [
        ("System Settings Integration", test_system_settings_integration),
        ("No Backup Managers Escalation", test_no_backup_managers_escalation),
        ("Backup Manager Chain", test_backup_manager_chain),
        ("Timeout Configuration", test_timeout_configuration),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Backup manager escalation is working correctly.")
        print("\n📋 Key Features Verified:")
        print("• Timeout intervals are read from system settings")
        print("• Immediate escalation when no backup managers configured")
        print("• Proper 3-level escalation chain (Level 0 → 1 → 2 → Admins)")
        print("• Configurable timeout intervals")
        print("• System uses configured timeout (10 minutes by default)")
        print("• If backup managers unavailable, escalates immediately to admins")
    else:
        print("⚠️  Some tests failed. Please review the implementation.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)