"""
Callback Data Factories

Паттерн: Type-safe callback data с использованием CallbackData фабрик
- Используйте короткие префиксы (экономия байтов в callback_data)
- Документируйте назначение каждого поля
- Используйте Optional для необязательных параметров
- action: str - для определения типа действия (view, select, delete и т.д.)
"""

from aiogram.filters.callback_data import CallbackData


class OrganizationCallback(CallbackData, prefix="org"):
    """
    Callback data для выбора организации.

    Поля:
    - action: Тип действия ('select', 'add_new', 'delete', 'skip', 'page', 'back_to_profile')
    - inn: ИНН организации (опционально)
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    inn: str | None = None
    page: int | None = None


class KeyCallback(CallbackData, prefix="key"):
    """
    Callback data для выбора GS_Key.

    Поля:
    - action: Тип действия ('toggle', 'add_new', 'delete', 'done', 'skip', 'page', 'back_to_profile')
    - key_id: ID ключа GS_Key (опционально)
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    key_id: int | None = None
    page: int | None = None


class DeliveryCallback(CallbackData, prefix="dlv"):
    """
    Callback data для выбора способа доставки.

    Поля:
    - method: Способ доставки ('telegram', 'email')
    """

    method: str


class ProfileCallback(CallbackData, prefix="prof"):
    """
    Callback data для действий в профиле.

    Поля:
    - action: Тип действия ('add_inn', 'add_key', 'change_phone', 'toggle_notif', 'view_orgs', 'view_keys', 'cancel', 'back')
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    page: int | None = None


class ExampleItemCallback(CallbackData, prefix="item"):
    """
    Пример фабрики для работы с элементами списка.

    Поля:
    - action: Тип действия ('view', 'select', 'delete', 'edit')
    - item_id: ID элемента (опционально для действий типа 'list')
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    item_id: int | None = None
    page: int | None = None


class ExampleNavigationCallback(CallbackData, prefix="nav"):
    """
    Пример фабрики для навигации между разделами.

    Поля:
    - action: Тип действия ('back', 'forward', 'cancel')
    - from_section: Откуда пришел пользователь (для контекстного возврата)
    - data: Дополнительные данные (опционально)
    """

    action: str
    from_section: str | None = None
    data: str | None = None


class EmployeeMenuCallback(CallbackData, prefix="emp_menu"):
    """
    Callback data для главного меню сотрудника.

    Поля:
    - action: Тип действия ('active_tickets', 'archive_search', 'settings', 'admin_panel')
    """

    action: str


class TicketListCallback(CallbackData, prefix="ticket_list"):
    """
    Callback data для взаимодействия со списком активных заявок.

    Поля:
    - action: Тип действия ('focus_ticket', 'filter', 'page')
    - ticket_id: ID заявки (опционально)
    - filter_type: Тип фильтра ('all', 'invoice', 'technical_support', 'renewal', опционально)
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    ticket_id: int | None = None
    filter_type: str | None = None
    page: int = 0


class TicketActionCallback(CallbackData, prefix="ticket_act"):
    """
    Callback data для действий с заявкой.

    Поля:
    - action: Тип действия ('take_ticket', 'close_ticket', 'set_waiting', 'transfer_ticket', 'view_history', 'exit_focus')
    - ticket_id: ID заявки
    """

    action: str
    ticket_id: int


class EmployeeSelectionCallback(CallbackData, prefix="emp_sel"):
    """
    Callback data для выбора сотрудника при передаче заявки.

    Поля:
    - action: Тип действия ('select', 'cancel')
    - employee_id: ID сотрудника (опционально для действия 'cancel')
    """

    action: str
    employee_id: int | None = None


class TicketHistoryCallback(CallbackData, prefix="ticket_hist"):
    """
    Callback data для пагинации истории заявки.

    Поля:
    - action: Тип действия ('page', 'back')
    - ticket_id: ID заявки
    - page: Номер страницы (опционально)
    """

    action: str
    ticket_id: int
    page: int = 0



class ArchiveSearchCallback(CallbackData, prefix="arch_srch"):
    """
    Callback data для результатов поиска в архиве.

    Поля:
    - action: Тип действия ('view_ticket', 'page', 'back', 'filter', 'custom_search', 'back_to_archive', 'cancel')
    - ticket_id: ID заявки (опционально для действий 'page', 'back')
    - filter_type: Тип фильтра ('day', 'week', 'month', 'custom', опционально)
    - page: Номер страницы (опционально)
    """

    action: str
    ticket_id: int | None = None
    filter_type: str | None = None
    page: int = 0


# ========== Admin Panel Callback Data Factories ==========


class AdminMenuCallback(CallbackData, prefix="adm_menu"):
    """
    Callback data для главного меню админ-панели.

    Поля:
    - action: Тип действия ('employees', 'operations', 'calendar', 'settings', 'analytics')
    """

    action: str


class EmployeeCallback(CallbackData, prefix="adm_emp"):
    """
    Callback data для управления сотрудниками.

    Поля:
    - action: Тип действия ('list', 'add', 'view', 'edit_sig', 'edit_role', 'deactivate', 'backups', 'transfer_clients')
    - employee_id: ID сотрудника (опционально)
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    employee_id: int | None = None
    page: int | None = None


class EmployeeRoleCallback(CallbackData, prefix="adm_role"):
    """
    Callback data для выбора роли сотрудника.

    Поля:
    - role: Роль ('manager', 'technical_support', 'duty_engineer', 'administrator')
    - employee_id: ID сотрудника (опционально для нового сотрудника)
    """

    role: str
    employee_id: int | None = None


class BackupManagerCallback(CallbackData, prefix="adm_backup"):
    """
    Callback data для настройки резервных менеджеров.

    Поля:
    - action: Тип действия ('select_slot', 'assign', 'remove')
    - employee_id: ID сотрудника
    - slot: Номер слота (1 или 2, опционально)
    - backup_id: ID резервного менеджера (опционально)
    """

    action: str
    employee_id: int
    slot: int | None = None
    backup_id: int | None = None


class RegistrationCallback(CallbackData, prefix="adm_reg"):
    """
    Callback data для одобрения регистраций.

    Поля:
    - action: Тип действия ('approve', 'reject', 'review', 'list')
    - user_id: ID пользователя (опционально)
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    user_id: int | None = None
    page: int | None = None


class BroadcastCallback(CallbackData, prefix="adm_bcast"):
    """
    Callback data для управления рассылками.

    Поля:
    - action: Тип действия ('create', 'target', 'preview', 'send', 'cancel')
    - target: Целевая аудитория ('all', 'active_subscription', 'marketing_consent', опционально)
    - broadcast_id: ID рассылки (опционально)
    """

    action: str
    target: str | None = None
    broadcast_id: int | None = None


class KeyConflictCallback(CallbackData, prefix="adm_conflict"):
    """
    Callback data для разрешения конфликтов ключей.

    Поля:
    - action: Тип действия ('transfer', 'reject', 'contact', 'list')
    - key_id: ID ключа (опционально)
    - new_user_id: ID нового пользователя (опционально)
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    key_id: int | None = None
    new_user_id: int | None = None
    page: int | None = None


class EscalationCallback(CallbackData, prefix="esc"):
    """
    Callback data для обработки эскалаций.

    Поля:
    - action: Тип действия ('list', 'view', 'reassign', 'take_over', 'contact', 'select_staff')
    - escalation_id: ID эскалации (опционально)
    - ticket_id: ID заявки (опционально)
    - staff_id: ID сотрудника для переназначения (опционально)
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    escalation_id: int | None = None
    ticket_id: int | None = None
    staff_id: int | None = None
    page: int | None = None


class CalendarCallback(CallbackData, prefix="adm_cal"):
    """
    Callback data для управления календарем.

    Поля:
    - action: Тип действия ('dashboard', 'week', 'list', 'delete', 'clear_period', 'confirm_add', 'cancel_add', 'confirm_delete', 'cancel_delete', 'next_month', 'prev_month')
    - rule_id: ID правила календаря (опционально)
    - page: Номер страницы для пагинации (опционально)
    - year: Год для пагинации по месяцам (опционально)
    - month: Месяц для пагинации по месяцам (опционально)
    """

    action: str
    rule_id: int | None = None
    page: int | None = None
    year: int | None = None
    month: int | None = None


class SettingsCallback(CallbackData, prefix="adm_set"):
    """
    Callback data для системных настроек.

    Поля:
    - action: Тип действия (
        'menu', 'timeouts', 'escalation', 'duty_support', 'nps', 'renewal_reminders', 
        'manager_backups', 'history', 'edit_timeout', 'edit_escalation_channel', 
        'edit_duty_account', 'edit_nps_frequency', 'edit_nps_trigger', 
        'add_renewal_reminder', 'remove_renewal_reminder', 'reset_setting', 'history_page'
    )
    - setting_key: Ключ настройки (опционально)
    - page: Номер страницы для пагинации истории (опционально)
    - reminder_days: Количество дней для напоминания о продлении (опционально)
    """

    action: str
    setting_key: str | None = None
    page: int | None = None
    reminder_days: int | None = None


class AnalyticsCallback(CallbackData, prefix="adm_stats"):
    """
    Callback data для панели аналитики.

    Поля:
    - action: Тип действия ('dashboard', 'period')
    - period: Период ('today', 'week', 'month', опционально)
    """

    action: str
    period: str | None = None


class ClientTicketListCallback(CallbackData, prefix="cl_ticket"):
    """
    Callback data для списка активных обращений клиента.

    Поля:
    - action: Тип действия ('select_ticket', 'page')
    - ticket_id: ID заявки (опционально для действия 'page')
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    ticket_id: int | None = None
    page: int = 0


class RenewalCallback(CallbackData, prefix="renewal"):
    """
    Callback data для действий с продлением подписки.

    Поля:
    - action: Тип действия ('renew', 'contact_manager', 'cancel')
    """

    action: str



class ClientArchiveCallback(CallbackData, prefix="cl_arch"):
    """
    Callback data for client archive interactions.

    Поля:
    - action: Тип действия ('filter', 'page', 'view_ticket', 'close')
    - ticket_id: ID заявки (опционально)
    - filter_type: Тип фильтра ('all', 'invoice', 'technical_support', 'renewal', опционально)
    - page: Номер страницы (опционально)
    """

    action: str
    ticket_id: int | None = None
    filter_type: str | None = None
    page: int = 0
