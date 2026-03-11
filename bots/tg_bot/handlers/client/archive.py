"""
Client Archive Handlers

Handles client archive viewing with filters and pagination.
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bots.tg_bot.callback_datas import ClientArchiveCallback
from bots.tg_bot.texts import MENU_ARCHIVE
from database.models import Ticket, TicketStatus
from services import client_service, employee_service
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = Router(name="client_archive")


@router.message(F.text == MENU_ARCHIVE)
async def handle_client_archive_button(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle "Archive" button from main menu.
    
    Shows client's closed tickets with filters and pagination.
    """
    try:
        user_id = message.from_user.id
        
        # Default filter: invoice (first filter button)
        current_filter = "invoice"
        current_page = 0
        
        # Get closed tickets by filter
        tickets = await client_service.get_client_closed_tickets_by_filter(
            session=session,
            tg_user_id=user_id,
            filter_type=current_filter
        )
        
        if not tickets:
            # Try to get any closed tickets
            all_tickets = await client_service.get_client_closed_tickets_by_filter(
                session=session,
                tg_user_id=user_id,
                filter_type="all"
            )
            
            if not all_tickets:
                await message.answer("📋 У вас пока нет закрытых обращений")
                logger.info(f"Client {user_id} has no closed tickets")
                return
        
        # Save filter to state
        await state.update_data(
            client_archive_filter=current_filter,
            client_archive_page=current_page
        )
        
        # Format header text
        header_text = await client_service.format_client_archive_header(
            tickets_count=len(tickets),
            current_filter=current_filter
        )
        
        # Generate inline keyboard
        keyboard = await client_service.get_client_archive_keyboard(
            tickets=tickets,
            current_filter=current_filter,
            current_page=current_page
        )
        
        # Send message with header and keyboard
        await message.answer(
            header_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Client {user_id} opened archive "
            f"(filter={current_filter}, page={current_page}, tickets_count={len(tickets)})"
        )
        
    except Exception as e:
        logger.error(f"Error opening client archive for user {message.from_user.id}: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при открытии архива.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.callback_query(ClientArchiveCallback.filter(F.action == "filter"))
async def handle_client_archive_filter(
    callback: CallbackQuery,
    callback_data: ClientArchiveCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle archive filter selection.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        new_filter = callback_data.filter_type or "invoice"
        
        # Switch to the new filter
        current_filter = new_filter
        current_page = 0  # Reset to first page
        
        # Get closed tickets by filter
        tickets = await client_service.get_client_closed_tickets_by_filter(
            session=session,
            tg_user_id=user_id,
            filter_type=current_filter
        )
        
        # Save filter to state
        await state.update_data(
            client_archive_filter=current_filter,
            client_archive_page=current_page
        )
        
        # Format header text
        header_text = await client_service.format_client_archive_header(
            tickets_count=len(tickets),
            current_filter=current_filter
        )
        
        # Generate inline keyboard
        keyboard = await client_service.get_client_archive_keyboard(
            tickets=tickets,
            current_filter=current_filter,
            current_page=current_page
        )
        
        # Edit message
        await callback.message.edit_text(
            header_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Client {user_id} changed archive filter to {current_filter} "
            f"(tickets_count={len(tickets)})"
        )
        
    except Exception as e:
        logger.error(f"Error handling client archive filter: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(ClientArchiveCallback.filter(F.action == "page"))
async def handle_client_archive_pagination(
    callback: CallbackQuery,
    callback_data: ClientArchiveCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle pagination for client archive.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        page = callback_data.page
        filter_type = callback_data.filter_type or "invoice"
        
        # Get tickets by filter
        tickets = await client_service.get_client_closed_tickets_by_filter(
            session=session,
            tg_user_id=user_id,
            filter_type=filter_type
        )
        
        # Update state
        await state.update_data(
            client_archive_filter=filter_type,
            client_archive_page=page
        )
        
        # Format header text
        header_text = await client_service.format_client_archive_header(
            tickets_count=len(tickets),
            current_filter=filter_type
        )
        
        # Generate inline keyboard
        keyboard = await client_service.get_client_archive_keyboard(
            tickets=tickets,
            current_filter=filter_type,
            current_page=page
        )
        
        # Edit message
        await callback.message.edit_text(
            header_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Client archive pagination: user={user_id}, filter={filter_type}, page={page}"
        )
        
    except Exception as e:
        logger.error(
            f"Error paginating client archive: user={callback.from_user.id}, "
            f"page={callback_data.page}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(ClientArchiveCallback.filter(F.action == "view_ticket"))
async def view_client_archived_ticket(
    callback: CallbackQuery,
    callback_data: ClientArchiveCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Display archived ticket with full details and message history.
    
    If message history exceeds 4096 characters, it's sent as a .txt file.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        logger.info(f"Client {user_id} viewing archived ticket {ticket_id}")
        
        # Get ticket with eager loading
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        # Verify ticket belongs to this user
        if ticket.user.tg_user_id != user_id:
            await callback.answer("❌ У вас нет доступа к этой заявке", show_alert=True)
            return
        
        # Verify ticket is closed
        if ticket.ticket_status not in [TicketStatus.CLOSED, TicketStatus.CANCELLED]:
            await callback.answer("❌ Эта заявка не закрыта", show_alert=True)
            return
        
        # Format full ticket details
        ticket_details = await client_service.format_client_archived_ticket_details(
            ticket=ticket,
            session=session
        )
        
        # Format message history
        message_history = await employee_service.format_ticket_message_history(
            ticket=ticket,
            session=session
        )
        
        # Build keyboard with back button
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        # Save current filter and page to state for back navigation
        data = await state.get_data()
        current_filter = data.get("client_archive_filter", "invoice")
        current_page = data.get("client_archive_page", 0)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Назад к архиву",
                    callback_data=ClientArchiveCallback(
                        action="page",
                        filter_type=current_filter,
                        page=current_page
                    ).pack()
                )
            ]
        ])
        
        # Check if combined text exceeds Telegram limit
        combined_text = f"{ticket_details}\n\n{message_history}"
        
        if len(combined_text) <= 4096:
            # Try to send as single message with HTML
            try:
                await callback.message.edit_text(
                    combined_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as html_error:
                # If HTML parsing fails, strip HTML tags and escape special chars
                logger.warning(
                    f"HTML parsing failed for ticket {ticket_id}, sending as plain text: {html_error}"
                )
                import re
                import html
                # Strip HTML tags
                plain_text = re.sub(r'<[^>]+>', '', combined_text)
                # Escape any remaining HTML entities
                plain_text = html.escape(plain_text, quote=False)
                await callback.message.edit_text(
                    plain_text,
                    reply_markup=keyboard
                )
        else:
            # Send details as message, history as file
            try:
                await callback.message.edit_text(
                    ticket_details,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as html_error:
                # If HTML parsing fails, strip HTML tags and escape special chars
                logger.warning(
                    f"HTML parsing failed for ticket {ticket_id} details, sending as plain text: {html_error}"
                )
                import re
                import html
                # Strip HTML tags
                plain_details = re.sub(r'<[^>]+>', '', ticket_details)
                # Escape any remaining HTML entities
                plain_details = html.escape(plain_details, quote=False)
                await callback.message.edit_text(
                    plain_details,
                    reply_markup=keyboard
                )
            
            # Send message history as .txt file
            from aiogram.types import BufferedInputFile
            
            # Create file content
            file_content = message_history.encode('utf-8')
            file_name = f"ticket_{ticket_id}_history.txt"
            
            # Create BufferedInputFile
            file = BufferedInputFile(
                file=file_content,
                filename=file_name
            )
            
            # Send file
            await callback.message.answer_document(
                document=file,
                caption=f"📎 История переписки по обращению #{ticket_id}"
            )
        
        logger.info(
            f"Displayed archived ticket {ticket_id} for client {user_id} "
            f"(history_length={len(message_history)}, sent_as_file={len(combined_text) > 4096})"
        )
        
    except Exception as e:
        logger.error(
            f"Error viewing client archived ticket: user={callback.from_user.id}, "
            f"ticket_id={callback_data.ticket_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при просмотре обращения.", show_alert=True)


@router.callback_query(ClientArchiveCallback.filter(F.action == "close"))
async def handle_client_archive_close(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """
    Close archive - remove keyboard.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Clear state
        await state.update_data(
            client_archive_filter=None,
            client_archive_page=None
        )
        
        # Edit message to remove keyboard
        await callback.message.edit_text(
            "📋 Архив обращений закрыт.",
            reply_markup=None
        )
        
        logger.info(f"Client {user_id} closed archive")
        
    except Exception as e:
        logger.error(f"Error closing client archive: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка.", show_alert=True)
