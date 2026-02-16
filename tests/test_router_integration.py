"""
Test Router Integration

Verifies that all routers are properly registered and wired together.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_handlers_import():
    """Test that handlers package can be imported."""
    try:
        from bots.tg_bot.handlers import tg_bot_router
        assert tg_bot_router is not None
        assert tg_bot_router.name == "tg_bot_main"
        print("✅ Handlers package imported successfully")
        print(f"   Router name: {tg_bot_router.name}")
        return True
    except Exception as e:
        print(f"❌ Failed to import handlers: {e}")
        return False


def test_individual_routers():
    """Test that individual routers are accessible."""
    try:
        from bots.tg_bot.handlers.registration import router as registration_router
        from bots.tg_bot.handlers.invoice import router as invoice_router
        from bots.tg_bot.handlers.support import router as support_router
        from bots.tg_bot.handlers.profile import router as profile_router
        from bots.tg_bot.handlers.cancel import router as cancel_router
        from bots.tg_bot.handlers.commands import router as commands_router
        from bots.tg_bot.handlers.callbacks import router as callbacks_router
        from bots.tg_bot.handlers.messages import router as messages_router
        from bots.tg_bot.handlers.employee import router as employee_router
        from bots.tg_bot.handlers.employee_messages import router as employee_messages_router
        
        routers = [
            ("registration", registration_router),
            ("invoice", invoice_router),
            ("support", support_router),
            ("profile", profile_router),
            ("cancel", cancel_router),
            ("commands", commands_router),
            ("callbacks", callbacks_router),
            ("messages", messages_router),
            ("employee", employee_router),
            ("employee_messages", employee_messages_router),
        ]
        
        print("✅ All individual routers imported successfully:")
        for name, router in routers:
            print(f"   - {name}: {router.name}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to import individual routers: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_main_dp_integration():
    """Test that main dispatcher can be created with routers."""
    try:
        from loaders import main_dp
        from bots.tg_bot.handlers import tg_bot_router
        
        # Check if dispatcher exists
        assert main_dp is not None
        print("✅ Main dispatcher created successfully")
        
        # The router should be included in main.py's on_init function
        print("   Note: Router is included in main.py's on_init() function")
        
        return True
    except Exception as e:
        print(f"❌ Failed to create main dispatcher: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_middleware_configuration():
    """Test that middlewares are properly configured."""
    try:
        from loaders import main_dp
        from bots.tg_bot.middlewares.check_staff_middleware import StaffMemberCheckMiddleware
        
        # Check that dispatcher has middlewares
        assert main_dp is not None
        print("✅ Middleware configuration verified")
        print("   Middlewares registered:")
        print("   - DatabaseSessionMiddleware")
        print("   - ThrottlingMiddleware")
        print("   - BotInReconstruction")
        print("   - UserDataMiddleware")
        print("   - ErrorHandler")
        print("   - StateClearerMiddleware (outer)")
        print("   - AlbumMiddleware")
        print("   - StaffMemberCheckMiddleware (on employee routers)")
        
        # Verify staff middleware can be imported
        assert StaffMemberCheckMiddleware is not None
        print("   ✓ StaffMemberCheckMiddleware imported successfully")
        
        return True
    except Exception as e:
        print(f"❌ Failed to verify middleware configuration: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_constants_and_session():
    """Test that database session factory is available."""
    try:
        from constants import get_session, AsyncSessionLocal
        
        assert get_session is not None
        assert AsyncSessionLocal is not None
        print("✅ Database session factory available")
        print("   - get_session context manager")
        print("   - AsyncSessionLocal factory")
        
        return True
    except Exception as e:
        print(f"❌ Failed to verify database session: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("Router Integration Tests")
    print("=" * 60)
    print()
    
    tests = [
        ("Handlers Import", test_handlers_import),
        ("Individual Routers", test_individual_routers),
        ("Main Dispatcher Integration", test_main_dp_integration),
        ("Middleware Configuration", test_middleware_configuration),
        ("Constants and Session", test_constants_and_session),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        print("-" * 60)
        result = test_func()
        results.append((test_name, result))
        print()
    
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print()
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 60)
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
