"""
Active Tickets Handlers for MAX Bot

Handles active tickets list display, pagination, and ticket selection.

Requirements: AC-1.3, TR-2
"""

import logging

from maxapi.context import MemoryContext
from maxapi.types import MessageCallback
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.keyboards.user.active_tickets_kb import (
    get_active_tickets_keyboard,
    format_ticket_card_for_client
)
from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    TicketSelectPayload,
    TicketsPaginationPayload,
    TicketHistoryPayload,
    TicketHistoryBackPayload,
)
from database.models import TicketStatus
from services.ticket_service import get_ticket_by_id, get_user_active_tickets
from services.user_service import get_user_by_max_id

logger = logging.getLogger(__name__)


async def handle_select_ticket_callback(
    event: MessageCallback,
    payload: TicketSelectPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle ticket selection from active tickets list.
    
    Sets the selected ticket as active and enters communication mode.
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses TicketSelectPayload for type-safe payload parsing
    - Payload automatically parsed by CallbackPayload.filter() decorator
    
    Args:
        event: MessageCallback event from maxapi
        payload: TicketSelectPayload with ticket_id field (auto-parsed)
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: AC-1.3, TR-2
    """
    chat_id = event.message.recipient.chat_id
    # In callback events, user_id comes from event.callback.user, not event.message.sender

    max_user_id = event.callback.user.user_id
    ticket_id = payload.ticket_id
    
    try:
        if not ticket_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка: ID заявки не указан",
                parse_mode="HTML"
            )
            return
        
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден",
                parse_mode="HTML"
            )
            return
        
        # Get ticket
        ticket = await get_ticket_by_id(session, ticket_id)
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена",
                parse_mode="HTML"
            )
            logger.warning(f"Ticket {ticket_id} not found for client {user.id}")
            return
        
        # Verify ticket belongs to this user
        if ticket.user_id != user.id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой заявке",
                parse_mode="HTML"
            )
            logger.warning(
                f"Client {user.id} attempted to access ticket {ticket_id} "
                f"belonging to user {ticket.user_id}"
            )
            return
        
        # Verify ticket is still active
        if ticket.ticket_status not in [
            TicketStatus.NEW,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_CLIENT
        ]:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка уже закрыта",
                parse_mode="HTML"
            )
            logger.info(f"Ticket {ticket_id} is no longer active (status: {ticket.ticket_status})")
            return
        
        # Set state for communication with manager
        await context.clear()
        await context.update_data(active_ticket_id=ticket_id)
        
        # Show ticket information with navigation buttons
        from bots.max_bot.payloads import ActiveTicketsClosePayload, TicketHistoryPayload
        
        ticket_card = await format_ticket_card_for_client(ticket)
        
        # Create keyboard with history and back buttons
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="📜 История переписки",
                        payload=TicketHistoryPayload(ticket_id=ticket_id, page=0).pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="🔙 К списку обращений",
                        payload=ActiveTicketsClosePayload().pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="🏠 В меню",
                        payload=ActiveTicketsClosePayload().pack()
                    )
                ]
            ],
            inline=True
        )
        
        # Delete old message and send new one (replace_message pattern)
        message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"{ticket_card}\n\n"
                 f"💬 <b>Вы можете продолжить общение с менеджером.</b>\n"
                 f"Отправьте текст, фото, документ или голосовое сообщение.",
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Client {user.id} selected ticket {ticket_id}")
    
    except Exception as e:
        logger.error(
            f"Error handling select ticket callback: ticket_id={ticket_id}, "
            f"user={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


async def handle_tickets_pagination_callback(
    event: MessageCallback,
    payload: TicketsPaginationPayload,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle pagination for active tickets list.
    
    Updates the message with tickets from the requested page.
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses TicketsPaginationPayload for type-safe payload parsing
    - Payload automatically parsed by CallbackPayload.filter() decorator
    
    Args:
        event: MessageCallback event from maxapi
        payload: TicketsPaginationPayload with page field (auto-parsed)
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: AC-1.3, TR-2
    """
    chat_id = event.message.recipient.chat_id
    # In callback events, user_id comes from event.callback.user, not event.message.sender

    max_user_id = event.callback.user.user_id
    page = payload.page
    
    try:
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден",
                parse_mode="HTML"
            )
            return
        
        # Get active tickets
        tickets = await get_user_active_tickets(session, user.id)
        
        if not tickets:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет активных обращений",
                parse_mode="HTML"
            )
            logger.info(f"Client {user.id} has no active tickets")
            return
        
        # Generate keyboard with pagination
        keyboard = await get_active_tickets_keyboard(tickets, page=page)
        
        # Update message with new page
        header_text = (
            f"📥 <b>Активные обращения ({len(tickets)})</b>\n\n"
            f"В этом меню вы можете переключаться между заявками. "
            f"При нажатии на заявку включается режим доставки сообщений назначенному менеджеру.\n\n"
            f"Выберите обращение для продолжения общения:"
        )
        
        # Get message ID for editing
        message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
        
        if message_id:
            await messenger_adapter.edit_message(
                chat_id=chat_id,
                message_id=message_id,
                text=header_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=header_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        
        logger.info(f"Client {user.id} navigated to page {page + 1} of active tickets")
    
    except Exception as e:
        logger.error(
            f"Error handling tickets pagination: page={page}, "
            f"user={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )




async def handle_close_active_tickets(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Close active tickets list and return to main menu.
    
    Follows maxapi pattern: delete old message, show main menu.
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses replace_message pattern (delete old + send new)
    
    Args:
        event: MessageCallback event from maxapi
        context: MemoryContext for FSM state management
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Client closing active tickets: max_user_id={max_user_id}")
    
    try:
        # Clear active ticket from context
        await context.update_data(active_ticket_id=None)
        
        # Delete old message (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Show main menu
        from services.ticket_service import get_user_active_tickets_count
        from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
        
        user = await get_user_by_max_id(session, max_user_id)
        if user:
            active_tickets_count = await get_user_active_tickets_count(session, user.id)
            keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
            
            main_menu_text = (
                "🎉 <b>Добро пожаловать в меню сметчика АЙТАТ!</b>\n\n"
                "Здесь вы можете:\n\n"
                "💰 <b>Получить счёт</b> — запросить счет на обновление базы\n"
                "🆘 <b>Техподдержка</b> — получить помощь по работе с программой ГРАНД-Смета\n"
                "🔄 <b>Продление</b> — продлить подписку на информационно-техническое сопровождение\n"
                "🗄 <b>Архив обращений</b> — просмотреть историю ваших обращений\n"
                "👤 <b>Мой профиль</b> — управление вашими данными и настройками\n\n"
                "Выберите нужное действие:"
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=main_menu_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        
        logger.info(f"Client closed active tickets and returned to main menu: max_user_id={max_user_id}")
        
    except Exception as e:
        logger.error(f"Error closing active tickets: max_user_id={max_user_id}, error={e}", exc_info=True)


# Message history pagination constants
MESSAGES_PER_PAGE = 10


async def handle_ticket_history(
    event: MessageCallback,
    payload: TicketHistoryPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show ticket message history with pagination.
    
    Displays messages in chronological order with navigation buttons.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: TicketHistoryPayload with ticket_id and page
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    ticket_id = payload.ticket_id
    page = payload.page
    
    logger.info(f"Client viewing ticket history: max_user_id={max_user_id}, ticket_id={ticket_id}, page={page}")
    
    try:
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден",
                parse_mode="HTML"
            )
            return
        
        # Get ticket
        ticket = await get_ticket_by_id(session, ticket_id)
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена",
                parse_mode="HTML"
            )
            return
        
        # Verify ticket belongs to this user
        if ticket.user_id != user.id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой заявке",
                parse_mode="HTML"
            )
            return
        
        # Get all messages for this ticket
        from database.models import Message
        from sqlalchemy.orm import selectinload
        
        stmt = (
            select(Message)
            .where(Message.ticket_id == ticket_id)
            .options(selectinload(Message.file_attachments))
            .order_by(Message.sent_at.asc())
        )
        result = await session.execute(stmt)
        all_messages = list(result.scalars().all())
        
        if not all_messages:
            # Delete old message
            if message_id:
                try:
                    await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception as e:
                    logger.warning(f"Failed to delete old message: {e}")
            
            # Show empty history message with back button
            from bots.max_bot.payloads import TicketHistoryBackPayload
            
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="🔙 К заявке",
                            payload=TicketHistoryBackPayload(ticket_id=ticket_id).pack()
                        )
                    ]
                ],
                inline=True
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="📭 История переписки пуста",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        # Calculate pagination
        total_messages = len(all_messages)
        total_pages = (total_messages + MESSAGES_PER_PAGE - 1) // MESSAGES_PER_PAGE
        
        # Validate page number
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1
        
        # Get messages for current page
        start_idx = page * MESSAGES_PER_PAGE
        end_idx = min(start_idx + MESSAGES_PER_PAGE, total_messages)
        page_messages = all_messages[start_idx:end_idx]
        
        # Format messages
        from database.models import SenderType, Staff_Member
        
        lines = [
            f"📜 <b>История переписки - Заявка #{ticket_id}</b>",
            f"Страница {page + 1} из {total_pages} (сообщений {start_idx + 1}-{end_idx} из {total_messages})",
            "─" * 30,
            ""
        ]
        
        for msg in page_messages:
            # Format timestamp
            timestamp = msg.sent_at.strftime("%d.%m %H:%M")
            
            # Determine sender
            if msg.sender_type == SenderType.USER:
                sender_label = "👤 Вы"
            elif msg.sender_type == SenderType.STAFF:
                # Get staff member name by internal ID
                if msg.sender_id:
                    stmt = select(Staff_Member).where(Staff_Member.id == msg.sender_id)
                    result = await session.execute(stmt)
                    staff = result.scalar_one_or_none()
                    
                    if staff:
                        sender_label = f"👨‍💼 {staff.full_name}"
                    else:
                        sender_label = "👨‍💼 Сотрудник"
                else:
                    sender_label = "👨‍💼 Сотрудник"
            elif msg.sender_type == SenderType.SYSTEM:
                sender_label = "🤖 Система"
            else:
                sender_label = "❓ Неизвестно"
            
            # Format message
            lines.append(f"<b>[{timestamp}] {sender_label}</b>")
            
            if msg.message_text:
                # Truncate long messages
                text = msg.message_text
                if len(text) > 200:
                    text = text[:200] + "..."
                lines.append(text)
            
            # Check for file attachments
            if msg.file_attachments:
                for attachment in msg.file_attachments:
                    file_type = attachment.file_type.value if attachment.file_type else "файл"
                    lines.append(f"📎 {attachment.file_name} ({file_type})")
            
            lines.append("")  # Empty line between messages
        
        lines.append("─" * 30)
        
        history_text = "\n".join(lines)
        
        # Build navigation keyboard
        from bots.max_bot.payloads import TicketHistoryBackPayload
        
        buttons = []
        
        # Pagination buttons
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(
                    KeyboardButton(
                        text="⬅️ Назад",
                        payload=TicketHistoryPayload(ticket_id=ticket_id, page=page - 1).pack()
                    )
                )
            if page < total_pages - 1:
                nav_buttons.append(
                    KeyboardButton(
                        text="Вперёд ➡️",
                        payload=TicketHistoryPayload(ticket_id=ticket_id, page=page + 1).pack()
                    )
                )
            if nav_buttons:
                buttons.append(nav_buttons)
        
        # Back button
        buttons.append([
            KeyboardButton(
                text="🔙 К заявке",
                payload=TicketHistoryBackPayload(ticket_id=ticket_id).pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        # Delete old message and send new one (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=history_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Client viewed ticket history: max_user_id={max_user_id}, ticket_id={ticket_id}, "
            f"page={page + 1}/{total_pages}"
        )
        
    except Exception as e:
        logger.error(
            f"Error viewing ticket history: max_user_id={max_user_id}, ticket_id={ticket_id}, "
            f"page={page}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке истории.",
            parse_mode="HTML"
        )


async def handle_ticket_history_back(
    event: MessageCallback,
    payload: TicketHistoryBackPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Return from ticket history to ticket card.
    
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: TicketHistoryBackPayload with ticket_id
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    ticket_id = payload.ticket_id
    
    logger.info(f"Client returning from history to ticket: max_user_id={max_user_id}, ticket_id={ticket_id}")
    
    try:
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден",
                parse_mode="HTML"
            )
            return
        
        # Get ticket
        ticket = await get_ticket_by_id(session, ticket_id)
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена",
                parse_mode="HTML"
            )
            return
        
        # Verify ticket belongs to this user
        if ticket.user_id != user.id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой заявке",
                parse_mode="HTML"
            )
            return
        
        # Show ticket card
        from bots.max_bot.payloads import ActiveTicketsClosePayload, TicketHistoryPayload
        
        ticket_card = await format_ticket_card_for_client(ticket)
        
        # Create keyboard with history and back buttons
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="📜 История переписки",
                        payload=TicketHistoryPayload(ticket_id=ticket_id, page=0).pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="🔙 К списку обращений",
                        payload=ActiveTicketsClosePayload().pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="🏠 В меню",
                        payload=ActiveTicketsClosePayload().pack()
                    )
                ]
            ],
            inline=True
        )
        
        # Delete old message and send new one (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"{ticket_card}\n\n"
                 f"💬 <b>Вы можете продолжить общение с менеджером.</b>\n"
                 f"Отправьте текст, фото, документ или голосовое сообщение.",
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Client returned to ticket card: max_user_id={max_user_id}, ticket_id={ticket_id}")
        
    except Exception as e:
        logger.error(
            f"Error returning to ticket card: max_user_id={max_user_id}, ticket_id={ticket_id}, "
            f"error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )
