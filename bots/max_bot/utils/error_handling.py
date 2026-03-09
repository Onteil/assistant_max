"""
Error Handling Utilities for MAX Bot

Provides comprehensive error handling with:
- User-friendly Russian error messages
- Database error handling with transaction rollback
- External API error handling with retry logic
- FSM state error recovery
- Validation error handling

Requirements: 11.4, 11.5, 11.6
"""

import asyncio
import logging
from typing import Any, Callable, Optional, TypeVar

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.texts import (
    ERROR_API_UNAVAILABLE,
    ERROR_GENERAL,
    ERROR_INVALID_INPUT,
    ERROR_VALIDATION_EMAIL,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    ERROR_VALIDATION_PHONE,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


# ========== Validation Error Handling ==========


class ValidationError(Exception):
    """Custom exception for validation errors with user-friendly messages."""
    
    def __init__(self, message: str, field: Optional[str] = None):
        """
        Initialize validation error.
        
        Args:
            message: User-friendly error message in Russian
            field: Optional field name that failed validation
        """
        self.message = message
        self.field = field
        super().__init__(message)


def get_validation_error_message(field: str) -> str:
    """
    Get user-friendly validation error message for a field.
    
    Args:
        field: Field name (phone, email, inn, key)
    
    Returns:
        User-friendly error message in Russian
    
    Requirements: 11.4
    """
    error_messages = {
        "phone": ERROR_VALIDATION_PHONE,
        "email": ERROR_VALIDATION_EMAIL,
        "inn": ERROR_VALIDATION_INN,
        "key": ERROR_VALIDATION_KEY,
        "gs_key": ERROR_VALIDATION_KEY,
    }
    
    return error_messages.get(field.lower(), ERROR_INVALID_INPUT)


async def handle_validation_error(
    error: ValidationError,
    chat_id: int,
    adapter: MAXMessengerAdapter
) -> None:
    """
    Handle validation error by sending user-friendly message.
    
    Args:
        error: Validation error
        chat_id: Chat ID to send message to
        adapter: Messenger adapter
    
    Requirements: 11.4
    """
    logger.warning(
        f"Validation error in chat {chat_id}: {error.message}",
        extra={"field": error.field, "chat_id": chat_id}
    )
    
    await adapter.send_message(
        chat_id=chat_id,
        text=error.message,
        parse_mode="HTML"
    )


# ========== Database Error Handling ==========


async def handle_database_error(
    error: SQLAlchemyError,
    session: AsyncSession,
    chat_id: int,
    adapter: MAXMessengerAdapter,
    user_id: Optional[int] = None
) -> None:
    """
    Handle database error with transaction rollback.
    
    Performs:
    1. Transaction rollback
    2. Error logging with context
    3. User-friendly error message
    
    Args:
        error: SQLAlchemy error
        session: Database session to rollback
        chat_id: Chat ID to send message to
        adapter: Messenger adapter
        user_id: Optional user ID for logging
    
    Requirements: 11.4
    """
    # Rollback transaction
    try:
        await session.rollback()
        logger.info(f"Transaction rolled back for chat {chat_id}")
    except Exception as rollback_error:
        logger.error(
            f"Failed to rollback transaction: {rollback_error}",
            exc_info=True
        )
    
    # Log error with context
    if isinstance(error, IntegrityError):
        logger.error(
            f"Database integrity error in chat {chat_id}: {error}",
            exc_info=True,
            extra={
                "chat_id": chat_id,
                "user_id": user_id,
                "error_type": "IntegrityError"
            }
        )
        error_message = "❌ Эти данные уже существуют в системе. Пожалуйста, проверьте введенную информацию."
    else:
        logger.error(
            f"Database error in chat {chat_id}: {error}",
            exc_info=True,
            extra={
                "chat_id": chat_id,
                "user_id": user_id,
                "error_type": type(error).__name__
            }
        )
        error_message = ERROR_GENERAL
    
    # Send user-friendly message
    await adapter.send_message(
        chat_id=chat_id,
        text=error_message,
        parse_mode="HTML"
    )


# ========== External API Error Handling with Retry ==========


async def retry_with_exponential_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs: Any
) -> T:
    """
    Retry function with exponential backoff.
    
    Retries up to max_attempts times with exponentially increasing delays:
    - Attempt 1: immediate
    - Attempt 2: wait initial_delay seconds
    - Attempt 3: wait initial_delay * backoff_factor seconds
    - etc.
    
    Args:
        func: Async function to retry
        *args: Positional arguments for func
        max_attempts: Maximum number of attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        backoff_factor: Backoff multiplier (default: 2.0)
        **kwargs: Keyword arguments for func
    
    Returns:
        Result from successful function call
    
    Raises:
        Last exception if all attempts fail
    
    Requirements: 11.5
    """
    last_exception = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            result = await func(*args, **kwargs)
            
            if attempt > 1:
                logger.info(
                    f"Function {func.__name__} succeeded on attempt {attempt}"
                )
            
            return result
        
        except Exception as e:
            last_exception = e
            
            if attempt < max_attempts:
                delay = initial_delay * (backoff_factor ** (attempt - 1))
                logger.warning(
                    f"Function {func.__name__} failed on attempt {attempt}/{max_attempts}, "
                    f"retrying in {delay:.1f}s: {e}"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Function {func.__name__} failed after {max_attempts} attempts: {e}",
                    exc_info=True
                )
    
    # All attempts failed
    raise last_exception


async def handle_api_error(
    error: Exception,
    chat_id: int,
    adapter: MAXMessengerAdapter,
    api_name: str = "external API",
    user_id: Optional[int] = None
) -> None:
    """
    Handle external API error with graceful degradation.
    
    Logs error and sends user-friendly message.
    
    Args:
        error: API error
        chat_id: Chat ID to send message to
        adapter: Messenger adapter
        api_name: Name of API for logging (default: "external API")
        user_id: Optional user ID for logging
    
    Requirements: 11.5, 11.6
    """
    logger.error(
        f"{api_name} error in chat {chat_id}: {error}",
        exc_info=True,
        extra={
            "chat_id": chat_id,
            "user_id": user_id,
            "api_name": api_name,
            "error_type": type(error).__name__
        }
    )
    
    await adapter.send_message(
        chat_id=chat_id,
        text=ERROR_API_UNAVAILABLE,
        parse_mode="HTML"
    )


# ========== FSM State Error Recovery ==========


async def recover_fsm_state(
    context: Any,
    chat_id: int,
    adapter: MAXMessengerAdapter,
    user_id: Optional[int] = None
) -> None:
    """
    Recover from FSM state error by clearing state.
    
    Args:
        context: FSM context
        chat_id: Chat ID
        adapter: Messenger adapter
        user_id: Optional user ID for logging
    
    Requirements: 11.6
    """
    try:
        await context.clear()
        logger.info(
            f"FSM state cleared for recovery in chat {chat_id}",
            extra={"chat_id": chat_id, "user_id": user_id}
        )
    except Exception as e:
        logger.error(
            f"Failed to clear FSM state in chat {chat_id}: {e}",
            exc_info=True,
            extra={"chat_id": chat_id, "user_id": user_id}
        )
    
    await adapter.send_message(
        chat_id=chat_id,
        text="❌ Произошла ошибка. Ваше действие было отменено. Используйте /start для начала работы.",
        parse_mode="HTML"
    )


# ========== Unexpected Error Handling ==========


async def handle_unexpected_error(
    error: Exception,
    chat_id: int,
    adapter: MAXMessengerAdapter,
    context_info: Optional[str] = None,
    user_id: Optional[int] = None
) -> None:
    """
    Handle unexpected error with generic user message.
    
    Logs full traceback and sends generic error message to user.
    
    Args:
        error: Unexpected error
        chat_id: Chat ID to send message to
        adapter: Messenger adapter
        context_info: Optional context information for logging
        user_id: Optional user ID for logging
    
    Requirements: 11.6
    """
    logger.error(
        f"Unexpected error in chat {chat_id}: {error}",
        exc_info=True,
        extra={
            "chat_id": chat_id,
            "user_id": user_id,
            "context": context_info,
            "error_type": type(error).__name__
        }
    )
    
    await adapter.send_message(
        chat_id=chat_id,
        text=ERROR_GENERAL,
        parse_mode="HTML"
    )


# ========== Decorator for Handler Error Handling ==========


def with_error_handling(handler_func: Callable) -> Callable:
    """
    Decorator to add comprehensive error handling to handlers.
    
    Wraps handler with try-except blocks for:
    - Validation errors
    - Database errors
    - API errors
    - Unexpected errors
    
    Usage:
        @with_error_handling
        async def my_handler(event, context, session, adapter):
            # handler code
    
    Requirements: 11.4, 11.5, 11.6
    """
    async def wrapper(*args, **kwargs):
        # Extract common parameters
        event = args[0] if args else None
        context = kwargs.get('context') or (args[1] if len(args) > 1 else None)
        session = kwargs.get('session') or (args[2] if len(args) > 2 else None)
        adapter = kwargs.get('adapter') or (args[3] if len(args) > 3 else None)
        
        # Extract chat_id and user_id
        chat_id = None
        user_id = None
        if event and hasattr(event, 'message'):
            if hasattr(event.message, 'recipient'):
                chat_id = event.message.recipient.chat_id
            if hasattr(event.message, 'sender'):
                user_id = event.message.sender.user_id
        
        try:
            return await handler_func(*args, **kwargs)
        
        except ValidationError as e:
            if chat_id and adapter:
                await handle_validation_error(e, chat_id, adapter)
        
        except SQLAlchemyError as e:
            if chat_id and adapter and session:
                await handle_database_error(e, session, chat_id, adapter, user_id)
        
        except Exception as e:
            if chat_id and adapter:
                await handle_unexpected_error(
                    e, chat_id, adapter,
                    context_info=f"Handler: {handler_func.__name__}",
                    user_id=user_id
                )
    
    return wrapper
