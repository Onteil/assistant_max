"""
Error Handler Service

Provides centralized error handling, message sanitization, and retry queue management.
Ensures technical details are not exposed to users while maintaining detailed logs.

Requirements: 25.1-25.5, 33.1-33.5
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ========== Error Message Sanitization ==========


def sanitize_error_message(error: Exception, user_friendly: bool = True) -> str:
    """
    Sanitize error message to remove technical details.
    
    Args:
        error: Exception object
        user_friendly: If True, return user-friendly message; if False, return technical details
    
    Returns:
        Sanitized error message
    
    Requirements: 25.4, 25.5
    """
    if user_friendly:
        # Map exception types to user-friendly messages
        if isinstance(error, httpx.TimeoutException):
            return "⚠️ Сервис временно недоступен. Ваш запрос сохранен и будет обработан в ближайшее время."
        
        elif isinstance(error, httpx.HTTPStatusError):
            if error.response.status_code >= 500:
                return "⚠️ Сервис временно недоступен. Пожалуйста, попробуйте позже."
            elif error.response.status_code == 404:
                return "❌ Запрошенный ресурс не найден."
            elif error.response.status_code == 403:
                return "❌ Доступ запрещен."
            elif error.response.status_code == 401:
                return "❌ Ошибка авторизации."
            else:
                return "❌ Произошла ошибка при обработке запроса."
        
        elif isinstance(error, httpx.ConnectError):
            return "⚠️ Не удается подключиться к сервису. Ваш запрос сохранен и будет обработан позже."
        
        elif isinstance(error, IntegrityError):
            if "unique" in str(error).lower() or "duplicate" in str(error).lower():
                return "❌ Такая запись уже существует."
            else:
                return "❌ Ошибка при сохранении данных. Пожалуйста, проверьте введенные данные."
        
        elif isinstance(error, SQLAlchemyError):
            return "❌ Произошла ошибка. Пожалуйста, попробуйте еще раз через минуту."
        
        elif isinstance(error, ValueError):
            # ValueError usually contains user-relevant information
            return f"❌ {str(error)}"
        
        else:
            return "❌ Произошла ошибка. Пожалуйста, попробуйте еще раз."
    
    else:
        # Return technical details for logging
        return f"{type(error).__name__}: {str(error)}"


def log_error_with_context(
    logger_instance: logging.Logger,
    error: Exception,
    context: dict[str, Any],
    operation: str
) -> None:
    """
    Log error with full context for debugging.
    
    Args:
        logger_instance: Logger instance to use
        error: Exception object
        context: Dictionary with context information (user_id, operation params, etc.)
        operation: Description of the operation that failed
    
    Requirements: 25.4, 25.5, 33.1, 33.2, 33.3, 33.4, 33.5
    """
    # Build context string
    context_str = ", ".join([f"{k}={v}" for k, v in context.items()])
    
    # Log with full details
    logger_instance.error(
        f"Error during {operation}: {type(error).__name__}: {str(error)} | Context: {context_str}",
        exc_info=True,
        extra={
            "operation": operation,
            "error_type": type(error).__name__,
            "context": context
        }
    )


# ========== API Error Handling ==========


async def handle_api_error(
    error: Exception,
    operation: str,
    payload: dict[str, Any],
    session: AsyncSession,
    telegram_id: int | None = None
) -> tuple[bool, str]:
    """
    Handle API errors with retry queue and user notification.
    
    Args:
        error: Exception that occurred
        operation: API operation name (e.g., "register_user", "check_key_conflict")
        payload: Request payload for retry
        session: Database session for retry queue
        telegram_id: User ID for context (optional)
    
    Returns:
        tuple[bool, str]: (should_retry, user_message)
        - should_retry: True if operation was queued for retry
        - user_message: User-friendly message to display
    
    Requirements: 25.1, 25.2, 25.3
    """
    # Log error with context
    context = {
        "operation": operation,
        "telegram_id": telegram_id,
        "payload_keys": list(payload.keys()) if payload else []
    }
    log_error_with_context(logger, error, context, f"API call: {operation}")
    
    # Determine if we should retry
    should_retry = isinstance(error, (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.HTTPStatusError
    ))
    
    if should_retry and isinstance(error, httpx.HTTPStatusError):
        # Only retry on 5xx errors
        should_retry = error.response.status_code >= 500
    
    # Queue for retry if applicable
    if should_retry:
        try:
            from services.retry_service import queue_api_retry
            await queue_api_retry(
                session=session,
                operation=operation,
                payload=payload,
                telegram_id=telegram_id
            )
            logger.info(f"API operation queued for retry: {operation}, user={telegram_id}")
        except Exception as retry_error:
            logger.error(
                f"Failed to queue retry: {retry_error}",
                exc_info=True
            )
            # Continue with user notification even if retry queue fails
    
    # Get user-friendly message
    user_message = sanitize_error_message(error, user_friendly=True)
    
    return should_retry, user_message


# ========== Database Error Handling ==========


async def handle_database_error(
    error: Exception,
    operation: str,
    context: dict[str, Any],
    session: AsyncSession
) -> str:
    """
    Handle database errors with rollback and user notification.
    
    Args:
        error: Exception that occurred
        operation: Database operation description
        context: Context information for logging
        session: Database session (will be rolled back)
    
    Returns:
        str: User-friendly error message
    
    Requirements: 25.4, 25.5, 33.1, 33.2, 33.3
    """
    # Log error with context
    log_error_with_context(logger, error, context, f"Database operation: {operation}")
    
    # Rollback transaction
    try:
        await session.rollback()
        logger.debug(f"Transaction rolled back for operation: {operation}")
    except Exception as rollback_error:
        logger.error(
            f"Error during rollback: {rollback_error}",
            exc_info=True
        )
    
    # Get user-friendly message
    user_message = sanitize_error_message(error, user_friendly=True)
    
    return user_message


# ========== Validation Error Handling ==========


def format_validation_error(
    field_name: str,
    error_message: str,
    user_input: str | None = None,
    format_example: str | None = None
) -> str:
    """
    Format validation error with helpful guidance.
    
    Args:
        field_name: Name of the field that failed validation
        error_message: Validation error message
        user_input: User's input (optional, for context)
        format_example: Example of correct format (optional)
    
    Returns:
        Formatted error message with guidance
    
    Requirements: 26.1, 26.2, 26.3, 26.4
    """
    message = f"❌ {error_message}\n"
    
    if user_input:
        # Truncate long inputs
        display_input = user_input[:50]
        if len(user_input) > 50:
            display_input += "..."
        message += f"\nВы ввели: {display_input}\n"
    
    if format_example:
        message += f"\nПример правильного формата: {format_example}\n"
    
    message += "\nПожалуйста, попробуйте еще раз:"
    
    return message
