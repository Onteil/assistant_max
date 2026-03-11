"""
User Data Middleware for MAX Bot

This middleware loads user data from the database and attaches it to the message context.
"""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from maxapi.filters.middleware import BaseMiddleware
from maxapi.types import UpdateUnion
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User

logger = logging.getLogger(__name__)


class UserDataMiddleware(BaseMiddleware):
    """
    Middleware to load user data from database and attach to context.
    
    This middleware extracts the user_id from the event, queries the database
    for user information, and adds it to the context data dictionary.
    
    Handlers can access user data via the 'user_data' key in data dict.
    
    Usage:
        user_data_mw = UserDataMiddleware()
        dp.middleware(user_data_mw)
        
        @dp.message_created(Command('profile'))
        async def profile_handler(event: MessageCreated, user_data: Optional[User]):
            if user_data:
                await event.message.answer(f"Hello, {user_data.name}!")
    """

    async def __call__(
        self,
        handler: Callable[[UpdateUnion, Dict[str, Any]], Awaitable[Any]],
        event: UpdateUnion,
        data: Dict[str, Any],
    ) -> Any:
        """
        Load user data and inject into handler context.
        
        Args:
            handler: Next handler in the chain
            event: Update event from MAX
            data: Context data dictionary
            
        Returns:
            Result from handler execution
        """
        # Extract user_id from event
        user_id = None
        if hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.user_id

        # Initialize user_data as None
        user_data: Optional[User] = None

        # Load user data from database if user_id is available
        if user_id:
            session: Optional[AsyncSession] = data.get("session")

            if session:
                try:
                    # Query user from database
                    result = await session.execute(
                        select(User).where(User.telegram_id == user_id)
                    )
                    user_data = result.scalar_one_or_none()

                    if user_data:
                        logger.debug(f"Loaded user data for user_id {user_id}")
                    else:
                        logger.debug(f"No user data found for user_id {user_id}")

                except Exception as e:
                    logger.error(f"Error loading user data for user_id {user_id}: {e}")
            else:
                logger.warning("No database session available in context for UserDataMiddleware")

        # Add user data to context
        data["user_data"] = user_data

        # Add bot reference to context if not already present
        if "bot" not in data:
            # Bot should be injected by the dispatcher, but we can add it here as fallback
            pass

        # Call next handler
        return await handler(event, data)
