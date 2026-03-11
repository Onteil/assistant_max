"""
Client Active Tickets Handlers

Handles client's active tickets list display, pagination, and ticket selection.
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bots.tg_bot.callback_datas import ClientTicketListCallback
from database.models import Ticket, TicketStatus
from services.client_service import (
    format_client_active_tickets_header,
    get_client_active_tickets,
    get_client_active_tickets_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name="client_active_tickets")


@router.callback_query(ClientTicketListCallback.filter(F.action == "select_ticket"))
async def handle_select_ticket_callback(
    callback: CallbackQuery,
    callback_data: ClientTicketListCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle ticket selection from active tickets list.
    
    Sets the selected ticket as active and enters communication mode.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        if not ticket_id:
            await callback.answer("❌ Ошибка: ID заявки не указан", show_alert=True)
            return
        
        # Get ticket from database with eager loading
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys),
            selectinload(Ticket.assigned_staff)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            logger.warning(f"Ticket {ticket_id} not found for client {user_id}")
            return
        
        # Verify ticket belongs to this user
        if ticket.user.tg_user_id != user_id:
            await callback.answer("❌ У вас нет доступа к этой заявке", show_alert=True)
            logger.warning(
                f"Client {user_id} attempted to access ticket {ticket_id} "
                f"belonging to user {ticket.user.tg_user_id}"
            )
            return
        
        # Verify ticket is still active
        if ticket.ticket_status not in [
            TicketStatus.NEW,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_CLIENT
        ]:
            await callback.answer("❌ Заявка уже закрыта", show_alert=True)
            logger.info(f"Ticket {ticket_id} is no longer active (status: {ticket.ticket_status})")
            return
        
        # Set state for communication with manager - use None state to allow message routing
        await state.clear()
        await state.update_data(active_ticket_id=ticket_id)
        
        # Show ticket information using client-specific formatting
        try:
            from services.client_service import format_ticket_card_for_client
            
            ticket_card = await format_ticket_card_for_client(ticket, session)
            await callback.message.answer(
                f"{ticket_card}\n\n"
                f"💬 Вы можете продолжить общение с менеджером.\n"
                f"Отправьте текст, фото или документ."
            )
            
            # Delete the ticket list message
            try:
                await callback.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete ticket list message: {e}")
            
            logger.info(f"Client {user_id} selected ticket {ticket_id}")
            
        except Exception as e:
            logger.error(f"Error formatting ticket card: {e}", exc_info=True)
            await callback.message.answer(
                f"✅ Вы вернулись к заявке #{ticket_id}\n\n"
                f"💬 Вы можете продолжить общение с менеджером.\n"
                f"Отправьте текст, фото или документ."
            )
        
    except Exception as e:
        logger.error(
            f"Error handling select ticket callback: ticket_id={callback_data.ticket_id}, "
            f"user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)


@router.callback_query(ClientTicketListCallback.filter(F.action == "page"))
async def handle_tickets_pagination_callback(
    callback: CallbackQuery,
    callback_data: ClientTicketListCallback,
    session: AsyncSession
) -> None:
    """
    Handle pagination for active tickets list.
    
    Updates the message with tickets from the requested page.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        page = callback_data.page
        
        # Get all active tickets for this client
        tickets = await get_client_active_tickets(session, user_id)
        
        if not tickets:
            await callback.message.edit_text("❌ У вас нет активных обращений")
            logger.info(f"Client {user_id} has no active tickets")
            return
        
        # Generate header text
        header_text = await format_client_active_tickets_header(
            tickets_count=len(tickets),
            current_page=page
        )
        
        # Generate inline keyboard with pagination
        keyboard = await get_client_active_tickets_keyboard(
            tickets=tickets,
            current_page=page
        )
        
        # Update message with new page
        await callback.message.edit_text(
            header_text,
            reply_markup=keyboard
        )
        
        logger.info(f"Client {user_id} navigated to page {page + 1} of active tickets")
        
    except Exception as e:
        logger.error(
            f"Error handling tickets pagination: page={callback_data.page}, "
            f"user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
