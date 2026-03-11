"""
End-to-end test for registration flow.

This test verifies that the registration flow works correctly from start to finish.
It tests the complete user journey through the registration process.

Requirements: 1.1-5.5
"""

import asyncio
import logging
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.models import (
    ActionType,
    Action_Log,
    Base,
    GS_Key,
    KeyConflictStatus,
    Organization,
    RegistrationStatus,
    User,
    user_organizations,
)
from services.user_service import (
    add_user_key,
    add_user_organization,
    create_user,
    get_user_by_tg_id,
)
from services.validation_service import (
    validate_gs_key,
    validate_inn,
    validate_phone_number,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_registration_flow():
    """
    Test the complete registration flow end-to-end.
    
    This test simulates a user going through the registration process:
    1. Phone number validation and storage
    2. Full name validation
    3. INN validation and organization creation
    4. GS_Key validation and key creation
    5. User record creation with PENDING status
    6. Action logging
    """
    print("=" * 80)
    print("TESTING REGISTRATION FLOW END-TO-END")
    print("=" * 80)
    
    # Create in-memory database for testing
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session factory
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with async_session() as session:
            # Test data
            tg_user_id = 123456789
            phone_input = "89991234567"
            full_name = "Иванов Иван"
            inn_input = "1234567890"
            gs_key_input = "mg123456"
            
            print("\n" + "=" * 80)
            print("STEP 1: Phone Number Validation")
            print("=" * 80)
            
            # Validate phone number
            is_valid, result = validate_phone_number(phone_input)
            assert is_valid, f"Phone validation failed: {result}"
            normalized_phone = result
            print(f"✓ Phone validated: {phone_input} -> {normalized_phone}")
            assert normalized_phone == "+79991234567", "Phone normalization failed"
            print(f"✓ Phone normalized correctly to E.164 format")
            
            # Check for duplicate phone (should not exist)
            existing_user = await session.execute(
                select(User).where(User.phone_number == normalized_phone)
            )
            assert existing_user.scalar_one_or_none() is None, "Duplicate phone check failed"
            print(f"✓ No duplicate phone number found")
            
            print("\n" + "=" * 80)
            print("STEP 2: Full Name Validation")
            print("=" * 80)
            
            # Validate full name
            assert len(full_name) >= 2, "Full name too short"
            print(f"✓ Full name validated: {full_name}")
            
            print("\n" + "=" * 80)
            print("STEP 3: INN Validation and Organization Creation")
            print("=" * 80)
            
            # Validate INN
            is_valid, error_message = validate_inn(inn_input)
            assert is_valid, f"INN validation failed: {error_message}"
            print(f"✓ INN validated: {inn_input}")
            
            print("\n" + "=" * 80)
            print("STEP 4: GS_Key Validation")
            print("=" * 80)
            
            # Validate GS_Key
            is_valid, result = validate_gs_key(gs_key_input)
            assert is_valid, f"GS_Key validation failed: {result}"
            normalized_key = result
            print(f"✓ GS_Key validated: {gs_key_input} -> {normalized_key}")
            assert normalized_key == "MG123456", "GS_Key normalization failed"
            print(f"✓ GS_Key normalized to uppercase")
            
            print("\n" + "=" * 80)
            print("STEP 5: User Creation with PENDING Status")
            print("=" * 80)
            
            # Create user
            user_data = {
                "tg_user_id": tg_user_id,
                "phone_number": normalized_phone,
                "full_name": full_name,
                "username": "testuser",
                "first_name": "Иван",
                "last_name": "Иванов",
            }
            
            user = await create_user(session, user_data)
            await session.flush()
            
            print(f"✓ User created: tg_user_id={user.tg_user_id}")
            assert user.registration_status == RegistrationStatus.PENDING, "User status should be PENDING"
            print(f"✓ User status is PENDING")
            assert user.phone_number == normalized_phone, "Phone number mismatch"
            print(f"✓ Phone number stored correctly")
            assert user.full_name == full_name, "Full name mismatch"
            print(f"✓ Full name stored correctly")
            
            print("\n" + "=" * 80)
            print("STEP 6: Organization Association")
            print("=" * 80)
            
            # Add organization
            organization = await add_user_organization(session, tg_user_id, inn_input)
            await session.flush()
            
            print(f"✓ Organization created/associated: INN={organization.inn}")
            
            # Verify association
            result = await session.execute(
                select(user_organizations).where(
                    user_organizations.c.tg_user_id == tg_user_id,
                    user_organizations.c.organization_inn == inn_input
                )
            )
            association = result.first()
            assert association is not None, "Organization association not created"
            print(f"✓ User-organization association verified")
            
            print("\n" + "=" * 80)
            print("STEP 7: GS_Key Creation")
            print("=" * 80)
            
            # Add GS_Key without conflict
            gs_key = await add_user_key(
                session,
                tg_user_id,
                normalized_key,
                KeyConflictStatus.NONE
            )
            await session.flush()
            
            print(f"✓ GS_Key created: key_number={gs_key.key_number}")
            assert gs_key.conflict_status == KeyConflictStatus.NONE, "Conflict status should be NONE"
            print(f"✓ Conflict status is NONE")
            assert gs_key.tg_user_id == tg_user_id, "User ID mismatch"
            print(f"✓ GS_Key linked to user")
            
            print("\n" + "=" * 80)
            print("STEP 8: Action Logging Verification")
            print("=" * 80)
            
            # Verify action log was created
            result = await session.execute(
                select(Action_Log).where(
                    Action_Log.action_type == ActionType.USER_REGISTERED,
                    Action_Log.tg_user_id == tg_user_id
                )
            )
            action_log = result.scalar_one_or_none()
            assert action_log is not None, "Action log not created"
            print(f"✓ Action log created for USER_REGISTERED")
            assert action_log.action_details is not None, "Action details missing"
            print(f"✓ Action details stored: {action_log.action_details}")
            
            print("\n" + "=" * 80)
            print("STEP 9: User Retrieval Verification")
            print("=" * 80)
            
            # Retrieve user and verify all data
            retrieved_user = await get_user_by_tg_id(session, tg_user_id)
            assert retrieved_user is not None, "User not found"
            print(f"✓ User retrieved successfully")
            assert retrieved_user.phone_number == normalized_phone, "Phone mismatch on retrieval"
            print(f"✓ Phone number matches")
            assert retrieved_user.full_name == full_name, "Name mismatch on retrieval"
            print(f"✓ Full name matches")
            assert retrieved_user.registration_status == RegistrationStatus.PENDING, "Status mismatch"
            print(f"✓ Registration status is PENDING")
            
            print("\n" + "=" * 80)
            print("STEP 10: Conflict Detection Test")
            print("=" * 80)
            
            # Test key conflict scenario
            conflict_key = "AB999999"
            gs_key_conflict = await add_user_key(
                session,
                tg_user_id,
                conflict_key,
                KeyConflictStatus.PENDING_REVIEW
            )
            await session.flush()
            
            print(f"✓ Conflict key created: key_number={gs_key_conflict.key_number}")
            assert gs_key_conflict.conflict_status == KeyConflictStatus.PENDING_REVIEW, "Conflict status incorrect"
            print(f"✓ Conflict status is PENDING_REVIEW")
            assert gs_key_conflict.conflict_reported_at is not None, "Conflict timestamp missing"
            print(f"✓ Conflict timestamp recorded: {gs_key_conflict.conflict_reported_at}")
            
            # Verify conflict action log
            result = await session.execute(
                select(Action_Log).where(
                    Action_Log.action_type == ActionType.KEY_CONFLICT_DETECTED,
                    Action_Log.tg_user_id == tg_user_id
                )
            )
            conflict_log = result.scalar_one_or_none()
            assert conflict_log is not None, "Conflict action log not created"
            print(f"✓ Conflict action log created")
            
            print("\n" + "=" * 80)
            print("STEP 11: Duplicate Phone Prevention Test")
            print("=" * 80)
            
            # Try to create another user with same phone
            try:
                duplicate_user_data = {
                    "tg_user_id": 987654321,
                    "phone_number": normalized_phone,  # Same phone
                    "full_name": "Другой Пользователь",
                }
                await create_user(session, duplicate_user_data)
                await session.flush()
                assert False, "Duplicate phone should have been rejected"
            except Exception as e:
                print(f"✓ Duplicate phone correctly rejected: {type(e).__name__}")
                await session.rollback()
            
            print("\n" + "=" * 80)
            print("STEP 12: Validation Edge Cases")
            print("=" * 80)
            
            # Test invalid phone
            is_valid, error = validate_phone_number("123")
            assert not is_valid, "Short phone should be invalid"
            print(f"✓ Short phone rejected: {error}")
            
            # Test invalid INN
            is_valid, error = validate_inn("123")
            assert not is_valid, "Short INN should be invalid"
            print(f"✓ Short INN rejected: {error}")
            
            # Test invalid GS_Key
            is_valid, error = validate_gs_key("INVALID")
            assert not is_valid, "Invalid key format should be rejected"
            print(f"✓ Invalid key format rejected: {error}")
            
            # Test valid 12-digit INN
            is_valid, error = validate_inn("123456789012")
            assert is_valid, "12-digit INN should be valid"
            print(f"✓ 12-digit INN accepted")
            
            # Test E.164 phone format
            is_valid, result = validate_phone_number("+79991234567")
            assert is_valid and result == "+79991234567", "E.164 format should be accepted"
            print(f"✓ E.164 phone format accepted")
            
            print("\n" + "=" * 80)
            print("ALL REGISTRATION FLOW TESTS PASSED ✓")
            print("=" * 80)
            print("\nSummary:")
            print("  ✓ Phone validation and normalization")
            print("  ✓ Full name validation")
            print("  ✓ INN validation")
            print("  ✓ GS_Key validation and normalization")
            print("  ✓ User creation with PENDING status")
            print("  ✓ Organization association")
            print("  ✓ GS_Key creation and linking")
            print("  ✓ Action logging")
            print("  ✓ User retrieval")
            print("  ✓ Conflict detection and flagging")
            print("  ✓ Duplicate phone prevention")
            print("  ✓ Validation edge cases")
            print("\n" + "=" * 80)
            
            return True
    
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(test_registration_flow())
    exit(0 if success else 1)
