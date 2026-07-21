"""
Main Menu Callback Handlers for MAX Bot

Handles callback queries from inline main menu keyboard:
- Invoice button
- Support button
- Renewal button
- Archive button
- Profile button
- Active tickets button
- Return to main menu

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, AC-1.3, TR-2
"""

import logging

from maxapi.context import MemoryContext
from maxapi.types import MessageCallback
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.payloads import MainMenuActionPayload, DonePayload
from bots.max_bot.utils.callback_utils import (
    answer_max_callback,
    is_stale_max_callback_error,
)

logger = logging.getLogger(__name__)


_is_stale_callback_error = is_stale_max_callback_error


async def handle_main_menu_callback(
    event: MessageCallback,
    payload: MainMenuActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Route main menu callback queries to appropriate handlers.
    
    Parses callback payload and routes to:
    - invoice → Invoice handler
    - support → Support handler
    - renewal → Renewal handler (part of support)
    - archive → Archive handler
    - profile → Profile handler
    - active_tickets → Active tickets list
    - main_menu → Client main menu
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses MainMenuActionPayload for type-safe payload parsing
    - Payload automatically parsed by CallbackPayload.filter() decorator
    - Calls event.answer() to acknowledge callback and remove loading indicator
    
    Args:
        event: MessageCallback event from maxapi
        payload: MainMenuActionPayload with action field (auto-parsed)
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
    """
    chat_id = event.message.recipient.chat_id
    # In callback events, user_id comes from event.callback.user, not event.message.sender
    # event.message.sender is the bot that sent the message with buttons
    max_user_id = event.callback.user.user_id
    
    # Get message ID for replacing the message (delete old + send new)
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    action = payload.action
    
    logger.info(f"Main menu callback: user={max_user_id}, action={action}, message_id={message_id}")
    
    # Answer callback to remove loading indicator
    try:
        if not await answer_max_callback(event):
            return
    except Exception as e:
        logger.warning(f"Failed to answer callback: {e}")
        return
    
    # Delete the old message with buttons to avoid confusion
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    # Import handlers to avoid circular imports
    from bots.max_bot.handlers.tickets.invoice import cmd_invoice
    from bots.max_bot.handlers.tickets.support import cmd_support
    from bots.max_bot.handlers.tickets.consultation import cmd_consultation
    from bots.max_bot.handlers.user.profile import cmd_profile
    from bots.max_bot.handlers.user.archive import show_archive_list
    from bots.max_bot.handlers.user.renewal import show_subscription_status
    
    try:
        if action == "invoice":
            # Route to invoice handler
            await cmd_invoice(event, context, session, messenger_adapter)
        
        elif action == "support":
            # Route to support handler
            await cmd_support(event, context, session, messenger_adapter)
        
        elif action == "consultation":
            # Route to consultation handler
            await cmd_consultation(event, context, session, messenger_adapter)
        
        elif action == "renewal":
            # Route to renewal handler - show subscription status
            await show_subscription_status(event, session, messenger_adapter)
        
        elif action == "archive":
            # Route to archive handler
            await show_archive_list(chat_id, max_user_id, session, messenger_adapter, context)
        
        elif action == "profile":
            # Route to profile handler
            await cmd_profile(event, session, messenger_adapter)
        
        elif action == "active_tickets":
            # Show active tickets list
            await show_active_tickets_list(event, session, messenger_adapter)

        elif action == "main_menu":
            from bots.max_bot.keyboards.user.main_menu_kb import (
                get_main_menu_inline_keyboard,
            )
            from bots.max_bot.texts import MAIN_MENU_WELCOME_TEXT
            from services.ticket_service import get_user_active_tickets_count
            from services.user_service import get_user_by_max_id

            user = await get_user_by_max_id(session, max_user_id)
            if not user:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Пользователь не найден. Используйте /start.",
                    parse_mode="HTML",
                )
                return

            await context.clear()
            active_tickets_count = await get_user_active_tickets_count(
                session,
                user.id,
            )
            keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=MAIN_MENU_WELCOME_TEXT,
                keyboard=keyboard,
                parse_mode="HTML",
            )
            logger.info(
                f"Client returned to main menu: user={max_user_id}, "
                f"active_tickets={active_tickets_count}"
            )
        
        else:
            logger.warning(f"Unknown main menu action: {action}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестное действие. Используйте /start для главного меню.",
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(
            f"Error handling main menu callback: user={max_user_id}, action={action}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


async def show_active_tickets_list(
    event: MessageCallback,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show list of active tickets for the client.
    
    Displays inline list of all active tickets (NEW, IN_PROGRESS, WAITING_CLIENT)
    with pagination support. Client can select a ticket to continue communication.
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    
    Args:
        event: MessageCallback event from maxapi
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: AC-1.3, TR-2
    """
    chat_id = event.message.recipient.chat_id
    # In callback events, user_id comes from event.callback.user, not event.message.sender
    max_user_id = event.callback.user.user_id
    
    try:
        from services.user_service import get_user_by_max_id
        from services.ticket_service import get_user_active_tickets
        from bots.max_bot.keyboards.user.active_tickets_kb import get_active_tickets_keyboard
        
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден. Используйте /start для регистрации.",
                parse_mode="HTML"
            )
            return
        
        # Get active tickets
        tickets = await get_user_active_tickets(session, user.id)
        
        if not tickets:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет активных обращений.",
                parse_mode="HTML"
            )
            logger.info(f"Client {user.id} has no active tickets")
            return
        
        # Generate keyboard with pagination and default filter
        keyboard = await get_active_tickets_keyboard(tickets, page=0, active_filter="all")
        
        # Send message with ticket list
        header_text = (
            f"📥 <b>Активные обращения</b>\n\n"
            f"Фильтр: Все заявки | Всего: {len(tickets)}\n\n"
            f"Выберите обращение для продолжения общения:"
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=header_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Client {user.id} viewed {len(tickets)} active tickets")
    
    except Exception as e:
        logger.error(
            f"Error showing active tickets: user={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке обращений.",
            parse_mode="HTML"
        )


async def handle_done_callback(
    event: MessageCallback,
    payload: DonePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "✅ Готово" button click after ticket creation.

    Deletes the old message with buttons (replace_message pattern),
    then sends a friendly farewell message with /start hint.

    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification
    - Uses replace_message pattern: delete old message, send new one
    - DonePayload.filter() ensures only this button triggers the handler

    Args:
        event: MessageCallback event from maxapi
        payload: DonePayload (auto-parsed, no fields)
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    logger.info(f"Done callback: user={event.callback.user.user_id}, message_id={message_id}")

    try:
        if not await answer_max_callback(event):
            return
    except Exception as e:
        logger.warning(f"Failed to answer done callback: {e}")
        return

    # Delete old message with buttons (replace_message pattern)
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")

    farewell_text = (
        "👍 <b>Хорошо, рад был помочь!</b>\n\n"
        "Если понадоблюсь — всегда здесь. 😊\n\n"
        "Напишите <b>/start</b>, чтобы открыть меню сметчика и создать новое обращение."
    )

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=farewell_text,
        parse_mode="HTML"
    )
