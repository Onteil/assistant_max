"""
Get Chat ID Handler for MAX Bot

Handles /get_chat_id command to retrieve chat ID for escalation channel setup.
Works in both private chats and group chats.

Requirements: Admin panel escalation channel configuration
"""

import logging

from maxapi.context import MemoryContext
from maxapi.types import MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter

logger = logging.getLogger(__name__)


async def cmd_get_chat_id(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /get_chat_id command - return chat ID for escalation setup.
    
    Returns the chat ID where the command was invoked. This is useful for
    administrators to get the chat ID for configuring escalation channels
    in the admin panel.
    
    Works in:
    - Private chats (returns user's chat_id)
    - Group chats (returns group chat_id with negative value)
    
    maxapi Pattern Notes:
    - Uses event.message.recipient.chat_id for chat identification
    - Uses event.message.sender.user_id for user identification
    - Includes commands_info marker for automatic command registration
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    commands_info: Получить ID чата для настройки эскалации
    
    Requirements: Escalation channel configuration
    """
    chat_id = event.message.recipient.chat_id
    user_id = event.message.sender.user_id
    
    logger.info(f"🆔 cmd_get_chat_id CALLED: user_id={user_id}, chat_id={chat_id}")
    
    try:
        # Determine chat type based on chat_id
        if chat_id < 0:
            chat_type = "групповой чат"
        else:
            chat_type = "личный чат"
        
        # Format response message
        response_text = (
            f"🆔 <b>ID чата</b>\n\n"
            f"<code>{chat_id}</code>\n\n"
            f"<i>Тип: {chat_type}</i>\n\n"
            f"Используйте этот ID для настройки канала эскалации в админ панели."
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=response_text,
            parse_mode="HTML"
        )
        
        logger.info(f"Chat ID sent: chat_id={chat_id}, type={chat_type}")
    
    except Exception as e:
        logger.error(
            f"Error in cmd_get_chat_id: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при получении ID чата.",
            parse_mode="HTML"
        )
