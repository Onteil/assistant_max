"""
Скрипт для проверки пользователей и их мессенджеров в БД.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from sqlalchemy import select
from constants import AsyncSessionLocal
from database.models import User


async def check_users():
    """Проверка пользователей в БД"""
    
    async with AsyncSessionLocal() as session:
        # Получаем всех пользователей
        stmt = select(User).limit(10)
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        if not users:
            print("❌ Пользователи не найдены в БД")
            return
        
        print(f"Найдено пользователей: {len(users)}\n")
        
        for user in users:
            print(f"User ID: {user.id}")
            print(f"  Имя: {user.first_name} {user.last_name or ''}")
            print(f"  Telegram ID: {user.tg_user_id or 'не указан'}")
            print(f"  MAX ID: {user.max_user_id or 'не указан'}")
            print(f"  Email: {user.email or 'не указан'}")
            print()


if __name__ == "__main__":
    asyncio.run(check_users())
