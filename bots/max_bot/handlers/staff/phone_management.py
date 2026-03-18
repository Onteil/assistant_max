"""
Обработчики для управления запросами на смену номера телефона.

Административные функции для одобрения и отклонения запросов на смену номера.
"""

import logging
from datetime import datetime

from maxapi.types import MessageCallback
from maxapi.context import MemoryContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from database.models import Ticket, TicketType, TicketStatus, Staff_Member, ActionType, Action_Log
from services.i_tat_service import get_itat_client
from bots.max_bot.handlers.user.phone_change import approve_phone_change, reject_phone_change

logger = logging.getLogger(__name__)


async def is_admin(session: AsyncSession, max_user_id: int) -> Staff_Member | None:
    """
    Check if user is administrator.
    
    Args:
        session: Database session
        max_user_id: MAX user ID to check
    
    Returns:
        Staff_Member if user is admin, None otherwise
    """
    stmt = select(Staff_Member).where(Staff_Member.max_user_id == max_user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def handle_phone_change_list(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show list of pending phone change requests.
    
    Args:
        event: MessageCallback event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой функции.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get pending phone change requests
        stmt = (
            select(Ticket)
            .where(
                Ticket.ticket_type == TicketType.PHONE_CHANGE,
                Ticket.ticket_status.in_([TicketStatus.NEW, TicketStatus.IN_PROGRESS])
            )
            .options(selectinload(Ticket.user))
            .order_by(Ticket.created_at.desc())
        )
        result = await session.execute(stmt)
        tickets = result.scalars().all()
        
        if not tickets:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="📱 <b>Запросы на смену номера</b>\n\nНет активных запросов на смену номера телефона.",
                parse_mode="HTML"
            )
            return
        
        # Build message text
        text = "📱 <b>Запросы на смену номера телефона</b>\n\n"
        
        buttons = []
        for ticket in tickets[:10]:  # Limit to 10 tickets
            user = ticket.user
            user_name = f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else "Не указано"
            
            text += (
                f"🎫 <b>Заявка #{ticket.id}</b>\n"
                f"👤 {user_name}\n"
                f"📞 {ticket.old_phone} → {ticket.new_phone}\n"
                f"📅 {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )
            
            # Add button for this ticket
            from bots.max_bot.payloads import PhoneChangePayload
            buttons.append([
                KeyboardButton(
                    text=f"📱 Заявка #{ticket.id}",
                    payload=PhoneChangePayload(action="view", ticket_id=ticket.id).pack()
                )
            ])
        
        # Add back button
        buttons.append([
            KeyboardButton(
                text="◀️ Назад",
                payload=PhoneChangePayload(action="back").pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error showing phone change list: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке списка запросов.",
            parse_mode="HTML"
        )


async def handle_phone_change_view(
    event: MessageCallback,
    payload: any,  # PhoneChangePayload
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show detailed view of phone change request.
    
    Args:
        event: MessageCallback event from maxapi
        payload: PhoneChangePayload with ticket_id
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой функции.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get ticket
        stmt = (
            select(Ticket)
            .where(Ticket.id == payload.ticket_id)
            .options(selectinload(Ticket.user))
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket or ticket.ticket_type != TicketType.PHONE_CHANGE:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return
        
        user = ticket.user
        user_name = f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else "Не указано"
        
        # Build message text
        text = (
            f"📱 <b>Заявка на смену номера #{ticket.id}</b>\n\n"
            f"👤 <b>Пользователь:</b> {user_name}\n"
            f"📧 <b>Email:</b> {user.email or 'Не указан'}\n"
            f"📞 <b>Текущий номер:</b> <code>{ticket.old_phone}</code>\n"
            f"📞 <b>Новый номер:</b> <code>{ticket.new_phone}</code>\n"
            f"📅 <b>Дата запроса:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"📋 <b>Статус:</b> {ticket.ticket_status.value}\n\n"
        )
        
        if ticket.description:
            text += f"💬 <b>Комментарий:</b> {ticket.description}\n\n"
        
        # Build keyboard
        buttons = []
        
        if ticket.ticket_status in [TicketStatus.NEW, TicketStatus.IN_PROGRESS]:
            buttons.extend([
                [
                    KeyboardButton(
                        text="✅ Одобрить",
                        payload=PhoneChangePayload(action="approve", ticket_id=ticket.id).pack()
                    ),
                    KeyboardButton(
                        text="❌ Отклонить",
                        payload=PhoneChangePayload(action="reject", ticket_id=ticket.id).pack()
                    )
                ]
            ])
        
        buttons.append([
            KeyboardButton(
                text="◀️ К списку",
                payload=PhoneChangePayload(action="list").pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error showing phone change view: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке заявки.",
            parse_mode="HTML"
        )


async def handle_phone_change_approve(
    event: MessageCallback,
    payload: any,  # PhoneChangePayload
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Approve phone change request.
    
    Args:
        event: MessageCallback event from maxapi
        payload: PhoneChangePayload with ticket_id
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой функции.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Approve phone change
        success = await approve_phone_change(
            session=session,
            ticket_id=payload.ticket_id,
            staff_id=admin.id,
            messenger_adapter=messenger_adapter
        )
        
        if success:
            # Log action locally
            action_log = Action_Log(
                action_type=ActionType.PHONE_CHANGE_APPROVED,
                user_id=None,  # Will be set by approve_phone_change
                staff_id=admin.id,
                ticket_id=payload.ticket_id,
                action_details={
                    "action": "phone_change_approved",
                    "admin_name": admin.full_name,
                    "admin_max_id": max_user_id
                },
                action_timestamp=datetime.utcnow()
            )
            session.add(action_log)
            
            # Log action to i-TAT API
            try:
                from services.i_tat_service import get_itat_client
                itat_client = get_itat_client()
                await itat_client.audit_log(
                    messenger="max",
                    action_type="phone_change_approved",
                    action_timestamp=datetime.utcnow().isoformat(),
                    staff_id=admin.id,
                    ticket_id=payload.ticket_id,
                    action_details={
                        "action": "phone_change_approved",
                        "admin_name": admin.full_name,
                        "admin_max_id": max_user_id
                    }
                )
                logger.info(f"i-TAT API audit log successful for phone change approval")
            except Exception as audit_error:
                logger.error(f"i-TAT API audit log error: {audit_error}")
                # Continue even if audit logging fails
            
            await session.commit()
            
            # Show success message
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="◀️ К списку запросов",
                            payload=PhoneChangePayload(action="list").pack()
                        )
                    ]
                ],
                inline=True
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"✅ <b>Запрос одобрен</b>\n\nЗаявка #{payload.ticket_id} на смену номера телефона одобрена.\nПользователь уведомлен о смене номера.",
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Произошла ошибка при одобрении запроса.",
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"Error approving phone change: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при одобрении запроса.",
            parse_mode="HTML"
        )


async def handle_phone_change_reject(
    event: MessageCallback,
    payload: any,  # PhoneChangePayload
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Reject phone change request.
    
    Args:
        event: MessageCallback event from maxapi
        payload: PhoneChangePayload with ticket_id
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой функции.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # For now, reject with a default reason
        # In a full implementation, you might want to ask for a reason
        reason = "Запрос отклонен администратором"
        
        # Reject phone change
        success = await reject_phone_change(
            session=session,
            ticket_id=payload.ticket_id,
            staff_id=admin.id,
            reason=reason,
            messenger_adapter=messenger_adapter
        )
        
        if success:
            # Log action locally
            action_log = Action_Log(
                action_type=ActionType.PHONE_CHANGE_REJECTED,
                user_id=None,  # Will be set by reject_phone_change
                staff_id=admin.id,
                ticket_id=payload.ticket_id,
                action_details={
                    "action": "phone_change_rejected",
                    "reason": reason,
                    "admin_name": admin.full_name,
                    "admin_max_id": max_user_id
                },
                action_timestamp=datetime.utcnow()
            )
            session.add(action_log)
            
            # Log action to i-TAT API
            try:
                from services.i_tat_service import get_itat_client
                itat_client = get_itat_client()
                await itat_client.audit_log(
                    messenger="max",
                    action_type="phone_change_rejected",
                    action_timestamp=datetime.utcnow().isoformat(),
                    staff_id=admin.id,
                    ticket_id=payload.ticket_id,
                    action_details={
                        "action": "phone_change_rejected",
                        "reason": reason,
                        "admin_name": admin.full_name,
                        "admin_max_id": max_user_id
                    }
                )
                logger.info(f"i-TAT API audit log successful for phone change rejection")
            except Exception as audit_error:
                logger.error(f"i-TAT API audit log error: {audit_error}")
                # Continue even if audit logging fails
            
            await session.commit()
            
            # Show success message
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="◀️ К списку запросов",
                            payload=PhoneChangePayload(action="list").pack()
                        )
                    ]
                ],
                inline=True
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Запрос отклонен</b>\n\nЗаявка #{payload.ticket_id} на смену номера телефона отклонена.\nПользователь уведомлен об отклонении.",
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Произошла ошибка при отклонении запроса.",
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"Error rejecting phone change: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при отклонении запроса.",
            parse_mode="HTML"
        )