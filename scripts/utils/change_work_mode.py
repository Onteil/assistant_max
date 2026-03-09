"""
Quick script to change work mode by creating calendar rules.

Usage:
    python change_work_mode.py regular    # Set to REGULAR mode
    python change_work_mode.py extended   # Set to EXTENDED mode
    python change_work_mode.py off        # Set to NON_WORKING mode
    python change_work_mode.py clear      # Clear all rules (use base schedule)
    python change_work_mode.py status     # Show current work mode
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import sys
from datetime import date, time, datetime

import pytz

from constants import get_session
from database.models import WorkMode
from services.calendar_service import CalendarService, get_current_work_mode


MOSCOW_TZ = pytz.timezone('Europe/Moscow')


async def set_work_mode(mode: str):
    """Set work mode for today."""
    today = datetime.now(MOSCOW_TZ).date()
    
    async with get_session() as session:
        calendar_service = CalendarService()
        
        # Clear existing rules for today
        await calendar_service.delete_rules_in_period(session, today, today)
        
        # Create new rule based on mode
        if mode == 'regular':
            work_mode = WorkMode.REGULAR
            work_start = time(8, 0)
            work_end = time(17, 0)
            print(f"✅ Set to REGULAR mode (08:00-17:00)")
        elif mode == 'extended':
            work_mode = WorkMode.EXTENDED
            work_start = time(8, 0)
            work_end = time(20, 0)
            print(f"✅ Set to EXTENDED mode (08:00-20:00)")
        elif mode == 'off':
            work_mode = WorkMode.NON_WORKING
            work_start = None
            work_end = None
            print(f"✅ Set to NON_WORKING mode (all day)")
        else:
            print(f"❌ Unknown mode: {mode}")
            return
        
        # Create rule
        rule = await calendar_service.create_rule(
            session=session,
            start_date=today,
            end_date=today,
            work_mode=work_mode,
            work_start_time=work_start,
            work_end_time=work_end
        )
        
        print(f"   Rule ID: {rule.id}")
        print(f"   Date: {today}")


async def clear_rules():
    """Clear all calendar rules."""
    async with get_session() as session:
        calendar_service = CalendarService()
        
        count = await calendar_service.delete_rules_in_period(
            session,
            date(2000, 1, 1),
            date(2100, 12, 31)
        )
        
        print(f"✅ Cleared {count} calendar rules")
        print(f"   Now using base schedule")


async def show_status():
    """Show current work mode."""
    async with get_session() as session:
        work_mode = await get_current_work_mode(session)
        current_time = datetime.now(MOSCOW_TZ)
        
        print(f"\n📅 Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"⚙️  Work mode: {work_mode.value}")
        
        if work_mode == WorkMode.REGULAR:
            print(f"   → Tickets assigned to managers")
        elif work_mode == WorkMode.EXTENDED:
            print(f"   → Tickets assigned to duty staff")
        else:
            print(f"   → Tickets queued (no assignment)")


def print_usage():
    """Print usage information."""
    print("\nUsage:")
    print("  python change_work_mode.py regular    # REGULAR mode (08:00-17:00)")
    print("  python change_work_mode.py extended   # EXTENDED mode (08:00-20:00)")
    print("  python change_work_mode.py off        # NON_WORKING mode (all day)")
    print("  python change_work_mode.py clear      # Clear rules (use base schedule)")
    print("  python change_work_mode.py status     # Show current mode")


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("❌ Missing argument")
        print_usage()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    try:
        if command in ['regular', 'extended', 'off']:
            await set_work_mode(command)
            print()
            await show_status()
        elif command == 'clear':
            await clear_rules()
            print()
            await show_status()
        elif command == 'status':
            await show_status()
        else:
            print(f"❌ Unknown command: {command}")
            print_usage()
            sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
