"""
Throttling Middleware for MAX Bot

This middleware implements rate limiting to prevent users from flooding the bot.
It uses Redis to track request timestamps per chat_id.
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from aioredis import Redis
from maxapi.filters.middleware import BaseMiddleware
from maxapi.types import MessageCreated, MessageCallback, UpdateUnion

from constants import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware to rate-limit updates by chat_id.
    
    Uses Redis to track request timestamps and prevent flooding.
    When throttled, sends a "Too many requests" message to the user.
    
    Args:
        rate_limit: Time window in seconds (default: 1.0)
        redis_client: Optional Redis client (will create one if not provided)
    
    Usage:
        throttling = ThrottlingMiddleware(rate_limit=1.0)
        dp.middleware(throttling)
    """

    def __init__(self, rate_limit: float = 1.0, redis_client: Redis = None):
        """
        Initialize throttling middleware.
        
        Args:
            rate_limit: Minimum time between requests in seconds
            redis_client: Optional Redis client instance
        """
        super().__init__()
        self.rate_limit = rate_limit
        self.redis_client = redis_client
        self._redis_initialized = False

    async def _ensure_redis(self):
        """Ensure Redis client is initialized."""
        if not self._redis_initialized and self.redis_client is None:
            try:
                import aioredis
                self.redis_client = await aioredis.create_redis_pool(
                    f"redis://{REDIS_HOST}:{REDIS_PORT}",
                    password=REDIS_PASSWORD if REDIS_PASSWORD else None,
                    encoding="utf-8"
                )
                self._redis_initialized = True
                logger.info("Redis client initialized for throttling middleware")
            except Exception as e:
                logger.error(f"Failed to initialize Redis client: {e}")
                # Continue without Redis - throttling will be disabled
                self._redis_initialized = True

    async def __call__(
        self,
        handler: Callable[[UpdateUnion, Dict[str, Any]], Awaitable[Any]],
        event: UpdateUnion,
        data: Dict[str, Any],
    ) -> Any:
        """
        Check rate limit before allowing handler execution.
        
        Args:
            handler: Next handler in the chain
            event: Update event from MAX
            data: Context data dictionary
            
        Returns:
            Result from handler execution or None if throttled
        """
        # Ensure Redis is initialized
        await self._ensure_redis()

        # If Redis is not available, skip throttling
        if self.redis_client is None:
            return await handler(event, data)

        # Extract chat_id from event
        chat_id = None
        if hasattr(event, 'message') and event.message:
            chat_id = event.message.chat.chat_id
        elif hasattr(event, 'chat') and event.chat:
            chat_id = event.chat.chat_id
        elif hasattr(event, 'from_user') and event.from_user:
            # Fallback to user_id for private chats
            chat_id = event.from_user.user_id

        if chat_id is None:
            # No chat_id found, allow request
            return await handler(event, data)

        # Create throttle key
        throttle_key = f"throttle:max_bot:{chat_id}"

        try:
            # Check if key exists (user is throttled)
            exists = await self.redis_client.exists(throttle_key)

            if exists:
                # User is throttled
                logger.info(f"Throttled request from chat_id {chat_id}")

                # Send throttle message if this is a message event
                if isinstance(event, (MessageCreated, MessageCallback)):
                    try:
                        bot = data.get("bot")
                        if bot and hasattr(event, 'message'):
                            await bot.send_message(
                                chat_id=chat_id,
                                text="⏱ Слишком много запросов. Пожалуйста, подождите немного."
                            )
                    except Exception as e:
                        logger.error(f"Failed to send throttle message: {e}")

                # Don't call handler
                return None

            # Set throttle key with expiration
            await self.redis_client.setex(
                throttle_key,
                int(self.rate_limit),
                "1"
            )

            # Allow request
            return await handler(event, data)

        except Exception as e:
            logger.error(f"Error in throttling middleware: {e}")
            # On error, allow request to proceed
            return await handler(event, data)
