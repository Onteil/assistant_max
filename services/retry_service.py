"""
API Retry Queue Service

Manages failed API operations with exponential backoff retry logic.
Queues failed operations and processes them in background tasks.

Requirements: 25.3, 34.1-34.5
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import API_Retry_Queue, RetryStatus

logger = logging.getLogger(__name__)


# Retry configuration
RETRY_DELAYS = [
    timedelta(minutes=5),   # 1st retry after 5 minutes
    timedelta(minutes=15),  # 2nd retry after 15 minutes
    timedelta(minutes=30),  # 3rd retry after 30 minutes
    timedelta(hours=1),     # 4th retry after 1 hour
    timedelta(hours=2),     # 5th retry after 2 hours
]
MAX_RETRY_ATTEMPTS = 5


async def queue_api_retry(
    session: AsyncSession,
    operation: str,
    payload: dict[str, Any],
    telegram_id: int | None = None
) -> API_Retry_Queue:
    """
    Queue failed API operation for retry.
    
    Args:
        session: Database session
        operation: API operation name (e.g., "register_user", "check_key_conflict")
        payload: Request payload to retry
        telegram_id: User ID for context (optional)
    
    Returns:
        Created API_Retry_Queue object
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 25.3
    """
    try:
        retry_record = API_Retry_Queue(
            operation=operation,
            payload=payload,
            tg_user_id=telegram_id,
            attempt_count=0,
            status=RetryStatus.PENDING,
            next_retry_at=datetime.utcnow() + RETRY_DELAYS[0],
            created_at=datetime.utcnow()
        )
        
        session.add(retry_record)
        await session.flush()
        
        logger.info(
            f"API operation queued for retry: id={retry_record.id}, "
            f"operation={operation}, user={telegram_id}, "
            f"next_retry={retry_record.next_retry_at}"
        )
        
        return retry_record
    
    except SQLAlchemyError as e:
        logger.error(
            f"Error queuing API retry: operation={operation}, "
            f"telegram_id={telegram_id}, error={e}",
            exc_info=True
        )
        raise


async def get_pending_retries(session: AsyncSession) -> list[API_Retry_Queue]:
    """
    Get all pending retry operations that are due for retry.
    
    Args:
        session: Database session
    
    Returns:
        List of API_Retry_Queue objects ready for retry
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        now = datetime.utcnow()
        
        result = await session.execute(
            select(API_Retry_Queue)
            .where(
                API_Retry_Queue.status == RetryStatus.PENDING,
                API_Retry_Queue.next_retry_at <= now,
                API_Retry_Queue.attempt_count < MAX_RETRY_ATTEMPTS
            )
            .order_by(API_Retry_Queue.next_retry_at)
        )
        
        retries = result.scalars().all()
        
        logger.debug(f"Found {len(retries)} pending retries")
        
        return list(retries)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Error fetching pending retries: error={e}",
            exc_info=True
        )
        raise


async def mark_retry_success(
    session: AsyncSession,
    retry_id: int
) -> None:
    """
    Mark retry operation as successful.
    
    Args:
        session: Database session
        retry_id: Retry record ID
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        result = await session.execute(
            select(API_Retry_Queue).where(API_Retry_Queue.id == retry_id)
        )
        retry_record = result.scalar_one_or_none()
        
        if retry_record:
            retry_record.status = RetryStatus.SUCCESS
            retry_record.completed_at = datetime.utcnow()
            await session.flush()
            
            logger.info(
                f"Retry marked as success: id={retry_id}, "
                f"operation={retry_record.operation}, "
                f"attempts={retry_record.attempt_count}"
            )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Error marking retry success: retry_id={retry_id}, error={e}",
            exc_info=True
        )
        raise


async def mark_retry_failed(
    session: AsyncSession,
    retry_id: int,
    error_message: str
) -> None:
    """
    Mark retry operation as failed and schedule next retry or escalate.
    
    Args:
        session: Database session
        retry_id: Retry record ID
        error_message: Error message from failed attempt
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        result = await session.execute(
            select(API_Retry_Queue).where(API_Retry_Queue.id == retry_id)
        )
        retry_record = result.scalar_one_or_none()
        
        if not retry_record:
            logger.warning(f"Retry record not found: id={retry_id}")
            return
        
        # Increment attempt count
        retry_record.attempt_count += 1
        retry_record.last_error = error_message
        
        # Check if max attempts reached
        if retry_record.attempt_count >= MAX_RETRY_ATTEMPTS:
            retry_record.status = RetryStatus.FAILED
            retry_record.completed_at = datetime.utcnow()
            
            logger.error(
                f"Retry failed after max attempts: id={retry_id}, "
                f"operation={retry_record.operation}, "
                f"attempts={retry_record.attempt_count}, "
                f"error={error_message}"
            )
            
            # TODO: Send admin notification for escalation
            await _escalate_failed_retry(session, retry_record)
        
        else:
            # Schedule next retry with exponential backoff
            delay = RETRY_DELAYS[retry_record.attempt_count]
            retry_record.next_retry_at = datetime.utcnow() + delay
            
            logger.warning(
                f"Retry attempt failed, scheduling next: id={retry_id}, "
                f"operation={retry_record.operation}, "
                f"attempt={retry_record.attempt_count}/{MAX_RETRY_ATTEMPTS}, "
                f"next_retry={retry_record.next_retry_at}, "
                f"error={error_message}"
            )
        
        await session.flush()
    
    except SQLAlchemyError as e:
        logger.error(
            f"Error marking retry failed: retry_id={retry_id}, error={e}",
            exc_info=True
        )
        raise


async def process_retry(
    session: AsyncSession,
    retry_record: API_Retry_Queue,
    api_client: Any
) -> bool:
    """
    Process a single retry operation.
    
    Args:
        session: Database session
        retry_record: Retry record to process
        api_client: API client instance
    
    Returns:
        True if retry succeeded, False otherwise
    """
    try:
        logger.info(
            f"Processing retry: id={retry_record.id}, "
            f"operation={retry_record.operation}, "
            f"attempt={retry_record.attempt_count + 1}/{MAX_RETRY_ATTEMPTS}"
        )
        
        # Get the API method
        if not hasattr(api_client, retry_record.operation):
            error_msg = f"Unknown API operation: {retry_record.operation}"
            logger.error(error_msg)
            await mark_retry_failed(session, retry_record.id, error_msg)
            return False
        
        api_method = getattr(api_client, retry_record.operation)
        
        # Call the API method with payload
        result = await api_method(**retry_record.payload)
        
        # Check if successful
        if result.get("status") == "ok":
            await mark_retry_success(session, retry_record.id)
            return True
        else:
            error_msg = f"API returned non-ok status: {result.get('status')}"
            await mark_retry_failed(session, retry_record.id, error_msg)
            return False
    
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        await mark_retry_failed(session, retry_record.id, error_msg)
        return False


async def _escalate_failed_retry(
    session: AsyncSession,
    retry_record: API_Retry_Queue
) -> None:
    """
    Escalate failed retry to admin notification.
    
    Internal helper to create admin notification ticket when retry fails
    after max attempts.
    
    Args:
        session: Database session
        retry_record: Failed retry record
    """
    try:
        from database.models import ActionType, Action_Log
        
        # Log escalation action
        action_log = Action_Log(
            action_type=ActionType.API_RETRY_FAILED,
            tg_user_id=retry_record.tg_user_id,
            action_details={
                "retry_id": retry_record.id,
                "operation": retry_record.operation,
                "attempt_count": retry_record.attempt_count,
                "last_error": retry_record.last_error,
                "payload": retry_record.payload
            },
            action_timestamp=datetime.utcnow()
        )
        
        session.add(action_log)
        await session.flush()
        
        logger.warning(
            f"API retry escalated to admin: retry_id={retry_record.id}, "
            f"operation={retry_record.operation}"
        )
        
        # TODO: Create admin ticket or send notification
        # This would integrate with the ticket service to create an admin ticket
    
    except Exception as e:
        logger.error(
            f"Error escalating failed retry: retry_id={retry_record.id}, error={e}",
            exc_info=True
        )


async def cleanup_old_retries(
    session: AsyncSession,
    days_old: int = 30
) -> int:
    """
    Clean up old completed/failed retry records.
    
    Args:
        session: Database session
        days_old: Delete records older than this many days (default: 30)
    
    Returns:
        Number of records deleted
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        result = await session.execute(
            select(API_Retry_Queue)
            .where(
                API_Retry_Queue.status.in_([RetryStatus.SUCCESS, RetryStatus.FAILED]),
                API_Retry_Queue.completed_at < cutoff_date
            )
        )
        
        old_records = result.scalars().all()
        count = len(old_records)
        
        for record in old_records:
            await session.delete(record)
        
        await session.flush()
        
        logger.info(f"Cleaned up {count} old retry records older than {days_old} days")
        
        return count
    
    except SQLAlchemyError as e:
        logger.error(
            f"Error cleaning up old retries: error={e}",
            exc_info=True
        )
        raise
