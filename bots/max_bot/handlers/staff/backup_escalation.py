"""
Backup Manager Escalation Handlers for MAX Bot

Handles backup manager escalation actions:
- Take over escalated tickets when notified as backup manager
- Update ticket status and cancel further escalations
- Log actions and notify relevant parties

Requirements: Backup Manager Escalation Flow
"""

import logging
from datetime import datetime, timezone

from maxapi.types import MessageCallback
from maxapi.context import MemoryContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import BackupEscalationPayload
from database.models import (
    Action_Log,
    ActionType,
    Staff_Member,
    Ticket,
    TicketStatus,
)
from services.ticket_service import take_ticket_into_work

logger = logging.getLogger(__name__)


async def handle_backup_escalation_take_over(
    event: MessageCallback,
    payload: BackupEscalationPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle backup manager taking over an escalated ticket.
    
    When a backup manager clicks "Take Over" button:
    1. Verify they are the assigned backup manager
    2. Change ticket status to IN_PROGRESS
    3. Cancel scheduled escalation tasks
    4. Delete the escalation notification message
    5. Send confirmation message
    6. Log the action
    
    Uses replace_message pattern (delete old + send new).
    
    Args:
        event: MessageCallback event
        payload: BackupEscalationPayload with ticket_id and escalation_level
        context: FSM context
        session: Database session
        messenger_adapter: MAX messenger adapter
    
    Requirements: Backup Manager Escalation Flow
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        ticket_id = payload.ticket_id
        escalation_level = payload.escalation_level
        
        # Get staff member
        stmt = select(Staff_Member).where(Staff_Member.max_user_id == max_user_id)
        result = await session.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if not staff:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка: Ваш профиль не найден в системе.",
                parse_mode="HTML"
            )
            return
        
        # Get ticket with relationships
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.assigned_staff),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.organization)
            )
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Verify ticket is still NEW
        if ticket.ticket_status != TicketStatus.NEW:
            # Delete old message
            if message_id:
                try:
                    await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception as e:
                    logger.warning(f"Failed to delete old message: {e}")
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"ℹ️ Заявка #{ticket_id} уже взята в работу другим сотрудником.",
                parse_mode="HTML"
            )
            return
        
        # For INVOICE/RENEWAL tickets: verify staff is assigned to this ticket
        # For TECHNICAL_SUPPORT/CONSULTATION tickets: allow any backup manager to take it
        from database.models import TicketType
        if ticket.ticket_type in (TicketType.INVOICE, TicketType.RENEWAL):
            if ticket.assigned_staff_id != staff.id:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=f"❌ Вы не назначены на эту заявку. Текущий исполнитель: {ticket.assigned_staff.full_name if ticket.assigned_staff else 'Не назначен'}",
                    parse_mode="HTML"
                )
                return
        
        # For TECHNICAL_SUPPORT/CONSULTATION: Set assigned_staff_id to backup manager taking the ticket
        if ticket.ticket_type in (TicketType.TECHNICAL_SUPPORT, TicketType.CONSULTATION):
            ticket.assigned_staff_id = staff.id
        
        # Take ticket into work (changes status to IN_PROGRESS and cancels escalation)
        try:
            await take_ticket_into_work(
                session=session,
                ticket_id=ticket_id,
                employee_id=staff.max_user_id,
                messenger="max"
            )
            
            logger.info(
                f"Backup manager {staff.id} took over ticket {ticket_id} "
                f"(ticket_type={ticket.ticket_type.value}, escalation_level={escalation_level})"
            )
        
        except Exception as e:
            logger.error(f"Failed to take ticket into work: {e}", exc_info=True)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка при взятии заявки в работу: {str(e)}",
                parse_mode="HTML"
            )
            return
        
        # Delete old escalation notification message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Show detailed ticket card with action buttons (like in manager menu)
        from bots.max_bot.handlers.staff.manager import (
            format_ticket_card_detailed,
            get_ticket_action_keyboard
        )
        
        # Check if focus mode is enabled
        current_state = await context.get_state()
        from bots.max_bot.states import EmployeeStates
        is_focus_enabled = (current_state == EmployeeStates.in_focus)
        
        # Format detailed ticket card
        ticket_card = format_ticket_card_detailed(ticket)
        
        # Build action keyboard based on ticket status and focus state
        keyboard = get_ticket_action_keyboard(ticket, is_focus_enabled)
        
        # Send ticket details with action buttons
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ticket_card,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        # Log action
        action_log = Action_Log(
            ticket_id=ticket_id,
            staff_id=staff.id,
            action_type=ActionType.TICKET_TAKEN,
            action_details={
                "escalation_level": escalation_level,
                "backup_type": f"backup_manager_{escalation_level}",
                "action": "taken_by_backup_manager"
            }
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Backup manager {staff.id} successfully took over ticket {ticket_id} "
            f"at escalation level {escalation_level}"
        )
    
    except Exception as e:
        logger.error(
            f"Error handling backup escalation take over: ticket_id={payload.ticket_id}, "
            f"error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при обработке запроса.",
            parse_mode="HTML"
        )
