"""
Отладочный скрипт для проверки выполнения Celery задачи NPS.
Показывает детальные логи выполнения.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from celery_app.nps_tasks import _send_survey_async


async def debug_nps_task():
    """Отладка NPS задачи с детальными логами"""
    
    print("=" * 60)
    print("ОТЛАДКА NPS ЗАДАЧИ")
    print("=" * 60)
    
    # Параметры
    user_id = 3  # Используем реального пользователя из БД
    survey_type = "loyalty"
    trigger_event_id = 1
    event_date = "2026-02-22T10:00:00"
    
    print(f"\nПараметры:")
    print(f"  user_id: {user_id}")
    print(f"  survey_type: {survey_type}")
    print(f"  trigger_event_id: {trigger_event_id}")
    print(f"  event_date: {event_date}")
    print()
    
    # Проверка пользователя в БД
    print("Шаг 1: Проверка пользователя в БД...")
    from sqlalchemy import select
    from constants import AsyncSessionLocal
    from database.models import User
    
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"  ❌ Пользователь с ID {user_id} не найден!")
            print("\n  Доступные пользователи:")
            stmt = select(User).limit(5)
            result = await session.execute(stmt)
            users = result.scalars().all()
            for u in users:
                print(f"    - ID: {u.id}, TG: {u.tg_user_id}, MAX: {u.max_user_id}")
            return
        
        print(f"  ✅ Пользователь найден:")
        print(f"    - Имя: {user.first_name} {user.last_name or ''}")
        print(f"    - Telegram ID: {user.tg_user_id or 'не указан'}")
        print(f"    - MAX ID: {user.max_user_id or 'не указан'}")
    
    # Определение мессенджера
    print("\nШаг 2: Определение мессенджера...")
    if user.tg_user_id:
        print(f"  ✅ Будет использован Telegram (ID: {user.tg_user_id})")
        messenger = "telegram"
    elif user.max_user_id:
        print(f"  ✅ Будет использован MAX (ID: {user.max_user_id})")
        messenger = "max"
    else:
        print("  ❌ У пользователя нет ID мессенджера!")
        return
    
    # Проверка обработчика
    print(f"\nШаг 3: Проверка обработчика для {messenger}...")
    try:
        if messenger == "telegram":
            from bots.tg_bot.handlers.client.nps_handler import send_nps_survey
            print("  ✅ Обработчик Telegram найден")
        else:
            from bots.max_bot.handlers.client.nps_handler import send_nps_survey
            print("  ✅ Обработчик MAX найден")
    except ImportError as e:
        print(f"  ❌ Обработчик не найден: {e}")
        print(f"  ⚠️  Задача вернет статус 'not_implemented'")
    
    # Выполнение задачи
    print("\nШаг 4: Выполнение задачи...")
    try:
        result = await _send_survey_async(
            user_id=user_id,
            survey_type=survey_type,
            trigger_event_id=trigger_event_id,
            event_date=event_date
        )
        
        print("\n" + "=" * 60)
        print("РЕЗУЛЬТАТ")
        print("=" * 60)
        print(f"Статус: {result.get('status')}")
        print(f"Мессенджер: {result.get('messenger', 'N/A')}")
        print(f"Messenger ID: {result.get('messenger_id', 'N/A')}")
        print(f"Причина: {result.get('reason', 'N/A')}")
        print(f"Ошибка: {result.get('error', 'N/A')}")
        print("=" * 60)
        
        return result
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    asyncio.run(debug_nps_task())
