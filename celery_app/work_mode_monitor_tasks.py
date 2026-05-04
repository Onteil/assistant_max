"""
Work Mode Monitor Tasks for Celery.

Monitors work mode changes and triggers queue processing when transitioning
from NON_WORKING to REGULAR mode.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import pytz
import redis

from celery_app.celery_config import app
from constants import REDIS
from database.models import WorkMode
from services.calendar_service import get_current_work_mode

logger = logging.getLogger(__name__)

MOSCOW_TZ = pytz.timezone('Europe/Moscow')
LAST_WORK_MODE_KEY = "work_mode_monitor:last_mode"
redis_client = redis.from_url(REDIS)


def _make_session():
    """Create a fresh engine + session factory bound to the current event loop."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from constants import DB_URL, DEBUG
    engine = create_async_engine(DB_URL, echo=DEBUG, pool_pre_ping=True)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    return engine, Session


# ========== Async implementations ==========

async def _check_work_mode_transition_async() -> dict[str, Any]:
    """Async implementation of work mode transition check."""
    engine, Session = _make_session()
    logger.info("Starting work mode transition check")
    try:
        async with Session() as session:
            current_work_mode = await get_current_work_mode(session)
            current_time = datetime.now(MOSCOW_TZ)

            last_mode_str = redis_client.get(LAST_WORK_MODE_KEY)
            last_work_mode = None
            redis_key_missing = False

            if last_mode_str:
                try:
                    last_work_mode = WorkMode(last_mode_str.decode('utf-8'))
                except ValueError:
                    logger.warning(f"Invalid work mode in Redis: {last_mode_str}")
            else:
                redis_key_missing = True
                last_work_mode = WorkMode.NON_WORKING
                logger.warning(
                    "Redis key missing for work mode monitor — treating previous mode as "
                    "NON_WORKING to ensure pending tickets are processed"
                )

            logger.info(
                f"Work mode check: current={current_work_mode.value}, "
                f"previous={last_work_mode.value}, "
                f"redis_key_missing={redis_key_missing}, "
                f"time={current_time.strftime('%H:%M')}"
            )

            transition_detected = False
            should_process_queue = False

            if last_work_mode is not None:
                if (last_work_mode == WorkMode.NON_WORKING and
                        current_work_mode in [WorkMode.REGULAR, WorkMode.EXTENDED]):
                    transition_detected = True
                    should_process_queue = True
                    logger.info(
                        f"Work mode transition detected: {last_work_mode.value} → {current_work_mode.value}"
                    )
                elif last_work_mode != current_work_mode:
                    transition_detected = True
                    logger.info(
                        f"Work mode transition (no queue processing): "
                        f"{last_work_mode.value} → {current_work_mode.value}"
                    )

            # Update Redis (TTL 48h to survive weekends/holidays)
            redis_client.set(LAST_WORK_MODE_KEY, current_work_mode.value, ex=172800)

            if should_process_queue:
                logger.info("Triggering immediate queue processing due to work mode transition")
                from celery_app.ticket_notification_tasks import process_pending_tickets_task
                task_result = process_pending_tickets_task.apply_async(queue="ticket_notifications")
                logger.info(f"Queue processing task scheduled: task_id={task_result.id}")
                return {
                    "status": "transition_detected",
                    "previous_mode": last_work_mode.value,
                    "current_mode": current_work_mode.value,
                    "queue_processing_triggered": True,
                    "queue_task_id": task_result.id,
                    "transition_time": current_time.isoformat()
                }
            
            # Even without a transition, check for unprocessed tickets.
            # In REGULAR: process all ticket types.
            # In EXTENDED: process only TECHNICAL_SUPPORT and CONSULTATION
            #   (INVOICE/RENEWAL have no manager on duty — they stay queued until REGULAR).
            # process_pending_tickets_task handles the type filtering internally,
            # so we just need to trigger it when there are relevant pending tickets.
            if current_work_mode in (WorkMode.REGULAR, WorkMode.EXTENDED):
                from sqlalchemy import select, and_
                from database.models import Ticket, TicketStatus, TicketType
                from datetime import timedelta

                if current_work_mode == WorkMode.REGULAR:
                    types_to_check = [
                        TicketType.INVOICE, TicketType.RENEWAL,
                        TicketType.TECHNICAL_SUPPORT, TicketType.CONSULTATION,
                    ]
                else:  # EXTENDED
                    types_to_check = [
                        TicketType.TECHNICAL_SUPPORT, TicketType.CONSULTATION,
                    ]

                cutoff = (current_time - timedelta(hours=336)).replace(tzinfo=None)
                stmt = select(Ticket.id).where(
                    and_(
                        Ticket.ticket_status == TicketStatus.NEW,
                        Ticket.created_at >= cutoff,
                        Ticket.ticket_type.in_(types_to_check),
                        Ticket.queue_notification_sent_at.is_(None),
                    )
                ).limit(1)
                result = await session.execute(stmt)
                has_pending = result.scalar_one_or_none() is not None

                if has_pending:
                    logger.info(
                        f"Unprocessed queued tickets found in {current_work_mode.value} mode "
                        f"— triggering queue processing"
                    )
                    from celery_app.ticket_notification_tasks import process_pending_tickets_task
                    task_result = process_pending_tickets_task.apply_async(queue="ticket_notifications")
                    logger.info(f"Queue processing task scheduled: task_id={task_result.id}")
                    return {
                        "status": "pending_tickets_found",
                        "current_mode": current_work_mode.value,
                        "queue_processing_triggered": True,
                        "queue_task_id": task_result.id,
                        "check_time": current_time.isoformat()
                    }

            if transition_detected:
                return {
                    "status": "transition_detected",
                    "previous_mode": last_work_mode.value,
                    "current_mode": current_work_mode.value,
                    "queue_processing_triggered": False,
                    "transition_time": current_time.isoformat()
                }
            else:
                return {
                    "status": "no_transition",
                    "current_mode": current_work_mode.value,
                    "check_time": current_time.isoformat()
                }
    finally:
        await engine.dispose()


async def _initialize_work_mode_monitor_async() -> dict[str, Any]:
    """Async implementation of work mode monitor initialization."""
    engine, Session = _make_session()
    logger.info("Initializing work mode monitor")
    try:
        async with Session() as session:
            current_work_mode = await get_current_work_mode(session)
            redis_client.set(LAST_WORK_MODE_KEY, current_work_mode.value, ex=172800)
            current_time = datetime.now(MOSCOW_TZ)
            logger.info(
                f"Work mode monitor initialized: mode={current_work_mode.value}, "
                f"time={current_time.strftime('%H:%M')}"
            )
            return {
                "status": "initialized",
                "initial_mode": current_work_mode.value,
                "initialization_time": current_time.isoformat()
            }
    finally:
        await engine.dispose()


async def _trigger_queue_processing_async(reason: str) -> dict[str, Any]:
    """Async implementation of manual queue processing trigger."""
    logger.info(f"Manually triggering queue processing: reason={reason}")
    from celery_app.ticket_notification_tasks import process_pending_tickets_task
    task_result = process_pending_tickets_task.apply_async(queue="ticket_notifications")
    current_time = datetime.now(MOSCOW_TZ)
    logger.info(f"Queue processing manually triggered: task_id={task_result.id}, reason={reason}")
    return {
        "status": "triggered",
        "reason": reason,
        "queue_task_id": task_result.id,
        "trigger_time": current_time.isoformat()
    }


# ========== Celery Tasks ==========

@app.task(
    bind=True,
    name="celery_app.work_mode_monitor_tasks.check_work_mode_transition",
    max_retries=3,
    default_retry_delay=60,
    queue="work_mode_monitor"
)
def check_work_mode_transition(self) -> dict[str, Any]:
    """Runs every 2 minutes. Triggers process_pending_tickets on NON_WORKING → REGULAR/EXTENDED."""
    try:
        return asyncio.run(_check_work_mode_transition_async())
    except Exception as e:
        logger.error(f"Error in work mode transition check: {e}", exc_info=True)
        try:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for work mode transition check")
            return {"status": "error", "error": str(e)}


@app.task(
    bind=True,
    name="celery_app.work_mode_monitor_tasks.initialize_work_mode_monitor",
    max_retries=1,
    queue="work_mode_monitor"
)
def initialize_work_mode_monitor(self) -> dict[str, Any]:
    """Initialize work mode monitor by storing current work mode in Redis."""
    try:
        return asyncio.run(_initialize_work_mode_monitor_async())
    except Exception as e:
        logger.error(f"Error initializing work mode monitor: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@app.task(
    bind=True,
    name="celery_app.work_mode_monitor_tasks.trigger_queue_processing",
    max_retries=1,
    queue="work_mode_monitor"
)
def trigger_queue_processing(self, reason: str = "manual") -> dict[str, Any]:
    """Manually trigger queue processing (for testing or manual intervention)."""
    try:
        return asyncio.run(_trigger_queue_processing_async(reason))
    except Exception as e:
        logger.error(f"Error manually triggering queue processing: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "reason": reason}
