"""
Database Session Middleware for MAX Bot

This middleware injects an AsyncSession into the handler context,
allowing handlers to interact with the database.
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from maxapi.filters.middleware import BaseMiddleware
from maxapi.types import UpdateUnion

from constants import get_session

logger = logging.getLogger(__name__)


class DatabaseSessionMiddleware(BaseMiddleware):
    """
    Middleware to inject database session into handler context.
    
    The session is automatically committed on success and rolled back on error.
    Handlers can access the session via the 'session' key in data dict.
    
    Usage:
        @dp.message_created(Command('start'))
        async def start_handler(event: MessageCreated, session: AsyncSession):
            user = await session.execute(select(User).where(User.id == event.from_user.user_id))
            # ... use session
    """

    async def __call__(
        self,
        handler: Callable[[UpdateUnion, Dict[str, Any]], Awaitable[Any]],
        event: UpdateUnion,
        data: Dict[str, Any],
    ) -> Any:
        """
        Inject database session into handler context.
        
        Args:
            handler: Next handler in the chain
            event: Update event from MAX
            data: Context data dictionary
            
        Returns:
            Result from handler execution
        """
        # Create session and add it to data
        async with get_session() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                # Session is automatically committed by get_session context manager
                return result
            except Exception as e:
                # Session is automatically rolled back by get_session context manager
                logger.error(f"Error in handler with database session: {e}")
                raise
