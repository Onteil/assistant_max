"""
Client Archive Handler for MAX Bot

Handles client archive viewing with filters and pagination.
Migrated from Telegram bot.

Requirements: Archive viewing for clients
"""

import logging

from maxapi import F
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.callback_datas import ClientArchiveCallback
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.payloads import (
    ArchiveFilterPayload,
    ArchivePaginationPayload,
    ViewArchivedTicketPayload,
    ArchiveClosePayload
)
from database.models import Ticket, TicketStatus
from services import client_service
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


# ========== Archive Button Handler ==========


async def handle_client_archive_button(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "📋 Архив обращений" button from main menu.
    
    Shows client's closed tickets with filters and pagination.
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    await show_archive_list(chat_id, max_user_id, session, messenger_adapter, context)


async def show_archive_list(
    chat_id: int,
    max_user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    context: MemoryContext
) -> None:
    """
    Show client's archive list with filters and pagination.
    
    Helper function that can be called from both message and callback handlers.
    
    Args:
        chat_id: Chat ID
        max_user_id: MAX user ID
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        context: FSM context for storing filter state
    """
    logger.info(f"Showing archive list: max_user_id={max_user_id}, chat_id={chat_id}")
    
    try:
        # Get user from database
        from services.user_service import get_user_by_max_id
        user = await get_user_by_max_id(session, max_user_id)
        
        if not user:
            logger.error(f"User not found for archive: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден. Пожалуйста, пройдите регистрацию командой /start",
                parse_mode="HTML"
            )
            return
        
        # Default filter: all
        current_filter = "all"
        current_page = 0

        # Get all closed tickets (for filter visibility)
        all_tickets = await client_service.get_client_closed_tickets_by_filter(
            session=session,
            user_id=user.id,
            filter_type="all"
        )

        if not all_tickets:
            from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
            from bots.max_bot.payloads import ArchiveClosePayload

            keyboard = Keyboard(
                buttons=[[KeyboardButton(text="🏠 В меню", payload=ArchiveClosePayload().pack())]],
                inline=True
            )
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="📋 У вас пока нет закрытых обращений",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            logger.info(f"Client {user.id} has no closed tickets")
            return

        tickets = all_tickets  # "all" filter — no additional filtering

        # Save filter to context
        await context.update_data(
            client_archive_filter=current_filter,
            client_archive_page=current_page
        )

        # Format header text
        header_text = await client_service.format_client_archive_header(
            tickets_count=len(tickets),
            current_filter=current_filter
        )

        # Generate inline keyboard
        keyboard = await client_service.get_client_archive_keyboard_max(
            tickets=tickets,
            current_filter=current_filter,
            current_page=current_page,
            all_tickets=all_tickets,
        )
        
        # Send message with header and keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=header_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Client {user.id} opened archive "
            f"(filter={current_filter}, page={current_page}, tickets_count={len(tickets)})"
        )
        
    except Exception as e:
        logger.error(f"Error opening client archive: max_user_id={max_user_id}, error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при открытии архива.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )


# ========== Archive Filter Handler ==========


async def handle_client_archive_filter(
    event: MessageCallback,
    payload: ArchiveFilterPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle archive filter selection.
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses ArchiveFilterPayload for type-safe payload parsing
    - Payload automatically parsed by CallbackPayload.filter() decorator
    
    Args:
        event: MessageCallback event from maxapi
        payload: ArchiveFilterPayload with filter_type field (auto-parsed)
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    logger.info(f"Archive filter callback: max_user_id={max_user_id}, filter_type={payload.filter_type}")
    
    try:
        # Get user from database
        from services.user_service import get_user_by_max_id
        user = await get_user_by_max_id(session, max_user_id)
        
        if not user:
            logger.error(f"User not found for archive filter: max_user_id={max_user_id}")
            return
        
        new_filter = payload.filter_type

        # Switch to the new filter
        current_filter = new_filter
        current_page = 0  # Reset to first page

        # Get all tickets (for filter visibility) and filtered tickets
        all_tickets = await client_service.get_client_closed_tickets_by_filter(
            session=session,
            user_id=user.id,
            filter_type="all"
        )
        tickets = await client_service.get_client_closed_tickets_by_filter(
            session=session,
            user_id=user.id,
            filter_type=current_filter
        )

        # Save filter to context
        await context.update_data(
            client_archive_filter=current_filter,
            client_archive_page=current_page
        )

        # Format header text
        header_text = await client_service.format_client_archive_header(
            tickets_count=len(tickets),
            current_filter=current_filter
        )

        # Generate inline keyboard
        keyboard = await client_service.get_client_archive_keyboard_max(
            tickets=tickets,
            current_filter=current_filter,
            current_page=current_page,
            all_tickets=all_tickets,
        )

        # Replace message (delete + send)
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

        logger.info(f"Client {user.id} changed archive filter to {current_filter} (tickets_count={len(tickets)})")

    except Exception as e:
        logger.error(f"Error handling archive filter: max_user_id={max_user_id}, error={e}", exc_info=True)


# ========== Archive Pagination Handler ==========


async def handle_client_archive_pagination(
    event: MessageCallback,
    payload: ArchivePaginationPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle pagination for client archive.
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses ArchivePaginationPayload for type-safe payload parsing
    - Payload automatically parsed by CallbackPayload.filter() decorator
    
    Args:
        event: MessageCallback event from maxapi
        payload: ArchivePaginationPayload with page and filter_type fields (auto-parsed)
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    logger.info(f"Archive pagination callback: max_user_id={max_user_id}, page={payload.page}, filter={payload.filter_type}")
    
    try:
        # Get user from database
        from services.user_service import get_user_by_max_id
        user = await get_user_by_max_id(session, max_user_id)
        
        if not user:
            logger.error(f"User not found for archive pagination: max_user_id={max_user_id}")
            return
        
        page = payload.page
        filter_type = payload.filter_type

        # Get all tickets (for filter visibility) and filtered tickets
        all_tickets = await client_service.get_client_closed_tickets_by_filter(
            session=session,
            user_id=user.id,
            filter_type="all"
        )
        tickets = await client_service.get_client_closed_tickets_by_filter(
            session=session,
            user_id=user.id,
            filter_type=filter_type
        )

        # Update context
        await context.update_data(
            client_archive_filter=filter_type,
            client_archive_page=page
        )

        # Format header text
        header_text = await client_service.format_client_archive_header(
            tickets_count=len(tickets),
            current_filter=filter_type
        )

        # Generate inline keyboard
        keyboard = await client_service.get_client_archive_keyboard_max(
            tickets=tickets,
            current_filter=filter_type,
            current_page=page,
            all_tickets=all_tickets,
        )

        # Replace message (delete + send)
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

        logger.info(f"Client archive pagination: user={user.id}, filter={filter_type}, page={page}")

    except Exception as e:
        logger.error(
            f"Error paginating client archive: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )


# ========== View Archived Ticket Handler ==========


async def view_client_archived_ticket(
    event: MessageCallback,
    payload: ViewArchivedTicketPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display archived ticket with full details and message history.
    
    If message history exceeds 4096 characters, it's sent as a .txt file.
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses ViewArchivedTicketPayload for type-safe payload parsing
    - Payload automatically parsed by CallbackPayload.filter() decorator
    
    Args:
        event: MessageCallback event from maxapi
        payload: ViewArchivedTicketPayload with ticket_id field (auto-parsed)
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    ticket_id = payload.ticket_id
    
    logger.info(f"Client viewing archived ticket: max_user_id={max_user_id}, ticket_id={ticket_id}")
    
    try:
        # Get user from database
        from services.user_service import get_user_by_max_id
        user = await get_user_by_max_id(session, max_user_id)
        
        if not user:
            logger.error(f"User not found for viewing ticket: max_user_id={max_user_id}")
            return
        
        # Get ticket with eager loading
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            logger.warning(f"Ticket not found: ticket_id={ticket_id}")
            return
        
        # Verify ticket belongs to this user
        if ticket.user_id != user.id:
            logger.warning(f"Access denied: user={user.id}, ticket={ticket_id}")
            return
        
        # Verify ticket is closed
        if ticket.ticket_status not in [TicketStatus.CLOSED, TicketStatus.CANCELLED]:
            logger.warning(f"Ticket not closed: ticket_id={ticket_id}, status={ticket.ticket_status}")
            return
        
        # Format full ticket details
        ticket_details = await client_service.format_client_archived_ticket_details(
            ticket=ticket,
            session=session
        )
        
        # Format message history
        from services import employee_service
        message_history = await employee_service.format_ticket_message_history(
            ticket=ticket,
            session=session
        )
        
        # Get current filter and page from context for back navigation
        data = await context.get_data()
        current_filter = data.get("client_archive_filter", "all")
        current_page = data.get("client_archive_page", 0)
        
        # Build keyboard with back button using proper payload
        from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
        from bots.max_bot.payloads import ArchivePaginationPayload
        
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="🔙 Назад к архиву",
                        payload=ArchivePaginationPayload(
                            page=current_page,
                            filter_type=current_filter
                        ).pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="🏠 В меню",
                        payload=ArchiveClosePayload().pack()
                    )
                ]
            ],
            inline=True
        )
        
        # Check if combined text exceeds MAX limit
        combined_text = f"{ticket_details}\n\n{message_history}"
        
        # Get message ID for replace_message pattern
        message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
        
        # Delete old message (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        if len(combined_text) <= 4096:
            # Send as single message
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=combined_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            # Send details as message, history as file
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ticket_details,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            # Send message history as .txt file
            import tempfile
            import os
            
            try:
                # Create temporary file
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    encoding='utf-8',
                    suffix='.txt',
                    delete=False
                ) as tmp_file:
                    tmp_file.write(message_history)
                    tmp_file_path = tmp_file.name
                
                # Send file
                await messenger_adapter.send_document(
                    chat_id=chat_id,
                    document_path=tmp_file_path,
                    caption=f"📎 История переписки по обращению #{ticket_id}",
                    parse_mode="HTML"
                )
                
                # Clean up temporary file
                os.unlink(tmp_file_path)
                
                logger.info(f"Sent history as file for ticket {ticket_id} (size: {len(message_history)} chars)")
                
            except Exception as e:
                logger.error(f"Failed to send history as file for ticket {ticket_id}: {e}", exc_info=True)
                # Fallback: send truncated history as text
                truncated_history = message_history[:3000] + "\n\n... (история обрезана)"
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=f"📎 История переписки (обрезана):\n\n{truncated_history}",
                    parse_mode="HTML"
                )
        
        logger.info(
            f"Displayed archived ticket {ticket_id} for client {user.id} "
            f"(history_length={len(message_history)}, sent_as_file={len(combined_text) > 4096})"
        )
        
    except Exception as e:
        logger.error(
            f"Error viewing client archived ticket: max_user_id={max_user_id}, "
            f"ticket_id={ticket_id}, error={e}",
            exc_info=True
        )


# ========== Close Archive Handler ==========


async def handle_client_archive_close(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Close archive and return to main menu.
    
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
    
    logger.info(f"Client closing archive: max_user_id={max_user_id}")
    
    try:
        # Clear context
        await context.update_data(
            client_archive_filter=None,
            client_archive_page=None
        )
        
        # Delete old message (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Show main menu
        from services.user_service import get_user_by_max_id
        from services.ticket_service import get_user_active_tickets_count
        from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
        
        user = await get_user_by_max_id(session, max_user_id)
        if user:
            active_tickets_count = await get_user_active_tickets_count(session, user.id)
            keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
            
            from bots.max_bot.texts import MAIN_MENU_WELCOME_TEXT
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=MAIN_MENU_WELCOME_TEXT,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        
        logger.info(f"Client closed archive and returned to main menu: max_user_id={max_user_id}")
        
    except Exception as e:
        logger.error(f"Error closing client archive: max_user_id={max_user_id}, error={e}", exc_info=True)


