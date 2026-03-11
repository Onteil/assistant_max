"""
Celery tasks for broadcast campaign delivery.

This module implements background tasks for broadcast system:
- Broadcast delivery task: Sends scheduled broadcast messages to target users
- Handles delivery in batches to avoid overwhelming messenger APIs

Requirements: 6.10 - Broadcast campaign delivery
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone

# Add project root to Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import select, and_

from constants import AsyncSessionLocal, MAX_BOT_TOKEN, TG_BOT_TOKEN
from database.models import (
    Broadcast,
    BroadcastStatus,
    Broadcast_Delivery,
    DeliveryStatus,
    User,
)

# Use Celery-specific logger
logger = get_task_logger(__name__)

# Batch size for delivery to avoid overwhelming messenger APIs
DELIVERY_BATCH_SIZE = 50
BATCH_DELAY_SECONDS = 2  # Delay between batches


# ========== Helper Functions ==========


async def _send_broadcast_message_async(
    user: User,
    message_text: str,
    messenger: str
) -> dict:
    """
    Async helper to send broadcast message via appropriate messenger.
    
    Args:
        user: User object to send message to
        message_text: Message content
        messenger: Messenger platform ("telegram" or "max")
    
    Returns:
        Dict with delivery status
    """
    try:
        # Determine messenger ID
        if messenger == "telegram":
            messenger_id = user.tg_user_id
        elif messenger == "max":
            messenger_id = user.max_user_id
        else:
            logger.error(f"Invalid messenger type: {messenger}")
            return {
                "status": "error",
                "reason": "invalid_messenger",
                "user_id": user.id
            }
        
        if not messenger_id:
            logger.warning(
                f"User {user.id} has no {messenger} ID, skipping"
            )
            return {
                "status": "error",
                "reason": "no_messenger_id",
                "user_id": user.id
            }
        
        # Send message via appropriate messenger
        if messenger == "telegram":
            result = await _send_telegram_broadcast(
                messenger_id=messenger_id,
                message_text=message_text
            )
        elif messenger == "max":
            result = await _send_max_broadcast(
                messenger_id=messenger_id,
                message_text=message_text
            )
        
        result["user_id"] = user.id
        return result
    
    except Exception as e:
        logger.error(
            f"Error in _send_broadcast_message_async: user_id={user.id}, error={e}",
            exc_info=True
        )
        return {
            "status": "error",
            "reason": str(e),
            "user_id": user.id
        }


async def _send_telegram_broadcast(
    messenger_id: int,
    message_text: str
) -> dict:
    """
    Send broadcast message via Telegram bot.
    
    Args:
        messenger_id: Telegram user ID
        message_text: Message content
    
    Returns:
        Dict with delivery status
    """
    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
        
        bot = Bot(
            token=TG_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode="HTML")
        )
        
        try:
            # Send message
            await bot.send_message(
                chat_id=messenger_id,
                text=message_text
            )
            
            logger.info(
                f"Telegram broadcast sent successfully: messenger_id={messenger_id}"
            )
            
            return {
                "status": "success",
                "messenger": "telegram",
                "messenger_id": messenger_id
            }
        
        except TelegramForbiddenError as e:
            # Bot was blocked by user
            logger.warning(
                f"Telegram bot blocked by user: messenger_id={messenger_id}, error={e}"
            )
            
            return {
                "status": "bot_blocked",
                "messenger": "telegram",
                "messenger_id": messenger_id,
                "error": str(e)
            }
        
        except TelegramBadRequest as e:
            # Invalid request
            logger.error(
                f"Telegram bad request: messenger_id={messenger_id}, error={e}",
                exc_info=True
            )
            
            return {
                "status": "bad_request",
                "messenger": "telegram",
                "messenger_id": messenger_id,
                "error": str(e)
            }
        
        finally:
            # Close bot session
            await bot.session.close()
    
    except Exception as e:
        # Network errors or other unexpected errors
        logger.error(
            f"Error sending Telegram broadcast: messenger_id={messenger_id}, error={e}",
            exc_info=True
        )
        return {
            "status": "error",
            "messenger": "telegram",
            "messenger_id": messenger_id,
            "error": str(e)
        }


async def _send_max_broadcast(
    messenger_id: int,
    message_text: str
) -> dict:
    """
    Send broadcast message via MAX bot.
    
    IMPORTANT: This function retrieves chat_id from max_messenger_data table.
    
    Args:
        messenger_id: MAX user ID (used to lookup chat_id)
        message_text: Message content
    
    Returns:
        Dict with delivery status
    """
    try:
        from maxapi import Bot as MAXBot
        from maxapi.enums.parse_mode import ParseMode
        from maxapi.exceptions import MaxApiError
        from database.models import MAX_Messenger_Data
        
        # Get MAX chat_id from database
        async with AsyncSessionLocal() as session:
            stmt = select(MAX_Messenger_Data.max_chat_id).where(
                MAX_Messenger_Data.max_user_id == messenger_id
            )
            result = await session.execute(stmt)
            chat_id = result.scalar_one_or_none()
            
            if chat_id is None:
                logger.error(f"No MAX chat_id found for max_user_id {messenger_id}")
                return {
                    "status": "error",
                    "messenger": "max",
                    "messenger_id": messenger_id,
                    "error": "No chat_id found in database"
                }
        
        bot = MAXBot(
            token=MAX_BOT_TOKEN,
            parse_mode=ParseMode.HTML
        )
        
        try:
            # Send message using chat_id
            await bot.send_message(
                chat_id=chat_id,
                text=message_text
            )
            
            logger.info(
                f"MAX broadcast sent successfully: max_user_id={messenger_id}, chat_id={chat_id}"
            )
            
            return {
                "status": "success",
                "messenger": "max",
                "messenger_id": messenger_id
            }
        
        except MaxApiError as e:
            # Check if bot was blocked
            error_str = str(e).lower()
            if "blocked" in error_str or "forbidden" in error_str or "user not found" in error_str or "chat.not.found" in error_str:
                logger.warning(
                    f"MAX bot blocked by user or chat not found: "
                    f"max_user_id={messenger_id}, chat_id={chat_id}, error={e}"
                )
                
                return {
                    "status": "bot_blocked",
                    "messenger": "max",
                    "messenger_id": messenger_id,
                    "error": str(e)
                }
            
            # Other MAX API errors
            logger.error(
                f"MAX API error: max_user_id={messenger_id}, chat_id={chat_id}, error={e}",
                exc_info=True
            )
            
            return {
                "status": "api_error",
                "messenger": "max",
                "messenger_id": messenger_id,
                "error": str(e)
            }
        
        finally:
            # Close bot session
            await bot.session.close()
    
    except Exception as e:
        # Network errors or other unexpected errors
        logger.error(
            f"Error sending MAX broadcast: max_user_id={messenger_id}, error={e}",
            exc_info=True
        )
        return {
            "status": "error",
            "messenger": "max",
            "messenger_id": messenger_id,
            "error": str(e)
        }


async def _process_broadcast_delivery_async(
    broadcast_id: str,
    messenger: str
) -> dict:
    """
    Async helper to process broadcast delivery.
    
    Queries broadcast and delivery records, sends messages in batches,
    and updates delivery status for each user.
    
    Args:
        broadcast_id: Broadcast ID to process
        messenger: Messenger platform ("telegram" or "max")
    
    Returns:
        Dict with delivery statistics
    """
    try:
        async with AsyncSessionLocal() as session:
            # Step 1: Query Broadcast record
            stmt = select(Broadcast).where(Broadcast.id == broadcast_id)
            result = await session.execute(stmt)
            broadcast = result.scalar_one_or_none()
            
            if not broadcast:
                logger.error(f"Broadcast not found: broadcast_id={broadcast_id}")
                return {
                    "status": "error",
                    "reason": "broadcast_not_found",
                    "broadcast_id": broadcast_id
                }
            
            # Update broadcast status to SENDING
            broadcast.broadcast_status = BroadcastStatus.SENDING
            broadcast.sent_at = datetime.now(timezone.utc)
            await session.commit()
            
            logger.info(
                f"Starting broadcast delivery: broadcast_id={broadcast_id}, "
                f"target_count={broadcast.target_user_count}"
            )
            
            # Step 2: Query all pending deliveries
            stmt = select(Broadcast_Delivery).where(
                and_(
                    Broadcast_Delivery.broadcast_id == broadcast_id,
                    Broadcast_Delivery.delivery_status == DeliveryStatus.PENDING
                )
            )
            result = await session.execute(stmt)
            pending_deliveries = result.scalars().all()
            
            if not pending_deliveries:
                logger.info(
                    f"No pending deliveries found: broadcast_id={broadcast_id}"
                )
                
                # Update broadcast status to COMPLETED
                broadcast.broadcast_status = BroadcastStatus.COMPLETED
                await session.commit()
                
                return {
                    "status": "success",
                    "broadcast_id": broadcast_id,
                    "total_count": 0,
                    "sent_count": 0,
                    "failed_count": 0
                }
            
            # Step 3: Process deliveries in batches
            total_count = len(pending_deliveries)
            sent_count = 0
            failed_count = 0
            
            # Process in batches
            for i in range(0, total_count, DELIVERY_BATCH_SIZE):
                batch = pending_deliveries[i:i + DELIVERY_BATCH_SIZE]
                batch_num = (i // DELIVERY_BATCH_SIZE) + 1
                total_batches = (total_count + DELIVERY_BATCH_SIZE - 1) // DELIVERY_BATCH_SIZE
                
                logger.info(
                    f"Processing batch {batch_num}/{total_batches}: "
                    f"broadcast_id={broadcast_id}, batch_size={len(batch)}"
                )
                
                # Query users for this batch
                user_ids = [delivery.user_id for delivery in batch]
                stmt = select(User).where(User.id.in_(user_ids))
                result = await session.execute(stmt)
                users = {user.id: user for user in result.scalars().all()}
                
                # Send messages to batch
                for delivery in batch:
                    user = users.get(delivery.user_id)
                    
                    if not user:
                        logger.error(
                            f"User not found for delivery: user_id={delivery.user_id}"
                        )
                        delivery.delivery_status = DeliveryStatus.FAILED
                        delivery.error_message = "User not found"
                        failed_count += 1
                        continue
                    
                    # Send message
                    result = await _send_broadcast_message_async(
                        user=user,
                        message_text=broadcast.message_text,
                        messenger=messenger
                    )
                    
                    # Update delivery status
                    if result["status"] == "success":
                        delivery.delivery_status = DeliveryStatus.DELIVERED
                        delivery.delivered_at = datetime.now(timezone.utc)
                        sent_count += 1
                    else:
                        delivery.delivery_status = DeliveryStatus.FAILED
                        delivery.error_message = result.get("error", result.get("reason", "Unknown error"))
                        failed_count += 1
                
                # Commit batch updates
                await session.commit()
                
                logger.info(
                    f"Batch {batch_num}/{total_batches} completed: "
                    f"broadcast_id={broadcast_id}, sent={sent_count}, failed={failed_count}"
                )
                
                # Delay between batches to avoid rate limiting
                if i + DELIVERY_BATCH_SIZE < total_count:
                    await asyncio.sleep(BATCH_DELAY_SECONDS)
            
            # Step 4: Update broadcast status to COMPLETED
            broadcast.broadcast_status = BroadcastStatus.COMPLETED
            broadcast.delivered_count = sent_count
            await session.commit()
            
            logger.info(
                f"Broadcast delivery completed: broadcast_id={broadcast_id}, "
                f"total={total_count}, sent={sent_count}, failed={failed_count}"
            )
            
            return {
                "status": "success",
                "broadcast_id": broadcast_id,
                "total_count": total_count,
                "sent_count": sent_count,
                "failed_count": failed_count
            }
    
    except Exception as e:
        logger.error(
            f"Error in _process_broadcast_delivery_async: "
            f"broadcast_id={broadcast_id}, error={e}",
            exc_info=True
        )
        
        # Try to update broadcast status to FAILED
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(Broadcast).where(Broadcast.id == broadcast_id)
                result = await session.execute(stmt)
                broadcast = result.scalar_one_or_none()
                
                if broadcast:
                    broadcast.broadcast_status = BroadcastStatus.FAILED
                    await session.commit()
        except Exception as update_error:
            logger.error(
                f"Failed to update broadcast status to FAILED: {update_error}",
                exc_info=True
            )
        
        return {
            "status": "error",
            "reason": str(e),
            "broadcast_id": broadcast_id
        }


# ========== Celery Tasks ==========


@shared_task(
    name="celery_app.broadcast_tasks.send_broadcast_campaign",
    bind=True,
    max_retries=0,  # Don't retry broadcast tasks
    queue="broadcasts"
)
def send_broadcast_campaign(
    self,
    broadcast_id: str,
    messenger: str
) -> dict:
    """
    Send broadcast campaign to all target users.
    
    This task is scheduled with an eta (execution time) and delivers
    the broadcast message to all users with PENDING delivery status.
    Messages are sent in batches to avoid overwhelming messenger APIs.
    
    Args:
        broadcast_id: Broadcast ID to process
        messenger: Messenger platform ("telegram" or "max")
    
    Returns:
        Dict with delivery statistics
    
    Requirements: 6.10 - Broadcast campaign delivery
    """
    logger.info(
        f"Starting send_broadcast_campaign: broadcast_id={broadcast_id}, "
        f"messenger={messenger}, task_id={self.request.id}"
    )
    
    try:
        # Create new event loop for async execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Execute async broadcast delivery
            result = loop.run_until_complete(
                _process_broadcast_delivery_async(
                    broadcast_id=broadcast_id,
                    messenger=messenger
                )
            )
            
            # Log result
            if result["status"] == "success":
                logger.info(
                    f"Broadcast campaign completed: broadcast_id={broadcast_id}, "
                    f"sent={result.get('sent_count')}, failed={result.get('failed_count')}, "
                    f"task_id={self.request.id}"
                )
            else:
                logger.error(
                    f"Broadcast campaign failed: broadcast_id={broadcast_id}, "
                    f"reason={result.get('reason')}, task_id={self.request.id}"
                )
            
            return result
        
        finally:
            # Dispose engine connections before closing loop (Windows asyncpg fix)
            from constants import engine
            loop.run_until_complete(engine.dispose())
            loop.close()
    
    except Exception as exc:
        logger.error(
            f"Task execution failed: broadcast_id={broadcast_id}, "
            f"task_id={self.request.id}, error={exc}",
            exc_info=True
        )
        
        # Don't retry - broadcast tasks should not be retried
        # If delivery fails, individual delivery records will have FAILED status
        return {
            "status": "error",
            "reason": str(exc),
            "broadcast_id": broadcast_id
        }

