"""
Celery tasks for subscription renewal reminder delivery and management.

This module implements background tasks for renewal reminder system:
- Expiration check task: Scans for upcoming subscription expirations daily
- Reminder delivery task: Sends scheduled renewal reminders to users

Requirements: 3.1-3.9, 8.1-8.7, 10.6, 10.7
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta

# Add project root to Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from constants import AsyncSessionLocal, TG_BOT_TOKEN
from database.models import (
    EventStatus,
    EventType,
    Notification_Event,
    SubscriptionStatus,
    User,
)
from services.renewal_service import schedule_renewal_reminders

# Use Celery-specific logger
logger = get_task_logger(__name__)


# ========== Helper Functions ==========


async def _check_expirations_async(reminder_days: list[int] = None) -> dict:
    """
    Async helper to check for upcoming subscription expirations.
    
    Queries users with subscriptions expiring in the configured number of days
    (default: 30 and 7 days) and creates Notification_Event records for each.
    Only processes users with ACTIVE subscriptions and valid end dates.
    
    Args:
        reminder_days: List of days before expiration to check.
                      Defaults to [30, 7] if not provided.
    
    Returns:
        Dict with execution statistics:
            - checked_users: Number of users checked
            - reminders_created: Number of new reminders created
            - reminders_skipped: Number of duplicate reminders skipped
            - errors: Number of errors encountered
    
    Requirements: 8.1-8.5
    """
    # Default reminder days if not provided
    if reminder_days is None:
        reminder_days = [30, 7]
    
    stats = {
        "checked_users": 0,
        "reminders_created": 0,
        "reminders_skipped": 0,
        "errors": 0,
        "reminder_days": reminder_days
    }
    
    try:
        # Get database session
        async with AsyncSessionLocal() as session:
            # Calculate target expiration dates for each reminder interval
            today = datetime.now().date()
            target_dates = [today + timedelta(days=days) for days in reminder_days]
            
            logger.info(
                f"Checking for expirations on dates: {[d.strftime('%Y-%m-%d') for d in target_dates]}"
            )
            
            # Query users with ACTIVE subscriptions expiring on target dates
            # We check the date part only (not time) for matching
            query = select(User).where(
                User.subscription_status == SubscriptionStatus.ACTIVE,
                User.subscription_end_date.isnot(None)
            )
            
            result = await session.execute(query)
            users = result.scalars().all()
            
            logger.info(f"Found {len(users)} users with ACTIVE subscriptions")
            
            # Process each user
            for user in users:
                stats["checked_users"] += 1
                
                try:
                    # Check if user's expiration date matches any target date
                    user_expiry_date = user.subscription_end_date.date()
                    
                    if user_expiry_date in target_dates:
                        logger.info(
                            f"User subscription expiring soon: user_id={user.id}, "
                            f"expiry_date={user_expiry_date.strftime('%Y-%m-%d')}"
                        )
                        
                        # Schedule reminders for this user
                        created_events = await schedule_renewal_reminders(
                            session=session,
                            user=user,
                            reminder_days=reminder_days
                        )
                        
                        # Update statistics
                        if created_events:
                            stats["reminders_created"] += len(created_events)
                            logger.info(
                                f"Created {len(created_events)} reminders for user_id={user.id}"
                            )
                        else:
                            stats["reminders_skipped"] += 1
                            logger.debug(
                                f"No new reminders created for user_id={user.id} (duplicates)"
                            )
                
                except Exception as e:
                    stats["errors"] += 1
                    logger.error(
                        f"Error processing user: user_id={user.id}, error={e}",
                        exc_info=True
                    )
                    # Continue processing other users
                    continue
            
            # Commit all created reminders
            await session.commit()
            
            logger.info(
                f"Expiration check complete: checked={stats['checked_users']}, "
                f"created={stats['reminders_created']}, "
                f"skipped={stats['reminders_skipped']}, "
                f"errors={stats['errors']}"
            )
            
            return stats
    
    except Exception as e:
        logger.error(
            f"Error in _check_expirations_async: {e}",
            exc_info=True
        )
        stats["errors"] += 1
        return stats


# ========== Celery Tasks ==========


@shared_task(
    name="celery_app.renewal_tasks.check_upcoming_expirations",
    queue="renewal_reminders"
)
def check_upcoming_expirations_task(reminder_days: list[int] = None) -> dict:
    """
    Periodic task to check for upcoming subscription expirations.
    
    Runs daily at 09:00 Moscow time (configured in celery_config.py).
    Scans all users with ACTIVE subscriptions and creates Notification_Event
    records for subscriptions expiring in 30 or 7 days (configurable).
    
    The task:
    1. Queries users with subscription_status=ACTIVE
    2. Filters for subscription_end_date in configured days (default: 30, 7)
    3. Creates Notification_Event records for each reminder
    4. Checks for duplicates before creating (via schedule_renewal_reminders)
    5. Returns execution statistics
    
    Args:
        reminder_days: List of days before expiration to send reminders.
                      Defaults to [30, 7] if not provided.
    
    Returns:
        Dict with execution statistics:
            - checked_users: Number of users checked
            - reminders_created: Number of new reminders created
            - reminders_skipped: Number of duplicate reminders skipped
            - errors: Number of errors encountered
            - reminder_days: Configured reminder days
    
    Requirements: 8.1-8.5
    """
    logger.info(
        f"Starting check_upcoming_expirations_task: "
        f"reminder_days={reminder_days or [30, 7]}"
    )
    
    try:
        # Create new event loop for async execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Execute async expiration check
            result = loop.run_until_complete(
                _check_expirations_async(reminder_days=reminder_days)
            )
            
            logger.info(
                f"Expiration check completed: "
                f"checked={result['checked_users']}, "
                f"created={result['reminders_created']}, "
                f"skipped={result['reminders_skipped']}, "
                f"errors={result['errors']}"
            )
            
            return result
        
        finally:
            # Dispose engine connections before closing loop (Windows asyncpg fix)
            from constants import engine
            loop.run_until_complete(engine.dispose())
            loop.close()
    
    except Exception as exc:
        logger.error(
            f"Task execution failed: error={exc}",
            exc_info=True
        )
        
        return {
            "status": "error",
            "error": str(exc),
            "checked_users": 0,
            "reminders_created": 0,
            "reminders_skipped": 0,
            "errors": 1
        }


async def _send_reminder_async(notification_event_id: int) -> dict:
    """
    Async helper to send renewal reminder to user.
    
    Retrieves Notification_Event, formats message with expiration date,
    sends via Telegram or MAX with renewal button, updates event status.
    Supports both Telegram and MAX messengers.
    
    Args:
        notification_event_id: ID of Notification_Event to process
    
    Returns:
        Dict with status and execution details:
            - status: "success", "bot_blocked", "failed", or "not_found"
            - notification_event_id: ID of processed event
            - user_id: User ID (if found)
            - messenger: Messenger type used
            - error: Error message (if failed)
    
    Requirements: 3.1-3.9, 10.6, 10.7
    """
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
    from maxapi import Bot as MAXBot
    from maxapi.enums.parse_mode import ParseMode as MAXParseMode
    from maxapi.exceptions import MaxApiError
    from database.models import MAX_Messenger_Data
    
    from bots.tg_bot.keyboards.renewal_kb import get_subscription_status_keyboard
    from bots.tg_bot.texts import RENEWAL_REMINDER_30_DAYS, RENEWAL_REMINDER_7_DAYS
    
    try:
        # Get database session
        async with AsyncSessionLocal() as session:
            # Retrieve Notification_Event by ID
            query = select(Notification_Event).where(
                Notification_Event.id == notification_event_id
            )
            result = await session.execute(query)
            event = result.scalar_one_or_none()
            
            if not event:
                logger.error(
                    f"Notification_Event not found: id={notification_event_id}"
                )
                return {
                    "status": "not_found",
                    "notification_event_id": notification_event_id,
                    "error": "Notification_Event not found"
                }
            
            # Get user with subscription data
            user_query = select(User).where(User.id == event.user_id)
            user_result = await session.execute(user_query)
            user = user_result.scalar_one_or_none()
            
            if not user:
                logger.error(
                    f"User not found: user_id={event.user_id}, "
                    f"event_id={notification_event_id}"
                )
                
                # Update event status to FAILED
                event.event_status = EventStatus.FAILED
                event.sent_at = datetime.now()
                await session.commit()
                
                return {
                    "status": "failed",
                    "notification_event_id": notification_event_id,
                    "user_id": event.user_id,
                    "error": "User not found"
                }
            
            # Determine messenger type (MAX only)
            messenger_type = None
            messenger_id = None
            
            if user.max_user_id:
                messenger_type = "max"
                messenger_id = user.max_user_id
            else:
                logger.error(
                    f"User has no MAX messenger ID: user_id={event.user_id}, "
                    f"event_id={notification_event_id}"
                )
                
                # Update event status to FAILED
                event.event_status = EventStatus.FAILED
                event.sent_at = datetime.now()
                await session.commit()
                
                return {
                    "status": "failed",
                    "notification_event_id": notification_event_id,
                    "user_id": event.user_id,
                    "error": "User has no MAX messenger ID"
                }
            
            # Format expiration date
            expiry_date = user.subscription_end_date.strftime("%d.%m.%Y")
            
            # Select message text based on event type
            if event.event_type == EventType.RENEWAL_REMINDER_30:
                message_text = RENEWAL_REMINDER_30_DAYS.format(expiry_date=expiry_date)
            elif event.event_type == EventType.RENEWAL_REMINDER_7:
                message_text = RENEWAL_REMINDER_7_DAYS.format(expiry_date=expiry_date)
            else:
                logger.error(
                    f"Unknown event type: event_id={notification_event_id}, "
                    f"event_type={event.event_type}"
                )
                
                # Update event status to FAILED
                event.event_status = EventStatus.FAILED
                event.sent_at = datetime.now()
                await session.commit()
                
                return {
                    "status": "failed",
                    "notification_event_id": notification_event_id,
                    "user_id": event.user_id,
                    "error": f"Unknown event type: {event.event_type}"
                }
            
            # Send reminder via MAX messenger
            try:
                # Get MAX chat_id from database
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == messenger_id
                )
                result_chat = await session.execute(stmt_chat)
                chat_id = result_chat.scalar_one_or_none()
                
                if chat_id is None:
                    logger.error(
                        f"No MAX chat_id found: event_id={notification_event_id}, "
                        f"user_id={user.id}, max_user_id={messenger_id}"
                    )
                    
                    # Update event status to FAILED
                    event.event_status = EventStatus.FAILED
                    event.sent_at = datetime.now()
                    await session.commit()
                    
                    return {
                        "status": "failed",
                        "notification_event_id": notification_event_id,
                        "user_id": user.id,
                        "messenger": messenger_type,
                        "error": "No MAX chat_id found"
                    }
                
                # Initialize MAX bot
                from constants import MAX_BOT_TOKEN
                
                bot = MAXBot(
                    token=MAX_BOT_TOKEN,
                    parse_mode=MAXParseMode.HTML
                )
                
                try:
                    # Send MAX message
                    # Note: MAX keyboards need to be sent as attachments
                    await bot.send_message(
                        chat_id=chat_id,
                        text=message_text
                    )
                    
                    logger.info(
                        f"MAX renewal reminder sent: event_id={notification_event_id}, "
                        f"user_id={user.id}, max_user_id={messenger_id}, "
                        f"chat_id={chat_id}, event_type={event.event_type.value}"
                    )
                
                except MaxApiError as e:
                    error_str = str(e).lower()
                    if "blocked" in error_str or "forbidden" in error_str or "chat.not.found" in error_str:
                        # Bot blocked by user - don't retry
                        logger.warning(
                            f"MAX bot blocked by user: event_id={notification_event_id}, "
                            f"user_id={user.id}, max_user_id={messenger_id}, "
                            f"chat_id={chat_id}, error={e}"
                        )
                        
                        # Update event status to FAILED
                        event.event_status = EventStatus.FAILED
                        event.sent_at = datetime.now()
                        await session.commit()
                        
                        return {
                            "status": "bot_blocked",
                            "notification_event_id": notification_event_id,
                            "user_id": user.id,
                            "messenger": messenger_type,
                            "messenger_id": messenger_id,
                            "error": str(e)
                        }
                    
                    # Other MAX API errors - will trigger retry
                    logger.error(
                        f"MAX API error: event_id={notification_event_id}, "
                        f"user_id={user.id}, max_user_id={messenger_id}, "
                        f"chat_id={chat_id}, error={e}",
                        exc_info=True
                    )
                    raise
                
                finally:
                    await bot.session.close()
                
                # Update event status to SENT
                event.event_status = EventStatus.SENT
                event.sent_at = datetime.now()
                await session.commit()
                
                return {
                    "status": "success",
                    "notification_event_id": notification_event_id,
                    "user_id": user.id,
                    "messenger": messenger_type,
                    "messenger_id": messenger_id,
                    "event_type": event.event_type.value
                }
            
            except Exception as e:
                # Unexpected error - will trigger retry
                logger.error(
                    f"Unexpected error sending reminder: "
                    f"event_id={notification_event_id}, user_id={user.id}, error={e}",
                    exc_info=True
                )
                
                # Don't update event status - let retry mechanism handle it
                raise
    
    except Exception as e:
        logger.error(
            f"Error in _send_reminder_async: "
            f"event_id={notification_event_id}, error={e}",
            exc_info=True
        )
        raise


@shared_task(
    name="celery_app.renewal_tasks.send_renewal_reminder",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=60,
    retry_backoff_max=240,
    retry_jitter=True,
    queue="renewal_reminders"
)
def send_renewal_reminder_task(
    self,
    notification_event_id: int
) -> dict:
    """
    Send renewal reminder to user.
    
    Retrieves Notification_Event, formats message with expiration date,
    sends via Telegram with renewal button, updates event status.
    
    Retries on failure with exponential backoff (3 attempts max).
    Does not retry if bot is blocked by user (TelegramForbiddenError).
    
    Args:
        notification_event_id: ID of Notification_Event to process
    
    Returns:
        Dict with status and execution details:
            - status: "success", "bot_blocked", "failed", or "not_found"
            - notification_event_id: ID of processed event
            - user_id: User ID (if found)
            - error: Error message (if failed)
    
    Requirements: 3.1-3.9, 10.6, 10.7
    """
    logger.info(
        f"Starting send_renewal_reminder_task: "
        f"notification_event_id={notification_event_id}, "
        f"attempt={self.request.retries + 1}"
    )
    
    try:
        # Create new event loop for async execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Execute async reminder send
            result = loop.run_until_complete(
                _send_reminder_async(notification_event_id=notification_event_id)
            )
            
            # Check if we should retry
            if result["status"] == "bot_blocked":
                # Don't retry if bot is blocked
                logger.info(
                    f"Bot blocked, not retrying: "
                    f"notification_event_id={notification_event_id}"
                )
                return result
            
            elif result["status"] in ("failed", "not_found"):
                # Check if we've exhausted retries
                if self.request.retries >= self.max_retries:
                    logger.error(
                        f"Max retries exhausted: "
                        f"notification_event_id={notification_event_id}, "
                        f"status={result['status']}"
                    )
                    return result
                else:
                    # Retry
                    logger.warning(
                        f"Reminder send failed, will retry: "
                        f"notification_event_id={notification_event_id}, "
                        f"attempt={self.request.retries + 1}/{self.max_retries}"
                    )
                    raise Exception(f"Reminder send failed: {result.get('error', 'Unknown error')}")
            
            logger.info(
                f"Reminder send completed: "
                f"notification_event_id={notification_event_id}, "
                f"status={result['status']}"
            )
            
            return result
        
        finally:
            # Dispose engine connections before closing loop (Windows asyncpg fix)
            from constants import engine
            loop.run_until_complete(engine.dispose())
            loop.close()
    
    except Exception as exc:
        logger.error(
            f"Task execution failed: "
            f"notification_event_id={notification_event_id}, "
            f"attempt={self.request.retries + 1}, error={exc}",
            exc_info=True
        )
        
        # If we've exhausted retries, return error status
        if self.request.retries >= self.max_retries:
            return {
                "status": "failed",
                "notification_event_id": notification_event_id,
                "error": str(exc),
                "attempts": self.request.retries + 1
            }
        
        # Otherwise, re-raise to trigger retry
        raise

