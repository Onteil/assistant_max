"""
Celery tasks definitions.
Все задачи Celery должны быть определены в этом файле.
"""

import asyncio

from celery import shared_task
from celery.utils.log import get_task_logger

from celery_app.jobs import create_posts_task, run_iec_cy_parser, save_results_task

# Используем специальный логгер для Celery задач
logger = get_task_logger(__name__)


@shared_task(name="celery_app.tasks.save_clipping_results", bind=True)
def save_clipping_results_task(self, results: dict):
    """
    Сохраняет результаты клиппинга в базу данных.

    Args:
        results: Словарь с результатами клиппинга

    Returns:
        Результат выполнения задачи
    """
    logger.info(f"Starting save_clipping_results_task with task_id: {self.request.id}")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        result = loop.run_until_complete(save_results_task(results))

        logger.info(f"Task {self.request.id} completed successfully")
        return result

    except Exception as exc:
        logger.error(f"Task {self.request.id} failed: {exc}")
        raise
    finally:
        loop.close()


@shared_task(name="celery_app.tasks.create_posts_from_clips", bind=True)
def create_posts_from_clips_task(self, selected_clip_ids: list[int], chat_id: int):
    """
    Создает посты из выбранных клипов.

    Args:
        selected_clip_ids: Список ID выбранных клипов
        chat_id: ID чата для отправки постов
    """
    logger.info(f"Starting create_posts_from_clips_task with task_id: {self.request.id}")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.run_until_complete(create_posts_task(selected_clip_ids, chat_id))

        logger.info(f"Task {self.request.id} completed successfully")

    except Exception as exc:
        logger.error(f"Task {self.request.id} failed: {exc}")
        raise
    finally:
        loop.close()


@shared_task(name="celery_app.tasks.run_iec_cy_parser_task", bind=True)
def run_iec_cy_parser_task(self):
    """
    Периодическая задача для запуска парсера IEC CY.
    Выполняется каждый час согласно расписанию в celery_tasks.py.
    """
    logger.info(f"Starting run_iec_cy_parser_task with task_id: {self.request.id}")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.run_until_complete(run_iec_cy_parser())

        logger.info(f"Task {self.request.id} completed successfully")

    except Exception as exc:
        logger.error(f"Task {self.request.id} failed: {exc}")
        raise
    finally:
        loop.close()
