"""
Active Tickets Handlers for MAX Bot

Handles active tickets list display, pagination, and ticket selection.

Requirements: AC-1.3, TR-2
"""

import logging
from html import escape

from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.states import ClientTicketCloseStates
from bots.max_bot.keyboards.user.active_tickets_kb import (
    get_active_tickets_keyboard,
    format_ticket_card_for_client
)
from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    MainMenuActionPayload,
    ReplyToManagerPayload,
    TicketSelectPayload,
    TicketsPaginationPayload,
    TicketsFilterPayload,
    ActiveTicketsClosePayload,
    TicketHistoryPayload,
    TicketHistoryBackPayload,
    ClientTicketCloseStartPayload,
    ClientTicketCloseCancelPayload,
)
from database.models import TicketStatus
from services.ticket_service import (
    TicketAlreadyClosedError,
    close_ticket_by_client,
    get_ticket_by_id,
    get_user_active_tickets,
)
from services.user_service import get_user_by_max_id

logger = logging.getLogger(__name__)

_FILTER_NAMES = {
    "all": "Все заявки",
    "invoice": "Счёт",
    "support": "ТП",
    "consultation": "Консультация",
    "renewal": "Активация подписки",
}

ACTIVE_STATUSES = {
    TicketStatus.NEW,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_CLIENT,
}


def _build_header(total: int, filtered: int, active_filter: str) -> str:
    """Build header text for active tickets list."""
    filter_name = _FILTER_NAMES.get(active_filter, active_filter)
    count_str = f"{filtered}" if active_filter != "all" else f"{total}"
    return (
        f"📥 <b>Активные обращения</b>\n\n"
        f"Фильтр: {filter_name} | Всего: {count_str}\n\n"
        f"Выберите обращение для продолжения общения:"
    )


def _get_ticket_actions_keyboard(ticket_id: int) -> Keyboard:
    """Build client ticket details keyboard."""
    return Keyboard(
        buttons=[
            [
                KeyboardButton(
                    text="📜 История переписки",
                    payload=TicketHistoryPayload(ticket_id=ticket_id, page=0).pack()
                )
            ],
            [
                KeyboardButton(
                    text="✅ Закрыть обращение",
                    payload=ClientTicketCloseStartPayload(ticket_id=ticket_id).pack()
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
                    payload=MainMenuActionPayload(action="main_menu").pack()
                )
            ],
        ],
        inline=True,
    )


def _get_cancel_close_keyboard(ticket_id: int) -> Keyboard:
    """Build cancel keyboard for client ticket closure flow."""
    return Keyboard(
        buttons=[
            [
                KeyboardButton(
                    text="❌ Отмена",
                    payload=ClientTicketCloseCancelPayload(ticket_id=ticket_id).pack(),
                )
            ]
        ],
        inline=True,
    )


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
        
        ticket_card = await format_ticket_card_for_client(ticket)
        
        keyboard = _get_ticket_actions_keyboard(ticket_id)
        
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

    Updates the message with tickets from the requested page, preserving active filter.
    Uses replace_message pattern (delete old + send new).
    Uses event.callback.user.user_id to identify the MAX user.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    page = payload.page
    active_filter = getattr(payload, 'filter', 'all') or 'all'

    try:
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден",
                parse_mode="HTML"
            )
            return

        tickets = await get_user_active_tickets(session, user.id)

        if not tickets:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет активных обращений",
                parse_mode="HTML"
            )
            return

        from bots.max_bot.keyboards.user.active_tickets_kb import filter_tickets
        filtered = filter_tickets(tickets, active_filter)

        keyboard = await get_active_tickets_keyboard(tickets, page=page, active_filter=active_filter)

        header_text = _build_header(len(tickets), len(filtered), active_filter)

        message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=header_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )

        logger.info(f"Client {user.id} navigated to page {page + 1}, filter={active_filter}")

    except Exception as e:
        logger.error(
            f"Error handling tickets pagination: page={page}, user={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


async def handle_tickets_filter_callback(
    event: MessageCallback,
    payload: TicketsFilterPayload,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle filter button click in active tickets list.

    Reloads the list with the selected ticket type filter applied.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    active_filter = payload.filter or 'all'

    try:
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден",
                parse_mode="HTML"
            )
            return

        tickets = await get_user_active_tickets(session, user.id)

        from bots.max_bot.keyboards.user.active_tickets_kb import filter_tickets
        filtered = filter_tickets(tickets, active_filter)

        keyboard = await get_active_tickets_keyboard(tickets, page=0, active_filter=active_filter)
        header_text = _build_header(len(tickets), len(filtered), active_filter)

        message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=header_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )

        logger.info(f"Client {user.id} applied filter={active_filter}, found {len(filtered)} tickets")

    except Exception as e:
        logger.error(
            f"Error handling tickets filter: filter={active_filter}, user={max_user_id}, error={e}",
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
    Close active tickets list and return to active tickets list.
    
    Follows maxapi pattern: delete old message, show active tickets list.
    
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
    
    logger.info(f"Client exiting reply mode: max_user_id={max_user_id}")
    
    try:
        # Clear active ticket from context
        await context.update_data(active_ticket_id=None)
        
        # Delete old message (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Show active tickets list
        from bots.max_bot.keyboards.user.active_tickets_kb import get_active_tickets_keyboard
        from services.ticket_service import get_user_active_tickets
        from services.user_service import get_user_by_max_id
        
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден",
                parse_mode="HTML"
            )
            return
        
        # Get active tickets
        active_tickets = await get_user_active_tickets(session, user.id)
        
        if not active_tickets:
            # No active tickets - show main menu
            from services.ticket_service import get_user_active_tickets_count
            from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
            from bots.max_bot.texts import MAIN_MENU_WELCOME_TEXT
            
            active_tickets_count = await get_user_active_tickets_count(session, user.id)
            keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=MAIN_MENU_WELCOME_TEXT,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            # Show active tickets list
            keyboard = await get_active_tickets_keyboard(
                tickets=active_tickets,
                page=0,
                active_filter="all"
            )
            
            total_count = len(active_tickets)
            header = f"📋 <b>Активные обращения</b>\n\nФильтр: Все заявки | Всего: {total_count}\n\nВыберите обращение для продолжения общения:"
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=header,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        
        logger.info(f"Client exited reply mode and returned to active tickets: max_user_id={max_user_id}")
        
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
            "─" * 5,
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
                    from database.models import FileType as FT
                    ft = attachment.file_type
                    if ft == FT.IMAGE:
                        label = "Изображение"
                        emoji = "🖼"
                    elif ft in (FT.DOCUMENT, FT.PDF):
                        label = "Документ"
                        emoji = "📄"
                    elif ft == FT.OTHER:
                        label = "Голосовое сообщение"
                        emoji = "🎤"
                    else:
                        label = "Файл"
                        emoji = "📎"
                    file_url = attachment.max_file_url or (
                        attachment.telegram_file_id
                        if attachment.telegram_file_id and attachment.telegram_file_id.startswith("http")
                        else None
                    )
                    if file_url:
                        lines.append(f'{emoji} <a href="{file_url}">{label}</a>')
                    else:
                        lines.append(f"{emoji} {label}")
            
            lines.append("")  # Empty line between messages
        
        lines.append("─" * 5)
        
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
        
        ticket_card = await format_ticket_card_for_client(ticket)
        
        keyboard = _get_ticket_actions_keyboard(ticket_id)
        
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


async def handle_client_ticket_close_start(
    event: MessageCallback,
    payload: ClientTicketCloseStartPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Ask client for a ticket closure reason."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    ticket_id = payload.ticket_id

    try:
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден",
                parse_mode="HTML",
            )
            return

        ticket = await get_ticket_by_id(session, ticket_id)
        if not ticket or ticket.user_id != user.id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена или недоступна.",
                parse_mode="HTML",
            )
            return

        if ticket.ticket_status not in ACTIVE_STATUSES:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"Заявка #{ticket_id} уже закрыта.",
                parse_mode="HTML",
            )
            return

        await context.clear()
        await context.update_data(closing_ticket_id=ticket_id)
        await context.set_state(ClientTicketCloseStates.waiting_for_reason)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"Укажите причину закрытия обращения #{ticket_id}.\n\n"
                "Например: вопрос решен, заявка больше не актуальна, "
                "получил ответ другим способом."
            ),
            keyboard=_get_cancel_close_keyboard(ticket_id),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(
            f"Error starting client ticket close: ticket_id={ticket_id}, "
            f"max_user_id={max_user_id}, error={e}",
            exc_info=True,
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Не удалось начать закрытие заявки. Попробуйте позже.",
            parse_mode="HTML",
        )


async def handle_client_ticket_close_cancel(
    event: MessageCallback,
    payload: ClientTicketCloseCancelPayload,
    context: MemoryContext,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Cancel client ticket closure flow."""
    chat_id = event.message.recipient.chat_id
    await context.clear()
    await context.update_data(active_ticket_id=payload.ticket_id)
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="Закрытие обращения отменено.",
        keyboard=_get_ticket_actions_keyboard(payload.ticket_id),
        parse_mode="HTML",
    )


async def process_client_ticket_close_reason(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Close ticket after client sends a reason."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    reason = event.message.body.text.strip() if event.message.body and event.message.body.text else ""

    if len(reason) < 3:
        data = await context.get_data()
        ticket_id = data.get("closing_ticket_id")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Напишите причину закрытия чуть подробнее.",
            keyboard=_get_cancel_close_keyboard(ticket_id) if ticket_id else None,
            parse_mode="HTML",
        )
        return

    try:
        data = await context.get_data()
        ticket_id = data.get("closing_ticket_id")
        if not ticket_id:
            await context.clear()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="Не нашла заявку для закрытия. Откройте активные обращения и попробуйте ещё раз.",
                parse_mode="HTML",
            )
            return

        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await context.clear()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден",
                parse_mode="HTML",
            )
            return

        await close_ticket_by_client(
            session=session,
            ticket_id=ticket_id,
            user_id=user.id,
            reason=reason,
        )
        await session.commit()
        await context.clear()

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ Обращение #{ticket_id} закрыто.\n\n"
                f"<b>Причина:</b> {escape(reason)}"
            ),
            parse_mode="HTML",
        )

    except TicketAlreadyClosedError:
        await session.rollback()
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Эта заявка уже закрыта.",
            parse_mode="HTML",
        )

    except PermissionError:
        await session.rollback()
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ У вас нет доступа к этой заявке.",
            parse_mode="HTML",
        )

    except Exception as e:
        await session.rollback()
        logger.error(
            f"Error closing ticket by client: max_user_id={max_user_id}, error={e}",
            exc_info=True,
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Не удалось закрыть заявку. Попробуйте позже.",
            parse_mode="HTML",
        )


async def handle_reply_to_manager_callback(
    event: MessageCallback,
    payload: ReplyToManagerPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Reply to manager" button click from manager's message.

    Sets active_ticket_id in FSM so subsequent client messages are routed
    directly to the manager without needing to open "Active tickets" menu.

    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses replace_message pattern (delete old + send new)
    - Does NOT delete the manager's message — only sends a confirmation

    Args:
        event: MessageCallback event from maxapi
        payload: ReplyToManagerPayload with ticket_id field (auto-parsed)
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    ticket_id = payload.ticket_id

    logger.info(
        f"handle_reply_to_manager_callback called: max_user_id={max_user_id}, "
        f"ticket_id={ticket_id}, payload_type={type(payload)}"
    )

    try:
        # Verify user exists
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден",
                parse_mode="HTML"
            )
            return

        # Verify ticket exists and belongs to this user
        ticket = await get_ticket_by_id(session, ticket_id)
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена",
                parse_mode="HTML"
            )
            return

        if ticket.user_id != user.id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой заявке",
                parse_mode="HTML"
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
                text=f"❌ Заявка #{ticket_id} уже закрыта.",
                parse_mode="HTML"
            )
            return

        # Set active_ticket_id in FSM — now all messages will be routed to manager
        await context.clear()
        await context.update_data(active_ticket_id=ticket_id)

        # Build "stop reply" keyboard so client can exit reply mode
        from bots.max_bot.payloads import ActiveTicketsClosePayload
        stop_keyboard = Keyboard(
            buttons=[[
                KeyboardButton(
                    text="🔙 Выйти из режима ответа",
                    payload=ActiveTicketsClosePayload().pack()
                )
            ]],
            inline=True
        )

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ <b>Режим ответа активирован</b>\n\n"
                f"Заявка #{ticket_id}\n\n"
                f"Теперь все ваши сообщения будут доставляться менеджеру напрямую.\n"
                f"Отправьте текст, фото, документ или голосовое сообщение."
            ),
            keyboard=stop_keyboard,
            parse_mode="HTML"
        )

        logger.info(
            f"Reply mode activated: max_user_id={max_user_id}, ticket_id={ticket_id}"
        )

    except Exception as e:
        logger.error(
            f"Error handling reply_to_manager callback: max_user_id={max_user_id}, "
            f"ticket_id={ticket_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )
