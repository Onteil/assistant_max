"""
NPS service layer for managing survey scheduling and frequency limiting.

Provides async functions for checking frequency limits, scheduling surveys,
and managing survey lifecycle.

Requirements: 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 3.3, 3.5, 7.4, 8.3, 9.1, 9.2, 9.5
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SurveyType, User
from services.settings_service import get_setting

logger = logging.getLogger(__name__)


# ========== Frequency Limiting ==========


async def check_frequency_limit(
    session: AsyncSession,
    user_id: int
) -> tuple[bool, Optional[datetime]]:
    """
    Check if user can receive an NPS survey based on frequency limits.
    
    Queries the user's last_nps_sent_at timestamp and compares it against
    the configured nps_frequency_days setting to determine if enough time
    has passed since the last survey.
    
    Args:
        session: Database session
        user_id: User ID to check
    
    Returns:
        Tuple of (can_send, last_sent_at):
        - can_send: True if user can receive survey, False if suppressed
        - last_sent_at: Timestamp of last survey sent, or None if never sent
    
    Requirements: 3.1, 3.2, 3.3, 3.5
    """
    try:
        # Query user's last NPS timestamp
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user is None:
            logger.warning(f"User {user_id} not found for frequency check")
            return False, None
        
        last_sent_at = user.last_nps_sent_at
        
        # If never sent, user can receive survey
        if last_sent_at is None:
            logger.info(f"User {user_id} has never received NPS survey - can send")
            return True, None
        
        # Retrieve frequency limit setting
        frequency_days = await get_setting(session, "nps_frequency_days")
        
        if frequency_days is None:
            logger.error("nps_frequency_days setting not found, using default of 30")
            frequency_days = 30
        
        # Calculate time difference
        current_time = datetime.utcnow()
        time_since_last = current_time - last_sent_at
        required_interval = timedelta(days=frequency_days)
        
        can_send = time_since_last >= required_interval
        
        if can_send:
            logger.info(
                f"User {user_id} can receive survey - "
                f"{time_since_last.days} days since last survey "
                f"(required: {frequency_days} days)"
            )
        else:
            days_remaining = (required_interval - time_since_last).days
            logger.info(
                f"User {user_id} suppressed by frequency limit - "
                f"{days_remaining} days remaining until next survey allowed"
            )
        
        return can_send, last_sent_at
    
    except Exception as e:
        logger.error(
            f"Error checking frequency limit for user {user_id}: {e}",
            exc_info=True
        )
        # On error, suppress survey to be safe
        return False, None



# ========== Survey Scheduling ==========


async def schedule_survey(
    session: AsyncSession,
    user_id: int,
    survey_type: SurveyType,
    trigger_event_id: int,
    event_date: datetime
) -> tuple[bool, str]:
    """
    Schedule an NPS survey with frequency checking and delay calculation.
    
    Validates user eligibility via frequency limits, calculates delivery time
    based on configured delay settings, and creates a Celery task scheduled
    for future execution.
    
    Args:
        session: Database session
        user_id: User ID to send survey to
        survey_type: Type of survey (LOYALTY or SERVICE_QUALITY)
        trigger_event_id: ID of triggering event (invoice_id or ticket_id)
        event_date: Timestamp of the triggering event
    
    Returns:
        Tuple of (scheduled, reason):
        - scheduled: True if survey scheduled, False if suppressed
        - reason: "scheduled" or suppression reason
    
    Requirements: 1.1, 1.2, 2.1, 2.2, 3.3, 7.4, 8.3
    """
    try:
        # Check frequency limit
        can_send, last_sent_at = await check_frequency_limit(session, user_id)
        
        if not can_send:
            reason = f"frequency_limit_suppressed (last sent: {last_sent_at})"
            logger.info(
                f"Survey suppressed by frequency limit: user_id={user_id}, "
                f"survey_type={survey_type.value}, reason={reason}"
            )
            return False, reason
        
        # Get delay setting based on survey type
        if survey_type == SurveyType.LOYALTY:
            delay_setting_key = "nps_trigger_after_payment"
        elif survey_type == SurveyType.SERVICE_QUALITY:
            delay_setting_key = "nps_trigger_after_support"
        else:
            logger.error(f"Invalid survey type: {survey_type}")
            return False, "invalid_survey_type"
        
        # Retrieve delay days from settings
        delay_days = await get_setting(session, delay_setting_key)
        
        if delay_days is None:
            logger.error(f"Setting not found: {delay_setting_key}, using default of 1")
            delay_days = 1
        
        # Calculate delivery time
        delivery_time = event_date + timedelta(days=delay_days)
        
        # Import Celery task (lazy import to avoid circular dependencies)
        from celery_app.nps_tasks import build_nps_task_id, send_nps_survey_task

        # Create Celery task with scheduled execution time
        task_id = build_nps_task_id(
            user_id=user_id,
            survey_type=survey_type.value,
            trigger_event_id=trigger_event_id,
        )
        task = send_nps_survey_task.apply_async(
            args=[user_id, survey_type.value, trigger_event_id, event_date.isoformat()],
            eta=delivery_time,
            task_id=task_id,
        )
        
        logger.info(
            f"Survey scheduled: user_id={user_id}, survey_type={survey_type.value}, "
            f"trigger_event_id={trigger_event_id}, event_date={event_date}, "
            f"delay_days={delay_days}, delivery_time={delivery_time}, "
            f"task_id={task.id}"
        )
        
        return True, "scheduled"
    
    except Exception as e:
        logger.error(
            f"Error scheduling survey: user_id={user_id}, "
            f"survey_type={survey_type.value if survey_type else 'None'}, "
            f"error={e}",
            exc_info=True
        )
        return False, f"error: {str(e)}"


async def cancel_pending_surveys(
    session: AsyncSession,
    user_id: int,
    reason: str
) -> int:
    """
    Cancel all pending NPS survey tasks for a user.
    
    Queries Celery for pending tasks associated with the user and revokes them.
    This is used when a user blocks the bot, account is deactivated, or other
    conditions require cancellation of scheduled surveys.
    
    Args:
        session: Database session
        user_id: User ID to cancel surveys for
        reason: Reason code for cancellation (e.g., "user_blocked", "account_deactivated")
    
    Returns:
        Count of cancelled surveys
    
    Requirements: 9.1, 9.2, 9.5
    """
    try:
        from celery_app.celery_config import app as celery_app
        from celery_app.nps_tasks import send_nps_survey_task
        
        # Get Celery inspector to query scheduled tasks
        inspector = celery_app.control.inspect()
        
        # Get all scheduled tasks (tasks with eta)
        scheduled_tasks = inspector.scheduled()
        
        if not scheduled_tasks:
            logger.info(f"No scheduled tasks found for cancellation: user_id={user_id}")
            return 0
        
        cancelled_count = 0
        
        # Iterate through all workers and their scheduled tasks
        for worker, tasks in scheduled_tasks.items():
            for task_info in tasks:
                # Check if this is an NPS survey task for our user
                if task_info.get("name") == send_nps_survey_task.name:
                    # Extract user_id from task args (first argument)
                    task_args = task_info.get("args", [])
                    if task_args and len(task_args) > 0 and task_args[0] == user_id:
                        task_id = task_info.get("id")
                        
                        # Revoke the task
                        celery_app.control.revoke(task_id, terminate=True)
                        
                        cancelled_count += 1
                        
                        logger.info(
                            f"Survey task cancelled: task_id={task_id}, "
                            f"user_id={user_id}, reason={reason}"
                        )
        
        logger.info(
            f"Survey cancellation completed: user_id={user_id}, "
            f"cancelled_count={cancelled_count}, reason={reason}"
        )
        
        return cancelled_count
    
    except Exception as e:
        logger.error(
            f"Error cancelling surveys: user_id={user_id}, reason={reason}, "
            f"error={e}",
            exc_info=True
        )
        return 0
