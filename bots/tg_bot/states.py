"""
FSM States

Паттерн: Группировка состояний по функциональным блокам
- Создавайте отдельный StatesGroup для каждого сценария/флоу
- Используйте понятные имена состояний
- Документируйте назначение каждой группы состояний
"""

from aiogram.filters.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Состояния для процесса регистрации пользователя."""

    waiting_for_phone = State()
    waiting_for_name = State()
    waiting_for_email = State()
    waiting_for_inn = State()
    waiting_for_key = State()
    key_conflict_choice = State()


class InvoiceStates(StatesGroup):
    """Состояния для запроса счета."""

    selecting_organization = State()
    adding_new_inn = State()
    selecting_keys = State()
    adding_new_key = State()
    entering_description = State()
    selecting_delivery = State()
    entering_email = State()
    confirming_invoice = State()


class SupportStates(StatesGroup):
    """Состояния для технической поддержки."""

    entering_problem = State()
    selecting_key_context = State()
    adding_new_key = State()


class ProfileStates(StatesGroup):
    """Состояния для управления профилем."""

    adding_inn = State()
    adding_key = State()
    changing_phone = State()


class FormStates(StatesGroup):
    """Состояния для заполнения формы."""

    waiting_for_input = State()
    waiting_for_file = State()
    waiting_for_confirmation = State()


class EmployeeStates(StatesGroup):
    """Состояния для интерфейса сотрудника."""

    in_focus = State()  # Сотрудник в режиме фокуса на тикете
    closing_ticket = State()  # Сотрудник вводит финальный комментарий для закрытия
    transferring_ticket = State()  # Сотрудник выбирает целевого сотрудника для передачи
    searching_archive = State()  # Сотрудник вводит критерии поиска в архиве
    archive_custom_search = State()  # Сотрудник вводит произвольный поисковый запрос


class AdminStates(StatesGroup):
    """Состояния для административной панели."""

    # Employee management
    adding_employee_id = State()  # Ожидание Telegram ID или пересланного сообщения
    adding_employee_role = State()  # Ожидание выбора роли
    adding_employee_signature = State()  # Ожидание текста подписи
    editing_employee_signature = State()  # Ожидание новой подписи
    editing_employee_name = State()  # Ожидание нового имени
    selecting_backup_manager = State()  # Ожидание выбора резервного менеджера

    # Registration approval
    reviewing_registration = State()  # Просмотр деталей регистрации
    entering_rejection_reason = State()  # Ввод причины отклонения
    WAITING_REJECTION_REASON = State()  # Ожидание причины отклонения регистрации

    # Broadcast
    creating_broadcast_content = State()  # Ожидание сообщения для рассылки
    selecting_broadcast_target = State()  # Ожидание выбора целевой аудитории
    confirming_broadcast = State()  # Просмотр превью рассылки

    # Key conflict
    resolving_key_conflict = State()  # Просмотр деталей конфликта ключа

    # Escalation management
    waiting_for_reassign_staff = State()  # Ожидание выбора сотрудника для переназначения эскалации

    # Calendar management
    entering_calendar_rule = State()  # Ожидание текстовой команды для правила
    selecting_period_to_clear = State()  # Ожидание диапазона дат

    # Settings
    editing_support_contact = State()  # Ожидание нового номера телефона поддержки


class CalendarStates(StatesGroup):
    """Состояния для управления календарем работы."""

    managing_calendar = State()  # Основное состояние управления календарем
    confirming_add_rule = State()  # Подтверждение добавления правила
    confirming_delete_rule = State()  # Подтверждение удаления правила
    waiting_for_clear_period_input = State()  # Ожидание ввода диапазона дат для очистки
    waiting_for_clear_period_confirmation = State()  # Ожидание подтверждения очистки периода


class SettingsStates(StatesGroup):
    """Состояния для настройки системных параметров."""

    # Timeout configuration
    entering_timeout_value = State()

    # Escalation channel configuration
    entering_escalation_chat_id = State()
    testing_escalation_channel = State()

    # Duty support configuration
    entering_duty_account_id = State()

    # NPS configuration
    entering_nps_frequency = State()
    entering_nps_trigger_timing = State()

    # Renewal reminders
    entering_renewal_reminder_days = State()



    class SettingsStates(StatesGroup):
        """Состояния для настройки системных параметров."""

        # Timeout configuration
        entering_timeout_value = State()

        # Escalation channel configuration
        entering_escalation_chat_id = State()
        testing_escalation_channel = State()

        # Duty support configuration
        entering_duty_account_id = State()

        # NPS configuration
        entering_nps_frequency = State()
        entering_nps_trigger_timing = State()

        # Renewal reminders
        entering_renewal_reminder_days = State()

