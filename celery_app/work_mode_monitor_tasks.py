"""
Work Mode Monitor Tasks for Celery.

Monitors work mode changes and triggers queue processing when transitioning
from NON_WORKING to REGULAR mode.

This allows immediate processing of queued tickets when work starts,
instead of waiting for the fixed 9:00 AM schedule.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import pytz
import redis
from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession

from celery_app.celery_config import app
from constants import AsyncSessionLocal, REDIS
from database.models import WorkMode
from services.calendar_service import get_current_work_mode

logger = logging.getLogger(__name__)

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Redis key for storing last work mode
LAST_WORK_MODE_KEY = "work_mode_monitor:last_mode"

# Initialize Redis connection
redis_client = redis.from_url(REDIS)


class AsyncTask(Task):
    """Base task class with async support."""
    
    def __call__(self, *args, **kwargs):
        import asyncio
        return asyncio.run(self.run_async(*args, **kwargs))
    
    async def run_async(self, *args, **kwargs):
        raise NotImplementedError()


@app.task(
    bind=True,
    base=AsyncTask,
    name="celery_app.work_mode_monitor_tasks.check_work_mode_transition",
    max_retries=3,
    default_retry_delay=60,
    queue="work_mode_monitor"
)
async def check_work_mode_transition(self) -> dict[str, Any]:
    """
    Check for work mode transitions and trigger queue processing.
    
    This task runs every 5 minutes to detect when work mode changes
    from NON_WORKING to REGULAR, and immediately triggers processing
    of queued tickets instead of waiting for the 9:00 AM schedule.
    
    Transitions monitored:
    - NON_WORKING → REGULAR: Trigger queue processing
    - NON_WORKING → EXTENDED: Trigger queue processing  
    - REGULAR → NON_WORKING: No action (tickets will queue)
    - EXTENDED → NON_WORKING: No action (tickets will queue)
    - REGULAR ↔ EXTENDED: No action (both are working modes)
    
    Returns:
        dict: Status and transition information
    """
    logger.info("Starting work mode transition check")
    
    try:
        async with AsyncSessionLocal() as session:
            # Get current work mode
            current_work_mode = await get_current_work_mode(session)
            
            # Get current Moscow time for logging
            current_time = datetime.now(MOSCOW_TZ)
            
            # Get last work mode from Redis
            last_mode_str = redis_client.get(LAST_WORK_MODE_KEY)
            last_work_mode = None
            if last_mode_str:
                try:
                    last_work_mode = WorkMode(last_mode_str.decode('utf-8'))
                except ValueError:
                    logger.warning(f"Invalid work mode in Redis: {last_mode_str}")
            
            logger.info(
                f"Work mode check: current={current_work_mode.value}, "
                f"previous={last_work_mode.value if last_work_mode else 'None'}, "
                f"time={current_time.strftime('%H:%M')}"
            )
            
            # Check for transition from NON_WORKING to working mode
            transition_detected = False
            should_process_queue = False
            
            if last_work_mode is not None:
                # Detect transition from NON_WORKING to any working mode
                if (last_work_mode == WorkMode.NON_WORKING and 
                    current_work_mode in [WorkMode.REGULAR, WorkMode.EXTENDED]):
                    
                    transition_detected = True
                    should_process_queue = True
                    
                    logger.info(
                        f"Work mode transition detected: {last_work_mode.value} → {current_work_mode.value}"
                    )
                
                # Log other transitions for monitoring
                elif last_work_mode != current_work_mode:
                    transition_detected = True
                    logger.info(
                        f"Work mode transition (no queue processing): {last_work_mode.value} → {current_work_mode.value}"
                    )
            
            # Update stored work mode in Redis
            redis_client.set(LAST_WORK_MODE_KEY, current_work_mode.value, ex=86400)  # Expire in 24 hours
            
            # Trigger queue processing if needed
            if should_process_queue:
                logger.info("Triggering immediate queue processing due to work mode transition")
                
                # Import and trigger the existing queue processing task
                from celery_app.ticket_notification_tasks import process_pending_tickets_task
                
                # Schedule immediate execution
                task_result = process_pending_tickets_task.apply_async(
                    queue="ticket_notifications"
                )
                
                logger.info(
                    f"Queue processing task scheduled: task_id={task_result.id}"
                )
                
                return {
                    "status": "transition_detected",
                    "previous_mode": last_work_mode.value if last_work_mode else None,
                    "current_mode": current_work_mode.value,
                    "queue_processing_triggered": True,
                    "queue_task_id": task_result.id,
                    "transition_time": current_time.isoformat()
                }
            
            elif transition_detected:
                return {
                    "status": "transition_detected",
                    "previous_mode": last_work_mode.value if last_work_mode else None,
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
    
    except Exception as e:
        logger.error(
            f"Error in work mode transition check: {e}",
            exc_info=True
        )
        
        # Retry with exponential backoff
        try:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for work mode transition check")
            return {
                "status": "error",
                "message": "Max retries exceeded",
                "error": str(e)
            }


@app.task(
    bind=True,
    base=AsyncTask,
    name="celery_app.work_mode_monitor_tasks.initialize_work_mode_monitor",
    max_retries=1,
    queue="work_mode_monitor"
)
async def initialize_work_mode_monitor(self) -> dict[str, Any]:
    """
    Initialize work mode monitor by setting the current work mode.
    
    This task should be run once when the system starts to establish
    the baseline work mode for transition detection.
    
    Returns:
        dict: Initialization status and current work mode
    """
    logger.info("Initializing work mode monitor")
    
    try:
        async with AsyncSessionLocal() as session:
            current_work_mode = await get_current_work_mode(session)
            
            # Store in Redis
            redis_client.set(LAST_WORK_MODE_KEY, current_work_mode.value, ex=86400)  # Expire in 24 hours
            
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
    
    except Exception as e:
        logger.error(
            f"Error initializing work mode monitor: {e}",
            exc_info=True
        )
        
        return {
            "status": "error",
            "message": "Failed to initialize work mode monitor",
            "error": str(e)
        }


# Utility function to manually trigger queue processing
@app.task(
    bind=True,
    base=AsyncTask,
    name="celery_app.work_mode_monitor_tasks.trigger_queue_processing",
    max_retries=1,
    queue="work_mode_monitor"
)
async def trigger_queue_processing(self, reason: str = "manual") -> dict[str, Any]:
    """
    Manually trigger queue processing.
    
    This can be used for testing or manual intervention.
    
    Args:
        reason: Reason for triggering (for logging)
    
    Returns:
        dict: Trigger status and task information
    """
    logger.info(f"Manually triggering queue processing: reason={reason}")
    
    try:
        from celery_app.ticket_notification_tasks import process_pending_tickets_task
        
        # Schedule immediate execution
        task_result = process_pending_tickets_task.apply_async(
            queue="ticket_notifications"
        )
        
        current_time = datetime.now(MOSCOW_TZ)
        
        logger.info(
            f"Queue processing manually triggered: task_id={task_result.id}, reason={reason}"
        )
        
        return {
            "status": "triggered",
            "reason": reason,
            "queue_task_id": task_result.id,
            "trigger_time": current_time.isoformat()
        }
    
    except Exception as e:
        logger.error(
            f"Error manually triggering queue processing: {e}",
            exc_info=True
        )
        
        return {
            "status": "error",
            "message": "Failed to trigger queue processing",
            "error": str(e),
            "reason": reason
        }