"""
Logging Service

Provides centralized logging utilities for action logging and error logging.
Ensures consistent logging format and context across the application.

Requirements: 32.1-32.5, 33.1-33.5
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Action_Log, ActionType

logger = logging.getLogger(__name__)


# ========== Action Logging ==========


async def log_user_action(
    session: AsyncSession,
    action_type: ActionType,
    tg_user_id: int,
    action_details: dict[str, Any] | None = None,
    ticket_id: int | None = None
) -> Action_Log | None:
    """
    Log user action to Action_Log table.
    
    Args:
        session: Database session
        action_type: Type of action being logged
        tg_user_id: User ID
        action_details: Additional details as JSON (optional)
        ticket_id: Related ticket ID (optional)
    
    Returns:
        Created Action_Log object or None if logging failed
    
    Requirements: 32.1, 32.2, 32.3, 32.4, 32.5
    """
    try:
        action_log = Action_Log(
            action_type=action_type,
            tg_user_id=tg_user_id,
            ticket_id=ticket_id,
            action_details=action_details,
            action_timestamp=datetime.utcnow()
        )
        
        session.add(action_log)
        await session.flush()
        
        logger.info(
            f"Action logged: type={action_type.value}, user={tg_user_id}, "
            f"ticket={ticket_id}, details={action_details}"
        )
        
        return action_log
    
    except SQLAlchemyError as e:
        logger.error(
            f"Failed to log action: type={action_type.value}, user={tg_user_id}, "
            f"error={e}",
            exc_info=True
        )
        # Don't raise - logging failure shouldn't break the main operation
        return None


async def log_ticket_action(
    session: AsyncSession,
    action_type: ActionType,
    ticket_id: int,
    action_details: dict[str, Any] | None = None,
    tg_user_id: int | None = None,
    staff_id: int | None = None
) -> Action_Log | None:
    """
    Log ticket-related action to Action_Log table.
    
    Args:
        session: Database session
        action_type: Type of action being logged
        ticket_id: Ticket ID
        action_details: Additional details as JSON (optional)
        tg_user_id: User ID (optional)
        staff_id: Staff member ID (optional)
    
    Returns:
        Created Action_Log object or None if logging failed
    
    Requirements: 32.1, 32.2, 32.3, 32.4, 32.5
    """
    try:
        action_log = Action_Log(
            action_type=action_type,
            ticket_id=ticket_id,
            tg_user_id=tg_user_id,
            staff_id=staff_id,
            action_details=action_details,
            action_timestamp=datetime.utcnow()
        )
        
        session.add(action_log)
        await session.flush()
        
        logger.info(
            f"Ticket action logged: type={action_type.value}, ticket={ticket_id}, "
            f"user={tg_user_id}, staff={staff_id}, details={action_details}"
        )
        
        return action_log
    
    except SQLAlchemyError as e:
        logger.error(
            f"Failed to log ticket action: type={action_type.value}, "
            f"ticket={ticket_id}, error={e}",
            exc_info=True
        )
        # Don't raise - logging failure shouldn't break the main operation
        return None


async def log_key_conflict(
    session: AsyncSession,
    tg_user_id: int,
    key_number: str,
    conflict_status: str,
    action_details: dict[str, Any] | None = None
) -> Action_Log | None:
    """
    Log GS_Key conflict detection.
    
    Args:
        session: Database session
        tg_user_id: User ID
        key_number: GS_Key number
        conflict_status: Conflict status value
        action_details: Additional details as JSON (optional)
    
    Returns:
        Created Action_Log object or None if logging failed
    
    Requirements: 32.3
    """
    details = action_details or {}
    details.update({
        "key_number": key_number,
        "conflict_status": conflict_status
    })
    
    return await log_user_action(
        session=session,
        action_type=ActionType.KEY_CONFLICT_DETECTED,
        tg_user_id=tg_user_id,
        action_details=details
    )


# ========== Error Logging ==========


def log_api_error(
    operation: str,
    error: Exception,
    context: dict[str, Any]
) -> None:
    """
    Log API error with full context.
    
    Args:
        operation: API operation name
        error: Exception that occurred
        context: Context information (user_id, payload, etc.)
    
    Requirements: 33.1, 33.2, 33.3, 33.4, 33.5
    """
    context_str = ", ".join([f"{k}={v}" for k, v in context.items()])
    
    logger.error(
        f"API error during {operation}: {type(error).__name__}: {str(error)} | "
        f"Context: {context_str}",
        exc_info=True,
        extra={
            "operation": operation,
            "error_type": type(error).__name__,
            "context": context,
            "category": "api_error"
        }
    )


def log_validation_error(
    field_name: str,
    user_input: str,
    error_message: str,
    tg_user_id: int | None = None
) -> None:
    """
    Log validation error.
    
    Args:
        field_name: Name of the field that failed validation
        user_input: User's input value
        error_message: Validation error message
        tg_user_id: User ID for context (optional)
    
    Requirements: 33.1, 33.2, 33.3
    """
    # Truncate long inputs for logging
    truncated_input = user_input[:100] if len(user_input) > 100 else user_input
    
    logger.warning(
        f"Validation error: field={field_name}, user={tg_user_id}, "
        f"input={truncated_input}, error={error_message}",
        extra={
            "field_name": field_name,
            "tg_user_id": tg_user_id,
            "error_message": error_message,
            "category": "validation_error"
        }
    )


def log_database_error(
    operation: str,
    error: Exception,
    context: dict[str, Any]
) -> None:
    """
    Log database error with full context.
    
    Args:
        operation: Database operation description
        error: Exception that occurred
        context: Context information (user_id, query params, etc.)
    
    Requirements: 33.1, 33.2, 33.3, 33.4, 33.5
    """
    context_str = ", ".join([f"{k}={v}" for k, v in context.items()])
    
    logger.error(
        f"Database error during {operation}: {type(error).__name__}: {str(error)} | "
        f"Context: {context_str}",
        exc_info=True,
        extra={
            "operation": operation,
            "error_type": type(error).__name__,
            "context": context,
            "category": "database_error"
        }
    )


# ========== Structured Logging Helpers ==========


def get_user_context(tg_user_id: int, **kwargs) -> dict[str, Any]:
    """
    Build user context dictionary for logging.
    
    Args:
        tg_user_id: User ID
        **kwargs: Additional context fields
    
    Returns:
        Context dictionary
    """
    context = {"tg_user_id": tg_user_id}
    context.update(kwargs)
    return context


def get_ticket_context(ticket_id: int, **kwargs) -> dict[str, Any]:
    """
    Build ticket context dictionary for logging.
    
    Args:
        ticket_id: Ticket ID
        **kwargs: Additional context fields
    
    Returns:
        Context dictionary
    """
    context = {"ticket_id": ticket_id}
    context.update(kwargs)
    return context


def get_api_context(operation: str, **kwargs) -> dict[str, Any]:
    """
    Build API context dictionary for logging.
    
    Args:
        operation: API operation name
        **kwargs: Additional context fields
    
    Returns:
        Context dictionary
    """
    context = {"operation": operation}
    context.update(kwargs)
    return context
