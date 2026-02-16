"""
Album Middleware for MAX Bot

This middleware groups multiple media attachments into albums.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from maxapi.filters.middleware import BaseMiddleware
from maxapi.types import MessageCreated, UpdateUnion

logger = logging.getLogger(__name__)


class AlbumMiddleware(BaseMiddleware):
    """
    Middleware to group multiple media attachments into albums.
    
    When multiple messages with the same media_group_id are received,
    this middleware collects them and processes them as a single album.
    
    For single media messages (no media_group_id), they are treated as
    an album with one item.
    
    Args:
        latency: Time to wait for additional messages in the album (default: 0.5 seconds)
    
    Usage:
        album_mw = AlbumMiddleware(latency=0.5)
        dp.middleware(album_mw)
        
        @dp.message_created()
        async def handle_media(event: MessageCreated, album: list[MessageCreated], is_last: bool):
            if is_last:
                # Process complete album
                for msg in album:
                    # Process each media item
                    pass
    """

    def __init__(self, latency: float = 0.5):
        """
        Initialize album middleware.
        
        Args:
            latency: Time to wait for additional messages in seconds
        """
        super().__init__()
        self.latency = latency
        self.album_data: Dict[str, list[MessageCreated]] = {}

    async def __call__(
        self,
        handler: Callable[[UpdateUnion, Dict[str, Any]], Awaitable[Any]],
        event: UpdateUnion,
        data: Dict[str, Any],
    ) -> Any:
        """
        Group media messages into albums.
        
        Args:
            handler: Next handler in the chain
            event: Update event from MAX
            data: Context data dictionary
            
        Returns:
            Result from handler execution
        """
        # Only process MessageCreated events
        if not isinstance(event, MessageCreated):
            return await handler(event, data)

        # Check if message has media_group_id
        media_group_id = None
        if hasattr(event, 'message') and event.message:
            # In MAX API, media_group_id might be in different locations
            # Check common locations
            if hasattr(event.message, 'media_group_id'):
                media_group_id = event.message.media_group_id
            elif hasattr(event.message, 'body') and hasattr(event.message.body, 'media_group_id'):
                media_group_id = event.message.body.media_group_id

        if media_group_id:
            # This is part of an album
            if media_group_id in self.album_data:
                # Add to existing album
                self.album_data[media_group_id].append(event)
                logger.debug(f"Added message to album {media_group_id}")
                # Don't process yet, wait for more messages
                return None

            # Create new album
            self.album_data[media_group_id] = [event]
            logger.debug(f"Created new album {media_group_id}")

            # Wait for other messages in the album
            await asyncio.sleep(self.latency)

            # Mark as last message in album
            data["is_last"] = True
            data["album"] = self.album_data.pop(media_group_id)

            logger.info(f"Processing album {media_group_id} with {len(data['album'])} messages")
        else:
            # Single message (not part of album)
            # Treat as album with one item
            data["is_last"] = True
            data["album"] = [event]
            logger.debug("Processing single message as album")

        # Call handler with album data
        return await handler(event, data)
