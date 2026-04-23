"""
Get Chat ID Handler for MAX Bot

Handles /get_chat_id command to retrieve chat ID for escalation channel setup.
Works in both private chats and group chats.

Requirements: Admin panel escalation channel configuration
"""

import logging

from maxapi.context import MemoryContext
from maxapi.types import MessageCreated
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from database.models import MAX_Messenger_Data, Staff_Member, User

logger = logging.getLogger(__name__)


async def _get_full_name_by_chat_id(session: AsyncSession, chat_id: int) -> str | None:
    """
    Resolve a human-readable full name for the given MAX chat_id.

    Lookup order:
    1. max_messenger_data → max_user_id → staff_members.full_name
    2. max_messenger_data → user_id     → users.full_name

    Returns the full name string, or None if not found.
    """
    # Step 1: find the messenger data record for this chat_id
    result = await session.execute(
        select(MAX_Messenger_Data).where(MAX_Messenger_Data.max_chat_id == chat_id)
    )
    messenger_data = result.scalar_one_or_none()

    if messenger_data is None:
        return None

    # Step 2a: try staff_members by max_user_id
    if messenger_data.max_user_id:
        staff_result = await session.execute(
            select(Staff_Member.full_name).where(
                Staff_Member.max_user_id == messenger_data.max_user_id
            )
        )
        staff_name = staff_result.scalar_one_or_none()
        if staff_name:
            return staff_name

    # Step 2b: fall back to users table by user_id
    if messenger_data.user_id:
        user_result = await session.execute(
            select(User.full_name).where(User.id == messenger_data.user_id)
        )
        user_name = user_result.scalar_one_or_none()
        if user_name:
            return user_name

    return None


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
    
    Also resolves and displays the full name associated with the chat_id
    (looked up via max_messenger_data → staff_members / users).
    
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

        # Resolve full name for this chat_id
        full_name = await _get_full_name_by_chat_id(session, chat_id)
        name_line = f"👤 <b>ФИО:</b> {full_name}\n" if full_name else ""

        # Format response message
        response_text = (
            f"🆔 <b>ID чата</b>\n\n"
            f"<code>{chat_id}</code>\n"
            f"{name_line}"
            f"\n<i>Тип: {chat_type}</i>\n\n"
            f"Используйте этот ID для настройки канала эскалации в админ панели."
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=response_text,
            parse_mode="HTML"
        )
        
        logger.info(f"Chat ID sent: chat_id={chat_id}, type={chat_type}, full_name={full_name!r}")
    
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
