"""
CallbackPayload class definitions for MAX bot handlers.

This module provides type-safe callback payload classes for handling inline button
callbacks in the MAX bot. Each class inherits from CallbackPayload and defines
a structured payload format with automatic JSON serialization/deserialization.

Usage:
    1. Define payload class with prefix and typed fields:
       class MyPayload(CallbackPayload, prefix='my_action'):
           field_name: int

    2. Use in handler decorator with filter:
       @dp.message_callback(MyPayload.filter())
       async def handler(event: MessageCallback, payload: MyPayload):
           value = payload.field_name

    3. Create payload in keyboard builders:
       payload = MyPayload(field_name=123)
       button = CallbackButton(text="Click", payload=payload.pack())

Benefits:
    - Type safety: Fields are validated automatically
    - No manual JSON parsing: Automatic deserialization
    - Cleaner code: Direct field access via dot notation
    - Prefix-based routing: Different payload types route to different handlers
    - Filter integration: Works with MagicFilter (F) for additional conditions

References:
    - maxapi library documentation: docs/MAX-API/maxapi-library-doc.md
    - Payload patterns: .kiro/specs/max-bot-handler-api-fixes/callback-payload-patterns.md
    - Payload inventory: .kiro/specs/max-bot-handler-api-fixes/payload-structures-inventory.md
"""

from maxapi.filters.callback_payload import CallbackPayload
from pydantic import field_validator


# ============================================================================
# Active Tickets Payloads
# ============================================================================

class ReplyToManagerPayload(CallbackPayload, prefix='reply_manager'):
    """Payload for quick reply to manager button in manager messages.
    
    Sent alongside every message from manager to client.
    Clicking it sets active_ticket_id in FSM so client can reply directly.
    
    Fields:
        ticket_id: ID of the ticket to reply to
    """
    ticket_id: int


class TicketSelectPayload(CallbackPayload, prefix='select_ticket'):
    """Payload for ticket selection in active tickets view.
    
    Used when user clicks on a ticket to view its details.
    
    Fields:
        ticket_id: ID of the selected ticket
    """
    ticket_id: int


class TicketsPaginationPayload(CallbackPayload, prefix='tickets_page'):
    """Payload for pagination in active tickets view.
    
    Used when user navigates between pages of active tickets.
    
    Fields:
        page: Page number (0-indexed)
        filter: Optional ticket type filter (all/invoice/support/consultation/renewal)
    """
    page: int
    filter: str = "all"


class TicketsFilterPayload(CallbackPayload, prefix='tickets_filter'):
    """Payload for filtering active tickets by type.
    
    Fields:
        filter: Ticket type filter (all/invoice/support/consultation/renewal)
    """
    filter: str


class ActiveTicketsClosePayload(CallbackPayload, prefix='close_tickets'):
    """Payload for closing active tickets list.
    
    Used when user clicks button to return to main menu from active tickets.
    No additional fields needed - action-only callback.
    """
    pass


class TicketHistoryPayload(CallbackPayload, prefix='ticket_history'):
    """Payload for viewing ticket message history with pagination.
    
    Used when user navigates through ticket message history.
    
    Fields:
        ticket_id: ID of the ticket
        page: Page number (0-indexed) for message history pagination
    """
    ticket_id: int
    page: int = 0


class TicketHistoryBackPayload(CallbackPayload, prefix='history_back'):
    """Payload for returning from ticket history to ticket card.
    
    Used when user clicks back button from history view.
    
    Fields:
        ticket_id: ID of the ticket to return to
    """
    ticket_id: int


class MessageTicketSelectPayload(CallbackPayload, prefix='msg_ticket_select'):
    """Payload for selecting a ticket when sending a free-text message.
    
    Shown when user sends a message without active FSM state and has multiple
    active tickets. User selects which ticket to route the message to.
    
    Fields:
        ticket_id: ID of the ticket to route the pending message to
    """
    ticket_id: int


class MessageTicketPaginationPayload(CallbackPayload, prefix='msg_ticket_page'):
    """Payload for pagination in the message ticket selection menu.
    
    Fields:
        page: Page number (0-indexed)
    """
    page: int


class MessageTicketCancelPayload(CallbackPayload, prefix='msg_ticket_cancel'):
    """Payload for canceling the ticket selection for message routing.
    
    No additional fields needed.
    """
    pass


# ============================================================================
# Archive Payloads
# ============================================================================

class ArchiveFilterPayload(CallbackPayload, prefix='filter'):
    """Payload for archive filter selection.
    
    Used when user selects a filter type in the archive view.
    
    Fields:
        filter_type: Filter type - "invoice", "support", "renewal", or "all"
    """
    filter_type: str


class ArchivePaginationPayload(CallbackPayload, prefix='page'):
    """Payload for pagination in archive view.
    
    Used when user navigates between pages of archived tickets.
    
    Fields:
        page: Page number (0-indexed)
        filter_type: Current filter type being applied
    """
    page: int
    filter_type: str


class ViewArchivedTicketPayload(CallbackPayload, prefix='view_ticket'):
    """Payload for viewing an archived ticket.
    
    Used when user clicks on an archived ticket to view its details.
    
    Fields:
        ticket_id: ID of the archived ticket to view
    """
    ticket_id: int


class ArchiveClosePayload(CallbackPayload, prefix='close'):
    """Payload for closing the archive view.
    
    Used when user clicks the close/back button in archive view.
    No additional fields needed - action-only callback.
    """
    pass


# ============================================================================
# Main Menu Payloads
# ============================================================================

class MainMenuActionPayload(CallbackPayload, prefix='menu'):
    """Payload for main menu action callbacks.
    
    Used when user selects an action from the main menu.
    Routes to different flows based on action type.
    
    Fields:
        action: Action type - "invoice", "support", "renewal", "archive", "profile", or "active_tickets"
    """
    action: str


# ============================================================================
# Profile Payloads
# ============================================================================

class ProfileActionPayload(CallbackPayload, prefix='profile'):
    """Payload for simple profile actions without parameters.
    
    Used for actions that don't require additional data.
    
    Fields:
        action: Action type - "toggle_notif", "confirm_disable_notif", 
                "broadcasts", "main_menu", "back", "cancel", or "noop"
    """
    action: str


class ProfileViewPayload(CallbackPayload, prefix='profile_view'):
    """Payload for viewing profile sections with pagination.
    
    Used for viewing organizations or keys lists.
    
    Fields:
        section: Section to view - "orgs" or "keys"
        page: Page number (0-indexed, default: 0)
    """
    section: str
    page: int = 0


class ProfileAddPayload(CallbackPayload, prefix='profile_add'):
    """Payload for adding items to profile.
    
    Used for initiating add flows.
    
    Fields:
        item_type: Type of item to add - "inn" or "key"
    """
    item_type: str


class ProfileDeleteOrgPayload(CallbackPayload, prefix='profile_del_org'):
    """Payload for deleting organization from profile.
    
    Fields:
        inn: INN of organization to delete
    """
    inn: str


class ProfileConfirmDeleteOrgPayload(CallbackPayload, prefix='profile_confirm_del_org'):
    """Payload for confirming organization deletion.
    
    Fields:
        inn: INN of organization to delete
    """
    inn: str


class ProfileDeleteKeyPayload(CallbackPayload, prefix='profile_del_key'):
    """Payload for deleting key from profile.
    
    Fields:
        key_id: ID of key to delete
    """
    key_id: int


class ProfileConfirmDeleteKeyPayload(CallbackPayload, prefix='profile_confirm_del_key'):
    """Payload for confirming key deletion.
    
    Fields:
        key_id: ID of key to delete
    """
    key_id: int


# ============================================================================
# Invoice Flow Payloads
# ============================================================================

class OrganizationSelectPayload(CallbackPayload, prefix='org_select'):
    """Payload for organization selection in invoice flow.
    
    Used when user selects an organization by INN.
    
    Fields:
        inn: INN number of the selected organization
    """
    inn: str


class OrganizationPagePayload(CallbackPayload, prefix='org_page'):
    """Payload for organization list pagination in invoice flow.
    
    Used when user navigates between pages of organizations.
    
    Fields:
        page: Page number (0-indexed)
    """
    page: int


class OrganizationActionPayload(CallbackPayload, prefix='org_action'):
    """Payload for organization-related actions in invoice flow.
    
    Used for actions like adding new organization, skipping, or canceling.
    
    Fields:
        action: Action type - "add_new", "skip", or "cancel"
    """
    action: str


class KeyTogglePayload(CallbackPayload, prefix='key_toggle'):
    """Payload for toggling key selection in invoice flow.
    
    Used when user selects/deselects a key for the invoice.
    
    Fields:
        key_id: ID of the key to toggle
    """
    key_id: int


class KeyPagePayload(CallbackPayload, prefix='key_page'):
    """Payload for key list pagination in invoice flow.
    
    Used when user navigates between pages of keys.
    
    Fields:
        page: Page number (0-indexed)
    """
    page: int


class KeyActionPayload(CallbackPayload, prefix='key_action'):
    """Payload for key-related actions in invoice flow.
    
    Used for actions like adding new key, completing selection, skipping, going back, or canceling.
    
    Fields:
        action: Action type - "add_new", "done", "skip", "back", or "cancel"
    """
    action: str


class DeliveryMethodPayload(CallbackPayload, prefix='delivery'):
    """Payload for delivery method selection in invoice flow.
    
    Used when user selects how they want to receive the invoice.
    
    Fields:
        method: Delivery method - "email", "pickup", or "courier"
    """
    method: str


class EmailConfirmPayload(CallbackPayload, prefix='email_confirm'):
    """Payload for email confirmation in invoice flow.
    
    Used when user needs to confirm or change their registered email.
    
    Fields:
        action: Action to take - "use_registered", "enter_new", "cancel"
    """
    action: str


# ============================================================================
# Support Flow Payloads
# ============================================================================

class RenewalActionPayload(CallbackPayload, prefix='renewal'):
    """Payload for renewal action callbacks in support flow.
    
    Used when user initiates a subscription renewal request.
    
    Fields:
        action: Action type - typically "renewal"
    """
    action: str


class KeyContextTogglePayload(CallbackPayload, prefix='key_ctx_toggle'):
    """Payload for toggling key selection in support flow context.
    
    Used when user selects/deselects a key for the support ticket.
    
    Fields:
        key_id: ID of the key to toggle
    """
    key_id: int


class KeyContextPagePayload(CallbackPayload, prefix='key_ctx_page'):
    """Payload for key list pagination in support flow context.
    
    Used when user navigates between pages of keys in support flow.
    
    Fields:
        page: Page number (0-indexed)
    """
    page: int


class KeyContextActionPayload(CallbackPayload, prefix='key_ctx_action'):
    """Payload for key-related actions in support flow context.
    
    Used for actions like adding new key, completing selection, skipping, 
    going back, or canceling in support flow.
    
    Fields:
        action: Action type - "add_new", "done", "skip", "back", "back_to_keys", 
                "skip_description", or "cancel"
    """
    action: str


# ============================================================================
# Support Flow Organization Payloads
# ============================================================================

class SupportOrgSelectPayload(CallbackPayload, prefix='sup_org_select'):
    """Payload for organization selection in support flow.

    Used when user selects an organization by INN in the support ticket flow.

    Fields:
        inn: INN number of the selected organization
    """
    inn: str


class SupportOrgPagePayload(CallbackPayload, prefix='sup_org_page'):
    """Payload for organization list pagination in support flow.

    Fields:
        page: Page number (0-indexed)
    """
    page: int


class SupportOrgActionPayload(CallbackPayload, prefix='sup_org_action'):
    """Payload for organization-related actions in support flow.

    Fields:
        action: Action type - "add_new", "skip", or "cancel"
    """
    action: str


# ============================================================================
# Consultation Flow Payloads
# ============================================================================

class ConsultationOrgSelectPayload(CallbackPayload, prefix='cons_org_select'):
    """Payload for organization selection in consultation flow.
    
    Fields:
        inn: INN number of the selected organization
    """
    inn: str


class ConsultationOrgPagePayload(CallbackPayload, prefix='cons_org_page'):
    """Payload for organization list pagination in consultation flow.
    
    Fields:
        page: Page number (0-indexed)
    """
    page: int


class ConsultationOrgActionPayload(CallbackPayload, prefix='cons_org_action'):
    """Payload for organization-related actions in consultation flow.
    
    Fields:
        action: Action type - "add_new", "skip", or "cancel"
    """
    action: str


class ConsultationKeyTogglePayload(CallbackPayload, prefix='cons_key_toggle'):
    """Payload for toggling key selection in consultation flow.
    
    Fields:
        key_id: ID of the key to toggle
    """
    key_id: int


class ConsultationKeyPagePayload(CallbackPayload, prefix='cons_key_page'):
    """Payload for key list pagination in consultation flow.
    
    Fields:
        page: Page number (0-indexed)
    """
    page: int


class ConsultationKeyActionPayload(CallbackPayload, prefix='cons_key_action'):
    """Payload for key-related actions in consultation flow.
    
    Fields:
        action: Action type - "add_new", "done", "skip", "back", or "cancel"
    """
    action: str


# ============================================================================
# Description "Next" Button Payloads
# ============================================================================

class InvoiceDescriptionNextPayload(CallbackPayload, prefix='inv_desc_next'):
    """Payload for "Next" button in invoice description step.

    Used when user clicks "Далее" after entering description/attachments.
    No additional fields needed - action-only callback.
    """
    pass


class SupportDescriptionNextPayload(CallbackPayload, prefix='sup_desc_next'):
    """Payload for "Next" button in support description step.

    Used when user clicks "Далее" after entering problem description/attachments.
    No additional fields needed - action-only callback.
    """
    pass


class ConsultationDescriptionNextPayload(CallbackPayload, prefix='cons_desc_next'):
    """Payload for "Next" button in consultation description step.

    Used when user clicks "Далее" after entering consultation description/attachments.
    No additional fields needed - action-only callback.
    """
    pass


# ============================================================================
# Registration Payloads
# ============================================================================

class RegistrationCancelPayload(CallbackPayload, prefix='reg_cancel'):
    """Payload for canceling registration flow.
    
    Used when user clicks cancel button during registration.
    No additional fields needed - action-only callback.
    """
    pass


class RegistrationSkipPayload(CallbackPayload, prefix='reg_skip'):
    """Payload for skipping optional steps in registration flow.
    
    Used when user clicks skip button during optional registration steps (e.g., email).
    No additional fields needed - action-only callback.
    """
    pass


class KeyConflictChoicePayload(CallbackPayload, prefix='key_conflict'):
    """Payload for key conflict resolution choice in registration flow.
    
    Used when a key conflict is detected during registration and user needs to choose
    whether to retry with a different key or continue without it.
    
    Fields:
        action: Action type - "retry" or "continue"
    """
    action: str


# ============================================================================
# Admin Creation Payloads
# ============================================================================

class AdminCreationCancelPayload(CallbackPayload, prefix='admin_cancel'):
    """Payload for canceling admin creation flow.
    
    Used when administrator clicks cancel button during admin creation.
    No additional fields needed - action-only callback.
    """
    pass


# ============================================================================
# Manager Menu Payloads
# ============================================================================

class ManagerMenuActionPayload(CallbackPayload, prefix='mgr_menu'):
    """Payload for manager menu action callbacks.
    
    Used when manager selects an action from the manager menu.
    
    Fields:
        action: Action type - "active_tickets", "archive", or "admin_panel"
    """
    action: str


# ============================================================================
# Manager Active Tickets Payloads
# ============================================================================

class ManagerTicketSelectPayload(CallbackPayload, prefix='mgr_ticket'):
    """Payload for manager ticket selection.
    
    Used when manager clicks on a ticket to view details.
    
    Fields:
        ticket_id: ID of the selected ticket
    """
    ticket_id: int


class ManagerTicketsFilterPayload(CallbackPayload, prefix='mgr_filter'):
    """Payload for manager tickets filter selection.
    
    Used when manager selects a ticket type filter.
    
    Fields:
        filter_type: Filter type - "invoice", "technical_support", "renewal", or "all"
    """
    filter_type: str


class ManagerTicketsPaginationPayload(CallbackPayload, prefix='mgr_page'):
    """Payload for manager tickets pagination.
    
    Used when manager navigates between pages of tickets.
    
    Fields:
        page: Page number (0-indexed)
    """
    page: int


class ManagerTicketsBackPayload(CallbackPayload, prefix='mgr_back'):
    """Payload for returning to manager menu or tickets list.
    
    Used for navigation buttons.
    
    Fields:
        action: Action type - "menu" (to manager menu) or "list" (to tickets list)
    """
    action: str


# ============================================================================
# Manager Archive Payloads
# ============================================================================

class ManagerArchiveFilterPayload(CallbackPayload, prefix='mgr_arc_filter'):
    """Payload for manager archive filter selection.
    
    Used when manager selects a time period filter.
    
    Fields:
        filter_type: Filter type - "day", "week", "month", or "custom"
    """
    filter_type: str


class ManagerArchivePaginationPayload(CallbackPayload, prefix='mgr_arc_page'):
    """Payload for manager archive pagination.
    
    Used when manager navigates between pages of archived tickets.
    
    Fields:
        page: Page number (0-indexed)
    """
    page: int


class ManagerArchiveTicketPayload(CallbackPayload, prefix='mgr_arc_ticket'):
    """Payload for viewing archived ticket details.
    
    Used when manager clicks on an archived ticket.
    
    Fields:
        ticket_id: ID of the archived ticket
    """
    ticket_id: int


class ManagerArchiveBackPayload(CallbackPayload, prefix='mgr_arc_back'):
    """Payload for archive navigation.
    
    Used for navigation buttons in archive.
    
    Fields:
        action: Action type - "menu" (to manager menu), "list" (to archive list), or "noop"
    """
    action: str


class ManagerArchiveTypeFilterPayload(CallbackPayload, prefix='mgr_arc_type'):
    """Payload for manager archive ticket-type filter.

    Fields:
        ticket_type: Ticket type filter - "all", "invoice", "technical_support", "consultation", "renewal"
    """
    ticket_type: str


# ============================================================================
# Manager Ticket Actions Payloads
# ============================================================================

class ManagerTicketActionPayload(CallbackPayload, prefix='mgr_ticket_action'):
    """Payload for ticket action buttons.
    
    Used when manager performs actions on a ticket.
    
    Fields:
        action: Action type - "take", "close", "transfer", "history", "back_to_list",
                "cancel_close", "view_card"
        ticket_id: ID of the ticket
    """
    action: str
    ticket_id: int


class ManagerViewTicketPayload(CallbackPayload, prefix='mgr_view_ticket'):
    """Payload for "К заявке" button in ticket notifications.
    
    Used when staff member clicks "К заявке" button in notification message
    to view ticket details without automatically taking it into work.
    
    Fields:
        ticket_id: ID of the ticket to view
    """
    ticket_id: int


class ManagerToggleFocusPayload(CallbackPayload, prefix='mgr_toggle_focus'):
    """Payload for toggling focus mode on/off.
    
    Used when manager clicks "Общение с клиентом" button to enable/disable focus mode.
    
    Fields:
        ticket_id: ID of the ticket
        enable: True to enable focus, False to disable
    """
    ticket_id: int
    enable: bool


class ManagerEmployeeSelectPayload(CallbackPayload, prefix='mgr_emp_select'):
    """Payload for employee selection in transfer flow.
    
    Used when manager selects an employee to transfer ticket to.
    
    Fields:
        action: Action type - "select" or "cancel"
        employee_id: ID of the selected employee (optional, only for "select" action)
        new_ticket_type: Optional new ticket type when cross-type transfer is needed
                         (e.g., TECHNICAL_SUPPORT → CONSULTATION or vice versa)
    """
    action: str
    employee_id: int | None = None
    new_ticket_type: str | None = None

    @field_validator('employee_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None for optional employee_id."""
        if v == '' or v is None:
            return None
        return v


class ManagerTicketHistoryPayload(CallbackPayload, prefix='mgr_history'):
    """Payload for viewing ticket message history with pagination (manager interface).
    
    Used when manager navigates through ticket message history.
    
    Fields:
        ticket_id: ID of the ticket
        page: Page number (0-indexed) for message history pagination
    """
    ticket_id: int
    page: int = 0


class ManagerTicketHistoryBackPayload(CallbackPayload, prefix='mgr_hist_back'):
    """Payload for returning from ticket history to ticket card (manager interface).
    
    Used when manager clicks back button from history view.
    
    Fields:
        ticket_id: ID of the ticket to return to
    """
    ticket_id: int


class ManagerTakeFromMessagePayload(CallbackPayload, prefix='mgr_take_msg'):
    """Payload for "Взять в работу" button in client message notifications.
    
    Used when manager clicks "Взять в работу" directly from a client message
    notification to take the ticket into work and enter focus mode.
    
    Fields:
        ticket_id: ID of the ticket to take into work
    """
    ticket_id: int


class ManagerFocusFromMessagePayload(CallbackPayload, prefix='mgr_focus_msg'):
    """Payload for "Общение с клиентом" button in client message notifications.
    
    Used when manager clicks "Общение с клиентом" from a client message notification
    to enter focus mode on an already in-progress ticket.
    
    Fields:
        ticket_id: ID of the ticket to focus on
    """
    ticket_id: int


# ============================================================================
# Admin Panel Payloads
# ============================================================================

class AdminMenuPayload(CallbackPayload, prefix='admin_menu'):
    """Payload for admin panel main menu navigation.
    
    Used when administrator navigates through admin panel sections.
    
    Fields:
        action: Action type - "employees", "operations", "calendar", "settings", "analytics", "back"
    """
    action: str


class OperationsMenuPayload(CallbackPayload, prefix='ops_menu'):
    """Payload for operations menu navigation.
    
    Used when administrator navigates through operations submenu.
    
    Fields:
        action: Action type - "key_conflicts", "escalations", "back"
    """
    action: str


class BroadcastPayload(CallbackPayload, prefix='broadcast'):
    """Payload for broadcast actions.
    
    Used for creating and managing broadcast messages.
    
    Fields:
        action: Action type - "create", "preview", "target", "send", "cancel"
        broadcast_id: ID of the broadcast (optional)
        target_type: Target audience type (optional) - "all", "active", "managers"
    """
    action: str
    broadcast_id: int | None = None
    target_type: str | None = None
    
    @field_validator('broadcast_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


class KeyConflictPayload(CallbackPayload, prefix='key_conflict_ops'):
    """Payload for key conflict resolution actions.
    
    Used for managing GS_Key ownership conflicts.
    
    Fields:
        action: Action type - "list", "view", "transfer", "reject", "contact"
        key_id: ID of the GS_Key in conflict (optional)
        new_user_id: ID of the user requesting the key (optional, required for transfer/reject)
        page: Page number for pagination (optional)
    """
    action: str
    key_id: int | None = None
    new_user_id: int | None = None
    page: int | None = None
    
    @field_validator('key_id', 'new_user_id', 'page', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


class EscalationPayload(CallbackPayload, prefix='escalation'):
    """Payload for escalation management actions.
    
    Used for managing ticket escalations in admin panel.
    
    Fields:
        action: Action type - "list", "view", "reassign", "take_over", "contact", "select_staff"
        escalation_id: ID of the escalation (optional)
        staff_id: ID of the staff member for reassignment (optional)
        page: Page number for pagination (optional)
    """
    action: str
    escalation_id: int | None = None
    staff_id: int | None = None
    page: int | None = None
    
    @field_validator('escalation_id', 'staff_id', 'page', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


# ============================================================================
# Calendar Management Payloads
# ============================================================================

class CalendarMenuPayload(CallbackPayload, prefix='cal_menu'):
    """Payload for calendar menu navigation.
    
    Fields:
        action: Action type - "weekly", "monthly", "rules", "clear", "examples", "back", "back_to_menu"
    """
    action: str


class CalendarRulePayload(CallbackPayload, prefix='cal_rule'):
    """Payload for calendar rule actions.
    
    Fields:
        action: Action type - "delete", "confirm_delete", "cancel_delete"
        rule_id: ID of the rule (optional)
    """
    action: str
    rule_id: int | None = None
    
    @field_validator('rule_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


class CalendarClearPayload(CallbackPayload, prefix='cal_clear'):
    """Payload for period clearing actions.
    
    Fields:
        action: Action type - "start", "confirm", "cancel"
    """
    action: str


class CalendarPaginationPayload(CallbackPayload, prefix='cal_page'):
    """Payload for calendar pagination.
    
    Fields:
        action: Action type - "next_month", "prev_month"
        year: Year for pagination
        month: Month for pagination
    """
    action: str
    year: int
    month: int


class CalendarConfirmPayload(CallbackPayload, prefix='cal_confirm'):
    """Payload for calendar confirmation actions.
    
    Used for confirming or canceling add/delete operations.
    
    Fields:
        action: Action type - "confirm_add", "cancel_add", "confirm_delete", "cancel_delete"
    """
    action: str


# ============================================================================
# Employee Management Payloads
# ============================================================================

class EmployeeMenuPayload(CallbackPayload, prefix='emp_menu'):
    """Payload for employee management menu navigation.
    
    Fields:
        action: Action type - "add", "list", "back"
    """
    action: str


class EmployeeListPayload(CallbackPayload, prefix='emp_list'):
    """Payload for employee list actions.
    
    Fields:
        action: Action type - "view", "page"
        employee_id: ID of the employee (optional, for view action)
        page: Page number (optional, for pagination)
    """
    action: str
    employee_id: int | None = None
    page: int | None = None
    
    @field_validator('employee_id', 'page', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


class EmployeeActionPayload(CallbackPayload, prefix='emp_action'):
    """Payload for employee actions.
    
    Fields:
        action: Action type - "view", "edit_name", "edit_signature", "edit_role", 
                "deactivate", "confirm_deactivate", "activate",
                "set_duty_support", "unset_duty_support",
                "set_estimate_specialist", "unset_estimate_specialist",
                "backup_config", "transfer_clients"
        employee_id: ID of the employee
    """
    action: str
    employee_id: int
    
    @field_validator('employee_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


class EmployeeRolePayload(CallbackPayload, prefix='emp_role'):
    """Payload for employee role selection when editing existing employee.
    
    Fields:
        role: Role type - "ADMINISTRATOR", "MANAGER", "technical_support"
        employee_id: ID of the employee
    """
    role: str
    employee_id: int


class EmployeeRoleAddPayload(CallbackPayload, prefix='emp_role_add'):
    """Payload for employee role selection when adding new employee.
    
    Fields:
        role: Role type - "ADMINISTRATOR", "MANAGER", "technical_support"
    """
    role: str


class EmployeeConfirmPayload(CallbackPayload, prefix='emp_confirm'):
    """Payload for employee action confirmation.
    
    Fields:
        action: Action type - "deactivate", "cancel"
        employee_id: ID of the employee
    """
    action: str
    employee_id: int


class BackupManagerPayload(CallbackPayload, prefix='backup_mgr'):
    """Payload for backup manager configuration.
    
    Fields:
        action: Action type - "config", "select_slot", "assign", "remove"
        employee_id: ID of the employee (manager being configured)
        slot: Backup slot number (1 or 2)
        backup_id: ID of the backup manager to assign (optional)
    """
    action: str
    employee_id: int
    slot: int | None = None
    backup_id: int | None = None
    
    @field_validator('slot', 'backup_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


class TransferTicketPayload(CallbackPayload, prefix='transfer_ticket'):
    """Payload for ticket transfer between employees.
    
    Fields:
        action: Action type - "start", "select", "confirm"
        ticket_id: ID of the ticket to transfer
        target_employee_id: ID of the target employee (optional)
    """
    action: str
    ticket_id: int
    target_employee_id: int | None = None
    
    @field_validator('target_employee_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


class TransferClientsPayload(CallbackPayload, prefix='transfer_clients'):
    """Payload for client transfer between managers.
    
    Fields:
        action: Action type - "start", "select", "confirm"
        source_manager_id: ID of the source manager
        target_manager_id: ID of the target manager (optional)
    """
    action: str
    source_manager_id: int
    target_manager_id: int | None = None
    
    @field_validator('target_manager_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


# ============================================================================
# Common/Example Payloads (Optional)
# ============================================================================

# TODO: Add example payload classes if needed (task 2.9)



# ============================================================================
# Settings Payloads
# ============================================================================

class SettingsPayload(CallbackPayload, prefix='settings'):
    """Payload for settings navigation and configuration.
    
    Used for navigating settings menu and editing configuration values.
    
    Fields:
        action: Action type - "menu", "timeouts", "escalation", "duty_support", 
                "nps", "renewal_reminders", "history", "edit_timeout", 
                "add_escalation_channel", "remove_escalation_channel",
                "edit_duty_account", "reset_timeouts", "reset_escalation"
        setting_key: Key of the setting being edited (optional)
        page: Page number for paginated views, or channel list index for remove_escalation_channel (optional)
    """
    action: str
    setting_key: str | None = None
    page: int | None = None
    
    @field_validator('setting_key', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v
    
    @field_validator('page', mode='before')
    @classmethod
    def empty_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


# ============================================================================
# Analytics/Statistics Payloads
# ============================================================================

class AnalyticsPayload(CallbackPayload, prefix='analytics'):
    """Payload for analytics dashboard navigation and period selection.
    
    Used for navigating analytics dashboard and selecting time periods.
    
    Fields:
        action: Action type - "period" (change period) or "refresh" (reload data)
        period: Time period - "today", "week", or "month" (optional, for period action)
    """
    action: str
    period: str | None = None
    
    @field_validator('period', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty string to None."""
        if v == '' or v is None:
            return None
        return v


# ============================================================================
# Renewal Payloads
# ============================================================================

class RenewalPayload(CallbackPayload, prefix='renewal'):
    """Payload for renewal actions.
    
    Used for subscription renewal flow and related actions.
    
    Fields:
        action: Action type ('renew', 'contact_manager', 'cancel')
    """
    action: str


# ============================================================================
# Backup Manager Escalation Payloads
# ============================================================================

class BackupEscalationPayload(CallbackPayload, prefix='backup_esc'):
    """Payload for backup manager escalation actions.
    
    Used when backup managers receive escalation notifications and need to take action.
    
    Fields:
        action: Action type - "take_over" (take ticket into work)
        ticket_id: ID of the escalated ticket
        escalation_level: Current escalation level (1 for backup1, 2 for backup2)
    """
    action: str
    ticket_id: int
    escalation_level: int


# ============================================================================
# Phone Change Management Payloads
# ============================================================================

class PhoneChangePayload(CallbackPayload, prefix='phone_change'):
    """Payload for phone change management actions.

    Used by administrators to manage phone number change requests.
    
    Fields:
        action: Action type - "list", "view", "approve", "reject", "back"
        ticket_id: ID of the phone change ticket (optional, for view/approve/reject)
    """
    action: str
    ticket_id: int | None = None


class PhoneChangeConfirmPayload(CallbackPayload, prefix='phone_change_confirm'):
    """Payload for user-side phone change confirmation/cancellation.

    Used when user confirms or cancels their phone change request after
    the target account has been verified.

    Fields:
        action: "confirm" or "cancel"
        new_phone: The new phone number being requested (URL-encoded)
    """
    action: str
    new_phone: str


# ============================================================================
# Done / No More Questions Payload
# ============================================================================

class DonePayload(CallbackPayload, prefix='done'):
    """Payload for "Done" button after ticket creation.

    Used when client clicks "✅ Готово" to indicate they have no more questions.
    Sends a friendly farewell message.
    """
    pass


# ============================================================================
# NPS Survey Payloads
# ============================================================================

class NPSRatingPayload(CallbackPayload, prefix='nps_rating'):
    """Payload for NPS rating button press.

    Used when client clicks a rating button (0-10) in NPS survey.

    Fields:
        survey_type: Survey type - "loyalty" or "service_quality"
        rating: Rating value (0-10)
        trigger_event_id: ID of the triggering event (invoice_id or ticket_id)
    """
    survey_type: str
    rating: int
    trigger_event_id: int


class NPSSkipFeedbackPayload(CallbackPayload, prefix='nps_skip'):
    """Payload for skipping feedback comment in NPS survey.

    Used when client clicks "⏭️️ Пропустить" after low rating.

    Fields:
        survey_type: Survey type - "loyalty" or "service_quality"
        rating: Rating value (0-7)
        trigger_event_id: ID of the triggering event
    """
    survey_type: str
    rating: int
    trigger_event_id: int


# ============================================================================
# Employee Self-Service Payloads (меню сотрудника)
# ============================================================================

class StaffSelfServicePayload(CallbackPayload, prefix='staff_self'):
    """Payload for employee self-service menu actions.

    Used when employee navigates the employee menu (shown via /manager for non-admin roles).

    Fields:
        action: Action type - "set_duty_tp", "set_duty_estimate", "toggle_working", "back_to_manager"
    """
    action: str


class StaffSetDutyPayload(CallbackPayload, prefix='staff_duty'):
    """Payload for employee setting themselves as duty specialist.

    Used when TP or estimate specialist clicks "Назначить себя дежурным".

    Fields:
        duty_type: "tp" for technical support duty, "estimate" for estimate consultation duty
        confirm: True to confirm, False to cancel
    """
    duty_type: str
    confirm: bool = False


class StaffToggleWorkingPayload(CallbackPayload, prefix='staff_work'):
    """Payload for employee toggling their working availability.

    Used when employee clicks "Сделать себя активным/неактивным".

    Fields:
        confirm: True to confirm the toggle, False to cancel
    """
    confirm: bool = False
