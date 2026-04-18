"""
Обработчики для управления запросами на смену номера телефона.

Административные функции для одобрения и отклонения запросов на смену номера.
"""

import logging
from datetime import datetime

from maxapi.types import MessageCallback, MessageCreated
from maxapi.context import MemoryContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import PhoneChangePayload, AdminMenuPayload, OperationsMenuPayload
from bots.max_bot.states import OperationsStates
from database.models import Ticket, TicketType, TicketStatus, Staff_Member, ActionType, Action_Log
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
            back_keyboard = Keyboard(
                buttons=[[KeyboardButton(
                    text="◀️ Назад",
                    payload=AdminMenuPayload(action="operations").pack()
                )]],
                inline=True
            )
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="📱 <b>Запросы на смену номера</b>\n\nНет активных запросов на смену номера телефона.",
                keyboard=back_keyboard,
                parse_mode="HTML"
            )
            return
        
        # Build message text
        text = "📱 <b>Запросы на смену номера телефона</b>\n\n"
        
        buttons = []
        for ticket in tickets[:10]:  # Limit to 10 tickets
            user = ticket.user
            user_name = f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else "Не указано"
            old_phone = ticket.old_phone or "—"
            new_phone = ticket.new_phone or "—"

            text += (
                f"🎫 <b>Заявка #{ticket.id}</b>\n"
                f"👤 {user_name}\n"
                f"📞 {old_phone} → {new_phone}\n"
                f"📅 {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )
            
            # Add button for this ticket
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
                payload=AdminMenuPayload(action="operations").pack()
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

        # Load target account data separately (avoid lazy load issues)
        target_user = None
        target_max_user_id = None
        if ticket.new_phone:
            from services.user_service import get_user_by_phone
            from database.models import MAX_Messenger_Data
            target_user = await get_user_by_phone(session, ticket.new_phone)
            if target_user:
                target_max_data = (
                    await session.execute(
                        select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == target_user.id)
                    )
                ).scalar_one_or_none()
                target_max_user_id = target_max_data.max_user_id if target_max_data else None

        def _fmt_name(u) -> str:
            return (
                u.full_name
                or f"{u.last_name or ''} {u.first_name or ''} {u.middle_name or ''}".strip()
                or "Не указано"
            )

        # Build message text
        status_labels = {
            "new": "🆕 Новая",
            "in_progress": "🔄 В работе",
            "closed": "✅ Закрыта",
            "cancelled": "❌ Отменена",
        }
        status_label = status_labels.get(ticket.ticket_status.value, ticket.ticket_status.value)

        text = (
            f"📱 <b>Заявка на смену номера #{ticket.id}</b>\n\n"
            f"<b>Заявитель (старый номер)</b>\n"
            f"👤 <b>ФИО:</b> {_fmt_name(user)}\n"
            f"📞 <b>Текущий номер:</b> <code>{ticket.old_phone or '—'}</code>\n"
            f"📧 <b>Email:</b> {user.email or 'Не указан'}\n"
            f"🆔 <b>MAX ID:</b> <code>{user.max_user_id or '—'}</code>\n"
            f"🪪 <b>ID в системе:</b> <code>{user.id}</code>\n\n"
        )

        if target_user:
            text += (
                f"<b>Целевой аккаунт (новый номер)</b>\n"
                f"👤 <b>ФИО:</b> {_fmt_name(target_user)}\n"
                f"📞 <b>Новый номер:</b> <code>{ticket.new_phone or '—'}</code>\n"
                f"📧 <b>Email:</b> {target_user.email or 'Не указан'}\n"
                f"🆔 <b>MAX ID:</b> <code>{target_max_user_id or '—'}</code>\n"
                f"🪪 <b>ID в системе:</b> <code>{target_user.id}</code>\n\n"
            )
        else:
            text += (
                f"<b>━━━ Целевой аккаунт (новый номер) ━━━</b>\n"
                f"📞 <b>Новый номер:</b> <code>{ticket.new_phone or '—'}</code>\n"
                f"⚠️ Аккаунт не найден (возможно удалён)\n\n"
            )

        text += (
            f"<b>━━━ Заявка ━━━</b>\n"
            f"📅 <b>Дата запроса:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"📋 <b>Статус:</b> {status_label}\n"
        )

        if ticket.resolution_comment:
            text += f"💬 <b>Решение:</b> {ticket.resolution_comment}\n"
        
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
        result = await approve_phone_change(
            session=session,
            ticket_id=payload.ticket_id,
            staff_id=admin.id,
            messenger_adapter=messenger_adapter
        )
        
        if result == "already_closed":
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="⚠️ Эта заявка уже была обработана ранее.",
                parse_mode="HTML"
            )
            return
        
        if result == "target_not_found":
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "❌ <b>Ошибка одобрения</b>\n\n"
                    "Целевой аккаунт (новый номер) не найден в системе. "
                    "Возможно, он был удалён после подачи заявки.\n\n"
                    "Заявка не может быть одобрена."
                ),
                parse_mode="HTML"
            )
            return
        
        if result:
            # Log action locally
            action_log = Action_Log(
                action_type=ActionType.PHONE_CHANGE_APPROVED,
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
            await session.commit()
            
            # Show success message
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="◀️ К списку запросов",
                            payload=OperationsMenuPayload(action="phone_changes").pack()
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
    Start phone change rejection flow — ask admin for a reason.

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

        # Store ticket_id in FSM and ask for reason
        await context.update_data(reject_ticket_id=payload.ticket_id)
        await context.set_state(OperationsStates.entering_phone_change_reject_reason)

        keyboard = Keyboard(
            buttons=[[KeyboardButton(
                text="◀️ Назад к заявке",
                payload=PhoneChangePayload(action="cancel_reject", ticket_id=payload.ticket_id).pack()
            )]],
            inline=True
        )

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"❌ <b>Отклонение заявки #{payload.ticket_id}</b>\n\n"
                "Введите причину отклонения запроса на смену номера:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Error starting phone change rejection: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_phone_change_reject_reason(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process rejection reason text input from admin.

    maxapi Pattern Notes:
    - Registered with FSM state filter: OperationsStates.entering_phone_change_reject_reason
    - Uses event.message.sender.user_id for user identification
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    reason = event.message.body.text.strip()

    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await context.clear()
            return

        data = await context.get_data()
        ticket_id = data.get("reject_ticket_id")
        if not ticket_id:
            await context.clear()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка: заявка не найдена. Попробуйте снова.",
                parse_mode="HTML"
            )
            return

        await context.clear()

        result = await reject_phone_change(
            session=session,
            ticket_id=ticket_id,
            staff_id=admin.id,
            reason=reason,
            messenger_adapter=messenger_adapter
        )

        if result == "already_closed":
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="⚠️ Эта заявка уже была обработана ранее.",
                parse_mode="HTML"
            )
            return

        if result:
            # Log action locally
            action_log = Action_Log(
                action_type=ActionType.PHONE_CHANGE_REJECTED,
                staff_id=admin.id,
                ticket_id=ticket_id,
                action_details={
                    "action": "phone_change_rejected",
                    "reason": reason,
                    "admin_name": admin.full_name,
                    "admin_max_id": max_user_id
                },
                action_timestamp=datetime.utcnow()
            )
            session.add(action_log)
            await session.commit()

            keyboard = Keyboard(
                buttons=[[KeyboardButton(
                    text="◀️ К списку запросов",
                    payload=OperationsMenuPayload(action="phone_changes").pack()
                )]],
                inline=True
            )

            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Запрос отклонён</b>\n\nЗаявка #{ticket_id} отклонена.\nПользователь уведомлён об отклонении.",
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
        logger.error(f"Error processing phone change rejection reason: {e}", exc_info=True)
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при отклонении запроса.",
            parse_mode="HTML"
        )