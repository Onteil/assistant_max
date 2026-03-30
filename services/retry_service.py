"""
API Retry Queue Service

Manages failed i-TAT API operations with exponential backoff retry logic.
Queues transient failures (connection errors, timeouts, 5xx) and retries them
in background. Non-retryable errors (4xx) are NOT queued.

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


# Retry configuration — exponential backoff
RETRY_DELAYS = [
    timedelta(minutes=5),   # 1st retry after 5 min
    timedelta(minutes=15),  # 2nd retry after 15 min
    timedelta(minutes=30),  # 3rd retry after 30 min
    timedelta(hours=1),     # 4th retry after 1 hour
    timedelta(hours=2),     # 5th retry after 2 hours
]
MAX_RETRY_ATTEMPTS = 5


async def queue_api_retry(
    session: AsyncSession,
    operation: str,
    payload: dict[str, Any],
    user_id: int | None = None,
    error_message: str | None = None,
) -> API_Retry_Queue:
    """
    Queue a failed retryable API operation for background retry.

    Only call this for RetryableAPIError (connection, timeout, 5xx).
    Do NOT call for NonRetryableAPIError (4xx client errors).

    Args:
        session: Database session
        operation: ITatAPIClient method name (e.g. "update_user_assets")
        payload: Keyword arguments to pass to the method on retry
        user_id: Internal user DB id for context (optional)
        error_message: Original error message for logging

    Returns:
        Created API_Retry_Queue record

    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        retry_record = API_Retry_Queue(
            operation=operation,
            payload=payload,
            user_id=user_id,
            attempt_count=0,
            status=RetryStatus.PENDING,
            next_retry_at=datetime.utcnow() + RETRY_DELAYS[0],
            created_at=datetime.utcnow(),
            last_error=error_message,
        )

        session.add(retry_record)
        await session.flush()

        logger.info(
            f"API operation queued for retry: id={retry_record.id}, "
            f"operation={operation}, user_id={user_id}, "
            f"next_retry={retry_record.next_retry_at}, error={error_message}"
        )

        return retry_record

    except SQLAlchemyError as e:
        logger.error(
            f"Error queuing API retry: operation={operation}, "
            f"user_id={user_id}, error={e}",
            exc_info=True,
        )
        raise


async def get_pending_retries(session: AsyncSession) -> list[API_Retry_Queue]:
    """
    Get all pending retry operations that are due for processing.

    Args:
        session: Database session

    Returns:
        List of API_Retry_Queue records ready for retry, ordered by next_retry_at
    """
    try:
        now = datetime.utcnow()

        result = await session.execute(
            select(API_Retry_Queue)
            .where(
                API_Retry_Queue.status == RetryStatus.PENDING,
                API_Retry_Queue.next_retry_at <= now,
                API_Retry_Queue.attempt_count < MAX_RETRY_ATTEMPTS,
            )
            .order_by(API_Retry_Queue.next_retry_at)
        )

        retries = list(result.scalars().all())
        logger.debug(f"Found {len(retries)} pending retries due for processing")
        return retries

    except SQLAlchemyError as e:
        logger.error(f"Error fetching pending retries: {e}", exc_info=True)
        raise


async def mark_retry_success(session: AsyncSession, retry_id: int) -> None:
    """Mark a retry record as successfully completed."""
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
                f"Retry succeeded: id={retry_id}, operation={retry_record.operation}, "
                f"total_attempts={retry_record.attempt_count + 1}"
            )

    except SQLAlchemyError as e:
        logger.error(f"Error marking retry success: retry_id={retry_id}, error={e}", exc_info=True)
        raise


async def mark_retry_failed(
    session: AsyncSession,
    retry_id: int,
    error_message: str,
) -> API_Retry_Queue | None:
    """
    Record a failed retry attempt and schedule next retry or mark as exhausted.

    Args:
        session: Database session
        retry_id: Retry record ID
        error_message: Error from this attempt

    Returns:
        Updated retry record (None if not found)
    """
    try:
        result = await session.execute(
            select(API_Retry_Queue).where(API_Retry_Queue.id == retry_id)
        )
        retry_record = result.scalar_one_or_none()

        if not retry_record:
            logger.warning(f"Retry record not found: id={retry_id}")
            return None

        retry_record.attempt_count += 1
        retry_record.last_error = error_message

        if retry_record.attempt_count >= MAX_RETRY_ATTEMPTS:
            retry_record.status = RetryStatus.FAILED
            retry_record.completed_at = datetime.utcnow()

            logger.error(
                f"Retry exhausted after {MAX_RETRY_ATTEMPTS} attempts: "
                f"id={retry_id}, operation={retry_record.operation}, "
                f"last_error={error_message}"
            )
        else:
            delay = RETRY_DELAYS[retry_record.attempt_count]
            retry_record.next_retry_at = datetime.utcnow() + delay

            logger.warning(
                f"Retry attempt {retry_record.attempt_count}/{MAX_RETRY_ATTEMPTS} failed: "
                f"id={retry_id}, operation={retry_record.operation}, "
                f"next_retry_in={delay}, error={error_message}"
            )

        await session.flush()
        return retry_record

    except SQLAlchemyError as e:
        logger.error(f"Error marking retry failed: retry_id={retry_id}, error={e}", exc_info=True)
        raise


async def process_retry(
    session: AsyncSession,
    retry_record: API_Retry_Queue,
    api_client: Any,
) -> bool:
    """
    Execute a single retry attempt using the stored operation and payload.

    Args:
        session: Database session
        retry_record: The retry record to process
        api_client: ITatAPIClient instance

    Returns:
        True if the retry succeeded, False otherwise
    """
    from services.i_tat_service import NonRetryableAPIError

    logger.info(
        f"Processing retry: id={retry_record.id}, operation={retry_record.operation}, "
        f"attempt={retry_record.attempt_count + 1}/{MAX_RETRY_ATTEMPTS}"
    )

    if not hasattr(api_client, retry_record.operation):
        error_msg = f"Unknown API operation: {retry_record.operation}"
        logger.error(error_msg)
        await mark_retry_failed(session, retry_record.id, error_msg)
        return False

    try:
        api_method = getattr(api_client, retry_record.operation)
        result = await api_method(**retry_record.payload)

        # Consider success if no exception raised and status is ok/success
        status_val = result.get("status", "") if isinstance(result, dict) else ""
        if status_val in ("ok", "success", "") or result:
            await mark_retry_success(session, retry_record.id)
            return True

        error_msg = f"API returned unexpected status: {status_val}"
        await mark_retry_failed(session, retry_record.id, error_msg)
        return False

    except NonRetryableAPIError as e:
        # 4xx on retry — no point retrying further, mark as failed immediately
        error_msg = f"NonRetryable error on retry: {e}"
        logger.error(
            f"Retry id={retry_record.id} got non-retryable error, marking failed: {e}"
        )
        retry_record.attempt_count = MAX_RETRY_ATTEMPTS  # force exhausted
        retry_record.status = RetryStatus.FAILED
        retry_record.completed_at = datetime.utcnow()
        retry_record.last_error = error_msg
        await session.flush()
        return False

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        updated = await mark_retry_failed(session, retry_record.id, error_msg)
        return False


async def _escalate_failed_retry(
    session: AsyncSession,
    retry_record: API_Retry_Queue,
) -> None:
    """
    Send admin notification when a retry is exhausted after all attempts.

    Args:
        session: Database session
        retry_record: The exhausted retry record
    """
    try:
        from bots.max_bot.utils.admin_notifications import notify_admins_api_retry_exhausted

        await notify_admins_api_retry_exhausted(
            session=session,
            retry_id=retry_record.id,
            operation=retry_record.operation,
            payload=retry_record.payload,
            attempt_count=retry_record.attempt_count,
            last_error=retry_record.last_error or "Unknown error",
            user_id=retry_record.user_id,
        )

        # Also log to Action_Log for audit trail
        from database.models import ActionType, Action_Log

        action_log = Action_Log(
            action_type=ActionType.API_RETRY_FAILED,
            action_details={
                "retry_id": retry_record.id,
                "operation": retry_record.operation,
                "attempt_count": retry_record.attempt_count,
                "last_error": retry_record.last_error,
                "payload": retry_record.payload,
            },
            action_timestamp=datetime.utcnow(),
        )
        session.add(action_log)
        await session.flush()

        logger.warning(
            f"Exhausted retry escalated to admins: retry_id={retry_record.id}, "
            f"operation={retry_record.operation}"
        )

    except Exception as e:
        logger.error(
            f"Error escalating failed retry: retry_id={retry_record.id}, error={e}",
            exc_info=True,
        )


async def cleanup_old_retries(session: AsyncSession, days_old: int = 30) -> int:
    """
    Delete completed/failed retry records older than `days_old` days.

    Returns:
        Number of records deleted
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)

        result = await session.execute(
            select(API_Retry_Queue).where(
                API_Retry_Queue.status.in_([RetryStatus.SUCCESS, RetryStatus.FAILED]),
                API_Retry_Queue.completed_at < cutoff_date,
            )
        )

        old_records = list(result.scalars().all())
        count = len(old_records)

        for record in old_records:
            await session.delete(record)

        await session.flush()
        logger.info(f"Cleaned up {count} old retry records older than {days_old} days")
        return count

    except SQLAlchemyError as e:
        logger.error(f"Error cleaning up old retries: {e}", exc_info=True)
        raise
