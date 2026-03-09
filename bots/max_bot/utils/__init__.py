"""
Utility modules for MAX Bot.
"""

from .error_handling import (
    ValidationError,
    get_validation_error_message,
    handle_api_error,
    handle_database_error,
    handle_unexpected_error,
    handle_validation_error,
    recover_fsm_state,
    retry_with_exponential_backoff,
    with_error_handling,
)
from .html_utils import (
    escape_html,
    escape_html_dict,
    format_list_item,
    format_numbered_item,
    format_profile_field,
    format_user_multiline,
    format_user_text,
    safe_format,
)
from .logging_utils import (
    create_log_context,
    log_api_error,
    log_callback_query,
    log_command,
    log_database_error,
    log_error,
    log_registration,
    log_state_transition,
    log_ticket_creation,
    log_user_action,
    log_validation_failure,
    log_validation_success,
    log_with_context,
)

__all__ = [
    # Error handling
    "ValidationError",
    "get_validation_error_message",
    "handle_api_error",
    "handle_database_error",
    "handle_unexpected_error",
    "handle_validation_error",
    "recover_fsm_state",
    "retry_with_exponential_backoff",
    "with_error_handling",
    # HTML utilities
    "escape_html",
    "escape_html_dict",
    "format_list_item",
    "format_numbered_item",
    "format_profile_field",
    "format_user_multiline",
    "format_user_text",
    "safe_format",
    # Logging
    "create_log_context",
    "log_api_error",
    "log_callback_query",
    "log_command",
    "log_database_error",
    "log_error",
    "log_registration",
    "log_state_transition",
    "log_ticket_creation",
    "log_user_action",
    "log_validation_failure",
    "log_validation_success",
    "log_with_context",
]
