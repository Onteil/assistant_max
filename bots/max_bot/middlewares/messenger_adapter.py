"""
Messenger Adapter Middleware for MAX Bot

Injects the messenger adapter instance into handler context.
This enables dependency injection pattern for all handlers.

Requirements: 14.5 - Inject dependencies into handlers
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from maxapi.filters.middleware import BaseMiddleware

logger = logging.getLogger(__name__)


class MessengerAdapterMiddleware(BaseMiddleware):
    """
    Middleware to inject messenger adapter into handler context.
    
    This middleware adds the messenger_adapter to the data dictionary,
    making it available to all handlers without explicit parameter passing.
    
    Usage in handlers:
        async def my_handler(message, messenger_adapter):
            await messenger_adapter.send_message(...)
    
    Requirements: 14.5 - Inject dependencies (messenger adapter) into handlers
    """

    def __init__(self, messenger_adapter):
        """
        Initialize middleware with messenger adapter instance.
        
        Args:
            messenger_adapter: MAXMessengerAdapter instance
        """
        super().__init__()
        self.messenger_adapter = messenger_adapter
        logger.info("MessengerAdapterMiddleware initialized")

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        """
        Inject messenger adapter into handler context.
        
        Args:
            handler: Next handler in the chain
            event: Incoming event (Message, CallbackQuery, etc.)
            data: Context data dictionary
        
        Returns:
            Result from handler execution
        """
        # Inject messenger adapter into context
        data["messenger_adapter"] = self.messenger_adapter

        # Call next handler
        return await handler(event, data)
