"""
Escalation Keyboards

Клавиатуры для раздела эскалаций в административной панели.
Включает список эскалаций, карточку эскалации с действиями и выбор сотрудника для переназначения.
"""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from bots.tg_bot.callback_datas import EscalationCallback, AdminMenuCallback


async def get_escalations_list_keyboard(
    escalations: list,
    page: int = 0,
    page_size: int = 5
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру со списком активных эскалаций с пагинацией.
    
    Args:
        escalations: Список объектов Escalation с загруженными relationships (ticket, ticket.user, ticket.assigned_to)
        page: Номер текущей страницы (начиная с 0)
        page_size: Количество эскалаций на странице
    
    Returns:
        InlineKeyboardMarkup со списком эскалаций и навигацией
    
    Requirements: 3.1
    
    Layout:
    [🔥 Заявка #123 - Клиент - 25 мин]
    [🔥 Заявка #124 - Клиент - 30 мин]
    ...
    [◀️ Назад] [Страница X/Y] [Вперед ▶️]
    [🔙 К админ-панели]
    """
    builder = InlineKeyboardBuilder()
    
    # Calculate pagination
    total_escalations = len(escalations)
    total_pages = (total_escalations + page_size - 1) // page_size if total_escalations > 0 else 1
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_escalations)
    
    # Add escalation buttons for current page
    for escalation in escalations[start_idx:end_idx]:
        ticket = escalation.ticket
        
        # Calculate time elapsed in minutes
        time_elapsed = int((datetime.now() - ticket.created_at).total_seconds() / 60)
        
        # Format button text
        button_text = f"🔥 Заявка #{ticket.id} - {ticket.user.full_name} - {time_elapsed} мин"
        
        builder.button(
            text=button_text,
            callback_data=EscalationCallback(
                action="view",
                escalation_id=escalation.id,
                ticket_id=ticket.id
            )
        )
    
    # Adjust to one button per row for escalation list
    builder.adjust(1)
    
    # Add pagination controls if needed
    if total_pages > 1:
        pagination_row = []
        
        # Previous page button
        if page > 0:
            builder.button(
                text="◀️ Назад",
                callback_data=EscalationCallback(
                    action="list",
                    page=page - 1
                )
            )
            pagination_row.append(1)
        
        # Page indicator (non-clickable, but we need a callback)
        builder.button(
            text=f"Страница {page + 1}/{total_pages}",
            callback_data=EscalationCallback(
                action="list",
                page=page
            )
        )
        pagination_row.append(1)
        
        # Next page button
        if page < total_pages - 1:
            builder.button(
                text="Вперед ▶️",
                callback_data=EscalationCallback(
                    action="list",
                    page=page + 1
                )
            )
            pagination_row.append(1)
        
        # Adjust pagination buttons to be in one row
        builder.adjust(*pagination_row)
    
    # Back to admin panel button (separate row)
    builder.button(
        text="🔙 К админ-панели",
        callback_data=AdminMenuCallback(action="back_to_main")
    )
    builder.adjust(1)  # Ensure back button is on its own row
    
    return builder.as_markup()


async def get_escalation_card_keyboard(
    escalation_id: int,
    ticket_id: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с действиями для карточки эскалации.
    
    Args:
        escalation_id: ID эскалации
        ticket_id: ID заявки
    
    Returns:
        InlineKeyboardMarkup с кнопками действий
    
    Requirements: 3.1
    
    Layout:
    [➡️ Переназначить] [🙋‍♂️ Взять на себя]
    [📞 Позвонить сотруднику]
    [🔙 К списку эскалаций]
    """
    builder = InlineKeyboardBuilder()
    
    # Reassign button
    builder.button(
        text="➡️ Переназначить",
        callback_data=EscalationCallback(
            action="reassign",
            escalation_id=escalation_id,
            ticket_id=ticket_id
        )
    )
    
    # Take over button
    builder.button(
        text="🙋‍♂️ Взять на себя",
        callback_data=EscalationCallback(
            action="take_over",
            escalation_id=escalation_id,
            ticket_id=ticket_id
        )
    )
    
    # Contact staff button
    # builder.button(
    #     text="📞 Позвонить сотруднику",
    #     callback_data=EscalationCallback(
    #         action="contact",
    #         escalation_id=escalation_id,
    #         ticket_id=ticket_id
    #     )
    # )
    
    # Back to list button
    builder.button(
        text="🔙 К списку эскалаций",
        callback_data=EscalationCallback(action="list")
    )
    
    # Layout: 2 buttons in first row, 1 in second, 1 in third
    builder.adjust(2, 1, 1)
    
    return builder.as_markup()


async def get_staff_selection_keyboard(
    escalation_id: int,
    ticket_id: int,
    staff_members: list,
    page: int = 0,
    page_size: int = 10
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для выбора сотрудника при переназначении с пагинацией.
    
    Args:
        escalation_id: ID эскалации
        ticket_id: ID заявки
        staff_members: Список объектов Staff_Member
        page: Номер текущей страницы (начиная с 0)
        page_size: Количество сотрудников на странице
    
    Returns:
        InlineKeyboardMarkup со списком сотрудников и навигацией
    
    Requirements: 3.1
    
    Layout:
    [👤 Имя Сотрудника 1 - Роль]
    [👤 Имя Сотрудника 2 - Роль]
    ...
    [◀️ Назад] [Страница X/Y] [Вперед ▶️]
    [🔙 Назад к эскалации]
    """
    builder = InlineKeyboardBuilder()
    
    # Calculate pagination
    total_staff = len(staff_members)
    total_pages = (total_staff + page_size - 1) // page_size if total_staff > 0 else 1
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_staff)
    
    # Role display names
    role_display = {
        "MANAGER": "Менеджер",
        "TECHNICAL_SUPPORT": "Техподдержка",
        "DUTY_ENGINEER": "Дежурный инженер",
        "ADMINISTRATOR": "Администратор"
    }
    
    # Add staff buttons for current page
    for staff in staff_members[start_idx:end_idx]:
        role_text = role_display.get(staff.staff_role.value, staff.staff_role.value)
        button_text = f"👤 {staff.full_name} - {role_text}"
        
        builder.button(
            text=button_text,
            callback_data=EscalationCallback(
                action="select_staff",
                escalation_id=escalation_id,
                ticket_id=ticket_id,
                staff_id=staff.id
            )
        )
    
    # Adjust to one button per row for staff list
    builder.adjust(1)
    
    # Add pagination controls if needed
    if total_pages > 1:
        # Previous page button
        if page > 0:
            builder.button(
                text="◀️ Назад",
                callback_data=EscalationCallback(
                    action="reassign",
                    escalation_id=escalation_id,
                    ticket_id=ticket_id,
                    page=page - 1
                )
            )
        
        # Page indicator
        builder.button(
            text=f"Страница {page + 1}/{total_pages}",
            callback_data=EscalationCallback(
                action="reassign",
                escalation_id=escalation_id,
                ticket_id=ticket_id,
                page=page
            )
        )
        
        # Next page button
        if page < total_pages - 1:
            builder.button(
                text="Вперед ▶️",
                callback_data=EscalationCallback(
                    action="reassign",
                    escalation_id=escalation_id,
                    ticket_id=ticket_id,
                    page=page + 1
                )
            )
    
    # Back to escalation card button
    builder.button(
        text="🔙 Назад к эскалации",
        callback_data=EscalationCallback(
            action="view",
            escalation_id=escalation_id,
            ticket_id=ticket_id
        )
    )
    
    return builder.as_markup()
