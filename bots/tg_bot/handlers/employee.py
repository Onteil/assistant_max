"""
Employee Interface Handlers

Handles employee menu navigation, ticket management, and employee settings.
Implements the employee workplace interface for managing customer support tickets.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 16.1
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import (
    ArchiveSearchCallback,
    EmployeeMenuCallback,
    EmployeeSelectionCallback,
    TicketActionCallback,
)
from bots.tg_bot.keyboards.employee_kb import get_employee_menu_keyboard
from bots.tg_bot.states import EmployeeStates
from bots.tg_bot.texts import (
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


@router.message(Command("employee"))
async def show_employee_menu(
    message: Message,
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
    try:
        user_id = message.from_user.id
        
        # Check if user is a staff member
        employee = await is_staff_member(session, user_id)
        
        if not employee:
            await message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника.\n"
                "Используйте /start для доступа к клиентскому интерфейсу."
            )
            logger.warning(f"Non-staff user {user_id} attempted to access employee menu")
            return
        
        # Generate menu keyboard based on employee role
        is_admin = employee.staff_role == StaffRole.ADMINISTRATOR
        keyboard = await get_employee_menu_keyboard(is_admin=is_admin)
        
        await message.answer(
            EMPLOYEE_MENU_TEXT,
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} ({employee.full_name}) accessed employee menu")
        
    except Exception as e:
        logger.error(f"Error showing employee menu for user {message.from_user.id}: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при загрузке меню.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Active Tickets Handler ==========


@router.callback_query(EmployeeMenuCallback.filter(F.action == "active_tickets"))
async def show_active_tickets(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Display list of active tickets assigned to employee.
    
    Queries tickets with status NEW, IN_PROGRESS, or WAITING_CLIENT.
    Shows ticket cards with inline action buttons.
    Indicates which ticket is currently in focus (if any).
    
    Requirements: 1.2, 13.2
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
        
        # Get current focus state
        current_state = await state.get_state()
        data = await state.get_data()
        focused_ticket_id = data.get("focused_ticket_id") if current_state == EmployeeStates.in_focus else None
        
        # Get active tickets for employee
        tickets = await get_employee_active_tickets(session, user_id)
        
        if not tickets:
            await callback.message.edit_text(
                EMPLOYEE_NO_ACTIVE_TICKETS_TEXT
            )
            logger.info(f"Employee {user_id} has no active tickets")
            return
        
        # Display header with focus indicator
        header_text = f"📥 Активные тикеты ({len(tickets)})"
        if focused_ticket_id:
            header_text += f"\n🎯 В фокусе: Тикет #{focused_ticket_id}"
        
        await callback.message.edit_text(header_text)
        
        # Display each ticket as a card with action buttons
        for ticket in tickets:
            # Add focus indicator to ticket card if this is the focused ticket
            ticket_card = await format_ticket_card(ticket, session)
            if focused_ticket_id and ticket.id == focused_ticket_id:
                ticket_card = f"🎯 **В ФОКУСЕ**\n\n{ticket_card}"
            
            keyboard = await get_ticket_action_keyboard(ticket)
            
            await callback.message.answer(
                ticket_card,
                reply_markup=keyboard
            )
        
        logger.info(
            f"Employee {user_id} viewed {len(tickets)} active tickets "
            f"(focused_ticket_id={focused_ticket_id})"
        )
        
    except Exception as e:
        logger.error(f"Error showing active tickets for user {callback.from_user.id}: {e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при загрузке активных тикетов.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Settings Handler ==========


@router.callback_query(EmployeeMenuCallback.filter(F.action == "settings"))
async def show_employee_settings(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Display employee settings.
    
    Shows employee's full name, position, role, and formatted signature.
    
    Requirements: 1.4, 16.1
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Get employee record
        employee = await is_staff_member(session, user_id)
        if not employee:
            await callback.message.answer(
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
        
        await callback.message.edit_text(settings_text)
        
        logger.info(f"Employee {user_id} viewed settings")
        
    except Exception as e:
        logger.error(f"Error showing settings for user {callback.from_user.id}: {e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при загрузке настроек.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Archive Search Handler ==========


@router.callback_query(EmployeeMenuCallback.filter(F.action == "archive_search"))
async def initiate_archive_search(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """
    Initiate archive search flow.
    
    Prompts for search criteria (ticket number, client name, or date range).
    Sets FSM state to EmployeeStates.searching_archive.
    
    Requirements: 1.3
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Set FSM state
        await state.set_state(EmployeeStates.searching_archive)
        
        await callback.message.edit_text(
            "🗄 Поиск в архиве обращений\n\n"
            "Введите критерий поиска:\n"
            "• Номер тикета (например: 123)\n"
            "• Имя клиента (например: Иван)\n"
            "• Диапазон дат (например: 2024-01-01 to 2024-01-31)\n\n"
            "Для отмены используйте /cancel"
        )
        
        logger.info(f"Employee {user_id} initiated archive search")
        
    except Exception as e:
        logger.error(f"Error initiating archive search for user {callback.from_user.id}: {e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при запуске поиска.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Ticket Action Handlers ==========


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
        ticket = await take_ticket_service(session, ticket_id, user_id)
        
        # Enter focus mode (or switch focus)
        await state.set_state(EmployeeStates.in_focus)
        await state.update_data(
            focused_ticket_id=ticket_id,
            focused_client_id=ticket.tg_user_id
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
                f"✅ Тикет взят в работу. Фокус переключен на тикет #{ticket_id}.\n"
                "Все ваши сообщения будут отправлены этому клиенту."
            )
        else:
            await callback.message.answer(
                "✅ Тикет взят в работу. Вы в режиме фокуса.\n"
                "Все ваши сообщения будут отправлены клиенту."
            )
        
        logger.info(f"Employee {user_id} took ticket {ticket_id} into work (focus_switched={focus_switched})")
        
    except Exception as e:
        logger.error(f"Error taking ticket into work: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при взятии тикета в работу.\n"
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
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Import service function (will be implemented in task 6)
        from services.ticket_service import set_ticket_waiting_client
        
        # Set ticket to waiting for client
        ticket = await set_ticket_waiting_client(session, ticket_id, user_id)
        
        # Update ticket card
        ticket_card = await format_ticket_card(ticket, session)
        keyboard = await get_ticket_action_keyboard(ticket)
        
        await callback.message.edit_text(
            ticket_card,
            reply_markup=keyboard
        )
        
        await callback.message.answer(
            "⏳ Статус тикета изменен на 'Ожидание клиента'."
        )
        
        logger.info(f"Employee {user_id} set ticket {ticket_id} to waiting for client")
        
    except Exception as e:
        logger.error(f"Error setting ticket to waiting: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при изменении статуса тикета.\n"
            "Пожалуйста, попробуйте позже."
        )


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
        await state.update_data(ticket_id=ticket_id)
        
        await callback.message.answer(
            "✅ Закрытие тикета\n\n"
            "Пожалуйста, введите финальный комментарий для закрытия тикета.\n\n"
            "Для отмены используйте /cancel"
        )
        
        logger.info(f"Employee {user_id} initiated closing for ticket {ticket_id}")
        
    except Exception as e:
        logger.error(f"Error initiating ticket close: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при запуске закрытия тикета.\n"
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
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
        # Get ticket
        from database.models import Ticket
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            await callback.message.answer("❌ Тикет не найден.")
            return
        
        # Import service function (will be implemented in task 8)
        from services.employee_service import get_available_employees_for_transfer
        
        # Get available employees for transfer
        available_employees = await get_available_employees_for_transfer(
            session, ticket, user_id
        )
        
        if not available_employees:
            await callback.message.answer(
                "❌ Нет доступных сотрудников для передачи тикета."
            )
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
                        employee_id=emp.tg_user_id
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
            "🔄 Передача тикета\n\n"
            "Выберите сотрудника для передачи тикета:",
            reply_markup=keyboard
        )
        
        logger.info(f"Employee {user_id} initiated transfer for ticket {ticket_id}")
        
    except Exception as e:
        logger.error(f"Error initiating ticket transfer: ticket_id={callback_data.ticket_id}, user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при запуске передачи тикета.\n"
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
            await callback.message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            return
        
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
        if has_more_pages:
            buttons.append([
                InlineKeyboardButton(
                    text="➡️ Следующая страница",
                    callback_data=TicketHistoryCallback(
                        action="page",
                        ticket_id=ticket_id,
                        page=1
                    ).pack()
                )
            ])
        
        buttons.append([
            InlineKeyboardButton(
                text="🔙 Назад к тикету",
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
        await callback.message.answer(
            "❌ Произошла ошибка при загрузке истории тикета.\n"
            "Пожалуйста, попробуйте позже."
        )


async def exit_focus_mode(
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
            "Показываю активные тикеты..."
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
            f"📥 Активные тикеты ({len(tickets)}):"
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
            "Используйте /employee для возврата в меню."
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
        
        if not ticket_id:
            logger.error(f"Employee {user_id} in closing_ticket state but no ticket_id in FSM")
            await state.clear()
            await message.answer(
                "❌ Ошибка состояния. Пожалуйста, выберите тикет заново.\n"
                "Используйте /employee для возврата в меню."
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
        ticket = await close_ticket(session, ticket_id, user_id, final_comment)
        
        # Clear FSM state (exits focus mode if active)
        await state.clear()
        
        # Update ticket card
        ticket_card = await format_ticket_card(ticket, session)
        
        await message.answer(
            "✅ Тикет успешно закрыт.\n\n"
            f"{ticket_card}"
        )
        
        await message.answer(
            "Используйте /employee для возврата в меню."
        )
        
        logger.info(f"Employee {user_id} closed ticket {ticket_id} with final comment")
        
    except Exception as e:
        logger.error(f"Error completing ticket close: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при закрытии тикета.\n"
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
                "Используйте /employee для возврата в меню."
            )
            return
        
        if not target_employee_id:
            logger.error(f"Employee {user_id} selected transfer but no target_employee_id")
            await state.clear()
            await callback.message.answer(
                "❌ Ошибка выбора сотрудника. Пожалуйста, попробуйте снова.\n"
                "Используйте /employee для возврата в меню."
            )
            return
        
        # Import service function
        from services.ticket_service import transfer_ticket
        
        # Transfer ticket
        ticket = await transfer_ticket(
            session,
            ticket_id,
            source_employee_id=user_id,
            target_employee_id=target_employee_id
        )
        
        # Get target employee info for notification
        target_employee = await session.get(Staff_Member, target_employee_id)
        
        # Clear FSM state (exits focus mode)
        await state.clear()
        
        # Notify source employee
        await callback.message.edit_text(
            f"✅ Тикет #{ticket_id} успешно передан сотруднику {target_employee.full_name}."
        )
        
        await callback.message.answer(
            "Используйте /employee для возврата в меню."
        )
        
        # Send notification to target employee with ticket card
        from services.ticket_service import send_ticket_transfer_notification
        
        await send_ticket_transfer_notification(
            bot=callback.bot,
            session=session,
            target_employee_id=target_employee_id,
            ticket=ticket,
            source_employee_id=user_id
        )
        
        logger.info(
            f"Employee {user_id} transferred ticket {ticket_id} to employee {target_employee_id}"
        )
        
    except ValueError as e:
        logger.error(f"Validation error completing ticket transfer: {e}", exc_info=True)
        await callback.message.answer(
            "❌ Ошибка при передаче тикета. Проверьте данные и попробуйте снова."
        )
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error completing ticket transfer: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.message.answer(
            "❌ Произошла ошибка при передаче тикета.\n"
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
            "❌ Передача тикета отменена.\n"
            "Используйте /employee для возврата в меню."
        )
        
        logger.info(f"Employee {user_id} cancelled ticket transfer")
        
    except Exception as e:
        logger.error(f"Error cancelling ticket transfer: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при отмене передачи.\n"
            "Используйте /employee для возврата в меню."
        )
        await state.clear()



# ========== Archive Search Handlers ==========


@router.message(EmployeeStates.searching_archive, F.text)
async def execute_archive_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Execute archive search with provided criteria.
    
    - Parses search criteria
    - Queries closed tickets matching criteria
    - Displays results with pagination
    - Clears FSM state
    
    Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
    """
    try:
        user_id = message.from_user.id
        search_criteria = message.text.strip()
        
        logger.info(f"Employee {user_id} searching archive with criteria: {search_criteria}")
        
        # Search closed tickets
        tickets = await employee_service.search_closed_tickets(
            session=session,
            search_criteria=search_criteria
        )
        
        # Clear FSM state
        await state.clear()
        
        # Handle no results
        if not tickets:
            await message.answer(
                "🗄 Результаты поиска\n\n"
                "Тикеты не найдены.\n\n"
                "Попробуйте изменить критерии поиска:\n"
                "• Проверьте правильность номера тикета\n"
                "• Используйте частичное совпадение имени\n"
                "• Проверьте формат даты (YYYY-MM-DD to YYYY-MM-DD)\n\n"
                "Используйте /employee для возврата в меню."
            )
            logger.info(f"No tickets found for criteria: {search_criteria}")
            return
        
        # Paginate results (10 per page)
        page_size = 10
        total_tickets = len(tickets)
        total_pages = (total_tickets + page_size - 1) // page_size
        
        # Show first page
        page = 0
        start_idx = page * page_size
        end_idx = min(start_idx + page_size, total_tickets)
        page_tickets = tickets[start_idx:end_idx]
        
        # Format results
        result_text = f"🗄 Результаты поиска\n\n"
        result_text += f"Найдено тикетов: {total_tickets}\n"
        result_text += f"Страница {page + 1} из {total_pages}\n\n"
        
        # Add ticket list
        for ticket in page_tickets:
            # Get user info
            user = await session.get(User, ticket.tg_user_id)
            client_name = user.full_name if user else "Неизвестный клиент"
            
            # Format ticket type
            ticket_type_str = "Счет" if ticket.ticket_type.value == "invoice" else "ТП"
            
            # Format status
            status_map = {
                "closed": "Закрыто",
                "cancelled": "Отменено"
            }
            status_str = status_map.get(ticket.ticket_status.value, ticket.ticket_status.value)
            
            # Format closed date
            closed_date_str = "Не указано"
            if ticket.closed_at:
                closed_date_str = ticket.closed_at.strftime("%d.%m.%Y %H:%M")
            
            result_text += (
                f"#{ticket.id} | {ticket_type_str} | {client_name}\n"
                f"Закрыто: {closed_date_str} | Статус: {status_str}\n\n"
            )
        
        # Build keyboard with ticket selection and pagination
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from bots.tg_bot.callback_datas import ArchiveSearchCallback
        
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
            
            if page > 0:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data=ArchiveSearchCallback(
                            action="page",
                            page=page - 1
                        ).pack()
                    )
                )
            
            if page < total_pages - 1:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="Вперед ▶️",
                        callback_data=ArchiveSearchCallback(
                            action="page",
                            page=page + 1
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
        
        # Store search results in FSM for pagination
        await state.update_data(
            search_criteria=search_criteria,
            search_results=[t.id for t in tickets]
        )
        
        await message.answer(
            result_text,
            reply_markup=keyboard
        )
        
        logger.info(
            f"Displayed archive search results: user={user_id}, "
            f"total={total_tickets}, page={page + 1}/{total_pages}"
        )
        
    except Exception as e:
        logger.error(
            f"Error executing archive search: user={message.from_user.id}, "
            f"criteria={message.text}, error={e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при поиске.\n"
            "Пожалуйста, попробуйте позже или используйте /employee для возврата в меню."
        )
        await state.clear()


@router.callback_query(ArchiveSearchCallback.filter(F.action == "page"))
async def archive_search_pagination(
    callback: CallbackQuery,
    callback_data: ArchiveSearchCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle pagination for archive search results.
    
    Requirements: 11.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        page = callback_data.page
        
        # Get search results from FSM
        data = await state.get_data()
        ticket_ids = data.get("search_results", [])
        search_criteria = data.get("search_criteria", "")
        
        if not ticket_ids:
            await callback.message.edit_text(
                "❌ Результаты поиска не найдены.\n"
                "Используйте /employee для возврата в меню."
            )
            return
        
        # Get tickets from database
        from sqlalchemy import select
        from database.models import Ticket
        
        query = select(Ticket).where(Ticket.id.in_(ticket_ids)).order_by(Ticket.closed_at.desc())
        result = await session.execute(query)
        tickets = list(result.scalars().all())
        
        # Paginate
        page_size = 10
        total_tickets = len(tickets)
        total_pages = (total_tickets + page_size - 1) // page_size
        
        # Validate page number
        if page < 0 or page >= total_pages:
            await callback.answer("❌ Неверная страница", show_alert=True)
            return
        
        start_idx = page * page_size
        end_idx = min(start_idx + page_size, total_tickets)
        page_tickets = tickets[start_idx:end_idx]
        
        # Format results
        result_text = f"🗄 Результаты поиска\n\n"
        result_text += f"Найдено тикетов: {total_tickets}\n"
        result_text += f"Страница {page + 1} из {total_pages}\n\n"
        
        # Add ticket list
        for ticket in page_tickets:
            # Get user info
            user = await session.get(User, ticket.tg_user_id)
            client_name = user.full_name if user else "Неизвестный клиент"
            
            # Format ticket type
            ticket_type_str = "Счет" if ticket.ticket_type.value == "invoice" else "ТП"
            
            # Format status
            status_map = {
                "closed": "Закрыто",
                "cancelled": "Отменено"
            }
            status_str = status_map.get(ticket.ticket_status.value, ticket.ticket_status.value)
            
            # Format closed date
            closed_date_str = "Не указано"
            if ticket.closed_at:
                closed_date_str = ticket.closed_at.strftime("%d.%m.%Y %H:%M")
            
            result_text += (
                f"#{ticket.id} | {ticket_type_str} | {client_name}\n"
                f"Закрыто: {closed_date_str} | Статус: {status_str}\n\n"
            )
        
        # Build keyboard
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
        
        # Add pagination buttons
        if total_pages > 1:
            pagination_row = []
            
            if page > 0:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data=ArchiveSearchCallback(
                            action="page",
                            page=page - 1
                        ).pack()
                    )
                )
            
            if page < total_pages - 1:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="Вперед ▶️",
                        callback_data=ArchiveSearchCallback(
                            action="page",
                            page=page + 1
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
        
        logger.info(
            f"Displayed archive search page: user={user_id}, page={page + 1}/{total_pages}"
        )
        
    except Exception as e:
        logger.error(
            f"Error paginating archive search: user={callback.from_user.id}, "
            f"page={callback_data.page}, error={e}",
            exc_info=True
        )
        await callback.message.answer(
            "❌ Произошла ошибка при переключении страницы.\n"
            "Используйте /employee для возврата в меню."
        )


@router.callback_query(ArchiveSearchCallback.filter(F.action == "view_ticket"))
async def view_archived_ticket(
    callback: CallbackQuery,
    callback_data: ArchiveSearchCallback,
    session: AsyncSession
) -> None:
    """
    Display archived ticket in read-only mode.
    
    Requirements: 11.5
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        ticket_id = callback_data.ticket_id
        
        logger.info(f"Employee {user_id} viewing archived ticket {ticket_id}")
        
        # Get ticket
        ticket = await session.get(Ticket, ticket_id)
        
        if not ticket:
            await callback.answer("❌ Тикет не найден", show_alert=True)
            return
        
        # Verify ticket is closed
        if ticket.ticket_status not in [TicketStatus.CLOSED, TicketStatus.CANCELLED]:
            await callback.answer("❌ Этот тикет не закрыт", show_alert=True)
            return
        
        # Format ticket card (read-only, no action buttons)
        ticket_card = await employee_service.format_ticket_card(
            ticket=ticket,
            session=session
        )
        
        # Add read-only indicator
        ticket_card = "📋 АРХИВНЫЙ ТИКЕТ (только просмотр)\n\n" + ticket_card
        
        # Build keyboard with only history and back buttons
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from bots.tg_bot.callback_datas import TicketHistoryCallback
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📁 История",
                    callback_data=TicketHistoryCallback(
                        action="page",
                        ticket_id=ticket_id,
                        page=0
                    ).pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад к результатам",
                    callback_data=ArchiveSearchCallback(action="back").pack()
                )
            ]
        ])
        
        await callback.message.edit_text(
            ticket_card,
            reply_markup=keyboard
        )
        
        logger.info(f"Displayed archived ticket {ticket_id} for employee {user_id}")
        
    except Exception as e:
        logger.error(
            f"Error viewing archived ticket: user={callback.from_user.id}, "
            f"ticket_id={callback_data.ticket_id}, error={e}",
            exc_info=True
        )
        await callback.message.answer(
            "❌ Произошла ошибка при просмотре тикета.\n"
            "Используйте /employee для возврата в меню."
        )


@router.callback_query(ArchiveSearchCallback.filter(F.action == "back"))
async def back_from_archive_search(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """
    Return to employee menu from archive search.
    
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
            "Используйте /employee для возврата в меню."
        )
        await state.clear()
