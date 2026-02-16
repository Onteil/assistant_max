"""
Chat Type Filter for MAX Bot

Filters updates based on chat type to ensure handlers only process
updates from specific chat types (private, group, channel).

Requirements: 10.4 - Implement private chat filtering
"""

import logging
from typing import Any, Dict

from maxapi.filters import BaseFilter
from maxapi.types import MessageCallback, MessageCreated, UpdateUnion

logger = logging.getLogger(__name__)


class PrivateChatFilter(BaseFilter):
    """
    Filter to accept only updates from private chats.
    
    This filter rejects updates from group chats and channels,
    ensuring that bot handlers only process private conversations.
    
    Usage:
        router.message.filter(PrivateChatFilter())
        router.message_callback.filter(PrivateChatFilter())
    
    Requirements: 10.4
    """

    def __init__(self, chat_types: list[str] = None):
        """
        Initialize the chat type filter.
        
        Args:
            chat_types: List of allowed chat types. Defaults to ["private"]
                       Valid values: "private", "group", "channel"
        """
        self.chat_types = chat_types or ["private"]

    async def __call__(self, event: UpdateUnion, data: Dict[str, Any]) -> bool:
        """
        Check if the update is from an allowed chat type.
        
        Args:
            event: Update event from MAX
            data: Context data dictionary
            
        Returns:
            True if chat type is allowed, False otherwise
        """
        try:
            # Extract chat from different event types
            chat = None

            if isinstance(event, MessageCreated):
                chat = event.message.chat
            elif isinstance(event, MessageCallback):
                # For callbacks, check the message's chat
                if hasattr(event, 'message') and event.message:
                    chat = event.message.chat

            # If we couldn't extract chat, reject the update
            if not chat:
                logger.warning(f"Could not extract chat from event type: {type(event).__name__}")
                return False

            # Check if chat type is in allowed list
            chat_type = chat.type if hasattr(chat, 'type') else None

            if chat_type in self.chat_types:
                return True
            else:
                logger.debug(f"Rejected update from chat type: {chat_type} (allowed: {self.chat_types})")
                return False

        except Exception as e:
            logger.error(f"Error in PrivateChatFilter: {e}", exc_info=True)
            return False
