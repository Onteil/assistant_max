"""
Cancel Command Handler for MAX Bot

Provides global /cancel command that works in all FSM states.
Cleans up state and returns user to main menu.
Migrated from Telegram bot to MAX messenger.

Requirements: 27.1-27.5, 28.1-28.5, 9.1, 9.2, 9.7
"""

import logging

from maxapi.context import MemoryContext
from maxapi.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.texts import FLOW_CANCELLED, MAIN_MENU
from database.models import RegistrationStatus
from services.user_service import get_user_by_max_id

logger = logging.getLogger(__name__)


async def cmd_cancel(
    message: Message,
    state: MemoryContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Global cancel command handler.
    
    Works in all FSM states:
    - Clears FSM state using maxapi's state.clear() method
    - Returns user to main menu (if registered and active)
    - Ensures no partial data is persisted
    
    Migrated from Telegram bot to MAX messenger.
    Uses messenger_adapter for sending messages.
    
    commands_info: Отменить текущую операцию и вернуться в главное меню
    
    Requirements: 27.1, 27.2, 27.3, 27.4, 27.5, 28.1, 28.2, 28.3, 28.4, 28.5, 9.1, 9.2, 9.7
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id

    # Get current state
    current_state = await state.get_state()

    # Clear FSM state using maxapi's state.clear() method
    await state.clear()

    logger.info(
        f"User {user_id} cancelled operation, "
        f"previous state: {current_state or 'None'}"
    )

    # Check if user is registered and active
    try:
        user = await get_user_by_max_id(session, user_id)

        if user and user.registration_status == RegistrationStatus.ACTIVE:
            # Show main menu for active users
            # TODO: Convert reply keyboard to abstraction layer
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=FLOW_CANCELLED + "\n\n" + MAIN_MENU,
                keyboard=None,  # TODO: Add main menu keyboard
                parse_mode="HTML"
            )
        else:
            # Just show cancellation message for non-active users
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=FLOW_CANCELLED + "\n\nИспользуйте /start для начала работы.",
                keyboard=None,
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(
            f"Error in cancel handler for user {user_id}: {e}",
            exc_info=True
        )
        # Fallback - just clear state and show cancellation
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=FLOW_CANCELLED,
            keyboard=None,
            parse_mode="HTML"
        )


async def handle_cancel_button(
    message: Message,
    state: MemoryContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Handle cancel button press (text-based).
    
    Delegates to cmd_cancel for consistent behavior.
    Migrated from Telegram bot to MAX messenger.
    
    Requirements: 28.2, 28.4, 9.2, 9.7
    """
    await cmd_cancel(message, state, session, messenger_adapter)

