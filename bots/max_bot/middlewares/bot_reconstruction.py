"""
Bot In Reconstruction Middleware for MAX Bot

This middleware blocks all updates during maintenance mode.
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from maxapi.filters.middleware import BaseMiddleware
from maxapi.types import MessageCreated, UpdateUnion

from constants import CONFIGS

logger = logging.getLogger(__name__)


class BotInReconstructionMiddleware(BaseMiddleware):
    """
    Middleware to block all updates during maintenance mode.
    
    When maintenance mode is enabled (BOT_ON_RECONSTRUCTION=True),
    this middleware intercepts all updates and sends a maintenance message.
    
    Usage:
        reconstruction = BotInReconstructionMiddleware()
        dp.middleware(reconstruction)
    """

    async def __call__(
        self,
        handler: Callable[[UpdateUnion, Dict[str, Any]], Awaitable[Any]],
        event: UpdateUnion,
        data: Dict[str, Any],
    ) -> Any:
        """
        Check maintenance mode before allowing handler execution.
        
        Args:
            handler: Next handler in the chain
            event: Update event from MAX
            data: Context data dictionary
            
        Returns:
            None if in maintenance mode, otherwise result from handler
        """
        # Check if bot is in reconstruction mode
        if CONFIGS.get("BOT_ON_RECONSTRUCTION", False):
            logger.info("Bot is in reconstruction mode, blocking update")

            # Try to send maintenance message if this is a message event
            if isinstance(event, MessageCreated):
                try:
                    bot = data.get("bot")
                    if bot and hasattr(event, 'message'):
                        await bot.send_message(
                            chat_id=event.message.chat.chat_id,
                            text="🔧 Бот временно на реконструкции. Пожалуйста, попробуйте позже."
                        )
                except Exception as e:
                    logger.error(f"Failed to send reconstruction message: {e}")

            # Don't call handler
            return None

        # Bot is operational, proceed with handler
        return await handler(event, data)
