"""
Telegram Bot Utilities

Utility modules for the Telegram bot implementation.
"""

from .escalation_notifications import (
    format_ticket_type,
    format_ticket_status,
    calculate_time_elapsed,
    format_datetime,
    get_reminder_notification_text,
    get_escalation_notification_text,
    get_escalation_notification_keyboard,
    get_reassignment_notification_text,
    get_reassignment_success_text,
    get_take_over_client_notification_text,
    get_take_over_success_text,
    get_contact_staff_text,
    get_error_escalation_not_found,
    get_error_escalation_already_resolved,
    get_error_no_staff_available,
    get_error_staff_not_found,
    get_error_ticket_not_found,
    get_error_generic,
    get_no_active_escalations_text,
)

__all__ = [
    "format_ticket_type",
    "format_ticket_status",
    "calculate_time_elapsed",
    "format_datetime",
    "get_reminder_notification_text",
    "get_escalation_notification_text",
    "get_escalation_notification_keyboard",
    "get_reassignment_notification_text",
    "get_reassignment_success_text",
    "get_take_over_client_notification_text",
    "get_take_over_success_text",
    "get_contact_staff_text",
    "get_error_escalation_not_found",
    "get_error_escalation_already_resolved",
    "get_error_no_staff_available",
    "get_error_staff_not_found",
    "get_error_ticket_not_found",
    "get_error_generic",
    "get_no_active_escalations_text",
]
