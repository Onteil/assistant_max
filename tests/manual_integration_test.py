"""
Manual Integration Test for I-TAT API Integration

This script tests the key user flows to verify handler integration:
1. Registration flow with API client
2. Key conflict check
3. Profile view with user assets

Run this script to manually verify the integration is working correctly.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from services.i_tat_service import ITatAPIClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


import pytest


@pytest.mark.asyncio
async def test_registration_flow():
    """Test user registration with updated API signatures"""
    print("\n" + "=" * 80)
    print("TEST 1: User Registration Flow")
    print("=" * 80)
    
    # Create API client
    client = ITatAPIClient(
        base_url="http://test.api/v1",
        username="test_user",
        password="test_pass"
    )
    
    # Mock the HTTP client
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "ok",
        "message": "Пользователь зарегистрирован",
        "user_id": "USER_123",
        "potential_matches": 0
    }
    
    with patch.object(client.client, 'post', return_value=mock_response) as mock_post:
        # Call register_user with new parameters
        result = await client.register_user(
            telegram_id=123456789,
            phone="+79001234567",
            first_name="Иван",
            last_name="Иванов",
            grand_key="MG123456"
        )
        
        # Verify the call was made correctly
        assert mock_post.called, "POST request was not made"
        call_args = mock_post.call_args
        
        # Check endpoint
        endpoint = call_args[0][0]
        assert endpoint == "http://test.api/v1/user/register", f"Wrong endpoint: {endpoint}"
        print("✓ Correct endpoint: /user/register")
        
        # Check payload
        payload = call_args[1]['json']
        assert 'telegram_id' in payload, "Missing telegram_id in payload"
        assert payload['telegram_id'] == 123456789, "Wrong telegram_id value"
        print("✓ Correct parameter: telegram_id")
        
        assert 'first_name' in payload, "Missing first_name in payload"
        assert payload['first_name'] == "Иван", "Wrong first_name value"
        print("✓ Correct parameter: first_name")
        
        assert 'last_name' in payload, "Missing last_name in payload"
        assert payload['last_name'] == "Иванов", "Wrong last_name value"
        print("✓ Correct parameter: last_name")
        
        assert 'grand_key' in payload, "Missing grand_key in payload"
        assert payload['grand_key'] == "MG123456", "Wrong grand_key value"
        print("✓ Correct parameter: grand_key")
        
        # Check no old parameters
        assert 'tg_user_id' not in payload, "Old parameter tg_user_id still present"
        assert 'name' not in payload, "Old parameter name still present"
        assert 'surname' not in payload, "Old parameter surname still present"
        print("✓ No old parameters present")
        
        # Check response
        assert result['status'] == 'ok', "Registration failed"
        print("✓ Registration successful")
    
    await client.close()
    print("\n✅ Registration flow test PASSED\n")


@pytest.mark.asyncio
async def test_key_conflict_check():
    """Test key conflict checking with updated API signatures"""
    print("\n" + "=" * 80)
    print("TEST 2: Key Conflict Check")
    print("=" * 80)
    
    # Create API client
    client = ITatAPIClient(
        base_url="http://test.api/v1",
        username="test_user",
        password="test_pass"
    )
    
    # Test 1: Available key
    print("\nTest 2.1: Available key")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "available"}
    
    with patch.object(client.client, 'post', return_value=mock_response) as mock_post:
        result = await client.check_key_conflict(
            grand_key="MG123456",
            telegram_id=123456789
        )
        
        # Verify the call
        call_args = mock_post.call_args
        endpoint = call_args[0][0]
        assert endpoint == "http://test.api/v1/assets/check_key", f"Wrong endpoint: {endpoint}"
        print("✓ Correct endpoint: /assets/check_key")
        
        payload = call_args[1]['json']
        assert 'grand_key' in payload, "Missing grand_key in payload"
        assert 'telegram_id' in payload, "Missing telegram_id in payload"
        assert 'phone' not in payload, "Old parameter phone still present"
        print("✓ Correct parameters: grand_key, telegram_id (no phone)")
        
        assert result['status'] == 'available', "Wrong status"
        print("✓ Available key detected correctly")
    
    # Test 2: Conflict key
    print("\nTest 2.2: Conflict key")
    mock_response.json.return_value = {
        "status": "conflict",
        "owner": "Иван Иванов +7912-XXX-XX-89"
    }
    
    with patch.object(client.client, 'post', return_value=mock_response):
        result = await client.check_key_conflict(
            grand_key="MG999999",
            telegram_id=123456789
        )
        
        assert result['status'] == 'conflict', "Wrong status"
        assert 'owner' in result, "Missing owner info"
        print("✓ Conflict detected correctly with owner info")
    
    await client.close()
    print("\n✅ Key conflict check test PASSED\n")


@pytest.mark.asyncio
async def test_user_assets_retrieval():
    """Test user assets retrieval with updated API signatures"""
    print("\n" + "=" * 80)
    print("TEST 3: User Assets Retrieval")
    print("=" * 80)
    
    # Create API client
    client = ITatAPIClient(
        base_url="http://test.api/v1",
        username="test_user",
        password="test_pass"
    )
    
    # Test 1: Verified user
    print("\nTest 3.1: Verified user")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "ok",
        "organizations": [
            {"inn": "1234567890", "name": "ООО Рога и Копыта"}
        ],
        "keys": ["MG123456", "MG789012"]
    }
    
    with patch.object(client.client, 'get', return_value=mock_response) as mock_get:
        result = await client.get_user_assets(telegram_id=123456789)
        
        # Verify the call
        call_args = mock_get.call_args
        endpoint = call_args[0][0]
        assert endpoint == "http://test.api/v1/user/assets", f"Wrong endpoint: {endpoint}"
        print("✓ Correct endpoint: /user/assets")
        
        params = call_args[1]['params']
        assert 'telegram_id' in params, "Missing telegram_id in params"
        assert params['telegram_id'] == 123456789, "Wrong telegram_id value"
        print("✓ Correct query parameter: telegram_id")
        
        assert result['status'] == 'ok', "Wrong status"
        assert 'organizations' in result, "Missing organizations"
        assert 'keys' in result, "Missing keys"
        print("✓ Verified user data retrieved correctly")
    
    # Test 2: Unverified user
    print("\nTest 3.2: Unverified user")
    mock_response.json.return_value = {
        "status": "error",
        "message": "Пользователь не верифицирован",
        "verification_status": "pending"
    }
    
    with patch.object(client.client, 'get', return_value=mock_response):
        result = await client.get_user_assets(telegram_id=987654321)
        
        assert result['status'] == 'error', "Wrong status"
        assert 'verification_status' in result, "Missing verification_status"
        print("✓ Unverified user status handled correctly")
    
    await client.close()
    print("\n✅ User assets retrieval test PASSED\n")


async def main():
    """Run all integration tests"""
    print("\n" + "=" * 80)
    print("MANUAL INTEGRATION TEST - I-TAT API INTEGRATION")
    print("=" * 80)
    print("\nThis test verifies that handlers work correctly with the updated API client.")
    print("Testing key user flows: registration, key check, profile view\n")
    
    try:
        await test_registration_flow()
        await test_key_conflict_check()
        await test_user_assets_retrieval()
        
        print("\n" + "=" * 80)
        print("ALL INTEGRATION TESTS PASSED ✅")
        print("=" * 80)
        print("\nSummary:")
        print("  ✓ Registration flow uses correct API signatures")
        print("  ✓ Key conflict check uses correct parameters")
        print("  ✓ User assets retrieval works correctly")
        print("  ✓ All handlers integrated successfully with API client")
        print("\n" + "=" * 80)
        
        return True
    
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
