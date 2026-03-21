"""
Проверка запланированных задач эскалации в Redis.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import redis
import json
from constants import REDIS, CELERY_REDIS_DB_NUMBER

def check_scheduled_tasks():
    """Проверить запланированные задачи в Redis."""
    print("─" * 5)
    print("Проверка задач эскалации в Redis")
    print("─" * 5)
    print()
    
    try:
        # Подключиться к Redis
        redis_url = f"{REDIS}/{CELERY_REDIS_DB_NUMBER}"
        r = redis.from_url(redis_url, decode_responses=False)
        
        print(f"Подключение к Redis: {redis_url}")
        r.ping()
        print("✅ Подключение успешно")
        print()
        
        # Проверить ключи Celery
        celery_keys = r.keys("celery*")
        print(f"📋 Найдено ключей Celery: {len(celery_keys)}")
        print()
        
        # Проверить задачи с ETA (запланированные)
        eta_keys = [k for k in celery_keys if b'task-meta' in k]
        
        if eta_keys:
            print(f"📝 Задачи с метаданными: {len(eta_keys)}")
            for key in eta_keys[:10]:
                try:
                    data = r.get(key)
                    if data:
                        task_data = json.loads(data)
                        task_name = task_data.get('task', 'Unknown')
                        status = task_data.get('status', 'Unknown')
                        print(f"  - {key.decode()[:50]}... : {task_name} ({status})")
                except:
                    pass
        
        # Проверить unacked (необработанные задачи)
        unacked_keys = r.keys("unacked*")
        if unacked_keys:
            print(f"\n⏰ Необработанных задач: {len(unacked_keys)}")
        
        # Проверить очереди
        queues = ['escalations', 'nps_surveys', 'renewal_reminders', 'celery']
        print(f"\n📊 Очереди:")
        for queue in queues:
            length = r.llen(queue)
            if length > 0:
                print(f"  - {queue}: {length} задач")
        
        # Проверить задачи в базе данных
        print(f"\n" + "─" * 5)
        print("Проверка задач в БД")
        print("─" * 5)
        print()
        
        import asyncio
        from constants import get_session
        from sqlalchemy import select, and_
        from database.models import Ticket, TicketStatus
        from datetime import datetime, timedelta
        
        async def check_db():
            async with get_session() as session:
                # Найти тикеты со статусом NEW и запланированными задачами
                stmt = select(Ticket).where(
                    and_(
                        Ticket.ticket_status == TicketStatus.NEW,
                        Ticket.escalation_task_reminder_id.isnot(None)
                    )
                ).order_by(Ticket.created_at.desc()).limit(10)
                
                result = await session.execute(stmt)
                tickets = result.scalars().all()
                
                if tickets:
                    print(f"✅ Найдено NEW тикетов с задачами: {len(tickets)}")
                    print()
                    
                    now = datetime.utcnow()
                    
                    for ticket in tickets:
                        age_minutes = (now - ticket.created_at).total_seconds() / 60
                        print(f"Тикет #{ticket.id}:")
                        print(f"  Создан: {ticket.created_at} ({age_minutes:.1f} мин назад)")
                        print(f"  Статус: {ticket.ticket_status.value}")
                        print(f"  Reminder Task: {ticket.escalation_task_reminder_id}")
                        print(f"  Escalation Task: {ticket.escalation_task_escalation_id}")
                        
                        if age_minutes > 10:
                            print(f"  ⚠️  Прошло больше 10 минут - напоминание должно было прийти!")
                        if age_minutes > 20:
                            print(f"  ⚠️  Прошло больше 20 минут - эскалация должна была произойти!")
                        print()
                else:
                    print("⚠️  Нет NEW тикетов с запланированными задачами")
        
        asyncio.run(check_db())
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_scheduled_tasks()
