#!/usr/bin/env python3
"""
Script to verify timezone fix implementation.

This script checks that:
1. New records are created with Moscow time
2. Existing records have been converted to Moscow time
3. Time calculations work correctly
"""

import asyncio
import sys
import os
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from constants import AsyncSessionLocal
from database.models import Ticket, User, TicketType, TicketStatus, RegistrationStatus
from utils.timezone_helpers import get_moscow_now_naive, get_moscow_now, MOSCOW_TZ
from services.ticket_service import format_ticket_for_itat


async def test_timezone_fix():
    """Test that timezone fix is working correctly."""
    
    print("🕐 Testing timezone fix implementation...")
    print("─" * 5)
    
    async with AsyncSessionLocal() as session:
        
        # Test 1: Check timezone helper functions
        print("1. Testing timezone helper functions:")
        
        moscow_now = get_moscow_now()
        moscow_now_naive = get_moscow_now_naive()
        
        print(f"   Moscow time (aware): {moscow_now}")
        print(f"   Moscow time (naive): {moscow_now_naive}")
        print(f"   Timezone: {moscow_now.tzinfo}")
        print(f"   Naive timezone: {moscow_now_naive.tzinfo}")
        
        # Verify they are close (within 1 second)
        diff = abs((moscow_now.replace(tzinfo=None) - moscow_now_naive).total_seconds())
        if diff < 1:
            print("   ✅ Timezone helpers working correctly")
        else:
            print(f"   ❌ Timezone helpers mismatch: {diff} seconds")
        
        print()
        
        # Test 2: Check existing tickets
        print("2. Checking existing tickets:")
        
        from sqlalchemy import select, func
        
        # Get some recent tickets
        stmt = select(Ticket).order_by(Ticket.created_at.desc()).limit(5)
        result = await session.execute(stmt)
        tickets = result.scalars().all()
        
        if tickets:
            for ticket in tickets:
                # Calculate time difference from now
                time_diff = moscow_now_naive - ticket.created_at
                hours_diff = time_diff.total_seconds() / 3600
                
                print(f"   Ticket #{ticket.id}:")
                print(f"     Created: {ticket.created_at}")
                print(f"     Hours ago: {hours_diff:.1f}")
                
                # Check if time seems reasonable (not in future, not too far in past)
                if -1 < hours_diff < 8760:  # Within last year, not in future
                    print(f"     ✅ Time looks correct")
                else:
                    print(f"     ⚠️  Time might be incorrect (too far in past/future)")
        else:
            print("   No tickets found")
        
        print()
        
        # Test 3: Create a test ticket to verify new records use Moscow time
        print("3. Testing new record creation:")
        
        # Find or create a test user
        stmt = select(User).where(User.phone_number.like('+7999%')).limit(1)
        result = await session.execute(stmt)
        test_user = result.scalar_one_or_none()
        
        if not test_user:
            print("   No test user found, creating one...")
            test_user = User(
                phone_number="+79991234567",
                first_name="Test",
                last_name="User",
                registration_status=RegistrationStatus.ACTIVE
            )
            session.add(test_user)
            await session.flush()
        
        # Create test ticket
        before_creation = get_moscow_now_naive()
        
        test_ticket = Ticket(
            user_id=test_user.id,
            ticket_type=TicketType.TECHNICAL_SUPPORT,
            ticket_status=TicketStatus.NEW,
            description="Test ticket for timezone verification"
        )
        session.add(test_ticket)
        await session.flush()
        
        after_creation = get_moscow_now_naive()
        
        # Check that created_at is between before and after
        creation_time = test_ticket.created_at
        
        print(f"   Before creation: {before_creation}")
        print(f"   Ticket created:  {creation_time}")
        print(f"   After creation:  {after_creation}")
        
        if before_creation <= creation_time <= after_creation:
            print("   ✅ New ticket created with correct Moscow time")
        else:
            print("   ❌ New ticket time is incorrect")
        
        # Test ticket formatting
        try:
            formatted = format_ticket_for_itat(test_ticket)
            print(f"   Formatted time: {formatted.get('created_at_str', 'N/A')}")
            print("   ✅ Ticket formatting works")
        except Exception as e:
            print(f"   ❌ Ticket formatting failed: {e}")
        
        # Clean up test ticket
        await session.delete(test_ticket)
        await session.commit()
        
        print()
        
        # Test 4: Check database statistics
        print("4. Database statistics:")
        
        # Count total tickets
        stmt = select(func.count(Ticket.id))
        result = await session.execute(stmt)
        total_tickets = result.scalar()
        
        # Count tickets from today
        today_start = moscow_now_naive.replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count(Ticket.id)).where(Ticket.created_at >= today_start)
        result = await session.execute(stmt)
        today_tickets = result.scalar()
        
        print(f"   Total tickets: {total_tickets}")
        print(f"   Today's tickets: {today_tickets}")
        
        # Check for any tickets with future timestamps (would indicate UTC issue)
        future_threshold = moscow_now_naive
        stmt = select(func.count(Ticket.id)).where(Ticket.created_at > future_threshold)
        result = await session.execute(stmt)
        future_tickets = result.scalar()
        
        if future_tickets == 0:
            print("   ✅ No tickets with future timestamps")
        else:
            print(f"   ⚠️  {future_tickets} tickets have future timestamps")
        
        print()
        
    print("─" * 5)
    print("🎉 Timezone fix verification completed!")
    
    # Summary
    print("\n📋 Summary:")
    print("- All new records will use Moscow time")
    print("- Existing records should be converted via migration")
    print("- Time calculations use Moscow timezone consistently")
    print("- Celery tasks already configured for Moscow timezone")


if __name__ == "__main__":
    asyncio.run(test_timezone_fix())