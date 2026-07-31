"""
Celery tasks for processing the i-TAT API retry queue.

Periodically picks up pending retry records and re-executes the failed
API calls. Notifies admins when retries are exhausted.

Requirements: 25.3, 34.1-34.5
"""

import asyncio
import os
import sys
from typing import Any

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    name="celery_app.retry_tasks.process_api_retry_queue",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="api_retries",
)
def process_api_retry_queue(self) -> dict[str, Any]:
    """
    Process all pending i-TAT API retry records that are due.

    Runs every 5 minutes via Celery Beat. For each due record:
    - Calls the original API method with the stored payload
    - Marks success or schedules next retry with exponential backoff
    - After MAX_RETRY_ATTEMPTS, marks as failed and notifies admins

    Returns:
        Dict with processing statistics
    """
    try:
        result = asyncio.run(_process_api_retry_queue_async())
        logger.info(
            f"process_api_retry_queue completed: "
            f"processed={result['processed']}, "
            f"succeeded={result['succeeded']}, "
            f"failed={result['failed']}, "
            f"exhausted={result['exhausted']}"
        )
        return result

    except Exception as exc:
        logger.error(f"process_api_retry_queue task error: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for process_api_retry_queue task itself")
            return {"status": "error", "message": str(exc)}



def _create_task_db() -> tuple[Any, Any]:
    """Create database resources bound to one Celery task event loop."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from constants import DB_URL, SQL_ECHO

    task_engine = create_async_engine(DB_URL, echo=SQL_ECHO, pool_pre_ping=True)
    task_session = async_sessionmaker(
        bind=task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return task_engine, task_session


async def _process_api_retry_queue_async() -> dict[str, Any]:
    """
    Async implementation of the retry queue processor.

    Returns:
        Dict with keys: processed, succeeded, failed, exhausted
    """
    from services.i_tat_service import ITatAPIClient
    from services.retry_service import (
        RETRY_BATCH_SIZE,
        RetryStatus,
        _escalate_failed_retry,
        get_next_pending_retry,
        process_retry,
    )

    stats = {"processed": 0, "succeeded": 0, "failed": 0, "exhausted": 0}

    task_engine, TaskSession = _create_task_db()
    try:
        async with TaskSession() as session:
            api_client = ITatAPIClient()
            try:
                for _ in range(RETRY_BATCH_SIZE):
                    retry_record = await get_next_pending_retry(session)
                    if retry_record is None:
                        if stats["processed"] == 0:
                            logger.debug("No pending retries to process")
                        break

                    stats["processed"] += 1
                    try:
                        success = await process_retry(session, retry_record, api_client)

                        if success:
                            stats["succeeded"] += 1
                            logger.info(
                                f"Retry succeeded: id={retry_record.id}, "
                                f"operation={retry_record.operation}"
                            )
                        else:
                            stats["failed"] += 1
                            # Refresh record from DB to get updated status
                            await session.refresh(retry_record)
                            # Check if this attempt exhausted all retries
                            if retry_record.status == RetryStatus.FAILED:
                                stats["exhausted"] += 1
                                await _escalate_failed_retry(session, retry_record)

                        # Persist each external operation independently. A later task
                        # timeout cannot roll back records already processed.
                        await session.commit()

                    except Exception as e:
                        await session.rollback()
                        logger.error(
                            f"Unexpected error processing retry id={retry_record.id}: {e}",
                            exc_info=True,
                        )
                        raise

            finally:
                await api_client.close()
    finally:
        await task_engine.dispose()

    return stats


@shared_task(
    name="celery_app.retry_tasks.cleanup_old_api_retries",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="api_retries",
)
def cleanup_old_api_retries(self) -> dict[str, Any]:
    """
    Delete completed/failed API retry records older than 30 days.

    Runs daily at 4:00 AM via Celery Beat.

    Returns:
        Dict with count of deleted records
    """
    try:
        result = asyncio.run(_cleanup_old_api_retries_async())
        logger.info(f"cleanup_old_api_retries completed: deleted={result['deleted']}")
        return result

    except Exception as exc:
        logger.error(f"cleanup_old_api_retries task error: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc, countdown=300 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            return {"status": "error", "message": str(exc)}



async def _cleanup_old_api_retries_async() -> dict[str, int]:
    from services.retry_service import cleanup_old_retries

    task_engine, TaskSession = _create_task_db()
    try:
        async with TaskSession() as session:
            deleted = await cleanup_old_retries(session, days_old=30)
            await session.commit()
            return {"deleted": deleted}
    finally:
        await task_engine.dispose()
