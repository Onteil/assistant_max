"""
Command Handlers for MAX Bot

Handles general commands and main menu routing:
- /help command - Display help text with available commands
- /cancel command - Clear FSM state and display cancellation message
- Main menu button routing - Route button presses to appropriate handlers

Migrated from Telegram bot to MAX messenger using maxapi.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

import logging

from maxapi import F
from maxapi.context import MemoryContext
from maxapi.types import MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_keyboard
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.texts import (
    FLOW_CANCELLED,
    HELP_TEXT,
    MAIN_MENU,
    MENU_INVOICE,
    MENU_PROFILE,
    MENU_RENEWAL,
    MENU_SUPPORT,
)
from database.models import RegistrationStatus
from services.user_service import get_user_by_max_id

logger = logging.getLogger(__name__)


# ========== /help Command Handler ==========


async def cmd_help(
    event: MessageCreated,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /help command - display help text with available commands.
    
    Shows:
    - Available commands (/start, /help, /cancel)
    - Main bot functions (invoices, support, renewal, profile)
    - Contact information
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Includes commands_info marker for automatic command registration
    
    Args:
        event: MessageCreated event from maxapi
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    commands_info: Показать справку и доступные команды
    
    Requirements: 5.1
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    logger.info(f"User {max_user_id} requested help")
    
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=HELP_TEXT,
        parse_mode="HTML"
    )


# ========== /my_id Command Handler ==========


async def cmd_my_id(
    event: MessageCreated,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /my_id command - display user's MAX user ID.
    
    Shows the user's MAX user ID which is needed for:
    - Adding staff members to the system
    - Troubleshooting and support
    - Administrative operations
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Includes commands_info marker for automatic command registration
    
    Args:
        event: MessageCreated event from maxapi
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    commands_info: Узнать свой MAX ID для регистрации в системе
    
    Requirements: Employee Management
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    logger.info(f"User {max_user_id} requested their MAX ID")
    
    # Format message with user ID
    message_text = (
        "🆔 <b>Ваш MAX ID</b>\n\n"
        f"<code>{max_user_id}</code>\n\n"
        "<i>Этот ID используется для добавления сотрудников в систему. "
        "Скопируйте его и отправьте администратору.</i>"
    )
    
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=message_text,
        parse_mode="HTML"
    )


# ========== /me Command Handler ==========


async def cmd_me(
    event: MessageCreated,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /me command - display bot information.

    Shows:
    - Bot name and description
    - Bot version
    - Available features
    - Contact information

    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Includes commands_info marker for automatic command registration

    Args:
        event: MessageCreated event from maxapi
        messenger_adapter: MAXMessengerAdapter for sending messages

    commands_info: Информация о боте

    Requirements: Bot Information
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id

    logger.info(f"User {max_user_id} requested bot information")

    # Format bot information message
    message_text = (
        "🤖 <b>i-TAT Bot</b>\n\n"
        "<b>Описание:</b>\n"
        "Бот для автоматизации работы с системой i-TAT. "
        "Позволяет получать счета, обращаться в техподдержку, "
        "управлять профилем и продлевать подписку.\n\n"
        "<b>Основные функции:</b>\n"
        "💰 Получение счетов на оплату\n"
        "🆘 Обращения в техподдержку\n"
        "🔄 Активация подписки\n"
        "👤 Управление профилем\n"
        "📋 История обращений\n\n"
        "<b>Доступные команды:</b>\n"
        "/start - Начать работу с ботом\n"
        "/help - Справка по командам\n"
        "/me - Информация о боте\n"
        "/my_id - Узнать свой MAX ID\n"
        "/cancel - Отменить текущую операцию\n\n"
        "<i>Для получения помощи используйте команду /help</i>"
    )

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=message_text,
        parse_mode="HTML"
    )

    # Format bot information message
    message_text = (
        "🤖 <b>i-TAT Bot</b>\n\n"
        "<b>Описание:</b>\n"
        "Бот для автоматизации работы с системой i-TAT. "
        "Позволяет получать счета, обращаться в техподдержку, "
        "управлять профилем и продлевать подписку.\n\n"
        "<b>Основные функции:</b>\n"
        "💰 Получение счетов на оплату\n"
        "🆘 Обращения в техподдержку\n"
        "🔄 Активация подписки\n"
        "👤 Управление профилем\n"
        "📋 История обращений\n\n"
        "<b>Доступные команды:</b>\n"
        "/start - Начать работу с ботом\n"
        "/help - Справка по командам\n"
        "/me - Информация о боте\n"
        "/my_id - Узнать свой MAX ID\n"
        "/cancel - Отменить текущую операцию\n\n"
        "<i>Для получения помощи используйте команду /help</i>"
    )

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=message_text,
        parse_mode="HTML"
    )





# ========== /cancel Command Handler ==========


async def cmd_cancel(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /cancel command - clear FSM state and display cancellation message.
    
    Works in all FSM states:
    - Clears FSM state completely
    - Returns user to main menu (if registered and active)
    - Ensures no partial data is persisted
    - Deletes any partially created records if applicable
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Clears FSM state using context.clear()
    - Retrieves current state using context.get_state()
    - Includes commands_info marker for automatic command registration
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    commands_info: Отменить текущую операцию и вернуться в главное меню
    
    Requirements: 5.6, 1.16, 2.16, 3.18, 4.16
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    # Get current state for logging
    current_state = await context.get_state()
    
    # Clear FSM state completely
    await context.clear()
    
    logger.info(
        f"User {max_user_id} cancelled operation, "
        f"previous state: {current_state or 'None'}"
    )
    
    # Check if user is registered and active
    try:
        user = await get_user_by_max_id(session, max_user_id)
        
        if user and user.registration_status == RegistrationStatus.ACTIVE:
            # Show main menu for active users
            main_menu_keyboard = await get_main_menu_keyboard()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=FLOW_CANCELLED + "\n\n" + MAIN_MENU,
                keyboard=main_menu_keyboard,
                parse_mode="HTML"
            )
        else:
            # Just show cancellation message for non-active users
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=FLOW_CANCELLED + "\n\nИспользуйте /start для начала работы.",
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(
            f"Error in cancel handler for user {max_user_id}: {e}",
            exc_info=True
        )
        # Fallback - just clear state and show cancellation
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=FLOW_CANCELLED,
            parse_mode="HTML"
        )


# ========== Main Menu Button Routing ==========


async def handle_main_menu(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Route main menu button presses to appropriate handlers.
    
    Routes based on button text:
    - "💰 Получить счет" → Invoice handler
    - "🆘 Техподдержка" → Support handler
    - "🔄 Активация подписки" → Renewal handler
    - "👤 Мой профиль" → Profile handler
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 5.3, 5.4, 5.5, 5.6, 5.7
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    message_text = event.message.body.text or ""
    
    logger.info(f"User {max_user_id} pressed main menu button: {message_text}")
    
    # Import handlers here to avoid circular imports
    from bots.max_bot.handlers.tickets.invoice import cmd_invoice
    from bots.max_bot.handlers.tickets.support import cmd_support
    from bots.max_bot.handlers.user.profile import cmd_profile
    from bots.max_bot.handlers.user.ai_agent import start_ai_agent
    from services.yandex_gpt_service import is_yandex_gpt_configured
    
    # Route to appropriate handler based on button text
    if message_text in {MENU_INVOICE, "Менеджер"}:
        if is_yandex_gpt_configured():
            await start_ai_agent(event, context, session, messenger_adapter)
        else:
            await cmd_invoice(event, context, session, messenger_adapter)
    
    elif message_text == MENU_SUPPORT:
        # Route to support handler
        await cmd_support(event, context, session, messenger_adapter)
    
    elif message_text == MENU_RENEWAL:
        # Route to renewal handler (part of support flow)
        # Renewal is handled within support flow when subscription is expired
        await cmd_support(event, context, session, messenger_adapter)
    
    elif message_text == MENU_PROFILE:
        # Route to profile handler
        await cmd_profile(event, context, session, messenger_adapter)
    
    else:
        # Unknown button - log warning
        logger.warning(
            f"Unknown main menu button pressed by user {max_user_id}: {message_text}"
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Неизвестная команда. Используйте /help для справки.",
            parse_mode="HTML"
        )


# ========== Cancel Button Handler ==========


async def handle_cancel_button(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle cancel button press (text-based "❌ Отмена").
    
    Delegates to cmd_cancel for consistent behavior.
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 5.6
    """
    await cmd_cancel(event, context, session, messenger_adapter)

