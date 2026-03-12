"""
Admin Panel - Escalation Handlers

Handles escalation management in the administrative panel:
- List active escalations
- View escalation card with ticket details
- Reassign escalated tickets to staff
- Take over escalated tickets
- Show staff contact information

Requirements: 3.1, 3.2, 3.3, 3.4
"""

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bots.tg_bot.callback_datas import AdminMenuCallback, EscalationCallback
from bots.tg_bot.keyboards.escalation_kb import (
    get_escalation_card_keyboard,
    get_escalations_list_keyboard,
    get_staff_selection_keyboard,
)
from bots.tg_bot.states import AdminStates
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
from services.logging_service import log_ticket_action

logger = logging.getLogger(__name__)

router = Router(name="admin_escalations")


# ========== Helper Functions ==========


async def is_admin(session: AsyncSession, user_id: int) -> Staff_Member | None:
    """
    Check if user is an administrator and return their record.
    
    Args:
        session: Database session
        user_id: Telegram user ID
    
    Returns:
        Staff_Member object if user is admin, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == user_id,
            Staff_Member.is_active == True,
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}", exc_info=True)
        return None


# ========== Escalation List Handlers ==========


@router.callback_query(AdminMenuCallback.filter(F.action == "escalations"))
async def handle_escalations_menu(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Handle "Escalations" menu button - show list of active escalations.
    
    Displays all active (unresolved) escalations with pagination.
    Shows ticket info, client name, and time elapsed.
    
    Requirements: 3.1, 3.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к этой функции.",
                show_alert=True
            )
            return
        
        # Get active escalations
        escalations = await get_active_escalations(session, limit=50)
        
        if not escalations:
            # No active escalations
            await callback.message.edit_text(
                "✅ <b>Нет активных эскалаций</b>\n\n"
                "Все заявки обрабатываются в срок.",
                reply_markup=await get_escalations_list_keyboard([], page=0)
            )
            logger.info(f"Admin {admin.id} viewed escalations list: 0 active")
            return
        
        # Build escalations list text
        text = (
            "⚠️ <b>Активные эскалации</b>\n\n"
            "Список заявок, требующих внимания администратора.\n"
            "Эти заявки не были обработаны сотрудниками в установленные сроки.\n\n"
            f"<b>Всего эскалаций:</b> {len(escalations)}\n\n"
            "Выберите заявку для просмотра деталей и принятия решения:"
        )
        
        # Get keyboard with pagination
        keyboard = await get_escalations_list_keyboard(escalations, page=0)
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Admin {admin.id} viewed escalations list: {len(escalations)} active")
        
    except Exception as e:
        logger.error(f"Error showing escalations list: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке списка эскалаций.",
            show_alert=True
        )


@router.callback_query(EscalationCallback.filter(F.action == "list"))
async def handle_escalations_list_pagination(
    callback: CallbackQuery,
    callback_data: EscalationCallback,
    session: AsyncSession
) -> None:
    """
    Handle pagination for escalations list.
    
    Requirements: 3.1
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к этой функции.",
                show_alert=True
            )
            return
        
        page = callback_data.page or 0
        
        # Get active escalations
        escalations = await get_active_escalations(session, limit=50)
        
        if not escalations:
            await callback.message.edit_text(
                "✅ <b>Нет активных эскалаций</b>\n\n"
                "Все заявки обрабатываются в срок.",
                reply_markup=await get_escalations_list_keyboard([], page=0)
            )
            return
        
        # Build escalations list text
        text = f"⚠️ <b>Активные эскалации</b>\n\n"
        text += f"Всего эскалаций: {len(escalations)}\n\n"
        
        # Get keyboard with pagination
        keyboard = await get_escalations_list_keyboard(escalations, page=page)
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Admin {admin.id} viewed escalations list page {page}")
        
    except Exception as e:
        logger.error(f"Error showing escalations list pagination: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке списка эскалаций.",
            show_alert=True
        )


# ========== Escalation Card Handler ==========


@router.callback_query(EscalationCallback.filter(F.action == "view"))
async def handle_escalation_view(
    callback: CallbackQuery,
    callback_data: EscalationCallback,
    session: AsyncSession
) -> None:
    """
    Handle escalation card view - show detailed information about escalation.
    
    Displays:
    - Ticket information (ID, type, status)
    - Client information (name, organization)
    - Assigned staff information
    - Time elapsed since ticket creation
    - Action buttons (reassign, take over, contact)
    
    Requirements: 3.1, 3.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к этой функции.",
                show_alert=True
            )
            return
        
        escalation_id = callback_data.escalation_id
        
        # Get escalation with relationships
        stmt = (
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .options(
                selectinload(Escalation.ticket).selectinload(Ticket.user),
                selectinload(Escalation.ticket).selectinload(Ticket.assigned_staff),
                selectinload(Escalation.ticket).selectinload(Ticket.organization)
            )
        )
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        
        if not escalation:
            await callback.answer(
                "❌ Эскалация не найдена.",
                show_alert=True
            )
            return
        
        # Check if already resolved
        if escalation.is_resolved:
            await callback.answer(
                "✅ Эта эскалация уже разрешена.",
                show_alert=True
            )
            return
        
        ticket = escalation.ticket
        
        # Calculate time elapsed
        time_elapsed = int((datetime.now() - ticket.created_at).total_seconds() / 60)
        
        # Ticket type display
        ticket_type_display = {
            TicketType.INVOICE: "Счет",
            TicketType.TECHNICAL_SUPPORT: "Техподдержка",
            TicketType.RENEWAL: "Продление"
        }
        ticket_type_text = ticket_type_display.get(ticket.ticket_type, ticket.ticket_type.value)
        
        # Status display
        status_display = {
            TicketStatus.NEW: "Новая",
            TicketStatus.IN_PROGRESS: "В работе",
            TicketStatus.WAITING_CLIENT: "Ожидание клиента",
            TicketStatus.CLOSED: "Закрыта"
        }
        status_text = status_display.get(ticket.ticket_status, ticket.ticket_status.value)
        
        # Build escalation card text
        text = (
            f"🔥 <b>Эскалация #{escalation.id}</b>\n\n"
            f"<b>Заявка:</b> #{ticket.id}\n"
            f"<b>Тип:</b> {ticket_type_text}\n"
            f"<b>Статус:</b> {status_text}\n"
            f"<b>Время ожидания:</b> {time_elapsed} мин\n\n"
            f"<b>Клиент:</b> {ticket.user.full_name}\n"
        )
        
        if ticket.organization:
            text += f"<b>ИНН:</b> {ticket.organization.inn}\n"

        if ticket.assigned_staff:
            text += f"\n<b>Ответственный:</b> {ticket.assigned_staff.full_name}\n"
            text += f"<b>Роль:</b> {ticket.assigned_staff.staff_role.value}\n"
        else:
            text += f"\n<b>Ответственный:</b> Не назначен\n"
        
        text += f"\n<b>Создана:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        # Get action keyboard
        keyboard = await get_escalation_card_keyboard(escalation.id, ticket.id)
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Admin {admin.id} viewed escalation card: escalation_id={escalation_id}")
        
    except Exception as e:
        logger.error(f"Error showing escalation card: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке карточки эскалации.",
            show_alert=True
        )


# ========== Reassignment Handlers ==========


@router.callback_query(EscalationCallback.filter(F.action == "reassign"))
async def handle_escalation_reassign(
    callback: CallbackQuery,
    callback_data: EscalationCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Reassign" button - start reassignment process.
    
    Shows list of available staff members for ticket reassignment.
    Sets FSM state to waiting_for_reassign_staff.
    
    Requirements: 3.1, 3.3
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к этой функции.",
                show_alert=True
            )
            return
        
        escalation_id = callback_data.escalation_id
        ticket_id = callback_data.ticket_id
        page = callback_data.page or 0
        
        logger.info(
            f"Reassignment initiated: admin_user_id={user_id}, admin_staff_id={admin.id}, "
            f"escalation_id={escalation_id}, ticket_id={ticket_id}"
        )
        
        # Get escalation
        stmt = select(Escalation).where(Escalation.id == escalation_id)
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        
        if not escalation:
            await callback.answer(
                "❌ Эскалация не найдена.",
                show_alert=True
            )
            return
        
        # Check if already resolved
        if escalation.is_resolved:
            await callback.answer(
                "✅ Эта эскалация уже разрешена.",
                show_alert=True
            )
            return
        
        # Get ticket with assigned staff
        ticket_stmt = (
            select(Ticket)
            .options(selectinload(Ticket.assigned_staff))
            .where(Ticket.id == ticket_id)
        )
        ticket_result = await session.execute(ticket_stmt)
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            await callback.answer(
                "❌ Заявка не найдена.",
                show_alert=True
            )
            return
        
        # Get available staff members based on ticket type
        if ticket.ticket_type == TicketType.INVOICE:
            allowed_roles = [StaffRole.MANAGER, StaffRole.ADMINISTRATOR]
        elif ticket.ticket_type == TicketType.TECHNICAL_SUPPORT:
            allowed_roles = [
                StaffRole.TECHNICAL_SUPPORT,
                StaffRole.DUTY_ENGINEER,
                StaffRole.ADMINISTRATOR
            ]
        else:
            allowed_roles = [
                StaffRole.MANAGER,
                StaffRole.TECHNICAL_SUPPORT,
                StaffRole.DUTY_ENGINEER,
                StaffRole.ADMINISTRATOR
            ]
        
        # Query available staff (exclude currently assigned staff and current admin)
        filters = [
            Staff_Member.is_active == True,
            Staff_Member.staff_role.in_(allowed_roles)
        ]
        
        # Collect IDs to exclude (avoid duplicates)
        exclude_ids = set()
        
        # Exclude currently assigned staff if ticket is assigned
        if ticket.assigned_staff_id:
            exclude_ids.add(ticket.assigned_staff_id)
        
        # Exclude current admin to prevent self-reassignment
        exclude_ids.add(admin.id)
        
        # Apply exclusion filter
        if exclude_ids:
            filters.append(Staff_Member.id.not_in(exclude_ids))
        
        staff_stmt = (
            select(Staff_Member)
            .where(*filters)
            .order_by(Staff_Member.full_name.asc())
        )
        
        staff_result = await session.execute(staff_stmt)
        available_staff = list(staff_result.scalars().all())
        
        logger.info(
            f"Reassignment filters: admin_id={admin.id}, assigned_staff_id={ticket.assigned_staff_id}, "
            f"exclude_ids={exclude_ids}, available_staff_count={len(available_staff)}, "
            f"available_staff_ids={[s.id for s in available_staff]}"
        )
        
        if not available_staff:
            await callback.answer(
                "❌ Нет других доступных сотрудников для переназначения.",
                show_alert=True
            )
            return
        
        logger.info(
            f"Available staff for reassignment: {[(s.id, s.full_name) for s in available_staff]}"
        )
        
        # Store escalation and ticket IDs in state
        await state.set_state(AdminStates.waiting_for_reassign_staff)
        await state.update_data(
            escalation_id=escalation_id,
            ticket_id=ticket_id
        )
        
        # Get staff selection keyboard
        keyboard = await get_staff_selection_keyboard(
            escalation_id=escalation_id,
            ticket_id=ticket_id,
            staff_members=available_staff,
            page=page
        )
        
        # Get ticket details for display
        ticket_type_display = {
            TicketType.INVOICE: "Счет",
            TicketType.TECHNICAL_SUPPORT: "Техподдержка",
            TicketType.RENEWAL: "Продление"
        }
        
        reassign_text = (
            f"➡️ <b>Переназначение заявки #{ticket_id}</b>\n\n"
            f"<b>Тип:</b> {ticket_type_display.get(ticket.ticket_type, ticket.ticket_type.value)}\n"
            f"<b>Текущий исполнитель:</b> {ticket.assigned_staff.full_name if ticket.assigned_staff else 'Не назначен'}\n\n"
            f"Выберите сотрудника для переназначения:"
        )
        
        await callback.message.edit_text(
            reassign_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Admin {admin.id} initiated reassignment for escalation {escalation_id}, "
            f"ticket {ticket_id}"
        )
        
    except Exception as e:
        logger.error(f"Error handling escalation reassignment: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при переназначении заявки.",
            show_alert=True
        )


@router.callback_query(EscalationCallback.filter(F.action == "select_staff"))
async def handle_staff_selection(
    callback: CallbackQuery,
    callback_data: EscalationCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle staff member selection for escalated ticket reassignment.
    
    Assigns the ticket to the selected staff member, resolves escalation,
    cancels monitoring tasks, and sends notifications.
    
    Requirements: 3.3, 3.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к этой функции.",
                show_alert=True
            )
            await state.clear()
            return
        
        escalation_id = callback_data.escalation_id
        ticket_id = callback_data.ticket_id
        target_staff_id = callback_data.staff_id
        
        # Get escalation
        escalation_stmt = select(Escalation).where(Escalation.id == escalation_id)
        escalation_result = await session.execute(escalation_stmt)
        escalation = escalation_result.scalar_one_or_none()
        
        if not escalation:
            await callback.answer(
                "❌ Эскалация не найдена.",
                show_alert=True
            )
            await state.clear()
            return
        
        # Check if already resolved
        if escalation.is_resolved:
            await callback.answer(
                "✅ Эта эскалация уже разрешена.",
                show_alert=True
            )
            await state.clear()
            return
        
        # Get ticket
        ticket_stmt = select(Ticket).where(Ticket.id == ticket_id)
        ticket_result = await session.execute(ticket_stmt)
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            await callback.answer(
                "❌ Заявка не найдена.",
                show_alert=True
            )
            await state.clear()
            return
        
        # Get target staff member
        target_stmt = select(Staff_Member).where(Staff_Member.id == target_staff_id)
        target_result = await session.execute(target_stmt)
        target_staff = target_result.scalar_one_or_none()
        
        if not target_staff:
            await callback.answer(
                "❌ Сотрудник не найден.",
                show_alert=True
            )
            await state.clear()
            return
        
        # Assign ticket to target staff
        old_assigned_id = ticket.assigned_staff_id
        ticket.assigned_staff_id = target_staff_id
        ticket.ticket_status = TicketStatus.IN_PROGRESS
        
        # Resolve escalation
        await resolve_escalation(
            session=session,
            escalation_id=escalation_id,
            resolved_by_staff_id=admin.id,
            resolution_action=ResolutionAction.REASSIGNED
        )
        
        # Cancel escalation monitoring tasks
        try:
            # Import here to avoid circular dependency
            from celery_app.escalation_tasks import cancel_escalation_monitoring
            
            await cancel_escalation_monitoring(ticket_id)
            logger.info(
                f"Escalation monitoring cancelled for reassigned ticket: ticket_id={ticket_id}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to cancel escalation monitoring: ticket_id={ticket_id}, error={e}"
            )
        
        await session.commit()
        
        # Log action
        await log_ticket_action(
            session=session,
            action_type=ActionType.TICKET_ASSIGNED,
            ticket_id=ticket_id,
            staff_id=admin.id,
            action_details={
                "from_staff_id": old_assigned_id,
                "to_staff_id": target_staff_id,
                "target_staff_name": target_staff.full_name,
                "escalation_reassignment": True,
                "escalation_id": escalation_id
            }
        )
        
        # Send notification to assigned staff
        try:
            bot = callback.bot
            await bot.send_message(
                chat_id=target_staff.tg_user_id,
                text=(
                    f"✅ <b>Вам назначена заявка</b>\n\n"
                    f"Заявка #{ticket_id} была назначена вам администратором.\n"
                    f"Пожалуйста, обработайте её как можно скорее."
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(
                f"Failed to send notification to staff {target_staff.id}: {e}",
                exc_info=True
            )
        
        # Clear state
        await state.clear()
        
        await callback.message.edit_text(
            f"✅ <b>Заявка переназначена</b>\n\n"
            f"Заявка #{ticket_id} успешно назначена сотруднику {target_staff.full_name}.\n"
            f"Эскалация разрешена.",
            parse_mode="HTML"
        )
        
        logger.info(
            f"Admin {admin.id} reassigned escalated ticket {ticket_id} to staff {target_staff.id}, "
            f"escalation {escalation_id} resolved"
        )
        
    except Exception as e:
        logger.error(f"Error handling staff selection for escalation: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при назначении заявки.",
            show_alert=True
        )
        await state.clear()


# ========== Take Over Handler ==========


@router.callback_query(EscalationCallback.filter(F.action == "take_over"))
async def handle_escalation_take_over(
    callback: CallbackQuery,
    callback_data: EscalationCallback,
    session: AsyncSession
) -> None:
    """
    Handle "Take Over" button - administrator takes the ticket.
    
    Assigns the ticket to the administrator, resolves escalation,
    cancels monitoring tasks, and sends notifications to client.
    
    Requirements: 3.3, 3.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к этой функции.",
                show_alert=True
            )
            return
        
        escalation_id = callback_data.escalation_id
        ticket_id = callback_data.ticket_id
        
        # Get escalation
        escalation_stmt = select(Escalation).where(Escalation.id == escalation_id)
        escalation_result = await session.execute(escalation_stmt)
        escalation = escalation_result.scalar_one_or_none()
        
        if not escalation:
            await callback.answer(
                "❌ Эскалация не найдена.",
                show_alert=True
            )
            return
        
        # Check if already resolved
        if escalation.is_resolved:
            await callback.answer(
                "✅ Эта эскалация уже разрешена.",
                show_alert=True
            )
            return
        
        # Get ticket with relationships
        ticket_stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization)
            )
        )
        ticket_result = await session.execute(ticket_stmt)
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            await callback.answer(
                "❌ Заявка не найдена.",
                show_alert=True
            )
            return
        
        # Assign ticket to administrator
        old_assigned_id = ticket.assigned_staff_id
        ticket.assigned_staff_id = admin.id
        ticket.ticket_status = TicketStatus.IN_PROGRESS
        
        # Resolve escalation
        await resolve_escalation(
            session=session,
            escalation_id=escalation_id,
            resolved_by_staff_id=admin.id,
            resolution_action=ResolutionAction.TAKEN_OVER
        )
        
        # Cancel escalation monitoring tasks
        try:
            # Import here to avoid circular dependency
            from celery_app.escalation_tasks import cancel_escalation_monitoring
            
            await cancel_escalation_monitoring(ticket_id)
            logger.info(
                f"Escalation monitoring cancelled for admin-taken ticket: ticket_id={ticket_id}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to cancel escalation monitoring: ticket_id={ticket_id}, error={e}"
            )
        
        await session.commit()
        
        # Log action
        await log_ticket_action(
            session=session,
            action_type=ActionType.TICKET_ASSIGNED,
            ticket_id=ticket_id,
            staff_id=admin.id,
            action_details={
                "from_staff_id": old_assigned_id,
                "to_staff_id": admin.id,
                "admin_took_escalation": True,
                "escalation_id": escalation_id
            }
        )
        
        # Send notification to client
        try:
            bot = callback.bot
            await bot.send_message(
                chat_id=ticket.user.tg_user_id,
                text=(
                    f"✅ <b>Ваша заявка взята в работу</b>\n\n"
                    f"Заявка #{ticket_id} взята в работу.\n"
                    f"С вами работает: {admin.signature}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(
                f"Failed to send notification to client {ticket.user.id}: {e}",
                exc_info=True
            )
        
        await callback.message.edit_text(
            f"✅ <b>Заявка взята на себя</b>\n\n"
            f"Заявка #{ticket_id} успешно взята на себя.\n"
            f"Эскалация разрешена.\n\n"
            f"Теперь вы можете общаться с клиентом.",
            parse_mode="HTML"
        )
        
        logger.info(
            f"Admin {admin.id} took over escalated ticket {ticket_id}, "
            f"escalation {escalation_id} resolved"
        )
        
    except Exception as e:
        logger.error(f"Error handling escalation take over: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при взятии заявки.",
            show_alert=True
        )


# ========== Contact Staff Handler ==========


@router.callback_query(EscalationCallback.filter(F.action == "contact"))
async def handle_escalation_contact(
    callback: CallbackQuery,
    callback_data: EscalationCallback,
    session: AsyncSession
) -> None:
    """
    Handle "Contact Staff" button - show staff contact information.
    
    Displays contact information for the assigned staff member.
    Does not resolve the escalation.
    
    Requirements: 3.3, 3.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к этой функции.",
                show_alert=True
            )
            return
        
        ticket_id = callback_data.ticket_id
        
        # Get ticket with assigned staff
        ticket_stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.assigned_staff))
        )
        ticket_result = await session.execute(ticket_stmt)
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            await callback.answer(
                "❌ Заявка не найдена.",
                show_alert=True
            )
            return
        
        if not ticket.assigned_staff:
            await callback.answer(
                "⚠️ Заявка не назначена ни одному сотруднику.",
                show_alert=True
            )
            return
        
        staff = ticket.assigned_staff
        
        # Role display
        role_display = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        role_text = role_display.get(staff.staff_role, staff.staff_role.value)
        
        # Build contact information text
        contact_text = (
            f"📞 <b>Контакт сотрудника</b>\n\n"
            f"<b>Имя:</b> {staff.full_name}\n"
            f"<b>Роль:</b> {role_text}\n"
        )
        
        if staff.tg_user_id:
            contact_text += f"<b>Telegram ID:</b> {staff.tg_user_id}\n"
        
        if staff.phone:
            contact_text += f"<b>Телефон:</b> {staff.phone}\n"
        
        if staff.email:
            contact_text += f"<b>Email:</b> {staff.email}\n"
        
        contact_text += (
            f"\nВы можете связаться с сотрудником для решения эскалированной заявки."
        )
        
        await callback.message.answer(
            contact_text,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Admin {admin.id} requested contact info for staff {staff.id}, "
            f"ticket {ticket_id}"
        )
        
    except Exception as e:
        logger.error(f"Error handling escalation contact: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при получении контактной информации.",
            show_alert=True
        )
