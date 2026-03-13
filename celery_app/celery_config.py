"""
Celery application configuration.
Этот файл содержит основную конфигурацию Celery приложения.
"""

import sys
import os

# CRITICAL: Add project root to Python path BEFORE any other imports
# This must be the FIRST thing that happens when Celery loads
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from celery import Celery
from celery.schedules import crontab

from constants import CELERY_REDIS_DB_NUMBER, REDIS

# Создаем экземпляр Celery приложения
app = Celery(
    "celery_app",
    broker=f"{REDIS}/{CELERY_REDIS_DB_NUMBER}",
    backend=f"{REDIS}/{CELERY_REDIS_DB_NUMBER}",
    include=[
        "celery_app.escalation_tasks",
        "celery_app.nps_tasks",
        "celery_app.renewal_tasks",
        "celery_app.broadcast_tasks",
        "celery_app.ticket_notification_tasks",
        "celery_app.work_mode_monitor_tasks"
    ],  # Автоматически импортирует escalation_tasks.py, nps_tasks.py, renewal_tasks.py, broadcast_tasks.py, ticket_notification_tasks.py и work_mode_monitor_tasks.py
)

# Конфигурация Celery
app.conf.update(
    # Настройки брокера
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    # Настройки времени
    timezone="Europe/Moscow",
    enable_utc=False,
    # Настройки задач
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 минут
    task_soft_time_limit=25 * 60,  # 25 минут
    # Настройки результатов
    result_expires=3600,  # Результаты хранятся 1 час
    result_backend_transport_options={"master_name": "mymaster"},
)

# Настройка периодических задач (Celery Beat)
app.conf.beat_schedule = {
    "cleanup-old-nps-surveys-daily": {
        "task": "celery_app.nps_tasks.cleanup_old_surveys",
        "schedule": crontab(minute=0, hour=3),  # Run daily at 3:00 AM
        "options": {"queue": "nps_surveys"},
    },
    "check-upcoming-expirations": {
        "task": "celery_app.renewal_tasks.check_upcoming_expirations",
        "schedule": crontab(minute=0, hour=9),  # Run daily at 9:00 AM Moscow time
        "options": {"queue": "renewal_reminders"},
    },
    "process-pending-tickets": {
        "task": "celery_app.ticket_notification_tasks.process_pending_tickets",
        "schedule": crontab(minute=0, hour=9),  # Run daily at 9:00 AM Moscow time (start of work day)
        "options": {"queue": "ticket_notifications"},
    },
    "check-work-mode-transition": {
        "task": "celery_app.work_mode_monitor_tasks.check_work_mode_transition",
        "schedule": crontab(minute="*/5"),  # Run every 5 minutes to detect work mode changes
        "options": {"queue": "work_mode_monitor"},
    },
}
