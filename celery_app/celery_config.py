"""
Celery application configuration.
Этот файл содержит основную конфигурацию Celery приложения.
"""

from celery import Celery
from celery.schedules import crontab

from constants import CELERY_REDIS_DB_NUMBER, REDIS

# Создаем экземпляр Celery приложения
app = Celery(
    "celery_app",
    broker=f"{REDIS}/{CELERY_REDIS_DB_NUMBER}",
    backend=f"{REDIS}/{CELERY_REDIS_DB_NUMBER}",
    include=["celery_app.tasks"],  # Автоматически импортирует tasks.py
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
    "run-iec-cy-parser-every-hour": {
        "task": "celery_app.tasks.run_iec_cy_parser_task",
        "schedule": crontab(minute=0, hour="*"),
    },
}
