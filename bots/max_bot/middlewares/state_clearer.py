"""
State Clearer Middleware for MAX Bot

This middleware clears FSM state when specific global commands are received.
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from maxapi.filters.middleware import BaseMiddleware
from maxapi.context import MemoryContext
from maxapi.types import MessageCreated, UpdateUnion

logger = logging.getLogger(__name__)


class StateClearerMiddleware(BaseMiddleware):
    """
    Middleware to clear FSM state on specific commands.
    
    This middleware intercepts messages and checks if they contain global commands
    that should clear the current FSM state (e.g., /start, /cancel, /clear_state).
    
    Args:
        global_commands: List of commands that should clear state (default: ["/clear_state"])
    
    Usage:
        state_clearer = StateClearerMiddleware(global_commands=["/start", "/cancel", "/clear_state"])
        dp.middleware(state_clearer)
    """

    def __init__(self, global_commands: list[str] = None):
        """
        Initialize state clearer middleware.
        
        Args:
            global_commands: List of commands that should clear state
        """
        super().__init__()
        self.global_commands = global_commands or ["/clear_state"]

    async def __call__(
        self,
        handler: Callable[[UpdateUnion, Dict[str, Any]], Awaitable[Any]],
        event: UpdateUnion,
        data: Dict[str, Any],
    ) -> Any:
        """
        Check for global commands and clear state if needed.
        
        Args:
            handler: Next handler in the chain
            event: Update event from MAX
            data: Context data dictionary
            
        Returns:
            Result from handler execution
        """
        # Only process MessageCreated events
        if isinstance(event, MessageCreated):
            # Check if message has text and starts with '/'
            if hasattr(event, 'message') and event.message and hasattr(event.message, 'body'):
                message_text = event.message.body.text if event.message.body else None

                if message_text and message_text.startswith("/"):
                    command_text = message_text.strip()

                    # Check if this is a global command
                    if command_text in self.global_commands:
                        # Get FSM context
                        state: MemoryContext = data.get("state")

                        if state:
                            # Get current state
                            current_state = await state.get_state()

                            if current_state:
                                logger.info(
                                    f"Middleware: User {event.from_user.user_id if event.from_user else 'unknown'} "
                                    f"used global command {command_text}. Clearing state {current_state}."
                                )

                                # Clear state
                                await state.clear()

        # Call next handler
        return await handler(event, data)
