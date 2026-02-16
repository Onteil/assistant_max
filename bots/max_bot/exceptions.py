"""
MAX API Error Handling

This module provides custom exception classes and error handling utilities
for MAX Bot API operations.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MAXAPIError(Exception):
    """
    Exception raised for MAX API errors.
    
    This exception encapsulates error information from MAX API responses,
    including error codes and messages for proper error handling and recovery.
    
    Attributes:
        code: HTTP status code or MAX API error code
        message: Human-readable error message
        response: Optional raw response data from the API
    
    Common error codes:
        400: Bad Request - Invalid parameters or malformed request
        401: Unauthorized - Invalid or missing authentication token
        403: Forbidden - Insufficient permissions
        429: Too Many Requests - Rate limit exceeded
        500: Internal Server Error - Server-side error
        502: Bad Gateway - Gateway or proxy error
        503: Service Unavailable - Service temporarily unavailable
    """

    def __init__(
        self,
        code: int,
        message: str,
        response: Optional[dict] = None
    ):
        """
        Initialize MAX API error.
        
        Args:
            code: Error code (HTTP status code or API-specific code)
            message: Error message describing what went wrong
            response: Optional raw response data from the API
        """
        self.code = code
        self.message = message
        self.response = response
        super().__init__(f"MAX API Error {code}: {message}")

    def is_rate_limit_error(self) -> bool:
        """Check if this is a rate limiting error (429)."""
        return self.code == 429

    def is_server_error(self) -> bool:
        """Check if this is a server error (5xx)."""
        return 500 <= self.code < 600

    def is_auth_error(self) -> bool:
        """Check if this is an authentication error (401)."""
        return self.code == 401

    def is_client_error(self) -> bool:
        """Check if this is a client error (4xx)."""
        return 400 <= self.code < 500

    def is_retryable(self) -> bool:
        """
        Check if this error is retryable.
        
        Returns:
            True if the error is transient and the request can be retried
        """
        # Rate limiting and server errors are typically retryable
        return self.is_rate_limit_error() or self.is_server_error()

    def __repr__(self) -> str:
        """Return detailed string representation."""
        return f"MAXAPIError(code={self.code}, message='{self.message}')"



import asyncio
from typing import Callable, TypeVar, Any, Optional
from functools import wraps

T = TypeVar('T')


async def handle_max_api_error(
    error: MAXAPIError,
    admin_notification_callback: Optional[Callable[[str], Any]] = None
) -> str:
    """
    Handle MAX API errors with appropriate recovery strategies.
    
    This function implements error handling strategies based on error type:
    - Rate limiting (429): Log and indicate retry needed
    - Server errors (5xx): Log and indicate retry needed
    - Auth errors (401): Log, notify admin, and indicate failure
    - Other errors: Log and indicate failure
    
    Args:
        error: The MAXAPIError to handle
        admin_notification_callback: Optional async callback to notify admins
        
    Returns:
        Action string: "retry" for retryable errors, "fail" for non-retryable
    """
    if error.is_rate_limit_error():
        logger.warning(
            f"Rate limit exceeded (429). Request should be retried with backoff. "
            f"Message: {error.message}"
        )
        return "retry"

    elif error.is_server_error():
        logger.error(
            f"MAX API server error ({error.code}). Request should be retried. "
            f"Message: {error.message}"
        )
        return "retry"

    elif error.is_auth_error():
        logger.critical(
            f"MAX API authentication error (401). Check bot token configuration. "
            f"Message: {error.message}"
        )

        # Notify admin if callback provided
        if admin_notification_callback:
            try:
                notification_msg = (
                    f"🚨 CRITICAL: MAX Bot Authentication Error\n\n"
                    f"Error Code: {error.code}\n"
                    f"Message: {error.message}\n\n"
                    f"Action Required: Check MAX_BOT_TOKEN configuration"
                )
                await admin_notification_callback(notification_msg)
            except Exception as e:
                logger.error(f"Failed to send admin notification: {e}")

        return "fail"

    else:
        logger.error(
            f"MAX API error ({error.code}): {error.message}",
            extra={"response": error.response}
        )
        return "fail"


async def retry_with_exponential_backoff(
    func: Callable[..., T],
    *args,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    **kwargs
) -> T:
    """
    Retry a function with exponential backoff strategy.
    
    This function implements exponential backoff for retrying failed operations:
    - First retry: wait initial_delay seconds
    - Second retry: wait initial_delay * backoff_factor seconds
    - Third retry: wait initial_delay * backoff_factor^2 seconds
    - And so on, up to max_delay
    
    Args:
        func: Async function to retry
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        backoff_factor: Multiplier for delay on each retry (default: 2.0)
        **kwargs: Keyword arguments for func
        
    Returns:
        Result from successful function execution
        
    Raises:
        MAXAPIError: If all retries are exhausted
        Exception: If a non-retryable error occurs
    """
    last_error = None
    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            # Attempt to execute the function
            result = await func(*args, **kwargs)

            # Log success if this was a retry
            if attempt > 0:
                logger.info(f"Operation succeeded after {attempt} retries")

            return result

        except MAXAPIError as e:
            last_error = e

            # Check if error is retryable
            if not e.is_retryable():
                logger.error(f"Non-retryable error encountered: {e}")
                raise

            # Check if we have retries left
            if attempt >= max_retries:
                logger.error(
                    f"Max retries ({max_retries}) exhausted for operation. "
                    f"Last error: {e}"
                )
                raise

            # Log retry attempt
            logger.warning(
                f"Retryable error on attempt {attempt + 1}/{max_retries + 1}: {e}. "
                f"Retrying in {delay:.1f} seconds..."
            )

            # Wait before retrying
            await asyncio.sleep(delay)

            # Calculate next delay with exponential backoff
            delay = min(delay * backoff_factor, max_delay)

        except Exception as e:
            # Non-MAX API errors are not retried
            logger.error(f"Unexpected error during operation: {e}")
            raise

    # This should not be reached, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Retry logic failed unexpectedly")


def with_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0
):
    """
    Decorator to add retry logic with exponential backoff to async functions.
    
    Usage:
        @with_retry(max_retries=3, initial_delay=1.0)
        async def send_message(chat_id: int, text: str):
            # Function implementation
            pass
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Multiplier for delay on each retry
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await retry_with_exponential_backoff(
                func,
                *args,
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                backoff_factor=backoff_factor,
                **kwargs
            )
        return wrapper
    return decorator



from maxapi import Bot
from maxapi.types import MessageCreated, UpdateUnion


async def safe_handler_execution(
    handler: Callable,
    event: UpdateUnion,
    data: dict,
    bot: Optional[Bot] = None,
    error_message: str = "❌ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
) -> Any:
    """
    Execute a handler with comprehensive error recovery logic.
    
    This wrapper provides:
    1. Automatic retry for transient MAX API errors (rate limits, server errors)
    2. User-friendly error messages sent to the chat on failures
    3. Detailed error logging for debugging
    4. Graceful degradation on non-retryable errors
    
    Args:
        handler: The handler function to execute
        event: The update event from MAX
        data: Context data dictionary
        bot: Optional Bot instance for sending error messages
        error_message: Custom error message to send to users on failure
        
    Returns:
        Result from handler execution, or None if error occurred
        
    Usage:
        @dp.message(Command("start"))
        async def start_handler(message: MessageCreated, **kwargs):
            # Handler implementation
            pass
        
        # Wrap handler execution
        result = await safe_handler_execution(
            start_handler,
            message,
            data,
            bot=bot
        )
    """
    try:
        # Execute handler with retry logic for MAX API errors
        result = await retry_with_exponential_backoff(
            handler,
            event,
            data,
            max_retries=2,  # Limit retries for handlers to avoid long delays
            initial_delay=0.5,
            max_delay=5.0
        )
        return result

    except MAXAPIError as e:
        # MAX API error that exhausted retries
        logger.error(
            f"MAX API error in handler after retries: {e}",
            extra={
                "error_code": e.code,
                "error_message": e.message,
                "event_type": event.update_type if hasattr(event, 'update_type') else "unknown"
            }
        )

        # Send user-friendly error message
        await _send_error_message_to_user(event, bot, error_message)
        return None

    except Exception as e:
        # Unexpected error
        logger.error(
            f"Unexpected error in handler: {e}",
            exc_info=True,
            extra={
                "event_type": event.update_type if hasattr(event, 'update_type') else "unknown",
                "handler": handler.__name__ if hasattr(handler, '__name__') else "unknown"
            }
        )

        # Send user-friendly error message
        await _send_error_message_to_user(event, bot, error_message)
        return None


async def _send_error_message_to_user(
    event: UpdateUnion,
    bot: Optional[Bot],
    error_message: str
) -> None:
    """
    Send error message to user if possible.
    
    Args:
        event: The update event
        bot: Bot instance for sending messages
        error_message: Error message to send
    """
    if not bot:
        logger.warning("No bot instance provided, cannot send error message to user")
        return

    try:
        # Extract chat_id from event
        chat_id = None

        if isinstance(event, MessageCreated):
            chat_id = event.message.chat.chat_id
        elif hasattr(event, 'message') and hasattr(event.message, 'chat'):
            chat_id = event.message.chat.chat_id
        elif hasattr(event, 'chat') and hasattr(event.chat, 'chat_id'):
            chat_id = event.chat.chat_id

        if chat_id:
            await bot.send_message(
                chat_id=chat_id,
                text=error_message
            )
            logger.info(f"Sent error message to user in chat {chat_id}")
        else:
            logger.warning("Could not extract chat_id from event to send error message")

    except Exception as e:
        logger.error(f"Failed to send error message to user: {e}")


def safe_handler(
    error_message: str = "❌ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
):
    """
    Decorator to wrap handlers with safe execution logic.
    
    This decorator automatically adds error handling and retry logic to handlers,
    ensuring that:
    1. Transient errors are retried automatically
    2. Users receive friendly error messages on failures
    3. Errors are logged for debugging
    4. The application doesn't crash on handler errors
    
    Usage:
        @dp.message(Command("start"))
        @safe_handler(error_message="Не удалось запустить бота. Попробуйте позже.")
        async def start_handler(message: MessageCreated, bot: Bot, **kwargs):
            # Handler implementation
            await bot.send_message(message.chat.chat_id, "Welcome!")
    
    Args:
        error_message: Custom error message to send to users on failure
        
    Returns:
        Decorated handler with safe execution logic
    """
    def decorator(handler: Callable) -> Callable:
        @wraps(handler)
        async def wrapper(event: UpdateUnion, **kwargs) -> Any:
            # Extract bot from kwargs if available
            bot = kwargs.get('bot')
            data = kwargs

            return await safe_handler_execution(
                handler,
                event,
                data,
                bot=bot,
                error_message=error_message
            )
        return wrapper
    return decorator
