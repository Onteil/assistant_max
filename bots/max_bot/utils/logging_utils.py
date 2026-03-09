"""
Logging Utilities for MAX Bot

Provides structured logging with consistent format:
- INFO level for all user actions with user_id and context
- ERROR level for all errors with exc_info=True and full traceback
- WARNING level for all validation failures
- Consistent format with relevant context

Requirements: 11.1, 11.2, 11.3, 11.7, 11.8
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ========== User Action Logging ==========


def log_user_action(
    action: str,
    user_id: int,
    chat_id: int,
    context: Optional[Dict[str, Any]] = None,
    **kwargs: Any
) -> None:
    """
    Log user action at INFO level with user_id and context.
    
    Args:
        action: Description of user action
        user_id: MAX user ID
        chat_id: Chat ID
        context: Optional context dictionary
        **kwargs: Additional context fields
    
    Requirements: 11.1, 11.7
    """
    extra_context = {
        "user_id": user_id,
        "chat_id": chat_id,
        "action": action,
    }
    
    if context:
        extra_context.update(context)
    
    if kwargs:
        extra_context.update(kwargs)
    
    logger.info(
        f"User action: {action} (user_id={user_id}, chat_id={chat_id})",
        extra=extra_context
    )


def log_command(
    command: str,
    user_id: int,
    chat_id: int,
    **kwargs: Any
) -> None:
    """
    Log command execution at INFO level.
    
    Args:
        command: Command name (e.g., "/start", "/help")
        user_id: MAX user ID
        chat_id: Chat ID
        **kwargs: Additional context fields
    
    Requirements: 11.1, 11.7
    """
    log_user_action(
        action=f"Command: {command}",
        user_id=user_id,
        chat_id=chat_id,
        command=command,
        **kwargs
    )


def log_state_transition(
    user_id: int,
    chat_id: int,
    from_state: Optional[str],
    to_state: str,
    **kwargs: Any
) -> None:
    """
    Log FSM state transition at INFO level.
    
    Args:
        user_id: MAX user ID
        chat_id: Chat ID
        from_state: Previous state (None if no previous state)
        to_state: New state
        **kwargs: Additional context fields
    
    Requirements: 11.1, 11.7
    """
    log_user_action(
        action=f"State transition: {from_state or 'None'} → {to_state}",
        user_id=user_id,
        chat_id=chat_id,
        from_state=from_state,
        to_state=to_state,
        **kwargs
    )


def log_callback_query(
    callback_action: str,
    user_id: int,
    chat_id: int,
    callback_data: Optional[Dict[str, Any]] = None,
    **kwargs: Any
) -> None:
    """
    Log callback query at INFO level.
    
    Args:
        callback_action: Callback action (e.g., "select_organization")
        user_id: MAX user ID
        chat_id: Chat ID
        callback_data: Optional callback data dictionary
        **kwargs: Additional context fields
    
    Requirements: 11.1, 11.7
    """
    context = {"callback_action": callback_action}
    if callback_data:
        context["callback_data"] = callback_data
    
    log_user_action(
        action=f"Callback: {callback_action}",
        user_id=user_id,
        chat_id=chat_id,
        context=context,
        **kwargs
    )


def log_ticket_creation(
    ticket_type: str,
    ticket_id: int,
    user_id: int,
    chat_id: int,
    **kwargs: Any
) -> None:
    """
    Log ticket creation at INFO level.
    
    Args:
        ticket_type: Type of ticket (INVOICE, SUPPORT, RENEWAL, etc.)
        ticket_id: Created ticket ID
        user_id: MAX user ID
        chat_id: Chat ID
        **kwargs: Additional context fields
    
    Requirements: 11.1, 11.7
    """
    log_user_action(
        action=f"Ticket created: {ticket_type}",
        user_id=user_id,
        chat_id=chat_id,
        ticket_type=ticket_type,
        ticket_id=ticket_id,
        **kwargs
    )


def log_registration(
    user_id: int,
    chat_id: int,
    status: str,
    **kwargs: Any
) -> None:
    """
    Log registration event at INFO level.
    
    Args:
        user_id: MAX user ID
        chat_id: Chat ID
        status: Registration status (PENDING, ACTIVE, etc.)
        **kwargs: Additional context fields
    
    Requirements: 11.1, 11.7
    """
    log_user_action(
        action=f"Registration: {status}",
        user_id=user_id,
        chat_id=chat_id,
        registration_status=status,
        **kwargs
    )


# ========== Error Logging ==========


def log_error(
    error: Exception,
    context: str,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    **kwargs: Any
) -> None:
    """
    Log error at ERROR level with exc_info=True and full traceback.
    
    Args:
        error: Exception that occurred
        context: Context description (e.g., "registration_handler")
        user_id: Optional MAX user ID
        chat_id: Optional chat ID
        **kwargs: Additional context fields
    
    Requirements: 11.2, 11.8
    """
    extra_context = {
        "context": context,
        "error_type": type(error).__name__,
    }
    
    if user_id:
        extra_context["user_id"] = user_id
    if chat_id:
        extra_context["chat_id"] = chat_id
    
    if kwargs:
        extra_context.update(kwargs)
    
    logger.error(
        f"Error in {context}: {error}",
        exc_info=True,
        extra=extra_context
    )


def log_database_error(
    error: Exception,
    operation: str,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    **kwargs: Any
) -> None:
    """
    Log database error at ERROR level.
    
    Args:
        error: Database exception
        operation: Database operation description
        user_id: Optional MAX user ID
        chat_id: Optional chat ID
        **kwargs: Additional context fields
    
    Requirements: 11.2, 11.8
    """
    log_error(
        error=error,
        context=f"database_{operation}",
        user_id=user_id,
        chat_id=chat_id,
        operation=operation,
        **kwargs
    )


def log_api_error(
    error: Exception,
    api_name: str,
    endpoint: Optional[str] = None,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    **kwargs: Any
) -> None:
    """
    Log external API error at ERROR level.
    
    Args:
        error: API exception
        api_name: Name of external API (e.g., "i-TAT")
        endpoint: Optional API endpoint
        user_id: Optional MAX user ID
        chat_id: Optional chat ID
        **kwargs: Additional context fields
    
    Requirements: 11.2, 11.8
    """
    context_data = {"api_name": api_name}
    if endpoint:
        context_data["endpoint"] = endpoint
    
    log_error(
        error=error,
        context=f"api_{api_name}",
        user_id=user_id,
        chat_id=chat_id,
        **{**context_data, **kwargs}
    )


# ========== Validation Logging ==========


def log_validation_failure(
    field: str,
    value: Any,
    reason: str,
    user_id: int,
    chat_id: int,
    **kwargs: Any
) -> None:
    """
    Log validation failure at WARNING level.
    
    Args:
        field: Field name that failed validation
        value: Value that failed (will be truncated if too long)
        reason: Reason for validation failure
        user_id: MAX user ID
        chat_id: Chat ID
        **kwargs: Additional context fields
    
    Requirements: 11.3, 11.7
    """
    # Truncate value if too long
    value_str = str(value)
    if len(value_str) > 100:
        value_str = value_str[:100] + "..."
    
    extra_context = {
        "user_id": user_id,
        "chat_id": chat_id,
        "field": field,
        "value": value_str,
        "reason": reason,
    }
    
    if kwargs:
        extra_context.update(kwargs)
    
    logger.warning(
        f"Validation failure: {field}={value_str} - {reason} (user_id={user_id})",
        extra=extra_context
    )


def log_validation_success(
    field: str,
    user_id: int,
    chat_id: int,
    **kwargs: Any
) -> None:
    """
    Log successful validation at INFO level.
    
    Args:
        field: Field name that passed validation
        user_id: MAX user ID
        chat_id: Chat ID
        **kwargs: Additional context fields
    
    Requirements: 11.1, 11.7
    """
    log_user_action(
        action=f"Validation success: {field}",
        user_id=user_id,
        chat_id=chat_id,
        field=field,
        **kwargs
    )


# ========== Structured Logging Helpers ==========


def create_log_context(
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Create structured log context dictionary.
    
    Args:
        user_id: Optional MAX user ID
        chat_id: Optional chat ID
        **kwargs: Additional context fields
    
    Returns:
        Context dictionary for logging
    
    Requirements: 11.7, 11.8
    """
    context = {}
    
    if user_id is not None:
        context["user_id"] = user_id
    if chat_id is not None:
        context["chat_id"] = chat_id
    
    if kwargs:
        context.update(kwargs)
    
    return context


def log_with_context(
    level: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
    exc_info: bool = False
) -> None:
    """
    Log message with structured context at specified level.
    
    Args:
        level: Log level (INFO, WARNING, ERROR)
        message: Log message
        context: Optional context dictionary
        exc_info: Whether to include exception info
    
    Requirements: 11.7, 11.8
    """
    log_func = getattr(logger, level.lower(), logger.info)
    
    if context:
        log_func(message, extra=context, exc_info=exc_info)
    else:
        log_func(message, exc_info=exc_info)
