"""
Admin Panel - Escalation Handlers for MAX Bot

Handles escalation management in the administrative panel:
- List active escalations with pagination
- View escalation card with ticket details
- Reassign escalated tickets to staff
- Take over escalated tickets
- Show staff contact information

Migrated from Telegram bot to MAX messenger.
Uses replace_message pattern for all callback handlers.

Requirements: 3.1, 3.2, 3.3, 3.4
"""

import logging
from datetime import datetime

from maxapi.types import MessageCallback
from maxapi.context import MemoryContext
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    OperationsMenuPayload,
    EscalationPayload,
    AdminMenuPayload,
    ManagerViewTicketPayload,
)
from database.models import (
    Action_Log,
    ActionType,
    Escalation,
    ResolutionAction,
    Staff_Member,
    StaffRole,
    Ticket,
    TicketStatus,
    TicketType,
)
from services.escalation_service import get_active_escalations, resolve_escalation

logger = logging.getLogger(__name__)


# ========== Helper Functions ==========


async def is_admin(session: AsyncSession, max_user_id: int) -> Staff_Member | None:
    """
    Check if user is an administrator and return their record.
    
    Args:
        session: Database session
        max_user_id: MAX user ID
    
    Returns:
        Staff_Member object if user is admin, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            and_(
                Staff_Member.max_user_id == max_user_id,
                Staff_Member.is_active == True,
                Staff_Member.staff_role == StaffRole.ADMINISTRATOR
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking admin status for user {max_user_id}: {e}", exc_info=True)
        return None


def format_time_elapsed(escalation: Escalation) -> str:
    """Format time elapsed since escalation was created."""
    if not escalation.created_at:
        return "Неизвестно"
    
    elapsed = datetime.utcnow() - escalation.created_at
    hours = int(elapsed.total_seconds() // 3600)
    minutes = int((elapsed.total_seconds() % 3600) // 60)
    
    if hours > 0:
        return f"{hours}ч {minutes}м"
    else:
        return f"{minutes}м"


# ========== Escalation List ==========


async def handle_escalations_list(
    event: MessageCallback,
    payload: OperationsMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    page: int = 0
) -> None:
    """
    Handle "Escalations" menu button - show list of active escalations.
    
    Displays all active (unresolved) escalations with pagination.
    Uses replace_message pattern.
    
    Requirements: 3.1, 3.2
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
        
        # Get active escalations
        escalations = await get_active_escalations(session)
        
        if not escalations:
            # No escalations - show message with back button
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="◀️ Назад",
                            payload=AdminMenuPayload(action="operations").pack()
                        )
                    ]
                ],
                inline=True
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="✅ <b>Эскалации</b>\n\nНет активных эскалаций.",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        # Pagination
        page_size = 5
        total_pages = (len(escalations) + page_size - 1) // page_size
        page = max(0, min(page, total_pages - 1))
        
        start_idx = page * page_size
        end_idx = start_idx + page_size
        page_escalations = escalations[start_idx:end_idx]
        
        # Build escalation list text
        lines = [
            f"⚠️ <b>Активные эскалации</b> (стр. {page + 1}/{total_pages})\n",
            f"Всего: {len(escalations)}\n"
        ]
        
        ticket_type_names = {
            TicketType.INVOICE: "💰 Счёт",
            TicketType.TECHNICAL_SUPPORT: "🛠 ТП",
            TicketType.CONSULTATION: "💬 Консультация",
            TicketType.RENEWAL: "🔄 Продление"
        }
        
        for esc in page_escalations:
            ticket = esc.ticket
            ticket_type = ticket_type_names.get(ticket.ticket_type, str(ticket.ticket_type)) if ticket else "Неизвестно"
            
            # Format date and time (day.month HH:MM)
            created_time = ""
            if esc.created_at:
                created_time = esc.created_at.strftime("%d.%m %H:%M")
            
            lines.append(
                f"\n🔸 <b>#{ticket.id if ticket else 'N/A'}</b> {ticket_type} ({created_time})"
            )
        
        list_text = "\n".join(lines)
        
        # Build keyboard with escalation buttons and pagination
        buttons = []
        
        # Escalation buttons
        for esc in page_escalations:
            ticket = esc.ticket
            ticket_type = ticket_type_names.get(ticket.ticket_type, str(ticket.ticket_type)) if ticket else "?"
            created_time = esc.created_at.strftime("%d.%m %H:%M") if esc.created_at else ""
            
            buttons.append([
                KeyboardButton(
                    text=f"#{ticket.id if ticket else 'N/A'} {ticket_type} ({created_time})",
                    payload=EscalationPayload(action="view", escalation_id=esc.id).pack()
                )
            ])
        
        # Pagination row
        if total_pages > 1:
            nav_row = []
            if page > 0:
                nav_row.append(
                    KeyboardButton(
                        text="⬅️ Назад",
                        payload=EscalationPayload(action="list", page=page - 1).pack()
                    )
                )
            if page < total_pages - 1:
                nav_row.append(
                    KeyboardButton(
                        text="Вперед ➡️",
                        payload=EscalationPayload(action="list", page=page + 1).pack()
                    )
                )
            if nav_row:
                buttons.append(nav_row)
        
        # Back button
        buttons.append([
            KeyboardButton(
                text="◀️ В меню операций",
                payload=AdminMenuPayload(action="operations").pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=list_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} viewed escalations list, page {page}")
        
    except Exception as e:
        logger.error(f"Error listing escalations: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке списка эскалаций.",
            parse_mode="HTML"
        )


# ========== Escalation View ==========


async def handle_escalation_view(
    event: MessageCallback,
    payload: EscalationPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display detailed view of a specific escalation with action buttons.
    
    Shows ticket details, client info, assigned staff, and action buttons.
    Uses replace_message pattern.
    
    Requirements: 3.3
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
        
        escalation_id = payload.escalation_id
        
        if not escalation_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Эскалация не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Get escalation with relationships
        stmt = (
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .options(
                selectinload(Escalation.ticket).selectinload(Ticket.user),
                selectinload(Escalation.ticket).selectinload(Ticket.assigned_staff),
                selectinload(Escalation.ticket).selectinload(Ticket.gs_keys),
                selectinload(Escalation.ticket).selectinload(Ticket.organization)
            )
        )
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        
        if not escalation:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Эскалация не найдена.",
                parse_mode="HTML"
            )
            return
        
        ticket = escalation.ticket
        
        # Format escalation details
        ticket_type_names = {
            TicketType.INVOICE: "💰 Счёт",
            TicketType.TECHNICAL_SUPPORT: "🛠 ТП",
            TicketType.CONSULTATION: "💬 Консультация",
            TicketType.RENEWAL: "🔄 Продление"
        }
        
        ticket_status_names = {
            TicketStatus.NEW: "Новая",
            TicketStatus.IN_PROGRESS: "В работе",
            TicketStatus.WAITING_CLIENT: "Ожидание клиента",
            TicketStatus.CLOSED: "Закрыта",
            TicketStatus.CANCELLED: "Отменена"
        }
        
        ticket_type = ticket_type_names.get(ticket.ticket_type, str(ticket.ticket_type))
        ticket_status = ticket_status_names.get(ticket.ticket_status, ticket.ticket_status.value) if ticket.ticket_status else "Неизвестно"
        user_name = ticket.user.full_name if ticket.user else "Неизвестно"
        user_phone = ticket.user.phone_number if ticket.user else "Не указано"
        assigned_to = ticket.assigned_staff.full_name if ticket.assigned_staff else "Не назначен"
        time_elapsed = format_time_elapsed(escalation)
        created_at = escalation.created_at.strftime("%d.%m.%Y %H:%M") if escalation.created_at else "Неизвестно"
        
        # Get GS_Keys
        gs_keys_text = "Не указаны"
        if ticket.gs_keys:
            gs_keys_text = ", ".join([key.key_number for key in ticket.gs_keys])
        
        # Get Organization
        org_text = "Не указана"
        if ticket.organization:
            org = ticket.organization
            if org.organization_name:
                org_text = f"{org.inn} ({org.organization_name})"
            else:
                org_text = org.inn
        
        # Build message text
        message_text = (
            f"⚠️ <b>Эскалация #{escalation.id}</b>\n\n"
            f"<b>Заявка:</b> #{ticket.id}\n"
            f"<b>Тип:</b> {ticket_type}\n"
            f"<b>Статус:</b> {ticket_status}\n\n"
            f"👤 <b>Клиент:</b>\n"
            f"   Имя: {user_name}\n"
            f"   Телефон: {user_phone}\n\n"
            f"🔑 <b>Ключи ГС:</b> {gs_keys_text}\n"
            f"🏢 <b>Организация:</b> {org_text}\n\n"
            f"👨‍💼 <b>Сотрудник:</b> {assigned_to}\n\n"
            f"⏱ <b>Время эскалации:</b> {time_elapsed}\n"
            f"📅 <b>Создана:</b> {created_at}\n\n"
            f"Выберите действие:"
        )
        
        # Build action buttons
        buttons = [
            [
                KeyboardButton(
                    text="🔄 Переназначить",
                    payload=EscalationPayload(action="reassign", escalation_id=escalation_id).pack()
                )
            ],
            [
                KeyboardButton(
                    text="✋ Взять в работу",
                    payload=EscalationPayload(action="take_over", escalation_id=escalation_id).pack()
                )
            ],
            # [
            #     KeyboardButton(
            #         text="📞 Контакты сотрудника",
            #         payload=EscalationPayload(action="contact", escalation_id=escalation_id).pack()
            #     )
            # ],
            [
                KeyboardButton(
                    text="◀️ К списку эскалаций",
                    payload=EscalationPayload(action="list").pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=message_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} viewed escalation {escalation_id}")
        
    except Exception as e:
        logger.error(f"Error displaying escalation view: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке эскалации.",
            parse_mode="HTML"
        )


# ========== Escalation Reassign ==========


async def handle_escalation_reassign(
    event: MessageCallback,
    payload: EscalationPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show staff selection for reassigning escalated ticket.
    
    Displays list of available staff members (managers and support) to reassign ticket to.
    Uses replace_message pattern.
    
    Requirements: 3.4
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
        
        escalation_id = payload.escalation_id
        
        if not escalation_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Эскалация не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Get escalation
        stmt = select(Escalation).where(Escalation.id == escalation_id)
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        
        if not escalation:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Эскалация не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Get available staff (managers and support)
        stmt = select(Staff_Member).where(
            and_(
                Staff_Member.is_active == True,
                Staff_Member.staff_role.in_([StaffRole.MANAGER, StaffRole.TECHNICAL_SUPPORT])
            )
        ).order_by(Staff_Member.full_name)
        
        result = await session.execute(stmt)
        staff_members = result.scalars().all()
        
        if not staff_members:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Нет доступных сотрудников для переназначения.",
                parse_mode="HTML"
            )
            return
        
        # Build staff selection message
        message_text = (
            f"🔄 <b>Переназначение эскалации #{escalation_id}</b>\n\n"
            f"Выберите сотрудника для переназначения заявки:"
        )
        
        # Build staff buttons
        buttons = []
        for staff in staff_members:
            role_emoji = "👨‍💼" if staff.staff_role == StaffRole.MANAGER else "🛠"
            buttons.append([
                KeyboardButton(
                    text=f"{role_emoji} {staff.full_name}",
                    payload=EscalationPayload(
                        action="reassign_confirm",
                        escalation_id=escalation_id,
                        staff_id=staff.id
                    ).pack()
                )
            ])
        
        # Back button
        buttons.append([
            KeyboardButton(
                text="◀️ Назад",
                payload=EscalationPayload(action="view", escalation_id=escalation_id).pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=message_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} initiated reassignment for escalation {escalation_id}")
        
    except Exception as e:
        logger.error(f"Error showing reassignment options: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке списка сотрудников.",
            parse_mode="HTML"
        )


# ========== Escalation Reassign Confirm ==========


async def handle_escalation_reassign_confirm(
    event: MessageCallback,
    payload: EscalationPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Confirm and execute ticket reassignment.
    
    Reassigns the escalated ticket to selected staff member and resolves escalation.
    Uses replace_message pattern.
    
    Requirements: 3.4
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
        
        escalation_id = payload.escalation_id
        staff_id = payload.staff_id
        
        if not escalation_id or not staff_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неверные параметры.",
                parse_mode="HTML"
            )
            return
        
        # Get escalation with ticket and all relationships
        stmt = (
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .options(
                selectinload(Escalation.ticket).selectinload(Ticket.user),
                selectinload(Escalation.ticket).selectinload(Ticket.gs_keys),
                selectinload(Escalation.ticket).selectinload(Ticket.organization)
            )
        )
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        
        if not escalation:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Эскалация не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Get staff member
        stmt = select(Staff_Member).where(Staff_Member.id == staff_id)
        result = await session.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if not staff:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Сотрудник не найден.",
                parse_mode="HTML"
            )
            return
        
        # Reassign ticket
        ticket = escalation.ticket
        old_staff_id = ticket.assigned_staff_id
        ticket.assigned_staff_id = staff_id
        
        # Resolve escalation
        await resolve_escalation(
            session=session,
            escalation_id=escalation_id,
            resolved_by_staff_id=admin.id,
            resolution_action=ResolutionAction.REASSIGNED
        )
        
        # Log action
        action_log = Action_Log(
            ticket_id=ticket.id,
            staff_id=admin.id,
            action_type=ActionType.TICKET_ASSIGNED,
            action_details={
                "escalation_id": escalation_id,
                "old_staff_id": old_staff_id,
                "new_staff_id": staff_id,
                "new_staff_name": staff.full_name,
                "action": "reassigned"
            }
        )
        session.add(action_log)
        
        await session.commit()
        
        # Send notification to assigned staff with full ticket details
        try:
            # Get staff_chat_id: first from Staff_Member, then fallback to MAX_Messenger_Data
            staff_chat_id = staff.max_chat_id
            
            # If not found in Staff_Member, try MAX_Messenger_Data table
            if not staff_chat_id and staff.max_user_id:
                from database.models import MAX_Messenger_Data
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == staff.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                staff_chat_id = result_chat.scalar_one_or_none()
                
                if staff_chat_id:
                    logger.info(
                        f"Found chat_id in MAX_Messenger_Data for staff {staff.id} "
                        f"(max_user_id={staff.max_user_id}): chat_id={staff_chat_id}"
                    )
            
            if staff_chat_id:
                # Build notification message with ticket details
                ticket_type_names = {
                    TicketType.INVOICE: "📄 Запрос счета",
                    TicketType.TECHNICAL_SUPPORT: "🔧 Техническая поддержка",
                    TicketType.CONSULTATION: "💬 Консультация",
                    TicketType.RENEWAL: "🔄 Продление подписки"
                }
                
                # Format created_at
                from utils.timezone_helpers import format_moscow_datetime
                created_at_str = format_moscow_datetime(ticket.created_at)
                
                # Build message
                notification_text = f"🔄 <b>Заявка #{ticket.id} переназначена на вас</b>\n\n"
                notification_text += f"📋 <b>Тип:</b> {ticket_type_names.get(ticket.ticket_type, ticket.ticket_type.value)}\n"
                
                # User information
                notification_text += f"👤 <b>От пользователя:</b> {ticket.user.full_name or ticket.user.phone_number}\n"
                notification_text += f"🆔 <b>ID пользователя:</b> <code>{ticket.user.max_user_id}</code>\n"
                
                # Organization(s)
                if ticket.organization_inn:
                    orgs = [org.strip() for org in ticket.organization_inn.split(',') if org.strip()]
                    if len(orgs) > 1:
                        notification_text += f"\n🏢 <b>Организации:</b>\n"
                        for idx, org in enumerate(orgs, 1):
                            notification_text += f"   {idx}. <code>{org}</code>\n"
                    else:
                        notification_text += f"\n🏢 <b>Организация:</b> <code>{ticket.organization_inn}</code>\n"
                
                # GS Keys
                try:
                    if ticket.gs_keys and len(ticket.gs_keys) > 0:
                        if len(ticket.gs_keys) > 1:
                            notification_text += f"🔑 <b>Ключи ГС:</b>\n"
                            for idx, key in enumerate(ticket.gs_keys, 1):
                                notification_text += f"   {idx}. <code>{key.key_number}</code>\n"
                        else:
                            notification_text += f"🔑 <b>Ключ ГС:</b> <code>{ticket.gs_keys[0].key_number}</code>\n"
                except Exception as e:
                    logger.warning(f"Failed to access gs_keys for ticket {ticket.id}: {e}")
                
                # Email if present
                try:
                    if hasattr(ticket.user, 'email') and ticket.user.email:
                        notification_text += f"📧 <b>Email:</b> {ticket.user.email}\n"
                except Exception as e:
                    logger.warning(f"Failed to access user email for ticket {ticket.id}: {e}")
                
                # Created timestamp
                notification_text += f"\n📅 <b>Дата создания:</b> {created_at_str}\n"
                
                # Delivery method
                if hasattr(ticket, 'delivery_method') and ticket.delivery_method:
                    delivery_method_names = {
                        "telegram": "💬 В чат",
                        "email": "📧 На Email",
                        "none": "❌ Не указан"
                    }
                    delivery_method_text = delivery_method_names.get(
                        ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method),
                        str(ticket.delivery_method)
                    )
                    notification_text += f"📦 <b>Способ получения:</b> {delivery_method_text}\n"
                    
                    # Add delivery email if method is email
                    if (ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method)) == "email":
                        if hasattr(ticket, 'delivery_email') and ticket.delivery_email:
                            notification_text += f"   └─ <b>Email для доставки:</b> {ticket.delivery_email}\n"
                
                # Description
                if ticket.description:
                    description = ticket.description[:200]
                    if len(ticket.description) > 200:
                        description += "..."
                    notification_text += f"\n📝 <b>Описание:</b>\n{description}\n"
                else:
                    notification_text += f"\n📝 <b>Описание:</b> <i>Без описания</i>\n"
                
                # Build keyboard with "К заявке" button
                keyboard = Keyboard(
                    buttons=[[
                        KeyboardButton(
                            text="📋 К заявке",
                            payload=ManagerViewTicketPayload(ticket_id=ticket.id).pack()
                        )
                    ]],
                    inline=True
                )
                
                await messenger_adapter.send_message(
                    chat_id=staff_chat_id,
                    text=notification_text,
                    keyboard=keyboard,
                    parse_mode="HTML"
                )
                
                logger.info(
                    f"Notification sent to staff {staff.id} ({staff.full_name}) "
                    f"about reassigned ticket {ticket.id}"
                )
            else:
                logger.warning(
                    f"Cannot send notification to staff {staff.id} ({staff.full_name}): "
                    f"max_chat_id not found in Staff_Member or MAX_Messenger_Data tables "
                    f"(max_user_id={staff.max_user_id})"
                )
        except Exception as e:
            logger.error(
                f"Failed to send notification to staff {staff.id}: {e}",
                exc_info=True
            )
        
        logger.info(
            f"Administrator {max_user_id} reassigned escalation {escalation_id} "
            f"to staff {staff_id}"
        )

        # Return directly to escalation list
        await handle_escalations_list(
            event, OperationsMenuPayload(action="escalations"), context, session, messenger_adapter
        )
        
    except Exception as e:
        logger.error(f"Error confirming reassignment: {e}", exc_info=True)
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при переназначении заявки.",
            parse_mode="HTML"
        )


# ========== Escalation Take Over ==========


async def handle_escalation_take_over(
    event: MessageCallback,
    payload: EscalationPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Administrator takes over the escalated ticket.
    
    Assigns the ticket to the administrator and resolves escalation.
    Uses replace_message pattern.
    
    Requirements: 3.4
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
        
        escalation_id = payload.escalation_id
        
        if not escalation_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Эскалация не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Get escalation with ticket
        stmt = (
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .options(selectinload(Escalation.ticket))
        )
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        
        if not escalation:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Эскалация не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Assign ticket to administrator
        ticket = escalation.ticket
        old_staff_id = ticket.assigned_staff_id
        ticket.assigned_staff_id = admin.id
        
        # Resolve escalation
        await resolve_escalation(
            session=session,
            escalation_id=escalation_id,
            resolved_by_staff_id=admin.id,
            resolution_action=ResolutionAction.TAKEN_OVER
        )
        
        # Log action
        action_log = Action_Log(
            ticket_id=ticket.id,
            staff_id=admin.id,
            action_type=ActionType.TICKET_ASSIGNED,
            action_details={
                "escalation_id": escalation_id,
                "old_staff_id": old_staff_id,
                "new_staff_id": admin.id,
                "action": "taken_over"
            }
        )
        session.add(action_log)
        
        await session.commit()
        
        # Success message
        message_text = (
            f"✅ <b>Эскалация разрешена</b>\n\n"
            f"Заявка #{ticket.id} взята вами в работу."
        )
        
        # Back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ К списку эскалаций",
                        payload=EscalationPayload(action="list").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=message_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} took over escalation {escalation_id}")
        
    except Exception as e:
        logger.error(f"Error taking over escalation: {e}", exc_info=True)
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при взятии заявки в работу.",
            parse_mode="HTML"
        )


# ========== Staff Contact Info ==========


async def handle_staff_contact(
    event: MessageCallback,
    payload: EscalationPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display contact information for staff assigned to escalated ticket.
    
    Shows staff member's name, role, phone, and email.
    Uses replace_message pattern.
    
    Requirements: 3.3
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
        
        escalation_id = payload.escalation_id
        
        if not escalation_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Эскалация не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Get escalation with ticket and assigned staff
        stmt = (
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .options(
                selectinload(Escalation.ticket).selectinload(Ticket.assigned_staff)
            )
        )
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        
        if not escalation:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Эскалация не найдена.",
                parse_mode="HTML"
            )
            return
        
        ticket = escalation.ticket
        staff = ticket.assigned_staff
        
        if not staff:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не назначена на сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Format role name
        role_names = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        role_name = role_names.get(staff.staff_role, str(staff.staff_role))
        
        # Build contact info message
        message_text = (
            f"📞 <b>Контакты сотрудника</b>\n\n"
            f"<b>Имя:</b> {staff.full_name}\n"
            f"<b>Должность:</b> {staff.position}\n"
            f"<b>Роль:</b> {role_name}\n"
            f"<b>MAX ID:</b> <code>{staff.max_user_id}</code>" if staff.max_user_id else ""
        )
        
        # Back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ Назад",
                        payload=EscalationPayload(action="view", escalation_id=escalation_id).pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=message_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} viewed contact info for escalation {escalation_id}")
        
    except Exception as e:
        logger.error(f"Error displaying staff contact: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке контактов.",
            parse_mode="HTML"
        )


