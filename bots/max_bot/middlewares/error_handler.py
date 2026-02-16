"""
Error Handler Middleware for MAX Bot

This middleware catches and logs handler exceptions to prevent application crashes.
"""

import logging
import traceback
from typing import Any, Awaitable, Callable, Dict

from maxapi import Bot
from maxapi.filters.middleware import BaseMiddleware
from maxapi.types import MessageCreated, UpdateUnion

from constants import ERROR_CHANNEL, MAX_BOT_TOKEN
from ..exceptions import MAXAPIError, handle_max_api_error

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    """
    Middleware to catch and log handler exceptions.
    
    This middleware wraps handler execution in a try-except block to:
    1. Prevent application crashes from unhandled exceptions
    2. Log detailed error information including traceback
    3. Send error notifications to admin channel (if configured)
    4. Send user-friendly error messages to users
    
    Usage:
        error_handler = ErrorHandlerMiddleware()
        dp.middleware(error_handler)
    """

    async def __call__(
        self,
        handler: Callable[[UpdateUnion, Dict[str, Any]], Awaitable[Any]],
        event: UpdateUnion,
        data: Dict[str, Any],
    ) -> Any:
        """
        Execute handler with error handling.
        
        Args:
            handler: Next handler in the chain
            event: Update event from MAX
            data: Context data dictionary
            
        Returns:
            Result from handler execution or None if error occurred
        """
        try:
            # Execute handler
            return await handler(event, data)

        except MAXAPIError as e:
            # Handle MAX API specific errors
            logger.error(
                f"MAX API error in handler: {e}",
                exc_info=True,
                extra={
                    "error_code": e.code,
                    "error_message": e.message,
                    "event_type": event.update_type if hasattr(event, 'update_type') else "unknown",
                    "user_id": event.from_user.user_id if hasattr(event, 'from_user') and event.from_user else None,
                }
            )

            # Use error handling strategy
            action = await handle_max_api_error(
                e,
                admin_notification_callback=self._send_admin_notification
            )

            # Send user-friendly error message
            if isinstance(event, MessageCreated):
                await self._send_user_error_message(event, data, e)

            return None

        except Exception as e:
            # Log error with full traceback
            logger.error(
                f"Error in handler: {e}",
                exc_info=True,
                extra={
                    "event_type": event.update_type if hasattr(event, 'update_type') else "unknown",
                    "user_id": event.from_user.user_id if hasattr(event, 'from_user') and event.from_user else None,
                }
            )

            # Send error notification to admin channel if configured
            if ERROR_CHANNEL:
                await self._send_admin_notification(
                    self._format_error_message(e, event)
                )

            # Send user-friendly error message if this is a message event
            if isinstance(event, MessageCreated):
                await self._send_user_error_message(event, data)

            # Return None to indicate error occurred
            return None


    async def _send_admin_notification(self, message: str) -> None:
        """
        Send error notification to admin channel.
        
        Args:
            message: Error message to send
        """
        if not ERROR_CHANNEL:
            return

        try:
            async with Bot(MAX_BOT_TOKEN).context(auto_close=True) as bot:
                await bot.send_message(
                    chat_id=int(ERROR_CHANNEL),
                    text=message
                )
        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")

    def _format_error_message(self, error: Exception, event: UpdateUnion) -> str:
        """
        Format error message for admin notification.
        
        Args:
            error: The exception that occurred
            event: The update event
            
        Returns:
            Formatted error message
        """
        # Extract traceback information
        tb = traceback.extract_tb(error.__traceback__)

        # Format error message
        error_message = "🚨 Error in MAX Bot Handler\n\n"
        error_message += f"Error: {type(error).__name__}: {str(error)}\n\n"

        # Add event information
        if hasattr(event, 'update_type'):
            error_message += f"Event Type: {event.update_type}\n"
        if hasattr(event, 'from_user') and event.from_user:
            error_message += f"User ID: {event.from_user.user_id}\n"

        error_message += "\nTraceback:\n"

        for frame in tb:
            error_message += f"File: {frame.filename}\n"
            error_message += f"Line: {frame.lineno}\n"
            error_message += f"Code: {frame.line}\n\n"

        # Limit message length
        if len(error_message) > 4000:
            error_message = error_message[:4000] + "\n... (truncated)"

        return error_message

    async def _send_user_error_message(
        self,
        event: MessageCreated,
        data: Dict[str, Any],
        error: Exception = None
    ) -> None:
        """
        Send user-friendly error message.
        
        Args:
            event: Message event
            data: Context data
            error: Optional exception for context
        """
        try:
            bot = data.get("bot")
            if bot and hasattr(event, 'message'):
                # Customize message based on error type
                if isinstance(error, MAXAPIError):
                    if error.is_rate_limit_error():
                        message = "⏳ Слишком много запросов. Пожалуйста, подождите немного."
                    elif error.is_auth_error():
                        message = "🔒 Ошибка авторизации. Пожалуйста, обратитесь к администратору."
                    else:
                        message = "❌ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
                else:
                    message = "❌ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже или обратитесь в поддержку."

                await bot.send_message(
                    chat_id=event.message.chat.chat_id,
                    text=message
                )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
