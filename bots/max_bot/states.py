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
    waiting_for_email = State()
    waiting_for_inn = State()
    waiting_for_key = State()


class InvoiceStates(StatesGroup):
    """States for invoice request flow."""

    selecting_organization = State()
    adding_new_inn = State()
    adding_org_name = State()  # Optional: ask user for short org name when INN not found in 1C
    selecting_keys = State()
    adding_new_key = State()
    entering_description = State()
    selecting_delivery = State()
    confirming_email = State()
    entering_email = State()


class SupportStates(StatesGroup):
    """States for technical support flow."""

    selecting_organization = State()
    adding_new_inn = State()
    adding_org_name = State()
    entering_problem = State()
    selecting_key_context = State()
    adding_new_key = State()


class ConsultationStates(StatesGroup):
    """States for consultation request flow."""

    selecting_organization = State()
    adding_new_inn = State()
    adding_org_name = State()  # Optional: ask user for short org name when INN not found in 1C
    selecting_keys = State()
    adding_new_key = State()
    entering_description = State()


class AIAgentStates(StatesGroup):
    """States for AI manager assistant flow."""

    waiting_for_request = State()
    waiting_for_key = State()
    waiting_for_manager_description = State()


class ClientTicketCloseStates(StatesGroup):
    """States for client-side ticket closure."""

    selecting_ticket = State()
    waiting_for_reason = State()


class ProfileStates(StatesGroup):
    """States for profile management."""

    adding_inn = State()
    adding_org_name = State()  # Optional: ask user for short org name when INN not found in 1C
    adding_key = State()
    changing_phone = State()
    changing_email = State()


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
    archive_custom_search = State()  # Employee entering custom search criteria in archive
    manager_closing_ticket = State()  # Manager entering final comment for closing ticket
    manager_transferring_ticket = State()  # Manager selecting employee for transfer


class CalendarStates(StatesGroup):
    """States for calendar management."""

    managing_calendar = State()  # Administrator managing calendar (text commands active)
    confirming_add_rule = State()  # Administrator confirming rule addition
    confirming_delete_rule = State()  # Administrator confirming rule deletion
    entering_clear_period = State()  # Administrator entering period to clear


class EmployeeManagementStates(StatesGroup):
    """States for employee management."""

    adding_employee_id = State()  # Administrator entering MAX user ID
    adding_employee_name = State()  # Administrator entering employee full name
    adding_employee_position = State()  # Administrator entering employee position/signature
    adding_employee_role = State()  # Administrator selecting employee role
    editing_employee_name = State()  # Administrator editing employee name
    editing_employee_signature = State()  # Administrator editing employee signature


class OperationsStates(StatesGroup):
    """States for operations management."""

    creating_broadcast_content = State()  # Administrator entering broadcast message content
    selecting_broadcast_target = State()  # Administrator selecting target audience
    confirming_broadcast = State()  # Administrator confirming broadcast send
    entering_phone_change_reject_reason = State()  # Administrator entering rejection reason


class NPSStates(StatesGroup):
    """States for NPS survey flow."""

    waiting_for_feedback = State()  # User entering feedback comment for low rating (0-7)



class SettingsStates(StatesGroup):
    """States for settings configuration."""

    entering_timeout_value = State()  # Administrator entering timeout value
    entering_escalation_chat_id = State()  # Administrator entering escalation channel chat ID
    entering_duty_account_id = State()  # Administrator entering duty support account ID
    entering_nps_frequency = State()  # Administrator entering NPS frequency value
    entering_nps_trigger_timing = State()  # Administrator entering NPS trigger timing value
    entering_renewal_reminder_days = State()  # Administrator entering renewal reminder days
    entering_renewal_reminder_days = State()  # Administrator entering renewal reminder days


class AdminCreationStates(StatesGroup):
    """States for admin creation flow."""

    waiting_for_phone = State()  # Waiting for phone number
    waiting_for_full_name = State()  # Waiting for full name
