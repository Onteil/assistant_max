"""
Broadcast service layer for managing admin broadcast operations.

Provides async functions for creating broadcasts, targeting users,
and sending mass messages with delivery tracking.

Requirements: 10.1, 10.2, 10.5, 10.6, 10.7
"""

import logging
from datetime import datetime
from typing import Any

from aiogram import Bot
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Broadcast,
    Broadcast_Delivery,
    BroadcastStatus,
    DeliveryStatus,
    SubscriptionStatus,
    User,
)

logger = logging.getLogger(__name__)


# ========== Broadcast Creation ==========


async def create_broadcast(
    session: AsyncSession,
    created_by_staff_id: int,
    message_text: str
) -> Broadcast:
    """
    Create new broadcast in DRAFT status.
    
    Args:
        session: Database session
        created_by_staff_id: ID of staff member creating the broadcast
        message_text: Content of the broadcast message
        
    Returns:
        Created Broadcast object
        
    Requirements: 10.1, 10.5
    """
    try:
        broadcast = Broadcast(
            created_by_staff_id=created_by_staff_id,
            message_text=message_text,
            broadcast_status=BroadcastStatus.DRAFT,
            target_user_count=0,
            delivered_count=0
        )
        
        session.add(broadcast)
        await session.commit()
        await session.refresh(broadcast)
        
        logger.info(f"Created broadcast {broadcast.id} by staff {created_by_staff_id}")
        return broadcast
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating broadcast: {e}")
        raise


# ========== Target User Selection ==========


async def get_target_users(
    session: AsyncSession,
    target: str,
    messenger: str = "telegram"
) -> list[User]:
    """
    Get target users based on criteria.
    
    Args:
        session: Database session
        target: Targeting criteria
            - 'all': all active users
            - 'active_subscription': users with active subscription
            - 'marketing_consent': users with notification_preferences=True
        messenger: Messenger type - "telegram" or "max" (default: "telegram")
            
    Returns:
        List of User objects matching criteria
        
    Requirements: 10.2, 10.4
    """
    try:
        # Base query - only users with messenger ID (can receive messages)
        if messenger == "max":
            query = select(User).where(User.max_user_id.isnot(None))
        else:  # telegram
            query = select(User).where(User.tg_user_id.isnot(None))
        
        if target == "all":
            # All users with messenger ID
            pass
            
        elif target == "active_subscription":
            # Users with active subscription
            query = query.where(
                User.subscription_status == SubscriptionStatus.ACTIVE
            )
            
        elif target == "marketing_consent":
            # Users who agreed to marketing notifications
            query = query.where(
                User.notification_preferences == True
            )
        else:
            logger.warning(f"Unknown target type: {target}, defaulting to 'all'")
        
        result = await session.execute(query)
        users = result.scalars().all()
        
        logger.info(f"Found {len(users)} users for target '{target}' on {messenger}")
        return list(users)
        
    except Exception as e:
        logger.error(f"Error getting target users: {e}")
        raise


# ========== Broadcast Delivery ==========


async def send_broadcast(
    session: AsyncSession,
    broadcast_id: int,
    bot: Bot = None,
    messenger_adapter = None
) -> tuple[int, int]:
    """
    Send broadcast to all target users.
    
    Creates Broadcast_Delivery records for tracking and sends messages
    to all users. Updates broadcast status and counts.
    
    Supports both Telegram (via bot) and MAX (via messenger_adapter).
    For MAX, uses max_messenger_data table to get chat_id by user_id.
    
    Args:
        session: Database session
        broadcast_id: ID of broadcast to send
        bot: Telegram Bot instance for sending messages (optional)
        messenger_adapter: MAX messenger adapter for sending messages (optional)
        
    Returns:
        Tuple of (delivered_count, error_count)
        
    Requirements: 10.5, 10.6, 10.7
    """
    from database.models import MAX_Messenger_Data
    
    try:
        # Get broadcast
        result = await session.execute(
            select(Broadcast).where(Broadcast.id == broadcast_id)
        )
        broadcast = result.scalar_one_or_none()
        
        if not broadcast:
            logger.error(f"Broadcast {broadcast_id} not found")
            raise ValueError(f"Broadcast {broadcast_id} not found")
        
        # Update status to SENDING
        broadcast.broadcast_status = BroadcastStatus.SENDING
        broadcast.sent_at = datetime.utcnow()
        await session.commit()
        
        # Get all delivery records for this broadcast
        result = await session.execute(
            select(Broadcast_Delivery)
            .where(Broadcast_Delivery.broadcast_id == broadcast_id)
            .where(Broadcast_Delivery.delivery_status == DeliveryStatus.PENDING)
        )
        deliveries = result.scalars().all()
        
        delivered_count = 0
        error_count = 0
        
        # Determine messenger type
        is_telegram = bot is not None
        is_max = messenger_adapter is not None
        
        if not is_telegram and not is_max:
            raise ValueError("Either bot or messenger_adapter must be provided")
        
        # Send to each user
        for delivery in deliveries:
            try:
                # Get user
                user_result = await session.execute(
                    select(User).where(User.id == delivery.user_id)
                )
                user = user_result.scalar_one_or_none()
                
                if not user:
                    delivery.delivery_status = DeliveryStatus.FAILED
                    delivery.error_message = "User not found"
                    error_count += 1
                    continue
                
                # Send via Telegram
                if is_telegram:
                    if not user.tg_user_id:
                        delivery.delivery_status = DeliveryStatus.FAILED
                        delivery.error_message = "No Telegram ID"
                        error_count += 1
                        continue
                    
                    await bot.send_message(
                        chat_id=user.tg_user_id,
                        text=broadcast.message_text
                    )
                
                # Send via MAX
                elif is_max:
                    if not user.max_user_id:
                        delivery.delivery_status = DeliveryStatus.FAILED
                        delivery.error_message = "No MAX user ID"
                        error_count += 1
                        continue
                    
                    # Get chat_id from max_messenger_data table
                    max_data_result = await session.execute(
                        select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == user.id)
                    )
                    max_data = max_data_result.scalar_one_or_none()
                    
                    if not max_data:
                        delivery.delivery_status = DeliveryStatus.FAILED
                        delivery.error_message = "No MAX messenger data found"
                        error_count += 1
                        continue
                    
                    await messenger_adapter.send_message(
                        chat_id=max_data.max_chat_id,
                        text=broadcast.message_text,
                        parse_mode="HTML"
                    )
                
                # Mark as delivered
                delivery.delivery_status = DeliveryStatus.DELIVERED
                delivery.delivered_at = datetime.utcnow()
                delivered_count += 1
                
                logger.info(f"Delivered broadcast {broadcast_id} to user {user.id}")
                
            except Exception as e:
                # Mark as failed
                delivery.delivery_status = DeliveryStatus.FAILED
                delivery.error_message = str(e)[:512]  # Truncate to fit column
                error_count += 1
                
                logger.error(f"Error delivering broadcast {broadcast_id} to user {delivery.user_id}: {e}")
        
        # Update broadcast counts and status
        broadcast.delivered_count = delivered_count
        broadcast.broadcast_status = BroadcastStatus.COMPLETED if error_count == 0 else BroadcastStatus.FAILED
        
        await session.commit()
        
        logger.info(
            f"Broadcast {broadcast_id} completed: "
            f"{delivered_count} delivered, {error_count} errors"
        )
        
        return (delivered_count, error_count)
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error sending broadcast {broadcast_id}: {e}")
        raise


# ========== Helper Functions ==========


async def create_delivery_records(
    session: AsyncSession,
    broadcast_id: int,
    user_ids: list[int]
) -> int:
    """
    Create Broadcast_Delivery records for all target users.
    
    Args:
        session: Database session
        broadcast_id: ID of broadcast
        user_ids: List of user IDs to create delivery records for
        
    Returns:
        Count of created delivery records
        
    Requirements: 10.7
    """
    try:
        delivery_records = [
            Broadcast_Delivery(
                broadcast_id=broadcast_id,
                user_id=user_id,
                delivery_status=DeliveryStatus.PENDING
            )
            for user_id in user_ids
        ]
        
        session.add_all(delivery_records)
        await session.commit()
        
        logger.info(f"Created {len(delivery_records)} delivery records for broadcast {broadcast_id}")
        return len(delivery_records)
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating delivery records: {e}")
        raise
