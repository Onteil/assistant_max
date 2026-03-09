"""
Проверка конкретного пользователя с tg_user_id = 7450451025
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from sqlalchemy import select
from constants import AsyncSessionLocal
from database.models import User


async def check_user():
    """Проверка пользователя с tg_user_id = 7450451025"""
    
    async with AsyncSessionLocal() as session:
        # Ищем пользователя по tg_user_id
        stmt = select(User).where(User.tg_user_id == 7450451025)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print("❌ Пользователь с tg_user_id=7450451025 не найден!")
            return
        
        print("✅ Пользователь найден:")
        print(f"  Внутренний ID: {user.id}")
        print(f"  Имя: {user.first_name} {user.last_name or ''}")
        print(f"  Telegram ID: {user.tg_user_id}")
        print(f"  MAX ID: {user.max_user_id or 'не указан'}")
        print(f"  Email: {user.email or 'не указан'}")
        print(f"  Последний NPS: {user.last_nps_sent_at or 'никогда'}")
        print()
        
        # Теперь проверим, что будет при отправке опроса
        print("Тестирование отправки NPS опроса...")
        from celery_app.nps_tasks import _send_survey_async
        
        result = await _send_survey_async(
            user_id=user.id,  # Используем внутренний ID
            survey_type="loyalty",
            trigger_event_id=1,
            event_date="2026-02-22T10:00:00"
        )
        
        print(f"\nРезультат:")
        print(f"  Статус: {result.get('status')}")
        print(f"  Мессенджер: {result.get('messenger', 'N/A')}")
        print(f"  Messenger ID: {result.get('messenger_id', 'N/A')}")
        print(f"  Причина: {result.get('reason', 'N/A')}")
        print(f"  Ошибка: {result.get('error', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(check_user())
