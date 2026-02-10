"""
Test Cancel Flow

Tests for /cancel command and state cleanup functionality.
Verifies that cancel works in all states and properly cleans up FSM data.

Requirements: 27.1-27.5, 28.1-28.5
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.handlers.cancel import cmd_cancel, handle_cancel_button
from bots.tg_bot.states import (
    RegistrationStates,
    InvoiceStates,
    SupportStates,
    ProfileStates
)
from database.models import RegistrationStatus, User as DBUser


@pytest.fixture
def mock_message():
    """Create a mock message object."""
    message = MagicMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 12345
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_state():
    """Create a mock FSM context."""
    state = MagicMock(spec=FSMContext)
    state.get_state = AsyncMock(return_value=None)
    state.clear = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    return state


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return MagicMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_cancel_command_no_state(mock_message, mock_state, mock_session):
    """
    Test /cancel command when no state is active.
    
    Should clear state and show cancellation message.
    
    Requirements: 28.2, 28.4
    """
    # Setup
    mock_state.get_state.return_value = None
    
    with patch('bots.tg_bot.handlers.cancel.get_user_by_tg_id', new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = None
        
        # Execute
        await cmd_cancel(mock_message, mock_state, mock_session)
        
        # Verify
        mock_state.clear.assert_called_once()
        mock_message.answer.assert_called_once()
        assert "отменена" in mock_message.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_cancel_command_during_registration(mock_message, mock_state, mock_session):
    """
    Test /cancel command during registration flow.
    
    Should clear state and return to start message.
    
    Requirements: 27.1, 28.2, 28.5
    """
    # Setup
    mock_state.get_state.return_value = RegistrationStates.waiting_for_name.state
    
    with patch('bots.tg_bot.handlers.cancel.get_user_by_tg_id', new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = None
        
        # Execute
        await cmd_cancel(mock_message, mock_state, mock_session)
        
        # Verify
        mock_state.clear.assert_called_once()
        mock_message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_command_during_invoice_flow(mock_message, mock_state, mock_session):
    """
    Test /cancel command during invoice request flow.
    
    Should clear state and return to main menu for active users.
    
    Requirements: 27.2, 28.2, 28.4
    """
    # Setup
    mock_state.get_state.return_value = InvoiceStates.entering_description.state
    
    mock_user = MagicMock(spec=DBUser)
    mock_user.registration_status = RegistrationStatus.ACTIVE
    
    with patch('bots.tg_bot.handlers.cancel.get_user_by_tg_id', new_callable=AsyncMock) as mock_get_user:
        with patch('bots.tg_bot.handlers.cancel.get_main_menu_keyboard', new_callable=AsyncMock) as mock_keyboard:
            mock_get_user.return_value = mock_user
            mock_keyboard.return_value = MagicMock()
            
            # Execute
            await cmd_cancel(mock_message, mock_state, mock_session)
            
            # Verify
            mock_state.clear.assert_called_once()
            mock_message.answer.assert_called_once()
            mock_keyboard.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_command_during_support_flow(mock_message, mock_state, mock_session):
    """
    Test /cancel command during support request flow.
    
    Should clear state and return to main menu.
    
    Requirements: 27.3, 28.2, 28.4
    """
    # Setup
    mock_state.get_state.return_value = SupportStates.entering_problem.state
    
    mock_user = MagicMock(spec=DBUser)
    mock_user.registration_status = RegistrationStatus.ACTIVE
    
    with patch('bots.tg_bot.handlers.cancel.get_user_by_tg_id', new_callable=AsyncMock) as mock_get_user:
        with patch('bots.tg_bot.handlers.cancel.get_main_menu_keyboard', new_callable=AsyncMock) as mock_keyboard:
            mock_get_user.return_value = mock_user
            mock_keyboard.return_value = MagicMock()
            
            # Execute
            await cmd_cancel(mock_message, mock_state, mock_session)
            
            # Verify
            mock_state.clear.assert_called_once()
            mock_message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_command_during_profile_flow(mock_message, mock_state, mock_session):
    """
    Test /cancel command during profile management flow.
    
    Should clear state and return to main menu.
    
    Requirements: 27.4, 28.2, 28.4
    """
    # Setup
    mock_state.get_state.return_value = ProfileStates.adding_inn.state
    
    mock_user = MagicMock(spec=DBUser)
    mock_user.registration_status = RegistrationStatus.ACTIVE
    
    with patch('bots.tg_bot.handlers.cancel.get_user_by_tg_id', new_callable=AsyncMock) as mock_get_user:
        with patch('bots.tg_bot.handlers.cancel.get_main_menu_keyboard', new_callable=AsyncMock) as mock_keyboard:
            mock_get_user.return_value = mock_user
            mock_keyboard.return_value = MagicMock()
            
            # Execute
            await cmd_cancel(mock_message, mock_state, mock_session)
            
            # Verify
            mock_state.clear.assert_called_once()
            mock_message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_button_handler(mock_message, mock_state, mock_session):
    """
    Test cancel button (text-based) handler.
    
    Should delegate to cmd_cancel for consistent behavior.
    
    Requirements: 28.2, 28.4
    """
    # Setup
    mock_state.get_state.return_value = InvoiceStates.selecting_keys.state
    
    with patch('bots.tg_bot.handlers.cancel.get_user_by_tg_id', new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = None
        
        # Execute
        await handle_cancel_button(mock_message, mock_state, mock_session)
        
        # Verify
        mock_state.clear.assert_called_once()
        mock_message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_state_cleanup_no_partial_data(mock_message, mock_state, mock_session):
    """
    Test that cancel ensures no partial data is persisted.
    
    When flow is cancelled, FSM state should be completely cleared
    and no database records should be created.
    
    Requirements: 28.5
    """
    # Setup - simulate state with partial data
    mock_state.get_state.return_value = InvoiceStates.entering_description.state
    mock_state.get_data.return_value = {
        "organization_inn": "1234567890",
        "selected_key_ids": {1, 2, 3},
        "description": "Partial description"
    }
    
    with patch('bots.tg_bot.handlers.cancel.get_user_by_tg_id', new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = None
        
        # Execute
        await cmd_cancel(mock_message, mock_state, mock_session)
        
        # Verify state is cleared
        mock_state.clear.assert_called_once()
        
        # Verify no database operations were performed
        # (session should not have any add/commit calls)
        assert not mock_session.add.called
        assert not mock_session.commit.called


@pytest.mark.asyncio
async def test_cancel_returns_to_main_menu_for_active_users(mock_message, mock_state, mock_session):
    """
    Test that cancel returns active users to main menu.
    
    Requirements: 27.5, 28.4
    """
    # Setup
    mock_state.get_state.return_value = InvoiceStates.selecting_organization.state
    
    mock_user = MagicMock(spec=DBUser)
    mock_user.registration_status = RegistrationStatus.ACTIVE
    
    with patch('bots.tg_bot.handlers.cancel.get_user_by_tg_id', new_callable=AsyncMock) as mock_get_user:
        with patch('bots.tg_bot.handlers.cancel.get_main_menu_keyboard', new_callable=AsyncMock) as mock_keyboard:
            mock_get_user.return_value = mock_user
            mock_keyboard.return_value = MagicMock()
            
            # Execute
            await cmd_cancel(mock_message, mock_state, mock_session)
            
            # Verify
            mock_state.clear.assert_called_once()
            mock_keyboard.assert_called_once()
            
            # Verify main menu message was sent
            call_args = mock_message.answer.call_args[0][0]
            assert "главное меню" in call_args.lower() or "main menu" in call_args.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
