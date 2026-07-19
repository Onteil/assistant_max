"""
Employee Interface Handlers for MAX Bot

Handles employee menu navigation, ticket management, and employee settings.
Migrated from Telegram bot to MAX messenger using maxapi.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 16.1, 9.3, 9.5, 9.6, 9.7, 9.8
"""

import logging

from maxapi import F, Router
from maxapi.types import MessageCreated, MessageCallback
from maxapi.context import MemoryContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.callback_datas import (
    TicketListCallback,
    TicketActionCallback,
    EmployeeSelectionCallback,
    ArchiveSearchCallback,
)
from bots.max_bot.states import EmployeeStates
from bots.max_bot.utils.callback_utils import answer_max_callback
from bots.max_bot.texts import (
    BTN_ACTIVE_TICKETS,
    BTN_ARCHIVE_SEARCH,
    BTN_EMPLOYEE_SETTINGS,
    EMPLOYEE_MENU_TEXT,
    EMPLOYEE_NO_ACTIVE_TICKETS_TEXT,
    EMPLOYEE_SETTINGS_TEXT,
)
from database.models import Staff_Member, StaffRole, Ticket, TicketStatus, User
from services import employee_service
from services.employee_service import (
    format_ticket_card,
    get_employee_active_tickets,
    get_ticket_action_keyboard,
    get_active_tickets_keyboard,
    format_active_tickets_header,
)

logger = logging.getLogger(__name__)

router = Router(router_id="employee")


# ========== Helper Functions ==========


async def is_staff_member(session: AsyncSession, user_id: int) -> Staff_Member | None:
    """
    Check if user is a staff member and return their record.
    
    Args:
        session: Database session
        user_id: MAX user ID
    
    Returns:
        Staff_Member object if user is staff, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == user_id,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking staff member status for user {user_id}: {e}", exc_info=True)
        return None


# ========== Main Menu Handler ==========


@router.message_created(F.message.body.text == "/manager")
async def show_employee_menu(
    event: MessageCreated,
    session: AsyncSession
) -> None:
    """
    Display employee main menu.
    
    Checks if user is a staff member and shows menu with:
    - Active tickets button
    - Archive search button
    - Settings button
    - Admin panel button (if administrator role)
    
    Requirements: 1.1, 1.5, 1.6
    """
    logger.info(f"show_employee_menu handler called for user {event.message.sender.user_id}")
    
    try:
        user_id = event.message.sender.user_id
        
        # Check if user is a staff member
        employee = await is_staff_member(session, user_id)
        
        logger.info(f"Employee check result for user {user_id}: {employee is not None}")
        
        if not employee:
            await event.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника.\n"
                "Используйте /start для доступа к клиентскому интерфейсу."
            )
            logger.warning(f"Non-staff user {user_id} attempted to access employee menu")
            return
        
        # Generate menu keyboard based on employee role
        is_admin = employee.staff_role == StaffRole.ADMINISTRATOR
        
        # Import reply keyboard for manager
        from bots.max_bot.keyboards.employee.employee_kb import get_manager_menu_keyboard
        keyboard = await get_manager_menu_keyboard(is_admin=is_admin)
        
        logger.info(f"Sending manager menu to user {user_id}")
        
        await event.message.answer(
            EMPLOYEE_MENU_TEXT,
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} ({employee.full_name}) accessed employee menu")
        
    except Exception as e:
        logger.error(f"Error showing employee menu for user {event.message.sender.user_id}: {e}", exc_info=True)
        await event.message.answer(
            "❌ Произошла ошибка при загрузке меню.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Reply Button Handlers ==========


@router.message_created(F.message.body.text == BTN_ACTIVE_TICKETS)
async def handle_active_tickets_button(
    event: MessageCreated,
    session: AsyncSession,
    context: MemoryContext
) -> None:
    """
    Handle "Active Tickets" reply button press.
    
    Display list of active tickets with inline keyboard.
    Each row contains: [Ticket button | Actions button (📋)]
    
    Requirements: 1.2, 13.2, Active Tickets Inline Keyboard
    """
    try:
        user_id = event.message.sender.user_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await event.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Get current focus state
        current_state = await context.get_state()
        data = await context.get_data()
        focused_ticket_id = data.get("focused_ticket_id") if current_state == EmployeeStates.in_focus else None
        
        # Get active tickets for employee
        tickets = await get_employee_active_tickets(session, user_id)
        
        if not tickets:
            await event.message.answer(
                EMPLOYEE_NO_ACTIVE_TICKETS_TEXT
            )
            logger.info(f"Employee {user_id} has no active tickets")
            return
        
        # Format header text
        header_text = await format_active_tickets_header(
            tickets_count=len(tickets),
            focused_ticket_id=focused_ticket_id
        )
        
        # Generate inline keyboard
        keyboard = await get_active_tickets_keyboard(
            tickets=tickets,
            focused_ticket_id=focused_ticket_id,
            employee_id=user_id,
            session=session
        )
        
        await event.message.answer(
            header_text,
            reply_markup=keyboard
        )
        
        logger.info(
            f"Employee {user_id} viewed {len(tickets)} active tickets "
            f"(focused_ticket_id={focused_ticket_id})"
        )
        
    except Exception as e:
        logger.error(f"Error showing active tickets for user {event.message.sender.user_id}: {e}", exc_info=True)
        await event.message.answer(
            "❌ Произошла ошибка при загрузке активных заявок.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.message_created(F.message.body.text == BTN_EMPLOYEE_SETTINGS)
async def handle_settings_button(
    event: MessageCreated,
    session: AsyncSession
) -> None:
    """
    Handle "Settings" reply button press.
    
    Display employee settings.
    
    Requirements: 1.4, 16.1
    """
    try:
        user_id = event.message.sender.user_id
        
        # Get employee record
        employee = await is_staff_member(session, user_id)
        if not employee:
            await event.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Format role display
        role_display = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техническая поддержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        role_text = role_display.get(employee.staff_role, str(employee.staff_role.value))
        
        # Format signature
        signature = f"{employee.full_name}, {employee.position}"
        
        # Build settings text
        settings_text = EMPLOYEE_SETTINGS_TEXT.format(
            full_name=employee.full_name,
            position=employee.position,
            role=role_text,
            signature=signature
        )
        
        await event.message.answer(settings_text)
        
        logger.info(f"Employee {user_id} viewed settings")
        
    except Exception as e:
        logger.error(f"Error showing settings for user {event.message.sender.user_id}: {e}", exc_info=True)
        await event.message.answer(
            "❌ Произошла ошибка при загрузке настроек.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.message_created(F.message.body.text == BTN_ARCHIVE_SEARCH)
async def handle_archive_search_button(
    event: MessageCreated,
    context: MemoryContext
) -> None:
    """
    Handle "Archive Search" reply button press.
    
    Initiate archive search flow.
    
    Requirements: 1.3
    """
    try:
        user_id = event.message.sender.user_id
        
        # Set FSM state
        await context.set_state(EmployeeStates.searching_archive)
        
        await event.message.answer(
            "🗄 Поиск в архиве обращений\n\n"
            "Введите критерий поиска:\n"
            "• Номер заявки (например: 123)\n"
            "• Имя клиента (например: Иван)\n"
            "• Диапазон дат (например: 2024-01-01 to 2024-01-31)\n\n"
            "Для отмены используйте /cancel"
        )
        
        logger.info(f"Employee {user_id} initiated archive search")
        
    except Exception as e:
        logger.error(f"Error initiating archive search for user {event.message.sender.user_id}: {e}", exc_info=True)
        await event.message.answer(
            "❌ Произошла ошибка при запуске поиска.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Ticket List Callback Handlers ==========


@router.message_callback(TicketListCallback.filter(F.action == "focus_ticket"))
async def handle_focus_ticket_callback(
    event: MessageCallback,
    callback_data: TicketListCallback,
    session: AsyncSession,
    context: MemoryContext
) -> None:
    """
    Handle direct focus on ticket from list.
    
    - If ticket is NEW, take it into work (change status to IN_PROGRESS)
    - Enter focus mode
    - Send confirmation with focus keyboard
    
    Requirements: Active Tickets Inline Keyboard
    """
    if not await answer_max_callback(event):
        return
    
    try:
        user_id = event.message.sender.user_id
        ticket_id = callback_data.ticket_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await event.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Get ticket with eager loading of relationships
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        if not ticket:
            await answer_max_callback(
                event,
                notification="❌ Заявка не найдена",
            )
            return
        
        # Check if already in focus mode on a different ticket
        current_state = await context.get_state()
        data = await context.get_data()
        previous_focused_ticket_id = data.get("focused_ticket_id")
        
        focus_switched = False
        if current_state == EmployeeStates.in_focus and previous_focused_ticket_id and previous_focused_ticket_id != ticket_id:
            focus_switched = True
            logger.info(
                f"Employee {user_id} switching focus from ticket {previous_focused_ticket_id} "
                f"to ticket {ticket_id}"
            )
        
        # If ticket is NEW, take it into work
        if ticket.ticket_status == TicketStatus.NEW:
            from services.ticket_service import take_ticket_into_work as take_ticket_service
            ticket = await take_ticket_service(session, ticket_id, user_id, messenger="max")
        
        # Enter focus mode
        await context.set_state(EmployeeStates.in_focus)
        await context.update_data(
            focused_ticket_id=ticket_id,
            focused_client_id=ticket.max_user_id
        )
        
        # Get client name
        client_name = ticket.user.full_name or ticket.user.first_name or "Неизвестно"
        
        # Generate focus keyboard
        keyboard = await get_ticket_action_keyboard(ticket)
        
        # Send focus confirmation
        focus_text = (
            f"✅ Работа с заявкой #{ticket_id}\n"
            f"Клиент: {client_name}\n"
            f"Введите текст или отправьте файл для клиента.\n\n"
            f"👇 Управление:"
        )
        
        await event.message.answer(
            focus_text,
            reply_markup=keyboard
        )
        
        if focus_switched:
            logger.info(f"Employee {user_id} switched focus to ticket {ticket_id}")
        else:
            logger.info(f"Employee {user_id} entered focus on ticket {ticket_id}")
        
    except Exception as e:
        logger.error(f"Error focusing on ticket: ticket_id={callback_data.ticket_id}, user={event.message.sender.user_id}, error={e}", exc_info=True)
        await event.message.answer(
            "❌ Произошла ошибка при открытии заявки.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.message_callback(TicketListCallback.filter(F.action == "ticket_actions"))
async def handle_ticket_actions_callback(
    event: MessageCallback,
    callback_data: TicketListCallback,
    session: AsyncSession
) -> None:
    """
    Handle opening ticket actions menu.
    
    - Edit message to show ticket card
    - Display action buttons based on ticket status
    - Include "Back to list" button
    
    Requirements: Active Tickets Inline Keyboard
    """
    if not await answer_max_callback(event):
        return
    
    try:
        user_id = event.message.sender.user_id
        ticket_id = callback_data.ticket_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await event.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Get ticket with eager loading of relationships
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        if not ticket:
            await answer_max_callback(
                event,
                notification="❌ Заявка не найдена",
            )
            return
        
        # Format ticket card
        ticket_card = await format_ticket_card(ticket, session)
        ticket_card += "\n\nВыберите действие:"
        
        # Generate action keyboard
        keyboard = await get_ticket_action_keyboard(ticket)
        
        # Edit message to show ticket card
        await event.message.edit_text(
            ticket_card,
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} opened actions menu for ticket {ticket_id}")
        
    except Exception as e:
        logger.error(f"Error opening ticket actions: ticket_id={callback_data.ticket_id}, user={event.message.sender.user_id}, error={e}", exc_info=True)
        await event.message.answer(
            "❌ Произошла ошибка при открытии меню действий.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Ticket Action Callback Handlers ==========


@router.message_callback(TicketActionCallback.filter(F.action == "back_to_list"))
async def handle_back_to_list_callback(
    event: MessageCallback,
    session: AsyncSession,
    context: MemoryContext
) -> None:
    """
    Handle return to active tickets list.
    
    - Edit message to show updated tickets list
    - Regenerate inline keyboard
    
    Requirements: Active Tickets Inline Keyboard
    """
    if not await answer_max_callback(event):
        return
    
    try:
        user_id = event.message.sender.user_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await event.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Get current focus state
        current_state = await context.get_state()
        data = await context.get_data()
        focused_ticket_id = data.get("focused_ticket_id") if current_state == EmployeeStates.in_focus else None
        
        # Get active tickets
        tickets = await get_employee_active_tickets(session, user_id)
        
        if not tickets:
            await event.message.edit_text(
                EMPLOYEE_NO_ACTIVE_TICKETS_TEXT
            )
            logger.info(f"Employee {user_id} has no active tickets")
            return
        
        # Format header text
        header_text = await format_active_tickets_header(
            tickets_count=len(tickets),
            focused_ticket_id=focused_ticket_id
        )
        
        # Generate inline keyboard
        keyboard = await get_active_tickets_keyboard(
            tickets=tickets,
            focused_ticket_id=focused_ticket_id,
            employee_id=user_id,
            session=session
        )
        
        # Edit message to show list
        await event.message.edit_text(
            header_text,
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} returned to active tickets list")
        
    except Exception as e:
        logger.error(f"Error returning to tickets list: user={event.message.sender.user_id}, error={e}", exc_info=True)
        await event.message.answer(
            "❌ Произошла ошибка при возврате к списку.\n"
            "Используйте /manager для возврата в меню."
        )


# TODO: Implement remaining ticket action handlers:
# - take_ticket_into_work (from ticket actions menu)
# - set_ticket_waiting
# - initiate_ticket_close
# - complete_ticket_close
# - initiate_ticket_transfer
# - complete_ticket_transfer
# - cancel_ticket_transfer
# - view_ticket_history
# - exit_focus_mode
# - execute_archive_search
# - archive_search_pagination
# - view_archived_ticket
# - back_from_archive_search
#
# See bots/tg_bot/handlers/staff/common.py for source implementation
