"""
Manager Interface Inline Keyboards for MAX Bot

Inline клавиатуры для интерфейса менеджера в MAX messenger.
В отличие от Telegram (reply keyboard), MAX использует inline keyboard.
"""

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from bots.max_bot.payloads import StaffSelfServicePayload, ManagerMenuActionPayload


def get_manager_menu_keyboard(
    is_admin: bool = False,
    is_manager: bool = False,
    active_tickets_count: int = 0,
    show_employee_menu: bool = False,
) -> Keyboard:
    """
    Создает главное меню менеджера с inline клавиатурой.
    
    В MAX используется inline keyboard вместо reply keyboard из Telegram.
    
    Args:
        is_admin: Флаг, является ли сотрудник администратором
        is_manager: Флаг, является ли сотрудник менеджером
        active_tickets_count: Количество активных заявок
        show_employee_menu: Показывать кнопку "Меню сотрудника" (для не-администраторов)
    
    Returns:
        Keyboard с кнопками меню менеджера
    
    Requirements: Manager Interface
    """
    # Format active tickets button text with count if there are active tickets
    active_tickets_text = "📥 Активные заявки"
    if active_tickets_count > 0:
        active_tickets_text = f"📥 Активные заявки ({active_tickets_count})"
    
    buttons = [
        # Row 1: Active Tickets
        [
            KeyboardButton(
                text=active_tickets_text,
                payload=ManagerMenuActionPayload(action="active_tickets").pack()
            )
        ],
        # Row 2: Archive
        [
            KeyboardButton(
                text="🗃️ Архив обращений",
                payload=ManagerMenuActionPayload(action="archive").pack()
            )
        ]
    ]
    
    # Row 3: Transfer clients (only for managers)
    if is_manager:
        buttons.append([
            KeyboardButton(
                text="👥 Передача клиентов",
                payload=ManagerMenuActionPayload(action="transfer_clients").pack()
            )
        ])
    
    # Row 4: Employee self-service menu (for all roles except ADMINISTRATOR)
    if show_employee_menu:
        buttons.append([
            KeyboardButton(
                text="👤 Меню сотрудника",
                payload=ManagerMenuActionPayload(action="employee_menu").pack()
            )
        ])
    
    # Row 5: Admin Panel (only for administrators)
    if is_admin:
        buttons.append([
            KeyboardButton(
                text="🔐 Админ-панель",
                payload=ManagerMenuActionPayload(action="admin_panel").pack()
            )
        ])
    
    return Keyboard(buttons=buttons, inline=True)


def get_employee_self_service_keyboard(
    can_set_duty_tp: bool = False,
    can_set_duty_estimate: bool = False,
    is_working_today: bool = True,
    is_current_duty_tp: bool = False,
    is_current_duty_estimate: bool = False,
) -> Keyboard:
    """
    Создает клавиатуру меню самообслуживания сотрудника.

    Показывает кнопки в зависимости от роли:
    - ТП (TECHNICAL_SUPPORT, is_estimate_tech_specialist=False): кнопка "Назначить себя дежурным ТП"
    - Сметный специалист (is_estimate_tech_specialist=True): кнопка "Назначить себя дежурным по сметной"
    - Все (кроме MANAGER): кнопка переключения активности

    Args:
        can_set_duty_tp: Может ли сотрудник назначить себя дежурным ТП
        can_set_duty_estimate: Может ли назначить себя дежурным по сметной консультации
        is_working_today: Текущий статус доступности сотрудника
        is_current_duty_tp: Является ли сотрудник текущим дежурным ТП
        is_current_duty_estimate: Является ли текущим дежурным по сметной

    Returns:
        Keyboard с кнопками самообслуживания
    """
    buttons = []

    # Duty TP button
    if can_set_duty_tp:
        if is_current_duty_tp:
            duty_tp_text = "⚡ Дежурный ТП: Вы ✅"
        else:
            duty_tp_text = "⚡ Назначить себя дежурным ТП"
        buttons.append([
            KeyboardButton(
                text=duty_tp_text,
                payload=StaffSelfServicePayload(action="set_duty_tp").pack()
            )
        ])

    # Duty estimate button
    if can_set_duty_estimate:
        if is_current_duty_estimate:
            duty_est_text = "📊 Дежурный по сметной: Вы ✅"
        else:
            duty_est_text = "📊 Назначить себя дежурным по сметной"
        buttons.append([
            KeyboardButton(
                text=duty_est_text,
                payload=StaffSelfServicePayload(action="set_duty_estimate").pack()
            )
        ])

    # Toggle working availability button
    if is_working_today:
        working_text = "🟢 Я доступен — сделать недоступным"
    else:
        working_text = "🔴 Я недоступен — сделать доступным"
    buttons.append([
        KeyboardButton(
            text=working_text,
            payload=StaffSelfServicePayload(action="toggle_working").pack()
        )
    ])

    # Back button
    buttons.append([
        KeyboardButton(
            text="🔙 Назад",
            payload=StaffSelfServicePayload(action="back_to_manager").pack()
        )
    ])

    return Keyboard(buttons=buttons, inline=True)


def get_employee_duty_confirm_keyboard(duty_type: str) -> Keyboard:
    """
    Создает клавиатуру подтверждения назначения дежурным.

    Args:
        duty_type: "tp" или "estimate"

    Returns:
        Keyboard с кнопками подтверждения/отмены
    """
    from bots.max_bot.payloads import StaffSetDutyPayload

    return Keyboard(
        buttons=[
            [
                KeyboardButton(
                    text="✅ Подтвердить",
                    payload=StaffSetDutyPayload(duty_type=duty_type, confirm=True).pack()
                ),
                KeyboardButton(
                    text="❌ Отмена",
                    payload=StaffSetDutyPayload(duty_type=duty_type, confirm=False).pack()
                )
            ]
        ],
        inline=True
    )


def get_employee_toggle_working_confirm_keyboard() -> Keyboard:
    """
    Создает клавиатуру подтверждения изменения статуса доступности.

    Returns:
        Keyboard с кнопками подтверждения/отмены
    """
    from bots.max_bot.payloads import StaffToggleWorkingPayload

    return Keyboard(
        buttons=[
            [
                KeyboardButton(
                    text="✅ Подтвердить",
                    payload=StaffToggleWorkingPayload(confirm=True).pack()
                ),
                KeyboardButton(
                    text="❌ Отмена",
                    payload=StaffToggleWorkingPayload(confirm=False).pack()
                )
            ]
        ],
        inline=True
    )
