"""
Admin Panel Keyboards

Клавиатуры для административной панели.
Включает главное меню админ-панели и все подменю для управления сотрудниками,
операциями, календарем, настройками и аналитикой.
"""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bots.tg_bot.callback_datas import AdminMenuCallback


async def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """
    Создает главное меню административной панели.
    
    Returns:
        InlineKeyboardMarkup с кнопками главного меню админ-панели
    
    Requirements: 1.3
    
    Layout:
    [👥 Сотрудники] [📋 Операции]
    [📅 График работы] [⚙️ Настройки]
    [📊 Статистика]
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Сотрудники"
    builder.button(
        text="👥 Сотрудники",
        callback_data=AdminMenuCallback(action="employees")
    )
    
    # Кнопка "Операции"
    builder.button(
        text="📋 Операции",
        callback_data=AdminMenuCallback(action="operations")
    )
    
    # Кнопка "График работы"
    builder.button(
        text="📅 График работы",
        callback_data=AdminMenuCallback(action="calendar")
    )
    
    # Кнопка "Настройки"
    builder.button(
        text="⚙️ Настройки",
        callback_data=AdminMenuCallback(action="settings")
    )
    
    # Кнопка "Статистика"
    builder.button(
        text="📊 Статистика",
        callback_data=AdminMenuCallback(action="analytics")
    )
    
    # Размещаем по 2 кнопки в ряду, последняя кнопка отдельно
    builder.adjust(2, 2, 1)
    
    return builder.as_markup()


async def get_cancel_keyboard(action: str = "employees", employee_id: int | None = None) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопкой отмены/возврата.
    
    Args:
        action: Действие для возврата (по умолчанию "employees")
        employee_id: ID сотрудника для возврата к карточке (опционально)
    
    Returns:
        InlineKeyboardMarkup с кнопкой "Назад"
    """
    from bots.tg_bot.callback_datas import EmployeeCallback
    
    builder = InlineKeyboardBuilder()
    
    if action == "view_employee" and employee_id:
        builder.button(
            text="🔙 Назад",
            callback_data=EmployeeCallback(action="view", employee_id=employee_id)
        )
    else:
        builder.button(
            text="🔙 Назад",
            callback_data=AdminMenuCallback(action=action)
        )
    
    return builder.as_markup()


async def get_role_selection_keyboard(
    employee_id: int | None = None,
    current_role: str | None = None
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для выбора роли сотрудника.
    
    Args:
        employee_id: ID сотрудника (опционально, для редактирования существующего)
        current_role: Текущая роль сотрудника (опционально, для отметки галочкой)
    
    Returns:
        InlineKeyboardMarkup с кнопками выбора роли
    
    Requirements: 2.5, 2.6
    
    Layout:
    [Менеджер] [Техподдержка]
    [Дежурный инженер] [Администратор]
    [🔙 Назад]
    """
    from bots.tg_bot.callback_datas import EmployeeRoleCallback
    
    builder = InlineKeyboardBuilder()
    
    # Mapping role keys to display names
    roles = [
        ("manager", "Менеджер"),
        ("technical_support", "Техподдержка"),
        ("duty_engineer", "Дежурный инженер"),
        ("administrator", "Администратор")
    ]
    
    for role_key, role_label in roles:
        # Add checkmark to current role
        button_text = f"✓ {role_label}" if role_key == current_role else role_label
        
        builder.button(
            text=button_text,
            callback_data=EmployeeRoleCallback(
                role=role_key,
                employee_id=employee_id
            )
        )
    
    # Кнопка "Назад" (отмена операции - возврат к карточке сотрудника)
    if employee_id:
        from bots.tg_bot.callback_datas import EmployeeCallback
        builder.button(
            text="🔙 Назад",
            callback_data=EmployeeCallback(action="view", employee_id=employee_id)
        )
    else:
        # Если нет employee_id (добавление нового), возврат к меню сотрудников
        from bots.tg_bot.callback_datas import AdminMenuCallback
        builder.button(
            text="🔙 Назад",
            callback_data=AdminMenuCallback(action="employees")
        )
    
    # Размещаем по 2 кнопки в ряду, последняя кнопка отдельно
    builder.adjust(2, 2, 1)
    
    return builder.as_markup()


async def get_employee_list_keyboard(
    employees: list,
    page: int = 0,
    page_size: int = 5
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру со списком сотрудников с пагинацией.
    
    Args:
        employees: Список объектов Staff_Member
        page: Номер текущей страницы (начиная с 0)
        page_size: Количество сотрудников на странице
    
    Returns:
        InlineKeyboardMarkup со списком сотрудников и навигацией
    
    Requirements: 3.1, 3.2
    
    Layout:
    [👤 Имя Сотрудника 1 - Роль]
    [👤 Имя Сотрудника 2 - Роль]
    ...
    [◀️ Назад] [Страница X/Y] [Вперед ▶️]
    [🔙 К меню сотрудников]
    """
    from bots.tg_bot.callback_datas import EmployeeCallback
    
    builder = InlineKeyboardBuilder()
    
    # Calculate pagination
    total_employees = len(employees)
    total_pages = (total_employees + page_size - 1) // page_size if total_employees > 0 else 1
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_employees)
    
    # Add employee buttons for current page
    for employee in employees[start_idx:end_idx]:
        # Role display names - map enum values to Russian text
        role_display = {
            "manager": "Менеджер",
            "technical_support": "Техподдержка",
            "duty_engineer": "Дежурный инженер",
            "administrator": "Администратор"
        }
        
        role_text = role_display.get(employee.staff_role.value, employee.staff_role.value)
        
        # Add deactivation marker if employee is not active
        status_emoji = "🚫 " if not employee.is_active else ""
        button_text = f"{status_emoji}👤 {employee.full_name} - {role_text}"
        
        builder.button(
            text=button_text,
            callback_data=EmployeeCallback(
                action="view",
                employee_id=employee.id
            )
        )
    
    # Adjust to one button per row for employee list
    builder.adjust(1)
    
    # Add pagination controls if needed
    if total_pages > 1:
        pagination_row = []
        
        # Previous page button
        if page > 0:
            pagination_row.append(
                builder.button(
                    text="◀️ Назад",
                    callback_data=EmployeeCallback(
                        action="list",
                        page=page - 1
                    )
                )
            )
        
        # Page indicator
        pagination_row.append(
            builder.button(
                text=f"Страница {page + 1}/{total_pages}",
                callback_data=EmployeeCallback(
                    action="list",
                    page=page
                )
            )
        )
        
        # Next page button
        if page < total_pages - 1:
            pagination_row.append(
                builder.button(
                    text="Вперед ▶️",
                    callback_data=EmployeeCallback(
                        action="list",
                        page=page + 1
                    )
                )
            )
    
    # Back to employees menu button (always on separate row)
    builder.row(
        InlineKeyboardButton(
            text="🔙 К меню сотрудников",
            callback_data=AdminMenuCallback(action="employees").pack()
        )
    )
    
    return builder.as_markup()


async def get_employee_card_keyboard(
    employee,
    is_duty_support: bool = False,
    is_duty_manager: bool = False
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с действиями для карточки сотрудника.
    
    Args:
        employee: Объект Staff_Member
        is_duty_support: Whether this employee is the designated duty support account (ТП)
        is_duty_manager: Whether this employee is the designated duty manager account
    
    Returns:
        InlineKeyboardMarkup с кнопками действий
    
    Requirements: 4.4, 4.5, 4.6, 4.7, 7.1 (Duty Support Configuration)
    
    Layout (for MANAGER):
    [✏️ Изменить имя] [✏️ Изменить подпись]
    [🎭 Сменить роль] [🛡 Настроить резервы]
    [⚙️ Дежурный аккаунт ТП] [⚙️ Дежурный аккаунт менеджеров]
    [👤 Передать всех клиентов]
    [🚫 Деактивировать]
    [🔙 К списку]
    
    Layout (for other roles):
    [✏️ Изменить имя] [✏️ Изменить подпись]
    [🎭 Сменить роль] [🛡 Настроить резервы]
    [⚙️ Дежурный аккаунт ТП] [⚙️ Дежурный аккаунт менеджеров]
    [🚫 Деактивировать]
    [🔙 К списку]
    """
    from bots.tg_bot.callback_datas import EmployeeCallback
    from database.models import StaffRole
    
    builder = InlineKeyboardBuilder()
    
    # Edit name button
    builder.button(
        text="✏️ Изменить имя",
        callback_data=EmployeeCallback(
            action="edit_name",
            employee_id=employee.id
        )
    )
    
    # Edit signature button
    builder.button(
        text="✏️ Изменить подпись",
        callback_data=EmployeeCallback(
            action="edit_signature",
            employee_id=employee.id
        )
    )
    
    # Change role button
    builder.button(
        text="🎭 Сменить роль",
        callback_data=EmployeeCallback(
            action="edit_role",
            employee_id=employee.id
        )
    )
    
    # Configure backups button
    builder.button(
        text="🛡 Настроить резервы",
        callback_data=EmployeeCallback(
            action="backups",
            employee_id=employee.id
        )
    )
    
    # Duty support toggle button (ТП)
    if is_duty_support:
        builder.button(
            text="✅ Дежурный аккаунт ТП",
            callback_data=EmployeeCallback(
                action="unset_duty_support",
                employee_id=employee.id
            )
        )
    else:
        builder.button(
            text="⚙️ Дежурный аккаунт ТП",
            callback_data=EmployeeCallback(
                action="set_duty_support",
                employee_id=employee.id
            )
        )
    
    # Duty manager toggle button
    if is_duty_manager:
        builder.button(
            text="✅ Дежурный аккаунт менеджеров",
            callback_data=EmployeeCallback(
                action="unset_duty_manager",
                employee_id=employee.id
            )
        )
    else:
        builder.button(
            text="⚙️ Дежурный аккаунт менеджеров",
            callback_data=EmployeeCallback(
                action="set_duty_manager",
                employee_id=employee.id
            )
        )
    
    # Transfer all clients button - only for MANAGER role
    if employee.staff_role == StaffRole.MANAGER:
        builder.button(
            text="👤 Передать всех клиентов",
            callback_data=EmployeeCallback(
                action="transfer_clients",
                employee_id=employee.id
            )
        )
    
    # Deactivate/Activate button based on current status
    if employee.is_active:
        builder.button(
            text="🚫 Деактивировать",
            callback_data=EmployeeCallback(
                action="deactivate",
                employee_id=employee.id
            )
        )
    else:
        builder.button(
            text="✅ Активировать",
            callback_data=EmployeeCallback(
                action="activate",
                employee_id=employee.id
            )
        )
    
    # Back to list button
    builder.button(
        text="🔙 К списку",
        callback_data=EmployeeCallback(action="list")
    )
    
    # Layout: 2 buttons per row for edit buttons, then 1 per row for duty/transfer/deactivate/back
    if employee.staff_role == StaffRole.MANAGER:
        builder.adjust(2, 2, 1, 1, 1, 1, 1)
    else:
        builder.adjust(2, 2, 1, 1, 1, 1)
    
    return builder.as_markup()



async def get_backup_manager_keyboard(
    employee,
    available_staff: list
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для настройки резервных менеджеров.
    
    Показывает текущие назначения и кнопки выбора для каждого слота.
    
    Args:
        employee: Объект Staff_Member
        available_staff: Список доступных сотрудников для назначения
    
    Returns:
        InlineKeyboardMarkup с кнопками настройки резервов
    
    Requirements: 6.1, 6.2, 6.3
    
    Layout:
    [Резерв 1: Текущий менеджер или "Не назначен"]
    [Выбрать резерв 1] [Удалить резерв 1]
    
    [Резерв 2: Текущий менеджер или "Не назначен"]
    [Выбрать резерв 2] [Удалить резерв 2]
    
    [🔙 Назад к карточке]
    """
    from bots.tg_bot.callback_datas import BackupManagerCallback, EmployeeCallback
    
    builder = InlineKeyboardBuilder()
    
    # Slot 1 section
    if employee.backup_manager_1_id:
        # Find backup manager 1 in available staff
        backup_1 = next(
            (s for s in available_staff if s.id == employee.backup_manager_1_id),
            None
        )
        backup_1_text = backup_1.full_name if backup_1 else "Неизвестно"
        
        builder.button(
            text=f"✅ Резерв 1: {backup_1_text}",
            callback_data=BackupManagerCallback(
                action="view",
                employee_id=employee.id,
                slot=1
            )
        )
    else:
        builder.button(
            text="⚠️ Резерв 1: Не назначен",
            callback_data=BackupManagerCallback(
                action="view",
                employee_id=employee.id,
                slot=1
            )
        )
    
    # Slot 1 action buttons
    builder.button(
        text="Выбрать резерв 1",
        callback_data=BackupManagerCallback(
            action="select_slot",
            employee_id=employee.id,
            slot=1
        )
    )
    
    if employee.backup_manager_1_id:
        builder.button(
            text="Удалить резерв 1",
            callback_data=BackupManagerCallback(
                action="remove",
                employee_id=employee.id,
                slot=1
            )
        )
    
    # Slot 2 section
    if employee.backup_manager_2_id:
        # Find backup manager 2 in available staff
        backup_2 = next(
            (s for s in available_staff if s.id == employee.backup_manager_2_id),
            None
        )
        backup_2_text = backup_2.full_name if backup_2 else "Неизвестно"
        
        builder.button(
            text=f"✅ Резерв 2: {backup_2_text}",
            callback_data=BackupManagerCallback(
                action="view",
                employee_id=employee.id,
                slot=2
            )
        )
    else:
        builder.button(
            text="⚠️ Резерв 2: Не назначен",
            callback_data=BackupManagerCallback(
                action="view",
                employee_id=employee.id,
                slot=2
            )
        )
    
    # Slot 2 action buttons
    builder.button(
        text="Выбрать резерв 2",
        callback_data=BackupManagerCallback(
            action="select_slot",
            employee_id=employee.id,
            slot=2
        )
    )
    
    if employee.backup_manager_2_id:
        builder.button(
            text="Удалить резерв 2",
            callback_data=BackupManagerCallback(
                action="remove",
                employee_id=employee.id,
                slot=2
            )
        )
    
    # Back button
    builder.button(
        text="🔙 Назад к карточке",
        callback_data=EmployeeCallback(
            action="view",
            employee_id=employee.id
        )
    )
    
    # Layout: 1 button per row for status, 2 buttons for actions
    # Adjust based on whether delete buttons are present
    if employee.backup_manager_1_id and employee.backup_manager_2_id:
        # Both slots have backups: 1, 2, 1, 2, 1
        builder.adjust(1, 2, 1, 2, 1)
    elif employee.backup_manager_1_id:
        # Only slot 1 has backup: 1, 2, 1, 1, 1
        builder.adjust(1, 2, 1, 1, 1)
    elif employee.backup_manager_2_id:
        # Only slot 2 has backup: 1, 1, 1, 2, 1
        builder.adjust(1, 1, 1, 2, 1)
    else:
        # No backups: 1, 1, 1, 1, 1
        builder.adjust(1, 1, 1, 1, 1)
    
    return builder.as_markup()


async def get_backup_manager_selection_keyboard(
    employee_id: int,
    slot: int,
    available_staff: list
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для выбора резервного менеджера из списка.
    
    Args:
        employee_id: ID сотрудника, для которого настраиваются резервы
        slot: Номер слота (1 или 2)
        available_staff: Список доступных сотрудников
    
    Returns:
        InlineKeyboardMarkup со списком сотрудников
    
    Requirements: 8.7
    """
    from bots.tg_bot.callback_datas import BackupManagerCallback
    
    builder = InlineKeyboardBuilder()
    
    # Add button for each available staff member
    for staff in available_staff:
        # Role display names - map enum values to Russian text
        role_display = {
            "manager": "Менеджер",
            "technical_support": "Техподдержка",
            "duty_engineer": "Дежурный инженер",
            "administrator": "Администратор"
        }
        
        role_text = role_display.get(staff.staff_role.value, staff.staff_role.value)
        button_text = f"{staff.full_name} - {role_text}"
        
        builder.button(
            text=button_text,
            callback_data=BackupManagerCallback(
                action="assign",
                employee_id=employee_id,
                slot=slot,
                backup_id=staff.id
            )
        )
    
    # Cancel button
    builder.button(
        text="🔙 Назад",
        callback_data=BackupManagerCallback(
            action="back_to_config",
            employee_id=employee_id
        )
    )
    
    # One button per row
    builder.adjust(1)
    
    return builder.as_markup()


async def get_deactivation_confirmation_keyboard(
    employee_id: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру подтверждения деактивации сотрудника.
    
    Args:
        employee_id: ID сотрудника для деактивации
    
    Returns:
        InlineKeyboardMarkup с кнопками подтверждения
    
    Requirements: 7.3, 7.4
    
    Layout:
    [✅ Да, деактивировать] [❌ Отмена]
    """
    from bots.tg_bot.callback_datas import EmployeeCallback
    
    builder = InlineKeyboardBuilder()
    
    # Confirm button
    builder.button(
        text="✅ Да, деактивировать",
        callback_data=EmployeeCallback(
            action="confirm_deactivate",
            employee_id=employee_id
        )
    )
    
    # Cancel button - return to employee card
    builder.button(
        text="❌ Отмена",
        callback_data=EmployeeCallback(
            action="view",
            employee_id=employee_id
        )
    )
    
    # Two buttons in one row
    builder.adjust(2)
    
    return builder.as_markup()


async def get_client_transfer_confirmation_keyboard(
    source_employee_id: int,
    target_employee_id: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру подтверждения передачи клиентов.
    
    Args:
        source_employee_id: ID менеджера-источника
        target_employee_id: ID менеджера-получателя
    
    Returns:
        InlineKeyboardMarkup с кнопками подтверждения
    
    Requirements: 9.8, 9.9
    
    Layout:
    [✅ Да, передать] [❌ Отмена]
    """
    from bots.tg_bot.callback_datas import EmployeeCallback
    
    builder = InlineKeyboardBuilder()
    
    # Confirm button - we'll encode both IDs in a special action
    builder.button(
        text="✅ Да, передать",
        callback_data=EmployeeCallback(
            action="confirm_transfer",
            employee_id=source_employee_id,
            page=target_employee_id  # Using page field to pass target_employee_id
        )
    )
    
    # Cancel button - return to source employee card
    builder.button(
        text="❌ Отмена",
        callback_data=EmployeeCallback(
            action="view",
            employee_id=source_employee_id
        )
    )
    
    # Two buttons in one row
    builder.adjust(2)
    
    return builder.as_markup()


# ========== Broadcast Keyboards ==========


async def get_broadcast_targeting_keyboard() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для выбора целевой аудитории рассылки.
    
    Returns:
        InlineKeyboardMarkup с кнопками выбора целевой аудитории
    
    Requirements: 10.2, 10.3
    
    Layout:
    [Всем]
    [С активной подпиской]
    [Только согласившимся на маркетинг]
    [❌ Отмена]
    """
    from bots.tg_bot.callback_datas import BroadcastCallback
    
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Всем"
    builder.button(
        text="Всем",
        callback_data=BroadcastCallback(action="target", target="all")
    )
    
    # Кнопка "С активной подпиской"
    builder.button(
        text="С активной подпиской",
        callback_data=BroadcastCallback(action="target", target="active_subscription")
    )
    
    # Кнопка "Только согласившимся на маркетинг"
    builder.button(
        text="Только согласившимся на маркетинг",
        callback_data=BroadcastCallback(action="target", target="marketing_consent")
    )
    
    # Кнопка "Отмена"
    builder.button(
        text="❌ Отмена",
        callback_data=BroadcastCallback(action="cancel")
    )
    
    # Размещаем по 1 кнопке в ряду
    builder.adjust(1)
    
    return builder.as_markup()


async def get_broadcast_preview_keyboard(
    broadcast_id: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для превью рассылки с кнопками запуска и отмены.
    
    Args:
        broadcast_id: ID рассылки
    
    Returns:
        InlineKeyboardMarkup с кнопками управления рассылкой
    
    Requirements: 10.3
    
    Layout:
    [🚀 Запустить] [✏️ Редактировать]
    [❌ Отмена]
    """
    from bots.tg_bot.callback_datas import BroadcastCallback
    
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Запустить"
    builder.button(
        text="🚀 Запустить",
        callback_data=BroadcastCallback(action="send", broadcast_id=broadcast_id)
    )
    
    # Кнопка "Редактировать"
    builder.button(
        text="✏️ Редактировать",
        callback_data=BroadcastCallback(action="create")
    )
    
    # Кнопка "Отмена"
    builder.button(
        text="❌ Отмена",
        callback_data=BroadcastCallback(action="cancel")
    )
    
    # Размещаем 2 кнопки в первом ряду, 1 во втором
    builder.adjust(2, 1)
    
    return builder.as_markup()


# ========== Escalation Keyboards ==========


async def get_escalation_keyboard(
    ticket_id: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для обработки эскалированной заявки.
    
    Args:
        ticket_id: ID заявки
    
    Returns:
        InlineKeyboardMarkup с кнопками действий для эскалации
    
    Requirements: 12.3
    
    Layout:
    [➡️ Переназначить] [🙋‍♂️ Взять на себя]
    [📞 Позвонить дежурному]
    """
    from bots.tg_bot.callback_datas import EscalationCallback
    
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Переназначить"
    builder.button(
        text="➡️ Переназначить",
        callback_data=EscalationCallback(action="reassign", ticket_id=ticket_id)
    )
    
    # Кнопка "Взять на себя"
    builder.button(
        text="🙋‍♂️ Взять на себя",
        callback_data=EscalationCallback(action="take", ticket_id=ticket_id)
    )
    
    # Кнопка "Позвонить дежурному"
    builder.button(
        text="📞 Позвонить дежурному",
        callback_data=EscalationCallback(action="contact", ticket_id=ticket_id)
    )
    
    # Размещаем 2 кнопки в первом ряду, 1 во втором
    builder.adjust(2, 1)
    
    return builder.as_markup()


# ========== Analytics Keyboards ==========


async def build_analytics_keyboard(
    selected_period: str = "today"
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для панели аналитики с выбором периода.
    
    Args:
        selected_period: Текущий выбранный период ("today", "week", "month")
    
    Returns:
        InlineKeyboardMarkup с кнопками выбора периода и управления
    
    Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8
    
    Layout:
    [✓ Сегодня] [Неделя] [Месяц]
    [🔄 Обновить]
    [🔙 Назад]
    """
    from bots.tg_bot.callback_datas import AnalyticsCallback, AdminMenuCallback
    
    builder = InlineKeyboardBuilder()
    
    # Period selection buttons with checkmark for selected period
    periods = [
        ("today", "Сегодня"),
        ("week", "Неделя"),
        ("month", "Месяц")
    ]
    
    for period_key, period_label in periods:
        # Add checkmark to selected period
        button_text = f"✓ {period_label}" if period_key == selected_period else period_label
        
        builder.button(
            text=button_text,
            callback_data=AnalyticsCallback(action="period", period=period_key)
        )
    
    # Refresh button
    builder.button(
        text="🔄 Обновить",
        callback_data=AnalyticsCallback(action="refresh")
    )
    
    # Back button
    builder.button(
        text="🔙 Назад",
        callback_data=AdminMenuCallback(action="back_to_main")
    )
    
    # Layout: 3 period buttons in first row, refresh in second, back in third
    builder.adjust(3, 1, 1)
    
    return builder.as_markup()


async def get_analytics_dashboard_keyboard(
    selected_period: str = "today"
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для панели аналитики с выбором периода.
    
    Args:
        selected_period: Текущий выбранный период ("today", "week", "month")
    
    Returns:
        InlineKeyboardMarkup с кнопками выбора периода и управления
    
    Requirements: 10.1, 10.2, 10.4, 10.5, 10.7, 10.8
    
    Layout:
    [✓ Сегодня] [Неделя] [Месяц]
    [🔄 Обновить]
    [🔙 Назад]
    """
    from bots.tg_bot.callback_datas import AnalyticsCallback, AdminMenuCallback
    
    builder = InlineKeyboardBuilder()
    
    # Period selection buttons with checkmark for selected period
    periods = [
        ("today", "Сегодня"),
        ("week", "Неделя"),
        ("month", "Месяц")
    ]
    
    for period_key, period_label in periods:
        # Add checkmark to selected period
        button_text = f"✓ {period_label}" if period_key == selected_period else period_label
        
        builder.button(
            text=button_text,
            callback_data=AnalyticsCallback(action="period", period=period_key)
        )
    
    # Refresh button
    builder.button(
        text="🔄 Обновить",
        callback_data=AnalyticsCallback(action="refresh")
    )
    
    # Back button
    builder.button(
        text="🔙 Назад",
        callback_data=AdminMenuCallback(action="back_to_main")
    )
    
    # Layout: 3 period buttons in first row, refresh in second, back in third
    builder.adjust(3, 1, 1)
    
    return builder.as_markup()
async def build_analytics_keyboard(
    selected_period: str = "today"
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для панели аналитики с выбором периода.

    Args:
        selected_period: Текущий выбранный период ("today", "week", "month")

    Returns:
        InlineKeyboardMarkup с кнопками выбора периода и управления

    Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8

    Layout:
    [✓ Сегодня] [Неделя] [Месяц]
    [🔄 Обновить]
    [🔙 Назад]
    """
    from bots.tg_bot.callback_datas import AnalyticsCallback, AdminMenuCallback

    builder = InlineKeyboardBuilder()

    # Period selection buttons with checkmark for selected period
    periods = [
        ("today", "Сегодня"),
        ("week", "Неделя"),
        ("month", "Месяц")
    ]

    for period_key, period_label in periods:
        # Add checkmark to selected period
        button_text = f"✓ {period_label}" if period_key == selected_period else period_label

        builder.button(
            text=button_text,
            callback_data=AnalyticsCallback(action="period", period=period_key)
        )

    # Refresh button
    builder.button(
        text="🔄 Обновить",
        callback_data=AnalyticsCallback(action="refresh")
    )

    # Back button
    builder.button(
        text="🔙 Назад",
        callback_data=AdminMenuCallback(action="back_to_main")
    )

    # Layout: 3 period buttons in first row, refresh in second, back in third
    builder.adjust(3, 1, 1)

    return builder.as_markup()


async def get_analytics_dashboard_keyboard(
    selected_period: str = "today"
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для панели аналитики с выбором периода.

    Args:
        selected_period: Текущий выбранный период ("today", "week", "month")

    Returns:
        InlineKeyboardMarkup с кнопками выбора периода и управления

    Requirements: 10.1, 10.2, 10.4, 10.5, 10.7, 10.8

    Layout:
    [✓ Сегодня] [Неделя] [Месяц]
    [🔄 Обновить]
    [🔙 Назад]
    """
    from bots.tg_bot.callback_datas import AnalyticsCallback, AdminMenuCallback

    builder = InlineKeyboardBuilder()

    # Period selection buttons with checkmark for selected period
    periods = [
        ("today", "Сегодня"),
        ("week", "Неделя"),
        ("month", "Месяц")
    ]

    for period_key, period_label in periods:
        # Add checkmark to selected period
        button_text = f"✓ {period_label}" if period_key == selected_period else period_label

        builder.button(
            text=button_text,
            callback_data=AnalyticsCallback(action="period", period=period_key)
        )

    # Refresh button
    builder.button(
        text="🔄 Обновить",
        callback_data=AnalyticsCallback(action="refresh")
    )

    # Back button
    builder.button(
        text="🔙 Назад",
        callback_data=AdminMenuCallback(action="back_to_main")
    )

    # Layout: 3 period buttons in first row, refresh in second, back in third
    builder.adjust(3, 1, 1)

    return builder.as_markup()


# ========== Settings Keyboards ==========


async def get_settings_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Создает главное меню настроек с категориями.
    
    Returns:
        InlineKeyboardMarkup с кнопками категорий настроек
    
    Requirements: 1.1, 1.2, 1.3
    
    Layout:
    [⏱ Таймауты] [📢 Эскалация]
    [🌙 Дежурная поддержка] [📊 NPS настройки]
    [🔔 Напоминания] [👥 Резервы менеджеров]
    [📜 История]
    [◀️ Назад]
    """
    from bots.tg_bot.callback_datas import SettingsCallback, AdminMenuCallback
    
    builder = InlineKeyboardBuilder()
    
    # Category buttons
    builder.button(
        text="⏱ Таймауты Эскалации",
        callback_data=SettingsCallback(action="timeouts")
    )
    
    builder.button(
        text="📢 Каналы Эскалации",
        callback_data=SettingsCallback(action="escalation")
    )
    
    # builder.button(
    #     text="🌙 Дежурная поддержка",
    #     callback_data=SettingsCallback(action="duty_support")
    # )
    
    builder.button(
        text="📊 NPS настройки",
        callback_data=SettingsCallback(action="nps")
    )
    
    builder.button(
        text="🔔 Напоминания о подписке",
        callback_data=SettingsCallback(action="renewal_reminders")
    )
    
    # builder.button(
    #     text="👥 Резервы менеджеров",
    #     callback_data=SettingsCallback(action="manager_backups")
    # )
    
    # History button
    builder.button(
        text="📜 История изменения настроек",
        callback_data=SettingsCallback(action="history")
    )
    
    # Back button
    builder.button(
        text="◀️ Назад к админ-панели",
        callback_data=AdminMenuCallback(action="back_to_main")
    )
    
    # Layout: 2 buttons per row for categories, then history, then back
    builder.adjust(2, 2, 2, 1, 1)
    
    return builder.as_markup()


async def get_timeout_settings_keyboard(
    current_values: dict[str, int]
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для настройки таймаутов с текущими значениями.
    
    Args:
        current_values: Словарь с текущими значениями таймаутов
            - manager_response_timeout: Таймаут ответа менеджера (минуты)
            - duty_taken_timeout: Таймаут взятия в работу дежурной (минуты)
    
    Returns:
        InlineKeyboardMarkup с кнопками настройки таймаутов
    
    Requirements: 2.1, 2.2
    
    Layout:
    [⏱ Таймаут менеджера: 10 мин]
    [⏱ Таймаут дежурной: 10 мин]
    [🔄 Сбросить по умолчанию]
    [◀️ Назад]
    """
    from bots.tg_bot.callback_datas import SettingsCallback
    
    builder = InlineKeyboardBuilder()
    
    # Manager response timeout
    manager_timeout = current_values.get("manager_response_timeout", 10)
    builder.button(
        text=f"⏱ Таймаут менеджера: {manager_timeout} мин",
        callback_data=SettingsCallback(
            action="edit_timeout",
            setting_key="manager_response_timeout"
        )
    )
    
    # Duty taken timeout
    duty_timeout = current_values.get("duty_taken_timeout", 10)
    builder.button(
        text=f"⏱ Таймаут дежурной: {duty_timeout} мин",
        callback_data=SettingsCallback(
            action="edit_timeout",
            setting_key="duty_taken_timeout"
        )
    )
    
    # Reset to defaults button
    builder.button(
        text="🔄 Сбросить по умолчанию",
        callback_data=SettingsCallback(
            action="reset_setting",
            setting_key="timeouts"
        )
    )
    
    # Back button
    builder.button(
        text="◀️ Назад",
        callback_data=SettingsCallback(action="menu")
    )
    
    # Layout: one button per row
    builder.adjust(1)
    
    return builder.as_markup()


async def get_escalation_settings_keyboard(
    manager_channel: str | None,
    duty_channel: str | None
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для настройки каналов эскалации.
    
    Args:
        manager_channel: ID канала эскалации менеджеров (или None)
        duty_channel: ID канала эскалации дежурной (или None)
    
    Returns:
        InlineKeyboardMarkup с кнопками настройки каналов эскалации
    
    Requirements: 3.1, 3.2
    
    Layout:
    [📢 Канал менеджеров: @channel / Не настроен]
    [📢 Канал дежурной: @channel / Не настроен]
    [🔄 Сбросить по умолчанию]
    [◀️ Назад]
    """
    from bots.tg_bot.callback_datas import SettingsCallback
    
    builder = InlineKeyboardBuilder()
    
    # Manager escalation channel
    manager_status = manager_channel if manager_channel else "Не настроен"
    builder.button(
        text=f"📢 Канал менеджеров: {manager_status}",
        callback_data=SettingsCallback(
            action="edit_escalation_channel",
            setting_key="escalation_manager_channel"
        )
    )
    
    # Duty escalation channel
    duty_status = duty_channel if duty_channel else "Не настроен"
    builder.button(
        text=f"📢 Канал дежурной: {duty_status}",
        callback_data=SettingsCallback(
            action="edit_escalation_channel",
            setting_key="escalation_duty_channel"
        )
    )
    
    # Reset to defaults button
    builder.button(
        text="🔄 Сбросить по умолчанию",
        callback_data=SettingsCallback(
            action="reset_setting",
            setting_key="escalation"
        )
    )
    
    # Back button
    builder.button(
        text="◀️ Назад",
        callback_data=SettingsCallback(action="menu")
    )
    
    # Layout: one button per row
    builder.adjust(1)
    
    return builder.as_markup()


async def get_nps_settings_keyboard(
    frequency_days: int,
    trigger_after_payment: int,
    trigger_after_support: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для настройки NPS опросов.
    
    Args:
        frequency_days: Частота опросов в днях
        trigger_after_payment: Дней после оплаты для отправки опроса
        trigger_after_support: Дней после закрытия тикета для отправки опроса
    
    Returns:
        InlineKeyboardMarkup с кнопками настройки NPS
    
    Requirements: 5.1, 5.2
    
    Layout:
    [📊 Частота опросов: 30 дней]
    [📊 После оплаты: 10 дней]
    [📊 После поддержки: 1 день]
    [🔄 Сбросить по умолчанию]
    [◀️ Назад]
    """
    from bots.tg_bot.callback_datas import SettingsCallback
    
    builder = InlineKeyboardBuilder()
    
    # NPS frequency
    builder.button(
        text=f"📊 Частота опросов: {frequency_days} дней",
        callback_data=SettingsCallback(
            action="edit_nps_frequency",
            setting_key="nps_frequency_days"
        )
    )
    
    # Trigger after payment
    builder.button(
        text=f"📊 После оплаты: {trigger_after_payment} дней",
        callback_data=SettingsCallback(
            action="edit_nps_trigger",
            setting_key="nps_trigger_after_payment"
        )
    )
    
    # Trigger after support
    builder.button(
        text=f"📊 После поддержки: {trigger_after_support} дней",
        callback_data=SettingsCallback(
            action="edit_nps_trigger",
            setting_key="nps_trigger_after_support"
        )
    )
    
    # Reset to defaults button
    builder.button(
        text="🔄 Сбросить по умолчанию",
        callback_data=SettingsCallback(
            action="reset_setting",
            setting_key="nps"
        )
    )
    
    # Back button
    builder.button(
        text="◀️ Назад",
        callback_data=SettingsCallback(action="menu")
    )
    
    # Layout: one button per row
    builder.adjust(1)
    
    return builder.as_markup()


async def get_renewal_reminders_keyboard(
    reminder_days: list[int]
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для настройки напоминаний о продлении.
    
    Args:
        reminder_days: Список дней для напоминаний (например, [30, 7])
    
    Returns:
        InlineKeyboardMarkup с кнопками управления напоминаниями
    
    Requirements: 6.1, 6.2
    
    Layout:
    [🔔 30 дней] [❌]
    [🔔 7 дней] [❌]
    [➕ Добавить напоминание]
    [🔄 Сбросить по умолчанию]
    [◀️ Назад]
    """
    from bots.tg_bot.callback_datas import SettingsCallback
    
    builder = InlineKeyboardBuilder()
    
    # Sort reminder days in descending order
    sorted_days = sorted(reminder_days, reverse=True)
    
    # Add a row for each reminder with remove button
    for days in sorted_days:
        # Reminder display button (non-clickable, just for display)
        builder.button(
            text=f"🔔 {days} дней",
            callback_data=SettingsCallback(
                action="view_reminder",
                reminder_days=days
            )
        )
        
        # Remove button
        builder.button(
            text="❌",
            callback_data=SettingsCallback(
                action="remove_renewal_reminder",
                reminder_days=days
            )
        )
    
    # Add new reminder button
    builder.button(
        text="➕ Добавить напоминание",
        callback_data=SettingsCallback(action="add_renewal_reminder")
    )
    
    # Reset to defaults button
    builder.button(
        text="🔄 Сбросить по умолчанию",
        callback_data=SettingsCallback(
            action="reset_setting",
            setting_key="renewal_reminders"
        )
    )
    
    # Back button
    builder.button(
        text="◀️ Назад",
        callback_data=SettingsCallback(action="menu")
    )
    
    # Layout: 2 buttons per row for reminders (display + remove), then single buttons
    reminder_count = len(sorted_days)
    if reminder_count > 0:
        builder.adjust(*([2] * reminder_count), 1, 1, 1)
    else:
        builder.adjust(1, 1, 1)
    
    return builder.as_markup()


async def get_settings_history_keyboard(
    page: int,
    total_pages: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для истории изменений настроек с пагинацией.
    
    Args:
        page: Текущая страница (0-indexed)
        total_pages: Общее количество страниц
    
    Returns:
        InlineKeyboardMarkup с кнопками пагинации
    
    Requirements: 2.3
    
    Layout:
    [◀️ Пред] [Страница 1/5] [След ▶️]
    [◀️ Назад в настройки]
    """
    from bots.tg_bot.callback_datas import SettingsCallback
    
    builder = InlineKeyboardBuilder()
    
    # Previous page button (disabled if on first page)
    if page > 0:
        builder.button(
            text="◀️ Пред",
            callback_data=SettingsCallback(
                action="history_page",
                page=page - 1
            )
        )
    else:
        # Placeholder button (non-functional)
        builder.button(
            text="◀️",
            callback_data=SettingsCallback(
                action="history_page",
                page=0
            )
        )
    
    # Page indicator (non-clickable, just for display)
    builder.button(
        text=f"Страница {page + 1}/{total_pages}",
        callback_data=SettingsCallback(
            action="history_page",
            page=page
        )
    )
    
    # Next page button (disabled if on last page)
    if page < total_pages - 1:
        builder.button(
            text="След ▶️",
            callback_data=SettingsCallback(
                action="history_page",
                page=page + 1
            )
        )
    else:
        # Placeholder button (non-functional)
        builder.button(
            text="▶️",
            callback_data=SettingsCallback(
                action="history_page",
                page=page
            )
        )
    
    # Back to settings button
    builder.button(
        text="◀️ Назад в настройки",
        callback_data=SettingsCallback(action="menu")
    )
    
    # Layout: 3 buttons in first row (prev, page, next), back button in second row
    builder.adjust(3, 1)
    
    return builder.as_markup()


# ========== Registration Keyboards ==========


async def build_registration_actions_keyboard(
    user_id: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с действиями для регистрации пользователя.
    
    Args:
        user_id: ID пользователя для регистрации
    
    Returns:
        InlineKeyboardMarkup с кнопками действий
    
    Requirements: 31.1, 31.6, 31.7
    
    Layout:
    [✅ Подтвердить] [❌ Отклонить]
    [🔍 На проверку]
    """
    from bots.tg_bot.callback_datas import RegistrationCallback
    
    builder = InlineKeyboardBuilder()
    
    # Approve button
    builder.button(
        text="✅ Подтвердить",
        callback_data=RegistrationCallback(
            action="approve",
            user_id=user_id
        )
    )
    
    # Reject button
    builder.button(
        text="❌ Отклонить",
        callback_data=RegistrationCallback(
            action="reject",
            user_id=user_id
        )
    )
    
    # Review button
    builder.button(
        text="🔍 На проверку",
        callback_data=RegistrationCallback(
            action="review",
            user_id=user_id
        )
    )
    
    # Layout: 2 buttons in first row, 1 in second
    builder.adjust(2, 1)
    
    return builder.as_markup()


async def build_registration_list_keyboard(
    registrations: list,
    page: int = 0,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру со списком ожидающих регистраций с пагинацией.
    
    Args:
        registrations: Список объектов User с ожидающими регистрациями
        page: Номер текущей страницы (начиная с 0)
        total_pages: Общее количество страниц
    
    Returns:
        InlineKeyboardMarkup со списком регистраций и навигацией
    
    Requirements: 31.4, 31.9
    
    Layout:
    [👤 Имя - Телефон]
    [👤 Имя - Телефон]
    ...
    [◀️ Назад] [Страница X/Y] [Вперед ▶️]
    [🔙 К операциям]
    """
    from bots.tg_bot.callback_datas import RegistrationCallback, AdminMenuCallback
    
    builder = InlineKeyboardBuilder()
    
    # Add registration buttons
    for user in registrations:
        button_text = f"👤 {user.full_name} - {user.phone_number}"
        
        builder.button(
            text=button_text,
            callback_data=RegistrationCallback(
                action="view",
                user_id=user.id
            )
        )
    
    # Adjust to one button per row for registration list
    builder.adjust(1)
    
    # Add pagination controls if needed
    if total_pages > 1:
        # Previous page button
        if page > 0:
            builder.button(
                text="◀️ Назад",
                callback_data=RegistrationCallback(
                    action="list",
                    page=page - 1
                )
            )
        
        # Page indicator
        builder.button(
            text=f"Страница {page + 1}/{total_pages}",
            callback_data=RegistrationCallback(
                action="list",
                page=page
            )
        )
        
        # Next page button
        if page < total_pages - 1:
            builder.button(
                text="Вперед ▶️",
                callback_data=RegistrationCallback(
                    action="list",
                    page=page + 1
                )
            )
    
    # Back to operations menu button
    builder.row(
        InlineKeyboardButton(
            text="🔙 К операциям",
            callback_data=AdminMenuCallback(action="operations").pack()
        )
    )
    
    return builder.as_markup()



async def build_key_conflict_actions_keyboard(
    key_id: int,
    new_user_id: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с действиями для разрешения конфликта ключей.
    
    Args:
        key_id: ID ключа GS_Key
        new_user_id: ID нового пользователя, претендующего на ключ
    
    Returns:
        InlineKeyboardMarkup с кнопками действий
    
    Requirements: 31.2, 31.6, 31.7
    
    Layout:
    [✅ Передать новому] [❌ Отказать новому]
    [📞 Связаться]
    """
    from bots.tg_bot.callback_datas import KeyConflictCallback
    
    builder = InlineKeyboardBuilder()
    
    # Transfer button
    builder.button(
        text="✅ Передать новому",
        callback_data=KeyConflictCallback(
            action="transfer",
            key_id=key_id,
            new_user_id=new_user_id
        )
    )
    
    # Reject button
    builder.button(
        text="❌ Отказать новому",
        callback_data=KeyConflictCallback(
            action="reject",
            key_id=key_id,
            new_user_id=new_user_id
        )
    )
    
    # Contact button
    builder.button(
        text="📞 Связаться",
        callback_data=KeyConflictCallback(
            action="contact",
            key_id=key_id,
            new_user_id=new_user_id
        )
    )
    
    # Layout: 2 buttons in first row, 1 in second
    builder.adjust(2, 1)
    
    return builder.as_markup()


async def build_conflict_list_keyboard(
    conflicts: list,
    page: int,
    total_pages: int
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру со списком конфликтов ключей с пагинацией.
    
    Args:
        conflicts: Список конфликтов (GS_Key объектов) для текущей страницы
        page: Номер текущей страницы (0-indexed)
        total_pages: Общее количество страниц
    
    Returns:
        InlineKeyboardMarkup со списком конфликтов и пагинацией
    
    Requirements: 31.5, 31.9
    
    Layout:
    [Конфликт 1]
    [Конфликт 2]
    ...
    [◀️ Назад] [Страница X/Y] [Вперед ▶️]
    [🔙 В меню]
    """
    from bots.tg_bot.callback_datas import KeyConflictCallback
    
    builder = InlineKeyboardBuilder()
    
    # Conflict selection buttons
    for conflict in conflicts:
        # Format: "Ключ: KEY_NUMBER - Новый: USER_NAME"
        button_text = f"🔑 {conflict.key_number}"
        if hasattr(conflict, 'user') and conflict.user:
            button_text += f" - {conflict.user.full_name or 'Не указано'}"
        
        builder.button(
            text=button_text,
            callback_data=KeyConflictCallback(
                action="view",
                key_id=conflict.id,
                new_user_id=conflict.user_id if hasattr(conflict, 'user_id') else None
            )
        )
    
    # Adjust to one button per row for conflict list
    builder.adjust(1)
    
    # Pagination buttons
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=KeyConflictCallback(
                    action="list",
                    page=page - 1
                ).pack()
            )
        )
    
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"Страница {page + 1}/{total_pages}",
            callback_data="noop"
        )
    )
    
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Вперед ▶️",
                callback_data=KeyConflictCallback(
                    action="list",
                    page=page + 1
                ).pack()
            )
        )
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    # Back button to operations menu
    from bots.tg_bot.callback_datas import AdminMenuCallback
    builder.button(
        text="🔙 В меню",
        callback_data=AdminMenuCallback(action="operations")
    )
    
    return builder.as_markup()
