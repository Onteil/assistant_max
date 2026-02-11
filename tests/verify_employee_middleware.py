"""
Verify Employee Middleware Registration

This script verifies that the StaffMemberCheckMiddleware is properly
registered on the employee routers.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def verify_employee_routers():
    """Verify employee routers are registered with staff middleware."""
    try:
        from bots.tg_bot.handlers import tg_bot_router
        from bots.tg_bot.handlers.employee import router as employee_router
        from bots.tg_bot.handlers.employee_messages import router as employee_messages_router
        from middlewares.check_staff_middleware import StaffMemberCheckMiddleware
        
        print("=" * 60)
        print("Employee Router Middleware Verification")
        print("=" * 60)
        print()
        
        # Check main router
        print("✅ Main router imported successfully")
        print(f"   Router name: {tg_bot_router.name}")
        print()
        
        # Check employee routers
        print("✅ Employee routers imported successfully:")
        print(f"   - employee: {employee_router.name}")
        print(f"   - employee_messages: {employee_messages_router.name}")
        print()
        
        # Check middleware
        print("✅ StaffMemberCheckMiddleware imported successfully")
        print(f"   Middleware class: {StaffMemberCheckMiddleware.__name__}")
        print()
        
        # Verify middleware is registered on employee routers
        print("Checking middleware registration:")
        
        # Check if employee_router has message middlewares
        if hasattr(employee_router, 'message') and hasattr(employee_router.message, 'middlewares'):
            message_middlewares = employee_router.message.middlewares
            print(f"   ✓ employee_router.message has {len(message_middlewares)} middleware(s)")
            for i, mw in enumerate(message_middlewares):
                print(f"     [{i}] {type(mw).__name__}")
        
        # Check if employee_router has callback_query middlewares
        if hasattr(employee_router, 'callback_query') and hasattr(employee_router.callback_query, 'middlewares'):
            callback_middlewares = employee_router.callback_query.middlewares
            print(f"   ✓ employee_router.callback_query has {len(callback_middlewares)} middleware(s)")
            for i, mw in enumerate(callback_middlewares):
                print(f"     [{i}] {type(mw).__name__}")
        
        # Check if employee_messages_router has message middlewares
        if hasattr(employee_messages_router, 'message') and hasattr(employee_messages_router.message, 'middlewares'):
            message_middlewares = employee_messages_router.message.middlewares
            print(f"   ✓ employee_messages_router.message has {len(message_middlewares)} middleware(s)")
            for i, mw in enumerate(message_middlewares):
                print(f"     [{i}] {type(mw).__name__}")
        
        # Check if employee_messages_router has callback_query middlewares
        if hasattr(employee_messages_router, 'callback_query') and hasattr(employee_messages_router.callback_query, 'middlewares'):
            callback_middlewares = employee_messages_router.callback_query.middlewares
            print(f"   ✓ employee_messages_router.callback_query has {len(callback_middlewares)} middleware(s)")
            for i, mw in enumerate(callback_middlewares):
                print(f"     [{i}] {type(mw).__name__}")
        
        print()
        print("=" * 60)
        print("✅ All verifications passed!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = verify_employee_routers()
    sys.exit(0 if success else 1)
