"""
FSM States for MAX Bot

This module defines all FSM state groups for the MAX bot using maxapi's
State and StatesGroup classes. These states mirror the Telegram bot states
to maintain consistent conversation flows.

Pattern: Group states by functional blocks
- Create separate StatesGroup for each scenario/flow
- Use clear, descriptive state names
- Document the purpose of each state group
"""

from maxapi.context import State, StatesGroup


class RegistrationStates(StatesGroup):
    """States for user registration process."""

    waiting_for_phone = State()
    waiting_for_name = State()
    waiting_for_inn = State()
    waiting_for_key = State()


class InvoiceStates(StatesGroup):
    """States for invoice request flow."""

    selecting_organization = State()
    adding_new_inn = State()
    selecting_keys = State()
    adding_new_key = State()
    entering_description = State()
    selecting_delivery = State()
    entering_email = State()


class SupportStates(StatesGroup):
    """States for technical support flow."""

    entering_problem = State()
    selecting_key_context = State()


class ProfileStates(StatesGroup):
    """States for profile management."""

    adding_inn = State()
    adding_key = State()
    changing_phone = State()


class FormStates(StatesGroup):
    """States for form filling."""

    waiting_for_input = State()
    waiting_for_file = State()
    waiting_for_confirmation = State()


class EmployeeStates(StatesGroup):
    """States for employee interface."""

    in_focus = State()  # Employee in focus mode on a ticket
    closing_ticket = State()  # Employee entering final comment for closing
    transferring_ticket = State()  # Employee selecting target employee for transfer
    searching_archive = State()  # Employee entering search criteria in archive
