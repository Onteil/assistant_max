"""
Обработчики для смены номера телефона пользователя.

Смена номера телефона требует одобрения администратора и происходит через создание заявки.
"""

import logging
from datetime import datetime

from maxapi.context import MemoryContext
from maxapi.types import MessageCreated, MessageCallback
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.states import ProfileStates
from database.models import TicketType, ActionType
from services.user_service import get_user_by_max_id
from services.ticket_service import create_ticket
from services.validation_service import validate_phone_number
from services.i_tat_service import get_itat_client
from services.itat_retry_helper import call_itat_with_retry
from bots.max_bot.texts import (
    ERROR_GENERAL,
    ERROR_VALIDATION_PHONE,
    PROFILE_PHONE_CHANGE_SUBMITTED,
    PROFILE_PHONE_CHANGE_PROMPT
)

logger = logging.getLogger(__name__)


async def start_phone_change(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Start phone number change process.
    
    Shows prompt for new phone number and sets FSM state.
    
    Args:
        event: MessageCallback event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Starting phone change process: max_user_id={max_user_id}")
    
    try:
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            logger.error(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            return
        
        # Set FSM state
        await context.set_state(ProfileStates.changing_phone)
        
        # Create cancel keyboard
        from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
        keyboard = get_cancel_keyboard()
        
        # Send prompt
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=PROFILE_PHONE_CHANGE_PROMPT.format(current_phone=user.phone_number),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error starting phone change: max_user_id={max_user_id}, error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_phone_change(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process phone number change request.
    
    Validates new phone number and creates a ticket for admin approval.
    Phone change requires manual approval by administrator.
    
    maxapi Pattern Notes:
    - Registered with FSM state filter: ProfileStates.changing_phone
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    - Clears FSM state using context.clear() after completion
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    new_phone = event.message.body.text.strip()
    
    logger.info(f"Processing phone change: max_user_id={max_user_id}, new_phone={new_phone}")
    
    try:
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            logger.error(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Validate phone format
        is_valid, result = validate_phone(new_phone)
        
        if not is_valid:
            logger.warning(f"Invalid phone: phone={new_phone}, error={result}")
            from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
            keyboard = get_cancel_keyboard()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_VALIDATION_PHONE.format(error_details=result),
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        normalized_phone = result
        
        # Check if phone is the same
        if normalized_phone == user.phone_number:
            await context.clear()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Новый номер совпадает с текущим. Смена не требуется.",
                parse_mode="HTML"
            )
            return
        
        # Create phone change ticket
        ticket_data = {
            "ticket_type": TicketType.PHONE_CHANGE,
            "user_id": user.id,
            "description": f"Запрос на смену номера телефона с {user.phone_number} на {normalized_phone}",
            "old_phone": user.phone_number,
            "new_phone": normalized_phone
        }
        
        ticket = await create_ticket(session, ticket_data)
        
        logger.info(f"Phone change ticket created: ticket_id={ticket.id}, user_id={user.id}")
        
        # Log phone change request to audit
        from bots.max_bot.utils.audit_logger import log_phone_change_requested
        await log_phone_change_requested(
            user_id=user.id,
            max_user_id=max_user_id,
            old_phone=user.phone_number,
            new_phone=normalized_phone,
            ticket_id=f"TKT_{ticket.id}"
        )
        
        # Log ticket creation to I-TAT API
        try:
            from bots.max_bot.utils.itat_logging import log_ticket_creation_to_itat
            await log_ticket_creation_to_itat(session, ticket)
        except Exception as e:
            # Log error but don't fail ticket creation
            logger.error(
                f"Failed to log phone change ticket to I-TAT API: ticket_id={ticket.id}, error={e}",
                exc_info=True
            )
        
        # Clear FSM state
        await context.clear()
        
        # Send success message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=PROFILE_PHONE_CHANGE_SUBMITTED.format(
                old_phone=user.phone_number,
                new_phone=normalized_phone,
                ticket_id=ticket.id
            ),
            parse_mode="HTML"
        )
        
        # Show profile
        from bots.max_bot.handlers.user.profile import show_profile
        await show_profile(chat_id, user.id, session, messenger_adapter)
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error processing phone change: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error processing phone change: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def approve_phone_change(
    session: AsyncSession,
    ticket_id: int,
    staff_id: int,
    messenger_adapter: MAXMessengerAdapter
) -> bool:
    """
    Approve phone number change request.
    
    Updates user phone number in database and calls i-TAT API.
    
    Args:
        session: Database session
        ticket_id: Ticket ID for phone change request
        staff_id: Staff member ID who approved the change
        messenger_adapter: Messenger adapter for notifications
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from database.models import Ticket, User
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        # Get ticket with user
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.user))
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket or ticket.ticket_type != TicketType.PHONE_CHANGE:
            logger.error(f"Phone change ticket not found: ticket_id={ticket_id}")
            return False
        
        user = ticket.user
        old_phone = ticket.old_phone
        new_phone = ticket.new_phone
        
        if not old_phone or not new_phone:
            logger.error(f"Missing phone data in ticket: ticket_id={ticket_id}")
            return False
        
        # Call i-TAT API to update phone
        api_response = await call_itat_with_retry(
            session=session,
            operation="change_phone",
            payload=dict(
                messenger="max",
                user_id=user.max_user_id,
                old_phone=old_phone,
                new_phone=new_phone,
                staff_id=staff_id,
            ),
            user_id=user.id,
        )
        if api_response is not None:
            logger.info(f"i-TAT API phone change successful: {api_response}")
        else:
            logger.warning(
                f"change_phone queued for retry: user_id={user.id}, "
                f"old={old_phone}, new={new_phone}"
            )
        
        # Update user phone number
        user.phone_number = new_phone
        
        # Update ticket status
        from database.models import TicketStatus
        ticket.ticket_status = TicketStatus.CLOSED
        ticket.resolution_comment = f"Номер телефона изменен с {old_phone} на {new_phone}"
        
        await session.commit()
        
        # Send notification to user
        if user.max_user_id:
            try:
                from database.models import MAX_Messenger_Data
                
                stmt = select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == user.id)
                result = await session.execute(stmt)
                max_data = result.scalar_one_or_none()
                
                if max_data:
                    await messenger_adapter.send_message(
                        chat_id=max_data.max_chat_id,
                        text=(
                            f"✅ <b>Номер телефона изменен</b>\n\n"
                            f"Ваш номер телефона успешно изменен с <code>{old_phone}</code> на <code>{new_phone}</code>.\n\n"
                            f"Заявка #{ticket.id} закрыта."
                        ),
                        parse_mode="HTML"
                    )
                    logger.info(f"Sent phone change approval notification to user {user.id}")
            except Exception as send_error:
                logger.error(f"Failed to send phone change notification: {send_error}")
        
        logger.info(f"Phone change approved: ticket_id={ticket_id}, user_id={user.id}, old={old_phone}, new={new_phone}")
        return True
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error approving phone change: ticket_id={ticket_id}, error={e}", exc_info=True)
        return False


async def reject_phone_change(
    session: AsyncSession,
    ticket_id: int,
    staff_id: int,
    reason: str,
    messenger_adapter: MAXMessengerAdapter
) -> bool:
    """
    Reject phone number change request.
    
    Updates ticket status and notifies user.
    
    Args:
        session: Database session
        ticket_id: Ticket ID for phone change request
        staff_id: Staff member ID who rejected the change
        reason: Reason for rejection
        messenger_adapter: Messenger adapter for notifications
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from database.models import Ticket, TicketStatus
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        # Get ticket with user
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.user))
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket or ticket.ticket_type != TicketType.PHONE_CHANGE:
            logger.error(f"Phone change ticket not found: ticket_id={ticket_id}")
            return False
        
        user = ticket.user
        old_phone = ticket.old_phone
        new_phone = ticket.new_phone
        
        # Update ticket status
        ticket.ticket_status = TicketStatus.CLOSED
        ticket.resolution_comment = f"Запрос на смену номера отклонен. Причина: {reason}"
        
        await session.commit()
        
        # Send notification to user
        if user.max_user_id:
            try:
                from database.models import MAX_Messenger_Data
                
                stmt = select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == user.id)
                result = await session.execute(stmt)
                max_data = result.scalar_one_or_none()
                
                if max_data:
                    await messenger_adapter.send_message(
                        chat_id=max_data.max_chat_id,
                        text=(
                            f"❌ <b>Запрос отклонен</b>\n\n"
                            f"Ваш запрос на смену номера телефона с <code>{old_phone}</code> на <code>{new_phone}</code> отклонен.\n\n"
                            f"<b>Причина:</b> {reason}\n\n"
                            f"Заявка #{ticket.id} закрыта."
                        ),
                        parse_mode="HTML"
                    )
                    logger.info(f"Sent phone change rejection notification to user {user.id}")
            except Exception as send_error:
                logger.error(f"Failed to send phone change rejection notification: {send_error}")
        
        logger.info(f"Phone change rejected: ticket_id={ticket_id}, user_id={user.id}, reason={reason}")
        return True
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error rejecting phone change: ticket_id={ticket_id}, error={e}", exc_info=True)
        return False