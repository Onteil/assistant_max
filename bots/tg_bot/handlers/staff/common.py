"""
Employee Interface Handlers

Handles employee menu navigation, ticket management, and employee settings.
Implements the employee workplace interface for managing customer support tickets.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 16.1
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import (
    ArchiveSearchCallback,
    EmployeeMenuCallback,
    EmployeeSelectionCallback,
    TicketActionCallback,
    TicketHistoryCallback,
    TicketListCallback,
)
from bots.tg_bot.keyboards.employee_kb import get_employee_menu_keyboard
from bots.tg_bot.states import EmployeeStates
from bots.tg_bot.texts import (
    BTN_ACTIVE_TICKETS,
    BTN_ARCHIVE_SEARCH,
    BTN_EMPLOYEE_SETTINGS,
    EMPLOYEE_MENU_TEXT,
    EMPLOYEE_NO_ACTIVE_TICKETS_TEXT,
    EMPLOYEE_SETTINGS_TEXT,
)
from database.models import File_Attachment, Staff_Member, StaffRole, Ticket, TicketStatus, TicketType, User
from services import employee_service
from services.employee_service import (
    calculate_ticket_elapsed_time,
    format_ticket_card,
    get_employee_active_tickets,
    get_ticket_action_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name="employee")


# ========== Helper Functions ==========


async def is_staff_member(session: AsyncSession, user_id: int) -> Staff_Member | None:
    """
    Check if user is a staff member and return their record.
    
    Args:
        session: Database session
        user_id: Telegram user ID
    
    Returns:
        Staff_Member object if user is staff, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == user_id,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking staff member status for user {user_id}: {e}", exc_info=True)
        return None


# ========== Main Menu Handler ==========


@router.message(Command("manager"))
async def show_employee_menu(
    message: Message,
    session: AsyncSession
) -> None:
    """
    Display employee main menu.
    
    Shows menu with:
    - Active tickets button
    - Archive search button
    - Settings button
    - Admin panel button (if administrator role)
    
    Requirements: 1.1, 1.5, 1.6
    """
    logger.info(f"show_employee_menu handler called for user {message.from_user.id}")
    
    try:
        user_id = message.from_user.id
        
        # Get employee record (filter already verified user is staff)
        employee = await is_staff_member(session, user_id)
        
        if not employee:
            # This should not happen if filter works correctly
            logger.error(f"Filter passed but employee not found for user {user_id}")
            await message.answer(
                "❌ Произошла ошибка. Пожалуйста, попробуйте позже."
            )
            return
        
        # Generate menu keyboard based on employee role
        is_admin = employee.staff_role == StaffRole.ADMINISTRATOR
        
        # Import reply keyboard for manager
        from bots.tg_bot.keyboards.manager_kb import get_manager_menu_keyboard
        keyboard = await get_manager_menu_keyboard(is_admin=is_admin)
        
        # Generate role-specific menu text
        from bots.tg_bot.texts import get_employee_menu_text
        menu_text = get_employee_menu_text(
            role=employee.staff_role.value,
            full_name=employee.full_name
        )
        
        logger.info(f"Sending manager menu to user {user_id}")
        
        await message.answer(
            menu_text,
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} ({employee.full_name}) accessed employee menu")
        
    except Exception as e:
        logger.error(f"Error showing employee menu for user {message.from_user.id}: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при загрузке меню.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Reply Button Handlers ==========


@router.message(StateFilter(None), F.text == BTN_ACTIVE_TICKETS)
async def handle_active_tickets_button(
    message: Message,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Active Tickets" reply button press.
    
    Display list of active tickets with inline keyboard interface including filters.
    Shows single message with header and inline keyboard for ticket selection.
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 10.2
    """
    logger.info(f"[STAFF HANDLER] handle_active_tickets_button called for user {message.from_user.id}, text: {message.text}")
    
    try:
        user_id = message.from_user.id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Get current focus state
        current_state = await state.get_state()
        data = await state.get_data()
        focused_ticket_id = data.get("focused_ticket_id") if current_state == EmployeeStates.in_focus else None
        
        # Default filter: show all tickets
        current_filter = "all"
        current_page = 0
        
        # Save filter to state
        await state.update_data(active_filter=current_filter)
        
        # Get active tickets for employee (no filter)
        tickets = await get_employee_active_tickets(session, user_id)
        
        if not tickets:
            await message.answer(
                EMPLOYEE_NO_ACTIVE_TICKETS_TEXT
            )
            logger.info(f"Employee {user_id} has no active tickets")
            return
        
        # Format header text
        header_text = await employee_service.format_active_tickets_header(
            tickets_count=len(tickets),
            focused_ticket_id=focused_ticket_id,
            current_filter=current_filter
        )
        
        # Generate inline keyboard
        keyboard = await employee_service.get_active_tickets_keyboard(
            tickets=tickets,
            focused_ticket_id=focused_ticket_id,
            employee_id=user_id,
            session=session,
            current_filter=current_filter,
            current_page=current_page
        )
        
        # Send single message with header and keyboard
        await message.answer(
            header_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Employee {user_id} viewed {len(tickets)} active tickets "
            f"(filter={current_filter}, page={current_page}, focused_ticket_id={focused_ticket_id})"
        )
        
    except Exception as e:
        logger.error(f"Error showing active tickets for user {message.from_user.id}: {e}", exc_info=True)
        # Clear FSM state on error to prevent invalid states
        await state.clear()
        await message.answer(
            "❌ Произошла ошибка при загрузке активных заявок.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.callback_query(TicketListCallback.filter(F.action == "focus_ticket"))
async def handle_focus_ticket_callback(
    callback: CallbackQuery,
    callback_data: TicketListCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle direct focus entry when user clicks a ticket button.
    
    - Verifies user is staff member
    - Gets ticket from database
    - Checks if already in focus mode (logs focus switch if different ticket)
    - If ticket status is NEW, calls take_ticket_into_work() service function
    - Sets FSM state to EmployeeStates.in_focus
    - Stores focused_ticket_id and focused_client_id in FSM data
    - Gets client name from ticket.user
    - Generates action keyboard with get_ticket_action_keyboard()
    - Sends focus confirmation message with keyboard
    
    Requirements: 2.4, 5.1, 5.2, 5.3, 5.4, 5.5, 11.1, 11.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Get ticket from database with eager loading
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        if not ticket:
            await callback.answer("❌ Заявка не найден", show_alert=True)
            logger.warning(f"Ticket {ticket_id} not found for employee {user_id}")
            return
        
        # Check if already in focus mode on a different ticket
        current_state = await state.get_state()
        data = await state.get_data()
        previous_focused_ticket_id = data.get("focused_ticket_id")
        
        focus_switched = False
        if current_state == EmployeeStates.in_focus and previous_focused_ticket_id and previous_focused_ticket_id != ticket_id:
            focus_switched = True
            logger.info(
                f"Employee {user_id} switching focus from ticket {previous_focused_ticket_id} "
                f"to ticket {ticket_id}"
            )
        
        # If ticket status is NEW, take it into work
        if ticket.ticket_status == TicketStatus.NEW:
            from services.ticket_service import take_ticket_into_work as take_ticket_service
            
            ticket = await take_ticket_service(session, ticket_id, user_id, messenger="telegram")
            await session.commit()
            logger.info(f"Ticket {ticket_id} status changed from NEW to IN_PROGRESS by employee {user_id}")
        
        # Set FSM state to in_focus
        await state.set_state(EmployeeStates.in_focus)
        
        # Store focused_ticket_id and focused_client_id in FSM data
        await state.update_data(
            focused_ticket_id=ticket_id,
            focused_client_id=ticket.user.tg_user_id
        )
        
        # Generate action keyboard
        keyboard = await get_ticket_action_keyboard(ticket)
        
        # Update Reply keyboard to include "Exit Focus" button
        from bots.tg_bot.keyboards.manager_kb import get_manager_menu_keyboard
        is_admin = employee.staff_role == StaffRole.ADMINISTRATOR
        reply_keyboard = await get_manager_menu_keyboard(is_admin=is_admin, focused_ticket_id=ticket_id)
        
        # Use unified format_ticket_card function
        ticket_card = await format_ticket_card(ticket, session)
        focus_message = (
            f"{ticket_card}\n\n"
            f"Введите текст или отправьте файл для клиента.\n\n"
            f"👇 Управление:"
        )
        
        # Send one message with inline keyboard
        await callback.message.answer(
            focus_message,
            reply_markup=keyboard
        )
        
        # Update reply keyboard separately
        await callback.answer(
            "✅ Вы вошли в режим фокуса по заявке.",
            reply_markup=reply_keyboard, show_alert=True
        )
        
        # Delete the ticket list message to avoid duplication
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete ticket list message: {e}")
        
        # Log focus entry
        if focus_switched:
            logger.info(
                f"Employee {user_id} switched focus to ticket {ticket_id} "
                f"(previous: {previous_focused_ticket_id})"
            )
        else:
            logger.info(f"Employee {user_id} entered focus mode on ticket {ticket_id}")
        
    except Exception as e:
        logger.error(
            f"Error handling focus ticket callback: ticket_id={callback_data.ticket_id}, "
            f"user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        # Clear FSM state on error to prevent invalid states
        await state.clear()
        await callback.message.answer(
            "❌ Произошла ошибка при входе в режим фокуса.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.callback_query(TicketListCallback.filter(F.action == "filter"))
async def handle_ticket_filter_callback(
    callback: CallbackQuery,
    callback_data: TicketListCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle ticket type filter selection.
    
    Updates the ticket list to show only tickets of the selected type.
    Filter acts as toggle - clicking active filter disables it.
    
    Requirements: Active Tickets Filter
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        requested_filter = callback_data.filter_type or "all"
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Get current focus state
        current_state = await state.get_state()
        data = await state.get_data()
        focused_ticket_id = data.get("focused_ticket_id") if current_state == EmployeeStates.in_focus else None
        current_filter = data.get("active_filter", "all")
        
        # Toggle logic: if clicking on active filter, switch to "all"
        if current_filter == requested_filter:
            new_filter = "all"
        else:
            new_filter = requested_filter
        
        # Save new filter to state
        await state.update_data(active_filter=new_filter)
        
        # Get filtered tickets
        ticket_type_filter = None if new_filter == "all" else new_filter
        tickets = await get_employee_active_tickets(session, user_id, ticket_type_filter)
        
        # Format header text (even if no tickets)
        header_text = await employee_service.format_active_tickets_header(
            tickets_count=len(tickets),
            focused_ticket_id=focused_ticket_id,
            current_filter=new_filter
        )
        
        # Generate inline keyboard
        keyboard = await employee_service.get_active_tickets_keyboard(
            tickets=tickets,
            focused_ticket_id=focused_ticket_id,
            employee_id=user_id,
            session=session,
            current_filter=new_filter,
            current_page=0
        )
        
        # Edit message
        await callback.message.edit_text(
            header_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Employee {user_id} filtered tickets: filter={new_filter}, count={len(tickets)}"
        )
        
    except Exception as e:
        logger.error(
            f"Error handling ticket filter callback: filter={callback_data.filter_type}, "
            f"user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Произошла ошибка при фильтрации заявок",
            show_alert=True
        )


@router.callback_query(TicketListCallback.filter(F.action == "page"))
async def handle_ticket_page_callback(
    callback: CallbackQuery,
    callback_data: TicketListCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle ticket list pagination.
    
    Updates the ticket list to show the requested page.
    
    Requirements: Active Tickets Pagination
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        page = callback_data.page
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Get current focus state and active filter
        current_state = await state.get_state()
        data = await state.get_data()
        focused_ticket_id = data.get("focused_ticket_id") if current_state == EmployeeStates.in_focus else None
        filter_type = data.get("active_filter", "all")
        
        # Get filtered tickets
        ticket_type_filter = None if filter_type == "all" else filter_type
        tickets = await get_employee_active_tickets(session, user_id, ticket_type_filter)
        
        # Format header text
        header_text = await employee_service.format_active_tickets_header(
            tickets_count=len(tickets),
            focused_ticket_id=focused_ticket_id,
            current_filter=filter_type
        )
        
        # Generate inline keyboard
        keyboard = await employee_service.get_active_tickets_keyboard(
            tickets=tickets,
            focused_ticket_id=focused_ticket_id,
            employee_id=user_id,
            session=session,
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
            f"Employee {user_id} navigated to page {page}: filter={filter_type}"
        )
        
    except Exception as e:
        logger.error(
            f"Error handling ticket page callback: page={callback_data.page}, "
            f"user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Произошла ошибка при навигации",
            show_alert=True
        )


@router.callback_query(TicketActionCallback.filter(F.action == "back_to_list"))
async def handle_back_to_list_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle back to list navigation from ticket card.
    
    - Verifies user is staff member
    - Gets current focus state from FSM
    - Gets active tickets with get_employee_active_tickets()
    - Formats header with format_active_tickets_header()
    - Generates keyboard with get_active_tickets_keyboard()
    - Edits message to show list
    
    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Get current focus state from FSM
        current_state = await state.get_state()
        data = await state.get_data()
        focused_ticket_id = data.get("focused_ticket_id") if current_state == EmployeeStates.in_focus else None
        
        # Reset filter to "all" when returning to list
        await state.update_data(active_filter="all")
        
        # Get active tickets for employee (default: all types)
        tickets = await get_employee_active_tickets(session, user_id)
        
        if not tickets:
            await callback.message.edit_text(
                EMPLOYEE_NO_ACTIVE_TICKETS_TEXT
            )
            logger.info(f"Employee {user_id} has no active tickets when returning to list")
            return
        
        # Format header text
        header_text = await employee_service.format_active_tickets_header(
            tickets_count=len(tickets),
            focused_ticket_id=focused_ticket_id,
            current_filter="all"
        )
        
        # Generate inline keyboard with current ticket states
        keyboard = await employee_service.get_active_tickets_keyboard(
            tickets=tickets,
            focused_ticket_id=focused_ticket_id,
            employee_id=user_id,
            session=session,
            current_filter="all",
            current_page=0
        )
        
        # Edit message to show list (maintain same message)
        await callback.message.edit_text(
            header_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Employee {user_id} returned to active tickets list "
            f"({len(tickets)} tickets, focused_ticket_id={focused_ticket_id})"
        )
        
    except Exception as e:
        logger.error(
            f"Error handling back to list: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        # Clear FSM state on error to prevent invalid states
        await state.clear()
        await callback.message.answer(
            "❌ Произошла ошибка при возврате к списку заявок.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.message(StateFilter(None), F.text == BTN_EMPLOYEE_SETTINGS)
async def handle_settings_button(
    message: Message,
    session: AsyncSession
) -> None:
    """
    Handle "Settings" reply button press.
    
    Display employee settings.
    
    Requirements: 1.4, 16.1
    """
    logger.info(f"[STAFF HANDLER] handle_settings_button called for user {message.from_user.id}, text: {message.text}")
    
    try:
        user_id = message.from_user.id
        
        # Get employee record
        employee = await is_staff_member(session, user_id)
        if not employee:
            await message.answer(
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
        
        await message.answer(settings_text)
        
        logger.info(f"Employee {user_id} viewed settings")
        
    except Exception as e:
        logger.error(f"Error showing settings for user {message.from_user.id}: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при загрузке настроек.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.message(StateFilter(None), F.text == BTN_ARCHIVE_SEARCH)
async def handle_archive_search_button(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle "Archive Search" reply button press.
    
    Show archive with filters (day, week, month, custom search).
    
    Requirements: 1.3
    """
    logger.info(f"[STAFF HANDLER] handle_archive_search_button called for user {message.from_user.id}, text: {message.text}")
    
    try:
        user_id = message.from_user.id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Default filter: day
        current_filter = "day"
        current_page = 0
        
        # Get closed tickets by filter
        tickets = await employee_service.get_closed_tickets_by_filter(
            session=session,
            filter_type=current_filter
        )
        
        # Save filter to state
        await state.update_data(
            archive_filter=current_filter,
            archive_page=current_page,
            archive_tickets_count=len(tickets)
        )
        
        # Format header text
        header_text = await employee_service.format_archive_header(
            tickets_count=len(tickets),
            current_filter=current_filter
        )
        
        # Generate inline keyboard
        keyboard = await employee_service.get_archive_keyboard(
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
            f"Employee {user_id} opened archive "
            f"(filter={current_filter}, page={current_page}, tickets_count={len(tickets)})"
        )
        
    except Exception as e:
        logger.error(f"Error opening archive for user {message.from_user.id}: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при открытии архива.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.callback_query(ArchiveSearchCallback.filter(F.action == "filter"))
async def handle_archive_filter(
    callback: CallbackQuery,
    callback_data: ArchiveSearchCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle archive filter selection (day, week, month).
    
    Toggles filter on/off like active tickets filters.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        new_filter = callback_data.filter_type
        
        # Get current filter from state
        data = await state.get_data()
        current_filter = data.get("archive_filter", "day")
        
        # Toggle filter: if same filter clicked, keep it (filters don't toggle off in archive)
        # Just switch to the new filter
        current_filter = new_filter
        current_page = 0  # Reset to first page
        
        # Get closed tickets by filter
        tickets = await employee_service.get_closed_tickets_by_filter(
            session=session,
            filter_type=current_filter
        )
        
        # Save filter to state
        await state.update_data(
            archive_filter=current_filter,
            archive_page=current_page,
            archive_tickets_count=len(tickets)
        )
        
        # Format header text
        header_text = await employee_service.format_archive_header(
            tickets_count=len(tickets),
            current_filter=current_filter
        )
        
        # Generate inline keyboard
        keyboard = await employee_service.get_archive_keyboard(
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
            f"Employee {user_id} changed archive filter to {current_filter} "
            f"(tickets_count={len(tickets)})"
        )
        
    except Exception as e:
        logger.error(f"Error handling archive filter: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(ArchiveSearchCallback.filter(F.action == "custom_search"))
async def handle_archive_custom_search(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """
    Handle custom search button (magnifying glass).
    
    Shows search examples and sets state for custom search input.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Set FSM state for custom search
        await state.set_state(EmployeeStates.archive_custom_search)
        
        # Prepare search examples text
        text = (
            "🔍 <b>Произвольный поиск в архиве</b>\n\n"
            "<b>Примеры поисковых запросов:</b>\n\n"
            "• <code>123</code> или <code>#123</code> — поиск по номеру заявки\n"
            "• <code>Иван</code> — поиск по имени клиента\n"
            "• <code>2024-01-01 to 2024-01-31</code> — поиск по диапазону дат\n"
            "• <code>01.01.2024 по 31.01.2024</code> — поиск по диапазону дат (русский формат)\n\n"
            "Введите поисковый запрос:"
        )
        
        # Create keyboard with back button
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔙 Вернуться к архиву",
                callback_data=ArchiveSearchCallback(action="back_to_archive").pack()
            )]
        ])
        
        # Edit message
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Employee {user_id} opened custom search in archive")
        
    except Exception as e:
        logger.error(f"Error opening custom search: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.message(EmployeeStates.archive_custom_search, F.text)
async def execute_archive_custom_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Execute custom search in archive with provided criteria.
    """
    try:
        user_id = message.from_user.id
        search_criteria = message.text.strip()
        
        logger.info(f"Employee {user_id} executing custom search: {search_criteria}")
        
        # Search closed tickets
        tickets = await employee_service.search_closed_tickets(
            session=session,
            search_criteria=search_criteria
        )
        
        # Clear FSM state
        await state.clear()
        
        # Save search results to state
        current_filter = "custom"
        current_page = 0
        
        await state.update_data(
            archive_filter=current_filter,
            archive_page=current_page,
            archive_tickets_count=len(tickets),
            archive_search_criteria=search_criteria
        )
        
        # Format header text
        header_text = await employee_service.format_archive_header(
            tickets_count=len(tickets),
            current_filter=current_filter
        )
        
        # Add search criteria to header
        header_text += f"\nЗапрос: <code>{search_criteria}</code>\n"
        
        # Generate inline keyboard
        keyboard = await employee_service.get_archive_keyboard(
            tickets=tickets,
            current_filter=current_filter,
            current_page=current_page
        )
        
        # Send results
        await message.answer(
            header_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Employee {user_id} custom search completed: "
            f"criteria='{search_criteria}', found={len(tickets)}"
        )
        
    except Exception as e:
        logger.error(
            f"Error executing custom search: user={message.from_user.id}, "
            f"criteria={message.text}, error={e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при выполнении поиска.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.callback_query(ArchiveSearchCallback.filter(F.action == "back_to_archive"))
async def handle_back_to_archive(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Return to archive list from custom search input.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Clear custom search state
        await state.clear()
        
        # Get last filter from state or default to day
        data = await state.get_data()
        current_filter = data.get("archive_filter", "day")
        current_page = data.get("archive_page", 0)
        
        # Get closed tickets by filter
        tickets = await employee_service.get_closed_tickets_by_filter(
            session=session,
            filter_type=current_filter
        )
        
        # Save filter to state
        await state.update_data(
            archive_filter=current_filter,
            archive_page=current_page,
            archive_tickets_count=len(tickets)
        )
        
        # Format header text
        header_text = await employee_service.format_archive_header(
            tickets_count=len(tickets),
            current_filter=current_filter
        )
        
        # Generate inline keyboard
        keyboard = await employee_service.get_archive_keyboard(
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
        
        logger.info(f"Employee {user_id} returned to archive from custom search")
        
    except Exception as e:
        logger.error(f"Error returning to archive: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(ArchiveSearchCallback.filter(F.action == "cancel"))
async def handle_archive_cancel(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """
    Cancel archive operation - remove keyboard and clear state.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Clear state
        await state.clear()
        
        # Edit message to remove keyboard
        await callback.message.edit_text(
            "🗄 Архив обращений закрыт.",
            reply_markup=None
        )
        
        logger.info(f"Employee {user_id} cancelled archive operation")
        
    except Exception as e:
        logger.error(f"Error cancelling archive: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


# ========== Active Tickets Handler (removed - now using reply button) ==========


@router.callback_query(TicketActionCallback.filter(F.action == "back_to_ticket"))
async def back_to_focused_ticket(
    callback: CallbackQuery,
    callback_data: TicketActionCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Return to focused ticket from archive search or other flows.
    
    Restores focus mode and shows ticket management interface.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.answer("❌ У вас нет доступа к интерфейсу сотрудника.", show_alert=True)
            return
        
        # Get ticket from database with eager loading
        from sqlalchemy.orm import selectinload
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
        
        # Restore focus mode
        await state.set_state(EmployeeStates.in_focus)
        await state.update_data(
            focused_ticket_id=ticket_id,
            focused_client_id=ticket.user.tg_user_id
        )
        
        # Format ticket card and show management interface
        ticket_card = await format_ticket_card(ticket, session)
        keyboard = await get_ticket_action_keyboard(ticket)
        
        await callback.message.edit_text(
            f"{ticket_card}\n\nВыберите действие:",
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} returned to focused ticket {ticket_id}")
        
    except Exception as e:
        logger.error(f"Error returning to focused ticket: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(TicketActionCallback.filter(F.action == "take_ticket"))
async def take_ticket_into_work(
    callback: CallbackQuery,
    callback_data: TicketActionCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Take ticket into work.
    
    - Changes status from NEW to IN_PROGRESS
    - Stops escalation timer
    - Enters focus mode (switches focus if already in focus on another ticket)
    - Logs action
    
    Requirements: 3.4, 4.1, 4.6, 4.7, 12.2, 13.1, 13.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Check if already in focus mode on a different ticket
        current_state = await state.get_state()
        data = await state.get_data()
        previous_focused_ticket_id = data.get("focused_ticket_id")
        
        focus_switched = False
        if current_state == EmployeeStates.in_focus and previous_focused_ticket_id and previous_focused_ticket_id != ticket_id:
            focus_switched = True
            logger.info(
                f"Employee {user_id} switching focus from ticket {previous_focused_ticket_id} "
                f"to ticket {ticket_id}"
            )
        
        # Import service function (will be implemented in task 6)
        from services.ticket_service import take_ticket_into_work as take_ticket_service
        
        # Take ticket into work
        ticket = await take_ticket_service(session, ticket_id, user_id, messenger="telegram")
        
        # Enter focus mode (or switch focus)
        await state.set_state(EmployeeStates.in_focus)
        await state.update_data(
            focused_ticket_id=ticket_id,
            focused_client_id=ticket.user.tg_user_id
        )
        
        # Update ticket card
        ticket_card = await format_ticket_card(ticket, session)
        keyboard = await get_ticket_action_keyboard(ticket)
        
        await callback.message.edit_text(
            ticket_card,
            reply_markup=keyboard
        )
        
        # Inform employee about focus mode
        if focus_switched:
            await callback.message.answer(
                f"✅ Заявка взят в работу. Фокус переключен на тикет #{ticket_id}.\n"
                "Все ваши сообщения будут отправлены этому клиенту."
            )
        else:
            await callback.message.answer(
                "✅ Заявка взят в работу. Вы в режиме фокуса.\n"
                "Все ваши сообщения будут отправлены клиенту."
            )
        
        logger.info(f"Employee {user_id} took ticket {ticket_id} into work (focus_switched={focus_switched})")
        
    except Exception as e:
        logger.error(f"Error taking ticket into work: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при взятии заявки в работу.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.callback_query(TicketActionCallback.filter(F.action == "set_waiting"))
async def set_ticket_waiting(
    callback: CallbackQuery,
    callback_data: TicketActionCallback,
    session: AsyncSession
) -> None:
    """
    Set ticket status to WAITING_CLIENT.
    
    - Changes status to WAITING_CLIENT
    - Logs action
    - Updates ticket card
    
    Requirements: 3.6
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.answer("❌ У вас нет доступа к интерфейсу сотрудника.", show_alert=True)
            return
        
        # Delete old message
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message: {e}")
        
        # Import service function (will be implemented in task 6)
        from services.ticket_service import set_ticket_waiting_client
        
        # Set ticket to waiting for client
        ticket = await set_ticket_waiting_client(session, ticket_id, user_id, messenger="telegram")
        
        # Update ticket card
        ticket_card = await format_ticket_card(ticket, session)
        keyboard = await get_ticket_action_keyboard(ticket)
        
        await callback.message.answer(
            "⏳ Статус заявки изменен на 'Ожидание клиента'.\n\n" + ticket_card,
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} set ticket {ticket_id} to waiting for client")
        
    except Exception as e:
        logger.error(f"Error setting ticket to waiting: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при изменении статуса заявки.", show_alert=True)
        
        # Try to show ticket menu again
        try:
            from sqlalchemy.orm import selectinload
            stmt = select(Ticket).where(Ticket.id == callback_data.ticket_id).options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys)
            )
            result = await session.execute(stmt)
            ticket = result.scalar_one_or_none()
            
            if ticket:
                ticket_card = await format_ticket_card(ticket, session)
                keyboard = await get_ticket_action_keyboard(ticket)
                await callback.message.answer(ticket_card, reply_markup=keyboard)
        except Exception as inner_e:
            logger.error(f"Could not restore ticket menu: {inner_e}")


@router.callback_query(TicketActionCallback.filter(F.action == "close_ticket"))
async def initiate_ticket_close(
    callback: CallbackQuery,
    callback_data: TicketActionCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Initiate ticket closing flow.
    
    - Prompts for final comment
    - Sets FSM state to EmployeeStates.closing_ticket
    - Stores ticket_id in FSM data
    - Provides cancel button to return to ticket details
    
    Requirements: 3.5, 14.1
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Set FSM state
        await state.set_state(EmployeeStates.closing_ticket)
        await state.update_data(
            ticket_id=ticket_id,
            prompt_message_id=callback.message.message_id
        )
        
        # Create cancel button
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🔙 Отменить закрытие заявки",
            callback_data=TicketActionCallback(action="back_to_ticket", ticket_id=ticket_id)
        )
        
        await callback.message.edit_text(
            "✅ Закрытие заявки\n\n"
            "Пожалуйста, введите финальный комментарий для закрытия заявки.",
            reply_markup=builder.as_markup()
        )
        
        logger.info(f"Employee {user_id} initiated closing for ticket {ticket_id}")
        
    except Exception as e:
        logger.error(f"Error initiating ticket close: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при запуске закрытия заявки.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.callback_query(TicketActionCallback.filter(F.action == "transfer_ticket"))
async def initiate_ticket_transfer(
    callback: CallbackQuery,
    callback_data: TicketActionCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Initiate ticket transfer flow.
    
    - Queries available employees filtered by ticket type
    - Displays employee selection keyboard
    - Sets FSM state to EmployeeStates.transferring_ticket
    
    Requirements: 3.7, 8.1, 17.1, 17.2, 17.4, 17.5
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.answer("❌ У вас нет доступа к интерфейсу сотрудника.", show_alert=True)
            return
        
        # Delete old message
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message: {e}")
        
        # Get ticket with eager loading
        from database.models import Ticket
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        if not ticket:
            await callback.answer("❌ Заявка не найден.", show_alert=True)
            return
        
        # Import service function (will be implemented in task 8)
        from services.employee_service import get_available_employees_for_transfer
        
        # Get available employees for transfer
        available_employees = await get_available_employees_for_transfer(
            session, ticket, user_id
        )
        
        if not available_employees:
            await callback.answer("❌ Нет доступных сотрудников для передачи заявки.", show_alert=True)
            # Show ticket menu again
            ticket_card = await format_ticket_card(ticket, session)
            keyboard = await get_ticket_action_keyboard(ticket)
            await callback.message.answer(ticket_card, reply_markup=keyboard)
            return
        
        # Build employee selection keyboard
        from bots.tg_bot.callback_datas import EmployeeSelectionCallback
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        
        buttons = []
        for emp in available_employees:
            role_display = {
                "MANAGER": "Менеджер",
                "TECHNICAL_SUPPORT": "ТП",
                "DUTY_ENGINEER": "Дежурный инженер",
                "ADMINISTRATOR": "Администратор"
            }
            role_text = role_display.get(emp.staff_role.value, emp.staff_role.value)
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"{emp.full_name} ({role_text})",
                    callback_data=EmployeeSelectionCallback(
                        action="select",
                        employee_id=emp.id
                    ).pack()
                )
            ])
        
        # Add cancel button
        buttons.append([
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=EmployeeSelectionCallback(
                    action="cancel"
                ).pack()
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Set FSM state
        await state.set_state(EmployeeStates.transferring_ticket)
        await state.update_data(ticket_id=ticket_id)
        
        await callback.message.answer(
            "🔄 Передача заявки\n\n"
            "Выберите сотрудника для передачи заявки:",
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} initiated transfer for ticket {ticket_id}")
        
    except Exception as e:
        logger.error(f"Error initiating ticket transfer: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при передаче заявки.", show_alert=True)
        
        # Try to show ticket menu again
        try:
            from sqlalchemy.orm import selectinload
            stmt = select(Ticket).where(Ticket.id == callback_data.ticket_id).options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys)
            )
            result = await session.execute(stmt)
            ticket = result.scalar_one_or_none()
            
            if ticket:
                ticket_card = await format_ticket_card(ticket, session)
                keyboard = await get_ticket_action_keyboard(ticket)
                await callback.message.answer(ticket_card, reply_markup=keyboard)
        except Exception as inner_e:
            logger.error(f"Could not restore ticket menu: {inner_e}")
        logger.info(f"Employee {user_id} initiated transfer for ticket {ticket_id}")
        
    except Exception as e:
        logger.error(f"Error initiating ticket transfer: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при запуске передачи заявки.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.callback_query(TicketActionCallback.filter(F.action == "view_history"))
async def view_ticket_history(
    callback: CallbackQuery,
    callback_data: TicketActionCallback,
    session: AsyncSession
) -> None:
    """
    Display ticket history.
    
    - Queries all messages for ticket
    - Formats history with timestamps and senders
    - Shows file attachments
    - Paginates if necessary
    
    Requirements: 3.8, 9.1, 9.2, 9.3, 9.4, 9.5
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.answer("❌ У вас нет доступа к интерфейсу сотрудника.", show_alert=True)
            return
        
        # Delete old message
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message: {e}")
        
        # Import service function (will be implemented in task 10)
        from services.employee_service import format_ticket_history
        
        # Get ticket history
        history_text, has_more_pages = await format_ticket_history(
            session, ticket_id, page=0
        )
        
        # Build keyboard with pagination if needed
        from bots.tg_bot.callback_datas import TicketHistoryCallback
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        
        buttons = []
        
        # Navigation buttons
        if has_more_pages:
            buttons.append([
                InlineKeyboardButton(
                    text="Следующая ➡️",
                    callback_data=TicketHistoryCallback(
                        action="page",
                        ticket_id=ticket_id,
                        page=1
                    ).pack()
                )
            ])
        
        # Back button
        buttons.append([
            InlineKeyboardButton(
                text="🔙 Назад к заявке",
                callback_data=TicketHistoryCallback(
                    action="back",
                    ticket_id=ticket_id
                ).pack()
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.answer(
            history_text,
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} viewed history for ticket {ticket_id}")
        
    except Exception as e:
        logger.error(f"Error viewing ticket history: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при загрузке истории заявки.", show_alert=True)
        
        # Try to show ticket menu again
        try:
            from sqlalchemy.orm import selectinload
            stmt = select(Ticket).where(Ticket.id == callback_data.ticket_id).options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys)
            )
            result = await session.execute(stmt)
            ticket = result.scalar_one_or_none()
            
            if ticket:
                ticket_card = await format_ticket_card(ticket, session)
                keyboard = await get_ticket_action_keyboard(ticket)
                await callback.message.answer(ticket_card, reply_markup=keyboard)
        except Exception as inner_e:
            logger.error(f"Could not restore ticket menu: {inner_e}")


@router.callback_query(TicketActionCallback.filter(F.action == "exit_focus"))
async def exit_focus_mode(
    callback: CallbackQuery,
    callback_data: TicketActionCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Exit focus mode.

    - Clears FSM state
    - Updates active tickets list keyboard
    - Shows alert

    Requirements: Focus mode management
    """
    try:
        user_id = callback.from_user.id

        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.answer("❌ У вас нет доступа к интерфейсу сотрудника.", show_alert=True)
            return

        # Get current state data
        data = await state.get_data()
        focused_ticket_id = data.get("focused_ticket_id")

        # Clear FSM state
        await state.clear()

        # Get active tickets for updated keyboard
        tickets = await get_employee_active_tickets(session, user_id)
        
        if tickets:
            # Format header text
            header_text = await employee_service.format_active_tickets_header(
                tickets_count=len(tickets),
                focused_ticket_id=None,  # No focus anymore
                current_filter="all"
            )
            
            # Generate inline keyboard without focus
            keyboard = await employee_service.get_active_tickets_keyboard(
                tickets=tickets,
                focused_ticket_id=None,  # No focus anymore
                employee_id=user_id,
                session=session,
                current_filter="all",
                current_page=0
            )
            
            # Update message with new keyboard
            try:
                await callback.message.edit_text(
                    header_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not edit message: {e}")
                # If edit fails, send new message
                await callback.message.answer(
                    header_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )

        # Update Reply keyboard to remove "Exit Focus" button
        from bots.tg_bot.keyboards.manager_kb import get_manager_menu_keyboard
        is_admin = employee.staff_role == StaffRole.ADMINISTRATOR
        reply_keyboard = await get_manager_menu_keyboard(is_admin=is_admin, focused_ticket_id=None)

        await callback.answer("✅ Вы вышли из режима фокуса.", show_alert=True)

        logger.info(f"Employee {user_id} exited focus mode (was on ticket {focused_ticket_id})")

    except Exception as e:
        logger.error(f"Error exiting focus mode: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при выходе из режима фокуса.", show_alert=True)
        await state.clear()


@router.message(F.text.startswith("❌ Снять фокус с заявки #"))
async def exit_focus_from_reply_button(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle exit focus from Reply keyboard button.
    
    Requirements: Focus mode management
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await message.answer("❌ У вас нет доступа к интерфейсу сотрудника.")
            return
        
        # Get current state data
        data = await state.get_data()
        focused_ticket_id = data.get("focused_ticket_id")
        
        # Clear FSM state
        await state.clear()
        
        # Update Reply keyboard to remove "Exit Focus" button
        from bots.tg_bot.keyboards.manager_kb import get_manager_menu_keyboard
        is_admin = employee.staff_role == StaffRole.ADMINISTRATOR
        reply_keyboard = await get_manager_menu_keyboard(is_admin=is_admin, focused_ticket_id=None)
        
        await message.answer(
            # f"✅ Вы вышли из режима фокуса с заявки #{focused_ticket_id}.",
            f"✅ Вы вышли из режима фокуса с заявки",
            reply_markup=reply_keyboard
        )
        
        logger.info(f"Employee {user_id} exited focus mode via Reply button (was on ticket {focused_ticket_id})")
        
    except Exception as e:
        logger.error(f"Error exiting focus from reply button: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при выходе из режима фокуса.")
        await state.clear()


@router.callback_query(TicketHistoryCallback.filter(F.action == "page"))
async def handle_ticket_history_pagination(
    callback: CallbackQuery,
    callback_data: TicketHistoryCallback,
    session: AsyncSession
) -> None:
    """
    Handle ticket history pagination.
    
    Requirements: 9.1, 9.2, 9.3
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        page = callback_data.page
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.answer("❌ У вас нет доступа к интерфейсу сотрудника.", show_alert=True)
            return
        
        # Get ticket history for the requested page
        from services.employee_service import format_ticket_history
        
        history_text, has_more_pages = await format_ticket_history(
            session, ticket_id, page=page
        )
        
        # Build keyboard with pagination
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        
        buttons = []
        
        # Navigation buttons row
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Предыдущая",
                    callback_data=TicketHistoryCallback(
                        action="page",
                        ticket_id=ticket_id,
                        page=page - 1
                    ).pack()
                )
            )
        
        if has_more_pages:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="Следующая ➡️",
                    callback_data=TicketHistoryCallback(
                        action="page",
                        ticket_id=ticket_id,
                        page=page + 1
                    ).pack()
                )
            )
        
        if nav_buttons:
            buttons.append(nav_buttons)
        
        # Back button
        buttons.append([
            InlineKeyboardButton(
                text="🔙 Назад к заявке",
                callback_data=TicketHistoryCallback(
                    action="back",
                    ticket_id=ticket_id
                ).pack()
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Edit message with new page
        try:
            await callback.message.edit_text(
                history_text,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.warning(f"Could not edit message, sending new one: {e}")
            await callback.message.delete()
            await callback.message.answer(
                history_text,
                reply_markup=keyboard
            )
        
        logger.info(f"Employee {user_id} viewed history page {page} for ticket {ticket_id}")
        
    except Exception as e:
        logger.error(
            f"Error handling ticket history pagination: ticket_id={callback_data.ticket_id}, "
            f"page={callback_data.page}, user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при загрузке страницы истории.", show_alert=True)


@router.callback_query(TicketHistoryCallback.filter(F.action == "back"))
async def back_to_ticket_from_history(
    callback: CallbackQuery,
    callback_data: TicketHistoryCallback,
    session: AsyncSession
) -> None:
    """
    Return to ticket card from history view.
    
    Requirements: History navigation
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.answer("❌ У вас нет доступа к интерфейсу сотрудника.", show_alert=True)
            return
        
        # Delete history message
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message: {e}")
        
        # Get ticket with eager loading
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            await callback.answer("❌ Заявка не найден", show_alert=True)
            return
        
        # Show ticket card
        ticket_card = await format_ticket_card(ticket, session)
        keyboard = await get_ticket_action_keyboard(ticket)
        
        await callback.message.answer(
            ticket_card,
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} returned to ticket {ticket_id} from history")
        
    except Exception as e:
        logger.error(f"Error returning to ticket from history: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


async def exit_focus_mode_old(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Exit focus mode.

    - Clears FSM state
    - Returns to active tickets list

    Requirements: 3.9, 13.5, 14.6
    """
    await callback.answer()

    try:
        user_id = callback.from_user.id

        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return

        # Get current state data
        data = await state.get_data()
        focused_ticket_id = data.get("focused_ticket_id")

        # Clear FSM state
        await state.clear()

        await callback.message.answer(
            "❌ Вы вышли из режима фокуса.\n"
            "Показываю активные заявки..."
        )

        logger.info(f"Employee {user_id} exited focus mode (was on ticket {focused_ticket_id})")

        # Show active tickets list
        tickets = await get_employee_active_tickets(session, user_id)

        if not tickets:
            await callback.message.answer(
                EMPLOYEE_NO_ACTIVE_TICKETS_TEXT
            )
            return

        # Display active tickets
        await callback.message.answer(
            f"📥 Активные заявки ({len(tickets)}):"
        )

        for ticket in tickets:
            ticket_card = await format_ticket_card(ticket, session)
            keyboard = await get_ticket_action_keyboard(ticket)

            await callback.message.answer(
                ticket_card,
                reply_markup=keyboard
            )

    except Exception as e:
        logger.error(f"Error exiting focus mode: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при выходе из режима фокуса.\n"
            "Используйте /manager для возврата в меню."
        )



# ========== Ticket Closing Handler ==========


@router.message(EmployeeStates.closing_ticket, F.text)
async def complete_ticket_close(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Complete ticket closing with final comment.
    
    - Retrieves ticket_id from FSM
    - Stores final comment as message
    - Changes status to CLOSED
    - Sets closed_at timestamp
    - Logs action
    - Clears FSM state
    - Exits focus mode if active
    
    Requirements: 14.2, 14.5, 14.6, 14.7
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            await state.clear()
            return
        
        # Get ticket_id from FSM data
        data = await state.get_data()
        ticket_id = data.get("ticket_id")
        prompt_message_id = data.get("prompt_message_id")
        
        if not ticket_id:
            logger.error(f"Employee {user_id} in closing_ticket state but no ticket_id in FSM")
            await state.clear()
            await message.answer(
                "❌ Ошибка состояния. Пожалуйста, выберите тикет заново.\n"
                "Используйте /manager для возврата в меню."
            )
            return
        
        # Get final comment text
        final_comment = message.text.strip()
        
        if not final_comment:
            await message.answer(
                "❌ Финальный комментарий не может быть пустым.\n"
                "Пожалуйста, введите комментарий или используйте /cancel для отмены."
            )
            return
        
        # Import service function
        from services.ticket_service import close_ticket
        
        # Close ticket with final comment
        ticket = await close_ticket(session, ticket_id, user_id, final_comment, messenger="telegram")
        
        # Commit the transaction to ensure all changes are persisted
        await session.commit()
        
        # Reload ticket with all relationships to avoid greenlet errors
        from sqlalchemy.orm import selectinload
        from database.models import Ticket, User, GS_Key
        
        result = await session.execute(
            select(Ticket)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.gs_keys)
            )
            .where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one()
        
        # Clear FSM state (exits focus mode if active)
        await state.clear()
        
        # Edit the prompt message to show success
        if prompt_message_id:
            try:
                from aiogram import Bot
                bot = message.bot
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=prompt_message_id,
                    text="✅ Заявка успешно закрыта"
                )
            except Exception as e:
                logger.warning(f"Could not edit prompt message: {e}")
        
        # Update ticket card
        ticket_card = await format_ticket_card(ticket, session)
        
        await message.answer(
            f"{ticket_card}"
        )
        
        # Send notification to client
        try:
            client_user_id = ticket.user.tg_user_id
            if client_user_id:
                from aiogram import Bot
                bot = message.bot
                
                # Get employee name
                from database.models import Staff_Member
                result = await session.execute(
                    select(Staff_Member).where(Staff_Member.tg_user_id == user_id)
                )
                staff = result.scalar_one_or_none()
                employee_name = staff.full_name if staff else "Менеджер"
                employee_position = staff.position if staff else ""
                # Format ticket type
                ticket_type_str = "Счет" if ticket.ticket_type.value == "invoice" else "Техническая поддержка"
                
                await bot.send_message(
                    chat_id=client_user_id,
                    text=(
                        f"✅ Ваша заявка #{ticket.id} ({ticket_type_str}) была закрыта.\n\n"
                        f"{employee_name}, {employee_position}\n"
                        f"Комментарий: {final_comment}\n\n"
                        "Спасибо за обращение!"
                    )
                )
                logger.info(f"Sent ticket closure notification to client {client_user_id} for ticket {ticket_id}")
        except Exception as e:
            logger.error(f"Error sending closure notification to client: ticket_id={ticket_id}, error={e}", exc_info=True)
        
        await message.answer(
            "Используйте /manager для возврата в меню."
        )
        
        logger.info(f"Employee {user_id} closed ticket {ticket_id} with final comment")
        
    except Exception as e:
        logger.error(f"Error completing ticket close: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при закрытии заявки.\n"
            "Пожалуйста, попробуйте позже."
        )
        await state.clear()



# ========== Ticket Transfer Handler ==========


@router.callback_query(
    EmployeeStates.transferring_ticket,
    EmployeeSelectionCallback.filter(F.action == "select")
)
async def complete_ticket_transfer(
    callback: CallbackQuery,
    callback_data: EmployeeSelectionCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Complete ticket transfer to selected employee.
    
    - Retrieves ticket_id from FSM
    - Updates assigned_staff_id
    - Logs transfer action with source and target
    - Sends notification to target employee
    - Clears FSM state
    - Exits focus mode
    
    Requirements: 8.2, 8.3, 8.4, 8.5
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        target_employee_id = callback_data.employee_id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            await state.clear()
            return
        
        # Get ticket_id from FSM data
        data = await state.get_data()
        ticket_id = data.get("ticket_id")
        
        if not ticket_id:
            logger.error(f"Employee {user_id} in transferring_ticket state but no ticket_id in FSM")
            await state.clear()
            await callback.message.answer(
                "❌ Ошибка состояния. Пожалуйста, выберите тикет заново.\n"
                "Используйте /manager для возврата в меню."
            )
            return
        
        if not target_employee_id:
            logger.error(f"Employee {user_id} selected transfer but no target_employee_id")
            await state.clear()
            await callback.message.answer(
                "❌ Ошибка выбора сотрудника. Пожалуйста, попробуйте снова.\n"
                "Используйте /manager для возврата в меню."
            )
            return
        
        # Get target employee info (target_employee_id is internal Staff_Member.id)
        target_employee = await session.get(Staff_Member, target_employee_id)
        
        if not target_employee or not target_employee.is_active:
            logger.error(f"Target employee not found or inactive: employee_id={target_employee_id}")
            await state.clear()
            await callback.message.answer(
                "❌ Выбранный сотрудник не найден или неактивен.\n"
                "Используйте /manager для возврата в меню."
            )
            return
        
        if not target_employee.tg_user_id:
            logger.error(f"Target employee has no Telegram ID: employee_id={target_employee_id}")
            await state.clear()
            await callback.message.answer(
                "❌ У выбранного сотрудника нет Telegram ID.\n"
                "Используйте /manager для возврата в меню."
            )
            return
        
        # Import service function
        from services.ticket_service import transfer_ticket
        
        # Transfer ticket (service expects tg_user_id)
        ticket = await transfer_ticket(
            session,
            ticket_id,
            source_employee_id=user_id,
            target_employee_id=target_employee.tg_user_id,
            messenger="telegram"
        )
        
        # Clear FSM state (exits focus mode)
        await state.clear()
        
        # Notify source employee
        await callback.message.edit_text(
            f"✅ Заявка #{ticket_id} успешно передана сотруднику {target_employee.full_name}."
        )
        
        await callback.message.answer(
            "Используйте /manager для возврата в меню."
        )
        
        # Send notification to target employee with ticket card
        from services.ticket_service import send_ticket_transfer_notification
        
        await send_ticket_transfer_notification(
            bot=callback.bot,
            session=session,
            target_employee_id=target_employee.tg_user_id,
            ticket=ticket,
            source_employee_id=user_id
        )
        
        logger.info(
            f"Employee {user_id} transferred ticket {ticket_id} to employee {target_employee.tg_user_id} (internal_id={target_employee_id})"
        )
        
    except ValueError as e:
        logger.error(f"Validation error completing ticket transfer: {e}", exc_info=True)
        await callback.message.answer(
            "❌ Ошибка при передаче заявки. Проверьте данные и попробуйте снова."
        )
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error completing ticket transfer: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.message.answer(
            "❌ Произошла ошибка при передаче заявки.\n"
            "Пожалуйста, попробуйте позже."
        )
        await state.clear()


@router.callback_query(
    EmployeeStates.transferring_ticket,
    EmployeeSelectionCallback.filter(F.action == "cancel")
)
async def cancel_ticket_transfer(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """
    Cancel ticket transfer flow.
    
    - Clears FSM state
    - Returns to menu
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Clear FSM state
        await state.clear()
        
        await callback.message.edit_text(
            "❌ Передача заявки отменена.\n"
            "Используйте /manager для возврата в меню."
        )
        
        logger.info(f"Employee {user_id} cancelled ticket transfer")
        
    except Exception as e:
        logger.error(f"Error cancelling ticket transfer: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при отмене передачи.\n"
            "Используйте /manager для возврата в меню."
        )
        await state.clear()



# ========== Archive Search Handlers ==========


# ========== Archive Search Handlers (Old - Removed) ==========


@router.callback_query(ArchiveSearchCallback.filter(F.action == "page"))
async def archive_search_pagination(
    callback: CallbackQuery,
    callback_data: ArchiveSearchCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle pagination for archive results.
    
    Requirements: 11.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        page = callback_data.page
        filter_type = callback_data.filter_type or "day"
        
        # Get tickets based on filter
        if filter_type == "custom":
            # Get custom search results from state
            data = await state.get_data()
            search_criteria = data.get("archive_search_criteria", "")
            
            if not search_criteria:
                await callback.answer("❌ Контекст поиска потерян", show_alert=True)
                return
            
            tickets = await employee_service.search_closed_tickets(
                session=session,
                search_criteria=search_criteria
            )
        else:
            # Get tickets by time filter
            tickets = await employee_service.get_closed_tickets_by_filter(
                session=session,
                filter_type=filter_type
            )
        
        # Update state
        await state.update_data(
            archive_filter=filter_type,
            archive_page=page,
            archive_tickets_count=len(tickets)
        )
        
        # Format header text
        header_text = await employee_service.format_archive_header(
            tickets_count=len(tickets),
            current_filter=filter_type
        )
        
        # Add search criteria if custom
        if filter_type == "custom":
            data = await state.get_data()
            search_criteria = data.get("archive_search_criteria", "")
            header_text += f"\nЗапрос: <code>{search_criteria}</code>\n"
        
        # Generate inline keyboard
        keyboard = await employee_service.get_archive_keyboard(
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
            f"Archive pagination: user={user_id}, filter={filter_type}, page={page}"
        )
        
    except Exception as e:
        logger.error(
            f"Error paginating archive: user={callback.from_user.id}, "
            f"page={callback_data.page}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(ArchiveSearchCallback.filter(F.action == "view_ticket"))
async def view_archived_ticket(
    callback: CallbackQuery,
    callback_data: ArchiveSearchCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Display archived ticket with full details and message history.
    
    If message history exceeds 4096 characters, it's sent as a .txt file.
    
    Requirements: 11.5
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        logger.info(f"Employee {user_id} viewing archived ticket {ticket_id}")
        
        # Get ticket with eager loading
        from sqlalchemy.orm import selectinload
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
        
        # Verify ticket is closed
        if ticket.ticket_status not in [TicketStatus.CLOSED, TicketStatus.CANCELLED]:
            await callback.answer("❌ Эта заявка не закрыта", show_alert=True)
            return
        
        # Format full ticket details
        ticket_details = await employee_service.format_archived_ticket_details(
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
        current_filter = data.get("archive_filter", "day")
        current_page = data.get("archive_page", 0)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Назад к архиву",
                    callback_data=ArchiveSearchCallback(
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
            from io import BytesIO
            
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
                caption=f"📎 История переписки по заявке #{ticket_id}"
            )
        
        logger.info(
            f"Displayed archived ticket {ticket_id} for employee {user_id} "
            f"(history_length={len(message_history)}, sent_as_file={len(combined_text) > 4096})"
        )
        
    except Exception as e:
        logger.error(
            f"Error viewing archived ticket: user={callback.from_user.id}, "
            f"ticket_id={callback_data.ticket_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при просмотре заявки.", show_alert=True)


@router.callback_query(ArchiveSearchCallback.filter(F.action == "back_to_results"))
async def back_to_search_results(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Return to archive search results from archived ticket view.
    
    Requirements: AC-5.1, TR-6
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Get saved search context from FSM
        data = await state.get_data()
        search_query = data.get("search_criteria")
        search_results = data.get("search_results", [])
        current_page = data.get("current_page", 0)
        
        if not search_results:
            # If context is lost, return to menu
            await callback.answer("Контекст поиска потерян", show_alert=True)
            await back_from_archive_search(callback, state)
            return
        
        # Get tickets for current page from database
        page_size = 10
        total_tickets = len(search_results)
        total_pages = (total_tickets + page_size - 1) // page_size
        
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, total_tickets)
        page_ticket_ids = search_results[start_idx:end_idx]
        
        # Load tickets from DB
        from sqlalchemy import select
        from database.models import Ticket
        
        query = select(Ticket).where(Ticket.id.in_(page_ticket_ids)).order_by(Ticket.closed_at.desc())
        result = await session.execute(query)
        page_tickets = list(result.scalars().all())
        
        # Format results
        result_text = f"🗄 Результаты поиска\n\n"
        result_text += f"Найдено заявок: {total_tickets}\n"
        result_text += f"Страница {current_page + 1} из {total_pages}\n\n"
        
        # Add ticket list
        for ticket in page_tickets:
            # Get user info
            user = await session.get(User, ticket.user_id)
            client_name = user.full_name if user else "Неизвестный клиент"
            
            # Format ticket type
            ticket_type_str = "Счет" if ticket.ticket_type.value == "invoice" else "ТП"
            
            # Format status
            status_map = {
                "closed": "Закрыто",
                "cancelled": "Отменено"
            }
            status_str = status_map.get(ticket.ticket_status.value, ticket.ticket_status.value)
            
            # Format created date
            created_date_str = ticket.created_at.strftime("%d.%m.%Y")
            
            # Format closed date
            closed_date_str = "Не указано"
            if ticket.closed_at:
                closed_date_str = ticket.closed_at.strftime("%d.%m.%Y %H:%M")
            
            result_text += (
                f"#{ticket.id} | {ticket_type_str} | {client_name} | {created_date_str}\n"
                f"Закрыто: {closed_date_str} | Статус: {status_str}\n\n"
            )
        
        # Build keyboard with ticket selection and pagination
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard_buttons = []
        
        # Add ticket selection buttons (2 per row)
        ticket_buttons = []
        for ticket in page_tickets:
            ticket_buttons.append(
                InlineKeyboardButton(
                    text=f"#{ticket.id}",
                    callback_data=ArchiveSearchCallback(
                        action="view_ticket",
                        ticket_id=ticket.id
                    ).pack()
                )
            )
        
        # Arrange in rows of 2
        for i in range(0, len(ticket_buttons), 2):
            row = ticket_buttons[i:i+2]
            keyboard_buttons.append(row)
        
        # Add pagination buttons if needed
        if total_pages > 1:
            pagination_row = []
            
            if current_page > 0:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data=ArchiveSearchCallback(
                            action="page",
                            page=current_page - 1
                        ).pack()
                    )
                )
            
            if current_page < total_pages - 1:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="Вперед ▶️",
                        callback_data=ArchiveSearchCallback(
                            action="page",
                            page=current_page + 1
                        ).pack()
                    )
                )
            
            if pagination_row:
                keyboard_buttons.append(pagination_row)
        
        # Add back button
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="🔙 Назад в меню",
                callback_data=ArchiveSearchCallback(action="back").pack()
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            result_text,
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} returned to search results (page {current_page + 1}/{total_pages})")
        
    except Exception as e:
        logger.error(
            f"Error returning to search results: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("Ошибка при возврате к результатам", show_alert=True)


@router.callback_query(ArchiveSearchCallback.filter(F.action == "back"))
async def back_from_archive_search(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """
    Return to employee menu from archive search results page.
    
    Requirements: 11.6
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Clear FSM state
        await state.clear()
        
        # Show employee menu
        from bots.tg_bot.keyboards.employee_kb import get_employee_menu_keyboard
        
        keyboard = await get_employee_menu_keyboard(user_id)
        
        await callback.message.edit_text(
            "👔 Меню сотрудника\n\n"
            "Выберите действие:",
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} returned to menu from archive search")
        
    except Exception as e:
        logger.error(
            f"Error returning from archive search: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.message.answer(
            "❌ Произошла ошибка.\n"
            "Используйте /manager для возврата в меню."
        )
        await state.clear()

