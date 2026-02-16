"""
Command Handlers for MAX Bot

Handles bot commands and main menu button interactions.
Migrated from Telegram bot to MAX messenger.

Pattern: Command handling
- Use Command filter for commands
- Always clear state when starting new flow
- Use FSMContext for state management
- Log important actions
"""

import logging

from maxapi.types import Message
from maxapi.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.texts import HELP_TEXT

logger = logging.getLogger(__name__)


async def help_command(message: Message, messenger_adapter):
    """
    Handler for /help command.
    
    Shows help information about bot usage.
    Migrated from Telegram bot to MAX messenger.
    Uses messenger_adapter for sending messages.
    
    Requirements: 9.1, 9.2, 9.7
    """
    chat_id = message.chat.chat_id
    user_id = message.from_user.user_id

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=HELP_TEXT,
        keyboard=None,
        parse_mode="HTML"
    )
    logger.info(f"User {user_id} requested help")


# Main menu button handlers - delegate to specific handlers

async def handle_invoice_button(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Handle "Get Invoice" button from main menu.
    
    Delegates to invoice handler's start_invoice_request.
    Migrated from Telegram bot to MAX messenger.
    
    Requirements: 9.2, 9.7
    """
    # TODO: Import and delegate to invoice handler when migrated
    # from .invoice import start_invoice_request
    # await start_invoice_request(message, state, session, messenger_adapter)

    chat_id = message.chat.chat_id
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="💰 Функция получения счета будет доступна после миграции invoice handler",
        keyboard=None,
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.user_id} requested invoice (not yet migrated)")


async def handle_support_button(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Handle "Technical Support" button from main menu.
    
    Delegates to support handler's start_support_request.
    Migrated from Telegram bot to MAX messenger.
    
    Requirements: 9.2, 9.7
    """
    # TODO: Import and delegate to support handler when migrated
    # from .support import start_support_request
    # await start_support_request(message, state, session, messenger_adapter)

    chat_id = message.chat.chat_id
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="🆘 Функция техподдержки будет доступна после миграции support handler",
        keyboard=None,
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.user_id} requested support (not yet migrated)")


async def handle_profile_button(
    message: Message,
    session: AsyncSession,
    messenger_adapter
):
    """
    Handle "My Profile" button from main menu.
    
    Delegates to profile handler's show_profile.
    Migrated from Telegram bot to MAX messenger.
    
    Requirements: 9.2, 9.7
    """
    # TODO: Import and delegate to profile handler when migrated
    # from .profile import show_profile
    # await show_profile(message, session, messenger_adapter)

    chat_id = message.chat.chat_id
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="👤 Функция профиля будет доступна после миграции profile handler",
        keyboard=None,
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.user_id} requested profile (not yet migrated)")
