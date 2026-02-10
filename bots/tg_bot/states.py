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
    waiting_for_inn = State()
    waiting_for_key = State()


class InvoiceStates(StatesGroup):
    """Состояния для запроса счета."""

    selecting_organization = State()
    adding_new_inn = State()
    selecting_keys = State()
    adding_new_key = State()
    entering_description = State()
    selecting_delivery = State()
    entering_email = State()


class SupportStates(StatesGroup):
    """Состояния для технической поддержки."""

    entering_problem = State()
    selecting_key_context = State()


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
