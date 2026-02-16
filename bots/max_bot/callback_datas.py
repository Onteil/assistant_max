"""
Callback Data Structures for MAX Bot

This module defines typed callback payload classes using maxapi's CallbackPayload.
These provide type-safe callback data handling for inline keyboard buttons.

Pattern: Use CallbackPayload with short prefixes to save bytes in callback_data
- Document the purpose of each field
- Use Optional for optional parameters
- action: str - for determining the type of action (view, select, delete, etc.)

Requirements: 5.1, 5.2, 5.4, 5.5
"""

from typing import Optional

from maxapi.filters.callback_payload import CallbackPayload


class OrganizationCallback(CallbackPayload, prefix="org"):
    """
    Callback data for organization selection.
    
    Fields:
    - action: Type of action ('select', 'add_new', 'skip', 'page')
    - inn: Organization INN (optional)
    - page: Page number for pagination (optional)
    """
    action: str
    inn: Optional[str] = None
    page: Optional[int] = None


class KeyCallback(CallbackPayload, prefix="key"):
    """
    Callback data for GS_Key selection.
    
    Fields:
    - action: Type of action ('toggle', 'add_new', 'done', 'skip', 'page')
    - key_id: GS_Key ID (optional)
    - page: Page number for pagination (optional)
    """
    action: str
    key_id: Optional[int] = None
    page: Optional[int] = None


class DeliveryCallback(CallbackPayload, prefix="dlv"):
    """
    Callback data for delivery method selection.
    
    Fields:
    - method: Delivery method ('telegram', 'email')
    """
    method: str


class ProfileCallback(CallbackPayload, prefix="prof"):
    """
    Callback data for profile actions.
    
    Fields:
    - action: Type of action ('add_inn', 'add_key', 'change_phone', 'toggle_notif', 'back')
    """
    action: str


class ExampleItemCallback(CallbackPayload, prefix="item"):
    """
    Example callback factory for working with list items.
    
    Fields:
    - action: Type of action ('view', 'select', 'delete', 'edit')
    - item_id: Item ID (optional for actions like 'list')
    - page: Page number for pagination (optional)
    """
    action: str
    item_id: Optional[int] = None
    page: Optional[int] = None


class ExampleNavigationCallback(CallbackPayload, prefix="nav"):
    """
    Example callback factory for navigation between sections.
    
    Fields:
    - action: Type of action ('back', 'forward', 'cancel')
    - from_section: Where the user came from (for contextual return)
    - data: Additional data (optional)
    """
    action: str
    from_section: Optional[str] = None
    data: Optional[str] = None


class EmployeeMenuCallback(CallbackPayload, prefix="emp_menu"):
    """
    Callback data for employee main menu.
    
    Fields:
    - action: Type of action ('active_tickets', 'archive_search', 'settings', 'admin_panel')
    """
    action: str


class TicketActionCallback(CallbackPayload, prefix="ticket_act"):
    """
    Callback data for ticket actions.
    
    Fields:
    - action: Type of action ('take_ticket', 'close_ticket', 'set_waiting', 'transfer_ticket', 'view_history', 'exit_focus')
    - ticket_id: Ticket ID
    """
    action: str
    ticket_id: int


class EmployeeSelectionCallback(CallbackPayload, prefix="emp_sel"):
    """
    Callback data for employee selection when transferring tickets.
    
    Fields:
    - action: Type of action ('select', 'cancel')
    - employee_id: Employee ID (optional for 'cancel' action)
    """
    action: str
    employee_id: Optional[int] = None


class TicketHistoryCallback(CallbackPayload, prefix="ticket_hist"):
    """
    Callback data for ticket history pagination.
    
    Fields:
    - action: Type of action ('page', 'back')
    - ticket_id: Ticket ID
    - page: Page number (default 0)
    """
    action: str
    ticket_id: int
    page: int = 0


class ArchiveSearchCallback(CallbackPayload, prefix="arch_srch"):
    """
    Callback data for archive search results.
    
    Fields:
    - action: Type of action ('view_ticket', 'page', 'back')
    - ticket_id: Ticket ID (optional for 'page', 'back' actions)
    - page: Page number (default 0)
    """
    action: str
    ticket_id: Optional[int] = None
    page: int = 0
