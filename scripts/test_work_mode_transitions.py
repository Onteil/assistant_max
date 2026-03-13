#!/usr/bin/env python3
"""
Test Work Mode Transitions

This script helps test the work mode transition monitoring system by:
1. Showing current work mode
2. Manually triggering queue processing
3. Simulating work mode changes
4. Monitoring transition detection

Usage:
    python scripts/test_work_mode_transitions.py [command]

Commands:
    status      - Show current work mode and monitor status
    trigger     - Manually trigger queue processing
    simulate    - Simulate work mode transition (for testing)
    monitor     - Monitor work mode changes in real-time
"""

import asyncio
import sys
import os
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pytz
from constants import get_session
from database.models import WorkMode
from services.calendar_service import get_current_work_mode

MOSCOW_TZ = pytz.timezone('Europe/Moscow')


async def show_status():
    """Show current work mode and system status."""
    print("📊 Work Mode Monitor Status")
    print("=" * 40)
    
    try:
        async with get_session() as session:
            work_mode = await get_current_work_mode(session)
            current_time = datetime.now(MOSCOW_TZ)
            
            print(f"🕐 Current time (Moscow): {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⚙️  Current work mode: {work_mode.value}")
            
            # Show work mode description
            mode_descriptions = {
                WorkMode.REGULAR: "Regular working hours - immediate notifications",
                WorkMode.EXTENDED: "Extended hours - duty staff notifications", 
                WorkMode.NON_WORKING: "Non-working hours - tickets queued"
            }
            print(f"📝 Description: {mode_descriptions.get(work_mode, 'Unknown')}")
            
            # Check if there are pending tickets
            from sqlalchemy import select, and_
            from database.models import Ticket, TicketStatus, TicketType
            
            # Find tickets created in the last 24 hours that are still NEW
            yesterday = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            
            stmt = select(Ticket).where(
                and_(
                    Ticket.ticket_status == TicketStatus.NEW,
                    Ticket.created_at >= yesterday,
                    Ticket.ticket_type.in_([TicketType.INVOICE, TicketType.RENEWAL])
                )
            )
            
            result = await session.execute(stmt)
            pending_tickets = result.scalars().all()
            
            print(f"📋 Pending tickets in queue: {len(pending_tickets)}")
            
            if pending_tickets:
                print("\n📋 Queued tickets:")
                for ticket in pending_tickets[:5]:  # Show first 5
                    created_time = ticket.created_at.strftime('%H:%M')
                    print(f"   • #{ticket.id} ({ticket.ticket_type.value}) - created at {created_time}")
                
                if len(pending_tickets) > 5:
                    print(f"   ... and {len(pending_tickets) - 5} more")
    
    except Exception as e:
        print(f"❌ Error getting status: {e}")
        return 1
    
    return 0


async def trigger_queue_processing():
    """Manually trigger queue processing."""
    print("🚀 Triggering queue processing manually...")
    
    try:
        from celery_app.work_mode_monitor_tasks import trigger_queue_processing
        
        # Schedule the task through Celery
        task_result = trigger_queue_processing.apply_async(
            args=["manual_test"],
            queue="work_mode_monitor"
        )
        
        print(f"✅ Queue processing triggered!")
        print(f"   Task ID: {task_result.id}")
        print(f"   Queue: work_mode_monitor")
        print("\n📋 Check Celery logs to see the processing results.")
    
    except Exception as e:
        print(f"❌ Error triggering queue processing: {e}")
        return 1
    
    return 0


async def simulate_transition():
    """Simulate work mode transition for testing."""
    print("🎭 Simulating work mode transition...")
    print("This will manually call the transition check task.")
    
    try:
        from celery_app.work_mode_monitor_tasks import check_work_mode_transition
        
        # Create a mock task instance for direct execution
        class MockTask:
            def __init__(self):
                self.request = None
                self.MaxRetriesExceededError = Exception
            
            def retry(self, exc, countdown):
                raise exc
        
        mock_task = MockTask()
        result = await check_work_mode_transition.run_async(mock_task)
        
        print(f"📊 Transition check result:")
        print(f"   Status: {result['status']}")
        print(f"   Current mode: {result['current_mode']}")
        
        if result['status'] == 'transition_detected':
            print(f"   Previous mode: {result.get('previous_mode', 'None')}")
            print(f"   Queue triggered: {result.get('queue_processing_triggered', False)}")
            if result.get('queue_task_id'):
                print(f"   Queue task ID: {result['queue_task_id']}")
        
        elif result['status'] == 'no_transition':
            print(f"   Check time: {result['check_time']}")
        
        elif result['status'] == 'error':
            print(f"   Error: {result.get('error', 'Unknown error')}")
    
    except Exception as e:
        print(f"❌ Error simulating transition: {e}")
        return 1
    
    return 0


async def monitor_transitions():
    """Monitor work mode changes in real-time."""
    print("👁️  Monitoring work mode transitions...")
    print("Press Ctrl+C to stop monitoring")
    print("=" * 50)
    
    last_mode = None
    
    try:
        while True:
            async with get_session() as session:
                current_mode = await get_current_work_mode(session)
                current_time = datetime.now(MOSCOW_TZ)
                
                if last_mode is None:
                    print(f"🔄 {current_time.strftime('%H:%M:%S')} - Initial mode: {current_mode.value}")
                elif last_mode != current_mode:
                    print(f"🔄 {current_time.strftime('%H:%M:%S')} - Transition: {last_mode.value} → {current_mode.value}")
                    
                    if (last_mode == WorkMode.NON_WORKING and 
                        current_mode in [WorkMode.REGULAR, WorkMode.EXTENDED]):
                        print("   ⚡ This transition should trigger queue processing!")
                else:
                    print(f"⏱️  {current_time.strftime('%H:%M:%S')} - Mode: {current_mode.value} (no change)")
                
                last_mode = current_mode
            
            # Wait 30 seconds before next check
            await asyncio.sleep(30)
    
    except KeyboardInterrupt:
        print("\n👋 Monitoring stopped by user")
        return 0
    except Exception as e:
        print(f"❌ Error during monitoring: {e}")
        return 1


async def main():
    """Main function."""
    if len(sys.argv) < 2:
        command = "status"
    else:
        command = sys.argv[1].lower()
    
    if command == "status":
        return await show_status()
    elif command == "trigger":
        return await trigger_queue_processing()
    elif command == "simulate":
        return await simulate_transition()
    elif command == "monitor":
        return await monitor_transitions()
    else:
        print("❌ Unknown command. Available commands:")
        print("   status      - Show current work mode and monitor status")
        print("   trigger     - Manually trigger queue processing")
        print("   simulate    - Simulate work mode transition (for testing)")
        print("   monitor     - Monitor work mode changes in real-time")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)