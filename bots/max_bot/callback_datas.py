"""
Callback Data Structures for MAX Bot

This module defines typed callback payload classes for inline keyboard buttons.
These provide type-safe callback data handling.

Pattern: Use dataclasses with short prefixes to save bytes in callback_data
- Document the purpose of each field
- Use Optional for optional parameters
- action: str - for determining the type of action (view, select, delete, etc.)

Requirements: 5.1, 5.2, 5.4, 5.5
"""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class OrganizationCallback:
    """
    Callback data for organization selection.
    
    Fields:
    - action: Type of action ('select', 'add_new', 'skip', 'page', 'cancel')
    - inn: Organization INN (optional)
    - page: Page number for pagination (optional)
    """
    action: str
    inn: Optional[str] = None
    page: Optional[int] = None
    
    def model_dump(self) -> dict:
        """Convert dataclass to dict for compatibility with Pydantic-style code"""
        return asdict(self)
    
    @staticmethod
    def filter():
        """Filter for organization selection callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["select", "add_new", "skip", "page", "cancel"])


@dataclass
@dataclass
class KeyCallback:
    """
    Callback data for GS_Key selection.
    
    Fields:
    - action: Type of action ('toggle', 'add_new', 'done', 'skip', 'page', 'cancel')
    - key_id: GS_Key ID (optional)
    - page: Page number for pagination (optional)
    """
    action: str
    key_id: Optional[int] = None
    page: Optional[int] = None
    
    def model_dump(self) -> dict:
        """Convert dataclass to dict for compatibility with Pydantic-style code"""
        return asdict(self)
    
    @staticmethod
    def filter():
        """Filter for key selection callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["toggle", "add_new", "done", "skip", "page", "cancel"])
        return lambda: True


@dataclass
class DeliveryCallback:
    """
    Callback data for delivery method selection.
    
    Fields:
    - method: Delivery method ('telegram', 'email', 'cancel')
    """
    method: str
    
    def model_dump(self) -> dict:
        """Convert dataclass to dict for compatibility with Pydantic-style code"""
        return asdict(self)
    
    @staticmethod
    def filter():
        """Filter for delivery method callbacks"""
        from maxapi import F
        return F.callback.payload.method.in_(["telegram", "email", "cancel"])


@dataclass
class ProfileCallback:
    """
    Callback data for profile actions.
    
    Fields:
    - action: Type of action ('add_inn', 'add_key', 'change_phone', 'toggle_notif', 'back')
    """
    action: str
    
    def model_dump(self) -> dict:
        """Convert dataclass to dict for compatibility with Pydantic-style code"""
        return asdict(self)
    
    @staticmethod
    def filter():
        """Filter for profile action callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["add_inn", "add_key", "change_phone", "toggle_notif", "back"])


@dataclass
class KeyConflictCallback:
    """
    Callback data for key conflict resolution.
    
    Fields:
    - action: Type of action ('retry', 'continue')
    """
    action: str
    
    def model_dump(self) -> dict:
        """Convert dataclass to dict for compatibility with Pydantic-style code"""
        return asdict(self)
    
    @staticmethod
    def filter():
        """Filter for key conflict resolution callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["retry", "continue"])


# TODO: Add RenewalCallback for MAX bot subscription renewal feature
# @dataclass
# class RenewalCallback:
#     """
#     Callback data for subscription renewal actions.
#     
#     Fields:
#     - action: Type of action ('renew', 'renew_from_notification', 'contact_manager', 'cancel')
#     """
#     action: str
#     
#     @staticmethod
#     def filter():
#         """Placeholder filter method for compatibility"""
#         return lambda: True


@dataclass
class ExampleItemCallback:
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
    
    @staticmethod
    def filter(condition=None):
        """Filter for example item callbacks - only matches 'example_' prefixed actions"""
        from maxapi import F
        # Only match actions that start with 'example_' to avoid interfering with real handlers
        return F.callback.payload.action.startswith("example_")


@dataclass
class ExampleNavigationCallback:
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
    
    @staticmethod
    def filter(condition=None):
        """Filter for example navigation callbacks - only matches 'example_nav_' prefixed actions"""
        from maxapi import F
        # Only match actions that start with 'example_nav_' to avoid interfering with real handlers
        return F.callback.payload.action.startswith("example_nav_")


@dataclass
class EmployeeMenuCallback:
    """
    Callback data for employee main menu.
    
    Fields:
    - action: Type of action ('active_tickets', 'archive_search', 'settings', 'admin_panel')
    """
    action: str
    
    @staticmethod
    def filter():
        """Filter for employee menu callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["active_tickets", "archive_search", "settings", "admin_panel"])


@dataclass
class TicketListCallback:
    """
    Callback data for ticket list buttons.
    
    Used in active tickets list inline keyboard where each row represents one ticket.
    
    Fields:
    - action: Type of action ('focus_ticket', 'ticket_actions')
    - ticket_id: Ticket ID
    
    Actions:
    - 'focus_ticket': Direct entry into focus mode on the ticket
    - 'ticket_actions': Open actions menu with ticket card
    """
    action: str
    ticket_id: int
    
    @staticmethod
    def filter():
        """Filter for ticket list callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["focus_ticket", "ticket_actions"])


@dataclass
class TicketActionCallback:
    """
    Callback data for ticket actions.
    
    Fields:
    - action: Type of action ('take_ticket', 'close_ticket', 'set_waiting', 'transfer_ticket', 'view_history', 'exit_focus', 'back_to_list')
    - ticket_id: Ticket ID
    """
    action: str
    ticket_id: int
    
    @staticmethod
    def filter():
        """Filter for ticket action callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["take_ticket", "close_ticket", "set_waiting", "transfer_ticket", "view_history", "exit_focus", "back_to_list"])


@dataclass
class EmployeeSelectionCallback:
    """
    Callback data for employee selection when transferring tickets.
    
    Fields:
    - action: Type of action ('select', 'cancel')
    - employee_id: Employee ID (optional for 'cancel' action)
    """
    action: str
    employee_id: Optional[int] = None
    
    @staticmethod
    def filter():
        """Filter for employee selection callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["select", "cancel"])


@dataclass
class TicketHistoryCallback:
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
    
    @staticmethod
    def filter():
        """Filter for ticket history callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["page", "back"])


@dataclass
class ArchiveSearchCallback:
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
    
    @staticmethod
    def filter():
        """Filter for archive search callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["view_ticket", "page", "back"])


@dataclass
class ClientArchiveCallback:
    """
    Callback data for client archive interactions.
    
    Fields:
    - action: Type of action ('filter', 'page', 'view_ticket', 'close')
    - filter_type: Filter type ('invoice', 'technical_support', 'renewal', 'all')
    - ticket_id: Ticket ID (optional)
    - page: Page number (default 0)
    """
    action: str
    filter_type: Optional[str] = None
    ticket_id: Optional[int] = None
    page: int = 0
    
    def model_dump(self) -> dict:
        """Convert dataclass to dict for compatibility with Pydantic-style code"""
        return asdict(self)
    
    @staticmethod
    def filter():
        """Filter for client archive callbacks"""
        from maxapi import F
        return F.callback.payload.action.in_(["filter", "page", "view_ticket", "close"])
