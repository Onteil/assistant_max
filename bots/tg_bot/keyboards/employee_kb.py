"""
Employee Interface Keyboards

Клавиатуры для интерфейса сотрудника.
Включает главное меню сотрудника, действия с заявкими, выбор сотрудников для передачи.
"""

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bots.tg_bot.callback_datas import (
    EmployeeMenuCallback,
    EmployeeSelectionCallback,
    TicketActionCallback,
    TicketHistoryCallback,
)
from bots.tg_bot.texts import (
    BTN_ACTIVE_TICKETS,
    BTN_ADMIN_PANEL,
    BTN_ARCHIVE_SEARCH,
    BTN_BACK,
    BTN_CANCEL,
    BTN_CLOSE_TICKET,
    BTN_EMPLOYEE_SETTINGS,
    BTN_EXIT_FOCUS,
    BTN_NEXT_PAGE,
    BTN_PREVIOUS_PAGE,
    BTN_SET_WAITING,
    BTN_TAKE_TICKET,
    BTN_TRANSFER_TICKET,
    BTN_VIEW_HISTORY,
)


async def get_employee_menu_keyboard(is_admin: bool = False):
    """
    Создает главное меню сотрудника.
    
    Args:
        is_admin: Флаг, является ли сотрудник администратором
    
    Returns:
        InlineKeyboardMarkup с кнопками меню сотрудника
    
    Requirements: 1.1, 1.5, 1.6
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Активные заявки"
    builder.button(
        text=BTN_ACTIVE_TICKETS,
        callback_data=EmployeeMenuCallback(action="active_tickets")
    )
    
    # Кнопка "Архив обращений"
    builder.button(
        text=BTN_ARCHIVE_SEARCH,
        callback_data=EmployeeMenuCallback(action="archive_search")
    )
    
    # # Кнопка "Настройки"
    # builder.button(
    #     text=BTN_EMPLOYEE_SETTINGS,
    #     callback_data=EmployeeMenuCallback(action="settings")
    # )
    
    # Кнопка "Админ-панель" только для администраторов
    if is_admin:
        builder.button(
            text=BTN_ADMIN_PANEL,
            callback_data=EmployeeMenuCallback(action="admin_panel")
        )
    
    # Размещаем по 2 кнопки в ряду
    builder.adjust(2)
    
    return builder.as_markup()


async def get_ticket_action_keyboard(ticket_id: int, status: str):
    """
    Создает клавиатуру с действиями для заявки в зависимости от статуса.
    
    Args:
        ticket_id: ID заявки
        status: Текущий статус заявки (NEW, IN_PROGRESS, WAITING_CLIENT)
    
    Returns:
        InlineKeyboardMarkup с кнопками действий для заявки
    
    Requirements: 3.1, 3.2, 3.3
    """
    builder = InlineKeyboardBuilder()
    
    if status == "NEW":
        # Кнопки для нового заявки
        builder.button(
            text=BTN_TAKE_TICKET,
            callback_data=TicketActionCallback(action="take_ticket", ticket_id=ticket_id)
        )
        builder.button(
            text=BTN_TRANSFER_TICKET,
            callback_data=TicketActionCallback(action="transfer_ticket", ticket_id=ticket_id)
        )
        builder.button(
            text=BTN_VIEW_HISTORY,
            callback_data=TicketActionCallback(action="view_history", ticket_id=ticket_id)
        )
        builder.button(
            text=BTN_EXIT_FOCUS,
            callback_data=TicketActionCallback(action="exit_focus", ticket_id=ticket_id)
        )
        builder.adjust(1, 1, 1, 1)
    
    elif status == "IN_PROGRESS":
        # Кнопки для заявки в работе
        builder.button(
            text=BTN_CLOSE_TICKET,
            callback_data=TicketActionCallback(action="close_ticket", ticket_id=ticket_id)
        )
        builder.button(
            text=BTN_SET_WAITING,
            callback_data=TicketActionCallback(action="set_waiting", ticket_id=ticket_id)
        )
        builder.button(
            text=BTN_TRANSFER_TICKET,
            callback_data=TicketActionCallback(action="transfer_ticket", ticket_id=ticket_id)
        )
        builder.button(
            text=BTN_VIEW_HISTORY,
            callback_data=TicketActionCallback(action="view_history", ticket_id=ticket_id)
        )
        builder.button(
            text=BTN_EXIT_FOCUS,
            callback_data=TicketActionCallback(action="exit_focus", ticket_id=ticket_id)
        )
        builder.adjust(2, 1, 1, 1)
    
    elif status == "WAITING_CLIENT":
        # Кнопки для заявки в ожидании клиента
        builder.button(
            text=BTN_CLOSE_TICKET,
            callback_data=TicketActionCallback(action="close_ticket", ticket_id=ticket_id)
        )
        builder.button(
            text=BTN_TRANSFER_TICKET,
            callback_data=TicketActionCallback(action="transfer_ticket", ticket_id=ticket_id)
        )
        builder.button(
            text=BTN_VIEW_HISTORY,
            callback_data=TicketActionCallback(action="view_history", ticket_id=ticket_id)
        )
        builder.button(
            text=BTN_EXIT_FOCUS,
            callback_data=TicketActionCallback(action="exit_focus", ticket_id=ticket_id)
        )
        builder.adjust(1, 1, 1, 1)
    
    return builder.as_markup()


async def get_employee_selection_keyboard(employees: list):
    """
    Создает клавиатуру для выбора сотрудника при передаче заявки.
    
    Args:
        employees: Список сотрудников (объекты Staff_Member)
    
    Returns:
        InlineKeyboardMarkup с кнопками выбора сотрудника
    
    Requirements: 8.1, 17.3
    """
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопку для каждого сотрудника
    for employee in employees:
        button_text = f"{employee.full_name} ({employee.staff_role.value})"
        builder.button(
            text=button_text,
            callback_data=EmployeeSelectionCallback(
                action="select",
                employee_id=employee.id
            )
        )
    
    # Кнопка отмены
    builder.button(
        text=BTN_CANCEL,
        callback_data=EmployeeSelectionCallback(action="cancel")
    )
    
    # Размещаем по 1 кнопке в ряду для читаемости
    builder.adjust(1)
    
    return builder.as_markup()


async def get_ticket_history_keyboard(ticket_id: int, page: int = 0, has_more: bool = False):
    """
    Создает клавиатуру для пагинации истории заявки.
    
    Args:
        ticket_id: ID заявки
        page: Текущая страница
        has_more: Есть ли еще страницы
    
    Returns:
        InlineKeyboardMarkup с кнопками пагинации
    
    Requirements: 9.6
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Назад" если не первая страница
    if page > 0:
        builder.button(
            text=BTN_PREVIOUS_PAGE,
            callback_data=TicketHistoryCallback(
                action="page",
                ticket_id=ticket_id,
                page=page - 1
            )
        )
    
    # Кнопка "Вперед" если есть еще страницы
    if has_more:
        builder.button(
            text=BTN_NEXT_PAGE,
            callback_data=TicketHistoryCallback(
                action="page",
                ticket_id=ticket_id,
                page=page + 1
            )
        )
    
    # Кнопка "Назад к заявке"
    builder.button(
        text=BTN_BACK,
        callback_data=TicketHistoryCallback(
            action="back",
            ticket_id=ticket_id,
            page=0
        )
    )
    
    # Размещаем кнопки пагинации в один ряд, кнопку "Назад" отдельно
    if page > 0 and has_more:
        builder.adjust(2, 1)
    else:
        builder.adjust(1, 1)
    
    return builder.as_markup()


async def get_active_tickets_list_keyboard(tickets: list):
    """
    Создает клавиатуру со списком активных заявок.
    
    Args:
        tickets: Список заявок
    
    Returns:
        InlineKeyboardMarkup с кнопками заявок
    
    Requirements: 10.1, 10.2, 10.4
    """
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопку для каждого заявки
    for ticket in tickets:
        ticket_type = "💰" if ticket.ticket_type.value == "INVOICE" else "🆘"
        button_text = f"{ticket_type} #{ticket.id} - {ticket.client.full_name}"
        builder.button(
            text=button_text,
            callback_data=TicketActionCallback(
                action="view_ticket",
                ticket_id=ticket.id
            )
        )
    
    # Размещаем по 1 кнопке в ряду
    builder.adjust(1)
    
    return builder.as_markup()
