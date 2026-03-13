#!/usr/bin/env python3
"""
Initialize Work Mode Monitor

This script initializes the work mode monitor by setting the current work mode
as the baseline for transition detection.

Should be run once when the system starts or when deploying the work mode monitor feature.

Usage:
    python scripts/initialize_work_mode_monitor.py
"""

import asyncio
import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from celery_app.work_mode_monitor_tasks import initialize_work_mode_monitor


async def main():
    """Initialize the work mode monitor."""
    print("🔄 Initializing work mode monitor...")
    
    try:
        # Call the initialization task directly (not through Celery)
        from celery_app.work_mode_monitor_tasks import initialize_work_mode_monitor
        
        # Create a mock task instance for direct execution
        class MockTask:
            def __init__(self):
                self.request = None
        
        mock_task = MockTask()
        result = await initialize_work_mode_monitor.run_async(mock_task)
        
        if result["status"] == "initialized":
            print(f"✅ Work mode monitor initialized successfully!")
            print(f"   Initial mode: {result['initial_mode']}")
            print(f"   Time: {result['initialization_time']}")
        else:
            print(f"❌ Failed to initialize work mode monitor:")
            print(f"   Error: {result.get('error', 'Unknown error')}")
            return 1
    
    except Exception as e:
        print(f"❌ Error initializing work mode monitor: {e}")
        return 1
    
    print("\n📋 Next steps:")
    print("1. Start Celery worker with work_mode_monitor queue:")
    print("   celery -A celery_app.celery_config worker -Q work_mode_monitor,default")
    print("2. Start Celery beat scheduler:")
    print("   celery -A celery_app.celery_config beat")
    print("3. Monitor logs for work mode transitions")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)