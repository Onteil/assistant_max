"""
Tests for I-TAT API Client integration.

This test suite verifies that the ITatAPIClient correctly implements
the I-TAT API specification as documented in docs/I-TAT-API-DOCUMENTATION.md.

Requirements: 1.1-10.7
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from services.i_tat_service import ITatAPIClient


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for testing"""
    mock_client = AsyncMock()
    return mock_client


@pytest.fixture
def api_client(mock_httpx_client):
    """Create API client with mocked HTTP client"""
    client = ITatAPIClient(
        base_url="http://test.api/v1",
        username="test_user",
        password="test_pass"
    )
    client.client = mock_httpx_client
    return client


class TestRegisterUser:
    """Test register_user method - Requirements 1.1-1.7, 7.1, 7.2"""
    
    @pytest.mark.asyncio
    async def test_correct_endpoint(self, api_client, mock_httpx_client):
        """Verify register_user uses correct endpoint /user/register"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "message": "Пользователь зарегистрирован",
            "user_id": "USER_123"
        }
        mock_httpx_client.post.return_value = mock_response
        
        await api_client.register_user(
            telegram_id=123456789,
            phone="+79001234567",
            first_name="Иван",
            last_name="Иванов",
            grand_key="MG123456"
        )
        
        # Verify correct endpoint was called
        call_args = mock_httpx_client.post.call_args
        assert call_args[0][0] == "http://test.api/v1/user/register"
    
    @pytest.mark.asyncio
    async def test_uses_telegram_id_parameter(self, api_client, mock_httpx_client):
        """Verify register_user uses telegram_id parameter, not tg_user_id"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "user_id": "USER_123"}
        mock_httpx_client.post.return_value = mock_response
        
        await api_client.register_user(
            telegram_id=123456789,
            phone="+79001234567",
            first_name="Иван",
            last_name="Иванов",
            grand_key="MG123456"
        )
        
        # Verify payload contains telegram_id, not tg_user_id
        call_kwargs = mock_httpx_client.post.call_args[1]
        payload = call_kwargs['json']
        
        assert 'telegram_id' in payload
        assert payload['telegram_id'] == 123456789
        assert 'tg_user_id' not in payload
    
    @pytest.mark.asyncio
    async def test_uses_first_name_last_name_parameters(self, api_client, mock_httpx_client):
        """Verify register_user uses first_name and last_name parameters"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "user_id": "USER_123"}
        mock_httpx_client.post.return_value = mock_response
        
        await api_client.register_user(
            telegram_id=123456789,
            phone="+79001234567",
            first_name="Иван",
            last_name="Иванов",
            grand_key="MG123456"
        )
        
        # Verify payload contains first_name and last_name, not name and surname
        call_kwargs = mock_httpx_client.post.call_args[1]
        payload = call_kwargs['json']
        
        assert 'first_name' in payload
        assert payload['first_name'] == "Иван"
        assert 'last_name' in payload
        assert payload['last_name'] == "Иванов"
        assert 'name' not in payload
        assert 'surname' not in payload


class TestErrorHandling:
    """Test error handling and logging - Requirements 9.1-9.6"""
    
    @pytest.mark.asyncio
    async def test_register_user_400_error(self, api_client, mock_httpx_client):
        """Verify register_user raises HTTPStatusError for 400 status"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid parameters"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request",
            request=MagicMock(),
            response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await api_client.register_user(
                telegram_id=123456789,
                phone="+79001234567",
                first_name="Иван",
                last_name="Иванов",
                grand_key="MG123456"
            )
        
        assert exc_info.value.response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_register_user_404_error(self, api_client, mock_httpx_client):
        """Verify register_user raises HTTPStatusError for 404 status (key not found)"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Grand key not found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await api_client.register_user(
                telegram_id=123456789,
                phone="+79001234567",
                first_name="Иван",
                last_name="Иванов",
                grand_key="MG123456"
            )
        
        assert exc_info.value.response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_register_user_409_error(self, api_client, mock_httpx_client):
        """Verify register_user raises HTTPStatusError for 409 status (user exists)"""
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.text = "User already exists"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Conflict",
            request=MagicMock(),
            response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await api_client.register_user(
                telegram_id=123456789,
                phone="+79001234567",
                first_name="Иван",
                last_name="Иванов",
                grand_key="MG123456"
            )
        
        assert exc_info.value.response.status_code == 409
    
    @pytest.mark.asyncio
    async def test_register_user_500_error(self, api_client, mock_httpx_client):
        """Verify register_user raises HTTPStatusError for 500 status"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await api_client.register_user(
                telegram_id=123456789,
                phone="+79001234567",
                first_name="Иван",
                last_name="Иванов",
                grand_key="MG123456"
            )
        
        assert exc_info.value.response.status_code == 500
    
    @pytest.mark.asyncio
    async def test_get_user_assets_404_error(self, api_client, mock_httpx_client):
        """Verify get_user_assets raises HTTPStatusError for 404 status (user not found)"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "User not found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response
        )
        mock_httpx_client.get.return_value = mock_response
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await api_client.get_user_assets(telegram_id=123456789)
        
        assert exc_info.value.response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_check_key_conflict_400_error(self, api_client, mock_httpx_client):
        """Verify check_key_conflict raises HTTPStatusError for 400 status"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid parameters"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request",
            request=MagicMock(),
            response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await api_client.check_key_conflict(
                grand_key="MG123456",
                telegram_id=123456789
            )
        
        assert exc_info.value.response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_log_ticket_400_error(self, api_client, mock_httpx_client):
        """Verify log_ticket raises HTTPStatusError for 400 status (invalid type/status)"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid ticket type or status"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request",
            request=MagicMock(),
            response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await api_client.log_ticket(
                ticket_id="TG_12345",
                telegram_id=123456789,
                ticket_type="InvalidType",
                status="InvalidStatus"
            )
        
        assert exc_info.value.response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_log_ticket_404_error(self, api_client, mock_httpx_client):
        """Verify log_ticket raises HTTPStatusError for 404 status (user not found)"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "User not found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await api_client.log_ticket(
                ticket_id="TG_12345",
                telegram_id=999999999,
                ticket_type="Техподдержка",
                status="Новое"
            )
        
        assert exc_info.value.response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_staff_500_error(self, api_client, mock_httpx_client):
        """Verify get_staff raises HTTPStatusError for 500 status"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=mock_response
        )
        mock_httpx_client.get.return_value = mock_response
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await api_client.get_staff()
        
        assert exc_info.value.response.status_code == 500
    
    @pytest.mark.asyncio
    async def test_timeout_exception_propagated(self, api_client, mock_httpx_client):
        """Verify TimeoutException is properly propagated"""
        mock_httpx_client.post.side_effect = httpx.TimeoutException("Request timeout")
        
        with pytest.raises(httpx.TimeoutException):
            await api_client.register_user(
                telegram_id=123456789,
                phone="+79001234567",
                first_name="Иван",
                last_name="Иванов",
                grand_key="MG123456"
            )
    
    @pytest.mark.asyncio
    async def test_connect_error_propagated(self, api_client, mock_httpx_client):
        """Verify ConnectError is properly propagated"""
        mock_httpx_client.post.side_effect = httpx.ConnectError("Connection failed")
        
        with pytest.raises(httpx.ConnectError):
            await api_client.register_user(
                telegram_id=123456789,
                phone="+79001234567",
                first_name="Иван",
                last_name="Иванов",
                grand_key="MG123456"
            )
    
    @pytest.mark.asyncio
    async def test_error_logging_includes_endpoint_and_status(self, api_client, mock_httpx_client, caplog):
        """Verify error logs include endpoint, method, status code, and response text"""
        import logging
        caplog.set_level(logging.ERROR)
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid parameters"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request",
            request=MagicMock(),
            response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response
        
        try:
            await api_client.register_user(
                telegram_id=123456789,
                phone="+79001234567",
                first_name="Иван",
                last_name="Иванов",
                grand_key="MG123456"
            )
        except httpx.HTTPStatusError:
            pass
        
        # Verify log contains required information
        assert any("API HTTP error" in record.message for record in caplog.records)
        assert any("endpoint=" in record.message for record in caplog.records)
        assert any("method=" in record.message for record in caplog.records)
        assert any("status=" in record.message for record in caplog.records)
        assert any("response=" in record.message for record in caplog.records)
