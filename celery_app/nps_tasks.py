"""
Celery tasks for NPS survey delivery and management.

This module implements background tasks for NPS survey system:
- Survey delivery task: Sends scheduled NPS surveys to users
- Cleanup task: Removes old survey tasks from queue

Requirements: 1.3, 2.3, 9.4, 13.1, 13.2
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

from constants import AsyncSessionLocal, MAX_BOT_TOKEN, TG_BOT_TOKEN
from database.models import SurveyType, User

# Use Celery-specific logger
logger = get_task_logger(__name__)


# ========== Helper Functions ==========


async def _send_survey_async(
    user_id: int,
    survey_type: str,
    trigger_event_id: int,
    event_date: str
) -> dict:
    """
    Async helper to send NPS survey via appropriate messenger.
    
    Queries user from database, determines messenger, and sends survey.
    Handles bot_blocked errors gracefully.
    
    Args:
        user_id: User ID to send survey to
        survey_type: Survey type ("loyalty" or "service_quality")
        trigger_event_id: ID of triggering event
        event_date: ISO format timestamp of triggering event
    
    Returns:
        Dict with delivery status
    """
    try:
        # Get database session
        async with AsyncSessionLocal() as session:
            # Query user from database
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if user is None:
                logger.error(f"User not found: user_id={user_id}")
                return {
                    "status": "error",
                    "reason": "user_not_found",
                    "user_id": user_id
                }
            
            # Determine which messenger to use
            # Priority: Telegram (tg_user_id) > MAX (max_user_id)
            messenger_type = None
            messenger_id = None
            
            if user.tg_user_id:
                messenger_type = "telegram"
                messenger_id = user.tg_user_id
            elif user.max_user_id:
                messenger_type = "max"
                messenger_id = user.max_user_id
            else:
                logger.error(
                    f"User has no messenger ID: user_id={user_id}"
                )
                return {
                    "status": "error",
                    "reason": "no_messenger_id",
                    "user_id": user_id
                }
            
            logger.info(
                f"Sending survey via {messenger_type}: "
                f"user_id={user_id}, messenger_id={messenger_id}"
            )
            
            # Parse event_date
            event_datetime = datetime.fromisoformat(event_date)
            
            # Convert survey_type string to enum
            survey_type_enum = SurveyType(survey_type)
            
            # Send survey via appropriate messenger
            if messenger_type == "telegram":
                result = await _send_telegram_survey(
                    messenger_id=messenger_id,
                    survey_type=survey_type_enum,
                    trigger_event_id=trigger_event_id,
                    event_date=event_datetime
                )
            elif messenger_type == "max":
                result = await _send_max_survey(
                    messenger_id=messenger_id,
                    survey_type=survey_type_enum,
                    trigger_event_id=trigger_event_id,
                    event_date=event_datetime
                )
            else:
                logger.error(f"Unknown messenger type: {messenger_type}")
                return {
                    "status": "error",
                    "reason": "unknown_messenger",
                    "user_id": user_id
                }
            
            return result
    
    except Exception as e:
        logger.error(
            f"Error in _send_survey_async: user_id={user_id}, error={e}",
            exc_info=True
        )
        return {
            "status": "error",
            "reason": str(e),
            "user_id": user_id
        }


async def _send_telegram_survey(
    messenger_id: int,
    survey_type: SurveyType,
    trigger_event_id: int,
    event_date: datetime
) -> dict:
    """
    Send NPS survey via Telegram bot.
    
    Wraps send_nps_survey() with comprehensive error handling for:
    - Bot blocked errors (user blocked the bot)
    - Network errors (connection issues)
    - API errors (Telegram API failures)
    
    Args:
        messenger_id: Telegram user ID
        survey_type: Survey type enum
        trigger_event_id: ID of triggering event
        event_date: Timestamp of triggering event
    
    Returns:
        Dict with delivery status
    
    Requirements: 13.2, 13.4
    """
    try:
        # Import bot handler function
        from bots.tg_bot.handlers.client.nps_handler import send_nps_survey
        
        # Initialize bot
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
        
        bot = Bot(
            token=TG_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode="HTML")
        )
        
        try:
            # Send survey with error handling
            success = await send_nps_survey(
                bot=bot,
                user_id=messenger_id,
                survey_type=survey_type,
                event_description=f"TP-{trigger_event_id}",  # Format ticket/invoice number
                trigger_event_id=trigger_event_id,
                event_date=event_date
            )
            
            if success:
                logger.info(
                    f"Telegram survey sent successfully: "
                    f"messenger_id={messenger_id}, survey_type={survey_type.value}, "
                    f"trigger_event_id={trigger_event_id}"
                )
                
                return {
                    "status": "success",
                    "messenger": "telegram",
                    "messenger_id": messenger_id
                }
            else:
                # Survey delivery failed but didn't raise exception
                logger.error(
                    f"Telegram survey delivery failed: "
                    f"messenger_id={messenger_id}, survey_type={survey_type.value}, "
                    f"trigger_event_id={trigger_event_id}"
                )
                return {
                    "status": "delivery_failed",
                    "messenger": "telegram",
                    "messenger_id": messenger_id
                }
        
        except TelegramForbiddenError as e:
            # Bot was blocked by user - don't retry
            logger.warning(
                f"Telegram bot blocked by user: messenger_id={messenger_id}, "
                f"survey_type={survey_type.value}, error={e}"
            )
            
            # TODO: Mark survey as undeliverable in database
            # This would require adding a status field to NPS_Response or separate tracking
            
            return {
                "status": "bot_blocked",
                "messenger": "telegram",
                "messenger_id": messenger_id,
                "error": str(e)
            }
        
        except TelegramBadRequest as e:
            # Invalid request - don't retry
            logger.error(
                f"Telegram bad request: messenger_id={messenger_id}, "
                f"survey_type={survey_type.value}, error={e}",
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
    
    except ImportError:
        # Handler not yet implemented
        logger.warning(
            f"Telegram NPS handler not yet implemented: "
            f"messenger_id={messenger_id}"
        )
        return {
            "status": "not_implemented",
            "messenger": "telegram",
            "messenger_id": messenger_id
        }
    
    except Exception as e:
        # Network errors or other unexpected errors - should be retried
        logger.error(
            f"Error sending Telegram survey: messenger_id={messenger_id}, "
            f"survey_type={survey_type.value}, trigger_event_id={trigger_event_id}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def _send_max_survey(
    messenger_id: int,
    survey_type: SurveyType,
    trigger_event_id: int,
    event_date: datetime
) -> dict:
    """
    Send NPS survey via MAX bot.
    
    IMPORTANT: This function retrieves chat_id from max_messenger_data table.
    
    Wraps send_nps_survey() with comprehensive error handling for:
    - Bot blocked errors (user blocked the bot)
    - Network errors (connection issues)
    - API errors (MAX API failures)
    
    Args:
        messenger_id: MAX user ID (used to lookup chat_id)
        survey_type: Survey type enum
        trigger_event_id: ID of triggering event
        event_date: Timestamp of triggering event
    
    Returns:
        Dict with delivery status
    
    Requirements: 13.2, 13.4
    """
    try:
        # Import bot handler function
        from bots.max_bot.handlers.client.nps_handler import send_nps_survey
        
        # Initialize bot
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
            # Send survey with error handling (using chat_id)
            success = await send_nps_survey(
                bot=bot,
                user_id=chat_id,  # Use chat_id instead of max_user_id
                survey_type=survey_type,
                event_description=f"TP-{trigger_event_id}",  # Format ticket/invoice number
                trigger_event_id=trigger_event_id,
                event_date=event_date
            )
            
            if success:
                logger.info(
                    f"MAX survey sent successfully: "
                    f"max_user_id={messenger_id}, chat_id={chat_id}, survey_type={survey_type.value}, "
                    f"trigger_event_id={trigger_event_id}"
                )
                
                return {
                    "status": "success",
                    "messenger": "max",
                    "messenger_id": messenger_id
                }
            else:
                # Survey delivery failed but didn't raise exception
                logger.error(
                    f"MAX survey delivery failed: "
                    f"max_user_id={messenger_id}, chat_id={chat_id}, survey_type={survey_type.value}, "
                    f"trigger_event_id={trigger_event_id}"
                )
                return {
                    "status": "delivery_failed",
                    "messenger": "max",
                    "messenger_id": messenger_id
                }
        
        except MaxApiError as e:
            # Check if bot was blocked
            error_str = str(e).lower()
            if "blocked" in error_str or "forbidden" in error_str or "user not found" in error_str or "chat.not.found" in error_str:
                logger.warning(
                    f"MAX bot blocked by user or chat not found: max_user_id={messenger_id}, "
                    f"chat_id={chat_id}, survey_type={survey_type.value}, error={e}"
                )
                
                # TODO: Mark survey as undeliverable in database
                
                return {
                    "status": "bot_blocked",
                    "messenger": "max",
                    "messenger_id": messenger_id,
                    "error": str(e)
                }
            
            # Other MAX API errors
            logger.error(
                f"MAX API error: max_user_id={messenger_id}, chat_id={chat_id}, "
                f"survey_type={survey_type.value}, error={e}",
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
    
    except ImportError:
        # Handler not yet implemented
        logger.warning(
            f"MAX NPS handler not yet implemented: "
            f"max_user_id={messenger_id}"
        )
        return {
            "status": "not_implemented",
            "messenger": "max",
            "messenger_id": messenger_id
        }
    
    except Exception as e:
        # Network errors or other unexpected errors - should be retried
        logger.error(
            f"Error sending MAX survey: max_user_id={messenger_id}, "
            f"survey_type={survey_type.value}, trigger_event_id={trigger_event_id}, "
            f"error={e}",
            exc_info=True
        )
        raise


# ========== Celery Tasks ==========


@shared_task(
    name="celery_app.nps_tasks.send_nps_survey",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    queue="nps_surveys"
)
def send_nps_survey_task(
    self,
    user_id: int,
    survey_type: str,
    trigger_event_id: int,
    event_date: str
) -> dict:
    """
    Send NPS survey to user at scheduled time.
    
    This task is scheduled with an eta (execution time) and delivers
    the survey via the user's registered messenger. Handles bot_blocked
    errors gracefully and retries on network failures with exponential backoff.
    
    Args:
        user_id: User ID to send survey to
        survey_type: Survey type ("loyalty" or "service_quality")
        trigger_event_id: ID of triggering event
        event_date: ISO format timestamp of triggering event
    
    Returns:
        Dict with status and execution details
    
    Requirements: 1.3, 2.3, 13.1, 13.2
    """
    logger.info(
        f"Starting send_nps_survey_task: user_id={user_id}, "
        f"survey_type={survey_type}, trigger_event_id={trigger_event_id}, "
        f"task_id={self.request.id}, attempt={self.request.retries + 1}"
    )
    
    try:
        # Create new event loop for async execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Execute async survey delivery
            result = loop.run_until_complete(
                _send_survey_async(
                    user_id=user_id,
                    survey_type=survey_type,
                    trigger_event_id=trigger_event_id,
                    event_date=event_date
                )
            )
            
            # Check result status
            if result["status"] == "success":
                logger.info(
                    f"Survey delivered successfully: user_id={user_id}, "
                    f"messenger={result.get('messenger')}, "
                    f"task_id={self.request.id}"
                )
                return result
            
            elif result["status"] == "bot_blocked":
                # Don't retry if bot is blocked
                logger.warning(
                    f"Survey not delivered - bot blocked: user_id={user_id}, "
                    f"task_id={self.request.id}"
                )
                return result
            
            elif result["status"] == "not_implemented":
                # Handler not yet implemented - don't retry
                logger.warning(
                    f"Survey not delivered - handler not implemented: "
                    f"user_id={user_id}, task_id={self.request.id}"
                )
                return result
            
            elif result["status"] == "error":
                # Log error and return (don't retry for user_not_found, etc.)
                logger.error(
                    f"Survey delivery error: user_id={user_id}, "
                    f"reason={result.get('reason')}, task_id={self.request.id}"
                )
                return result
            
            else:
                logger.error(
                    f"Unknown result status: {result['status']}, "
                    f"user_id={user_id}, task_id={self.request.id}"
                )
                return result
        
        finally:
            # Dispose engine connections before closing loop (Windows asyncpg fix)
            from constants import engine
            loop.run_until_complete(engine.dispose())
            loop.close()
    
    except Exception as exc:
        logger.error(
            f"Task execution failed: user_id={user_id}, "
            f"task_id={self.request.id}, attempt={self.request.retries + 1}, "
            f"error={exc}",
            exc_info=True
        )
        
        # Retry with exponential backoff (handled by autoretry_for)
        # Max retries: 3, backoff: 60s, 120s, 240s (with jitter)
        raise


@shared_task(
    name="celery_app.nps_tasks.cleanup_old_surveys",
    queue="nps_surveys"
)
def cleanup_old_surveys_task() -> dict:
    """
    Periodic task to clean up survey tasks older than 90 days.
    
    Queries Celery for old tasks and revokes them to prevent queue buildup.
    Configured to run daily via Celery beat schedule.
    
    Returns:
        Dict with cleanup statistics
    
    Requirements: 9.4
    """
    logger.info("Starting cleanup_old_surveys_task")
    
    try:
        from celery_app.celery_config import app as celery_app
        
        # Calculate cutoff date (90 days ago)
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        logger.info(f"Cleaning up surveys older than {cutoff_date}")
        
        # Get Celery inspector to query scheduled tasks
        inspector = celery_app.control.inspect()
        
        # Get all scheduled tasks (tasks with eta)
        scheduled_tasks = inspector.scheduled()
        
        if not scheduled_tasks:
            logger.info("No scheduled tasks found")
            return {
                "status": "success",
                "cleaned_count": 0,
                "cutoff_date": cutoff_date.isoformat()
            }
        
        cleaned_count = 0
        
        # Iterate through all workers and their scheduled tasks
        for worker, tasks in scheduled_tasks.items():
            for task_info in tasks:
                # Check if this is an NPS survey task
                if task_info.get("name") == "celery_app.nps_tasks.send_nps_survey":
                    # Get task eta (scheduled execution time)
                    eta = task_info.get("eta")
                    
                    if eta:
                        # Parse eta timestamp
                        try:
                            # eta is in format: "2024-02-15T10:30:00"
                            eta_datetime = datetime.fromisoformat(eta)
                            
                            # Check if task is older than cutoff
                            if eta_datetime < cutoff_date:
                                task_id = task_info.get("id")
                                
                                # Revoke the task
                                celery_app.control.revoke(
                                    task_id,
                                    terminate=True
                                )
                                
                                cleaned_count += 1
                                
                                logger.info(
                                    f"Revoked old survey task: task_id={task_id}, "
                                    f"eta={eta}, worker={worker}"
                                )
                        
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                f"Failed to parse task eta: {eta}, error={e}"
                            )
        
        logger.info(
            f"Cleanup completed: cleaned_count={cleaned_count}, "
            f"cutoff_date={cutoff_date}"
        )
        
        return {
            "status": "success",
            "cleaned_count": cleaned_count,
            "cutoff_date": cutoff_date.isoformat()
        }
    
    except Exception as e:
        logger.error(
            f"Error in cleanup_old_surveys_task: {e}",
            exc_info=True
        )
        return {
            "status": "error",
            "error": str(e)
        }
