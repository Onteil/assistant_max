"""
Messenger Utilities for Webhooks

Centralized utilities for sending messages via Telegram and MAX messengers.
Used by webhook endpoints to send notifications to users.

IMPORTANT: For MAX messenger, always use chat_id from max_messenger_data table,
not max_user_id from users table. MAX API requires chat_id for sending messages.
"""

import logging
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup
from maxapi import Bot as MaxBot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from constants import TG_BOT_TOKEN, MAX_BOT_TOKEN
from database.models import MAX_Messenger_Data

logger = logging.getLogger(__name__)


async def get_max_chat_id(session: AsyncSession, user_id: int) -> int | None:
    """
    Get MAX chat_id for user from max_messenger_data table.
    
    Args:
        session: Database session
        user_id: Internal user ID
    
    Returns:
        MAX chat_id or None if not found
    """
    try:
        stmt = select(MAX_Messenger_Data.max_chat_id).where(
            MAX_Messenger_Data.user_id == user_id
        )
        result = await session.execute(stmt)
        chat_id = result.scalar_one_or_none()
        return chat_id
    except Exception as e:
        logger.error(f"Error getting MAX chat_id for user {user_id}: {e}", exc_info=True)
        return None


async def send_message_to_user(
    messenger: str,
    user_id: int,
    text: str,
    session: AsyncSession | None = None,
    keyboard: InlineKeyboardMarkup | Any | None = None,
    parse_mode: str = "HTML"
) -> dict[str, Any]:
    """
    Send message to user via specified messenger.
    
    IMPORTANT: For MAX messenger, this function automatically retrieves chat_id
    from max_messenger_data table using user_id. Do NOT pass max_user_id as user_id.
    
    NOTE: parse_mode is only used for Telegram. MAX messenger does not support HTML formatting.
    
    Args:
        messenger: Messenger type ("telegram" or "max")
        user_id: Internal user ID (from users.id)
        text: Message text (HTML tags will be stripped for MAX)
        session: Database session (REQUIRED for MAX messenger)
        keyboard: Optional keyboard (Telegram InlineKeyboardMarkup or MAX keyboard)
        parse_mode: Parse mode for Telegram ("HTML" or "Markdown"), ignored for MAX
    
    Returns:
        Dictionary with status and details:
        {
            "success": bool,
            "status": "sent" | "bot_blocked" | "failed" | "error" | "no_chat_id",
            "message": str,
            "error": str | None
        }
    """
    try:
        if messenger == "telegram":
            return await _send_telegram_message(user_id, text, keyboard, parse_mode)
        elif messenger == "max":
            if session is None:
                logger.error("Database session required for MAX messenger")
                return {
                    "success": False,
                    "status": "error",
                    "message": "Database session required for MAX messenger",
                    "error": "Missing session"
                }
            # Strip HTML tags for MAX messenger
            import re
            text_plain = re.sub(r'<[^>]+>', '', text)
            return await _send_max_message(user_id, text_plain, keyboard, session)
        else:
            logger.error(f"Invalid messenger type: {messenger}")
            return {
                "success": False,
                "status": "error",
                "message": f"Invalid messenger type: {messenger}",
                "error": "Invalid messenger"
            }
    except Exception as e:
        logger.error(f"Unexpected error sending message via {messenger}: {e}", exc_info=True)
        return {
            "success": False,
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "error": str(e)
        }


async def _send_telegram_message(
    user_id: int,
    text: str,
    keyboard: InlineKeyboardMarkup | None,
    parse_mode: str
) -> dict[str, Any]:
    """
    Send message via Telegram bot.
    
    Args:
        user_id: Telegram user ID (same as chat_id for private chats)
        text: Message text
        keyboard: Optional inline keyboard
        parse_mode: Parse mode ("HTML" or "Markdown")
    
    Returns:
        Status dictionary
    """
    bot = None
    try:
        # Initialize bot
        bot = Bot(
            token=TG_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML if parse_mode == "HTML" else ParseMode.MARKDOWN)
        )
        
        # Send message (for Telegram, user_id = chat_id in private chats)
        await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=keyboard
        )
        
        logger.info(f"Message sent successfully to Telegram user {user_id}")
        return {
            "success": True,
            "status": "sent",
            "message": "Message sent successfully",
            "error": None
        }
    
    except TelegramForbiddenError as e:
        logger.warning(f"Bot blocked by Telegram user {user_id}: {e}")
        return {
            "success": False,
            "status": "bot_blocked",
            "message": "Bot is blocked by user",
            "error": str(e)
        }
    
    except TelegramBadRequest as e:
        logger.error(f"Telegram bad request for user {user_id}: {e}", exc_info=True)
        return {
            "success": False,
            "status": "failed",
            "message": f"Telegram error: {str(e)}",
            "error": str(e)
        }
    
    except Exception as e:
        logger.error(f"Error sending Telegram message to {user_id}: {e}", exc_info=True)
        return {
            "success": False,
            "status": "error",
            "message": f"Error: {str(e)}",
            "error": str(e)
        }
    
    finally:
        # Close bot session
        if bot:
            try:
                await bot.session.close()
            except Exception as e:
                logger.warning(f"Error closing Telegram bot session: {e}")


async def _send_max_message(
    user_id: int,
    text: str,
    keyboard: Any | None,
    session: AsyncSession
) -> dict[str, Any]:
    """
    Send message via MAX bot.
    
    IMPORTANT: This function retrieves chat_id from max_messenger_data table.
    
    Args:
        user_id: Internal user ID (from users.id)
        text: Message text
        keyboard: Optional MAX keyboard (ButtonsPayload or similar)
        session: Database session for retrieving chat_id
    
    Returns:
        Status dictionary
    """
    bot = None
    try:
        # Get MAX chat_id from database
        chat_id = await get_max_chat_id(session, user_id)
        
        if chat_id is None:
            logger.error(f"No MAX chat_id found for user {user_id}")
            return {
                "success": False,
                "status": "no_chat_id",
                "message": "User has no MAX chat_id in database",
                "error": "No chat_id found"
            }
        
        # Initialize bot
        bot = MaxBot(token=MAX_BOT_TOKEN)
        
        # Prepare attachments if keyboard provided
        attachments = [keyboard] if keyboard else None
        
        # Send message using chat_id
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            attachments=attachments
        )
        
        logger.info(f"Message sent successfully to MAX user {user_id} (chat_id: {chat_id})")
        return {
            "success": True,
            "status": "sent",
            "message": "Message sent successfully",
            "error": None
        }
    
    except Exception as e:
        # MAX API doesn't have specific exception types like Telegram
        # Check error message for common cases
        error_str = str(e).lower()
        
        if "forbidden" in error_str or "blocked" in error_str:
            logger.warning(f"Bot blocked by MAX user {user_id}: {e}")
            return {
                "success": False,
                "status": "bot_blocked",
                "message": "Bot is blocked by user",
                "error": str(e)
            }
        else:
            logger.error(f"Error sending MAX message to user {user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "status": "failed",
                "message": f"MAX error: {str(e)}",
                "error": str(e)
            }
    
    finally:
        # Close bot session if needed
        if bot:
            try:
                # MAX bot may not need explicit session close, but check
                if hasattr(bot, 'session') and bot.session:
                    await bot.session.close()
            except Exception as e:
                logger.warning(f"Error closing MAX bot session: {e}")
