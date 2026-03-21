"""
Скрипт для проверки статуса Celery и зарегистрированных задач.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from celery_app.celery_config import app as celery_app

def check_celery_status():
    """Проверить статус Celery."""
    print("─" * 5)
    print("Проверка статуса Celery")
    print("─" * 5)
    print()
    
    try:
        # Проверить подключение к брокеру
        inspector = celery_app.control.inspect()
        
        # Получить активные воркеры
        active_workers = inspector.active()
        
        if not active_workers:
            print("❌ Celery worker не запущен!")
            print()
            print("Запустите worker:")
            print("  python start_celery_worker.py")
            print()
            return False
        
        print(f"✅ Найдено воркеров: {len(active_workers)}")
        print()
        
        # Показать зарегистрированные задачи
        registered = inspector.registered()
        
        if registered:
            print("📋 Зарегистрированные задачи:")
            for worker, tasks in registered.items():
                print(f"\n  Worker: {worker}")
                for task in sorted(tasks):
                    # Показать только наши задачи
                    if task.startswith("celery_app."):
                        status = "✅"
                        print(f"    {status} {task}")
        
        print()
        print("─" * 5)
        print("Проверка очередей")
        print("─" * 5)
        print()
        
        # Проверить активные задачи
        active_tasks = inspector.active()
        if active_tasks:
            total_active = sum(len(tasks) for tasks in active_tasks.values())
            print(f"🔄 Активных задач: {total_active}")
        else:
            print("✅ Нет активных задач")
        
        # Проверить запланированные задачи
        scheduled_tasks = inspector.scheduled()
        if scheduled_tasks:
            total_scheduled = sum(len(tasks) for tasks in scheduled_tasks.values())
            print(f"⏰ Запланированных задач: {total_scheduled}")
            
            # Показать первые 5
            count = 0
            for worker, tasks in scheduled_tasks.items():
                for task in tasks:
                    if count < 5:
                        task_name = task.get('name', 'Unknown')
                        eta = task.get('eta', 'Unknown')
                        print(f"  - {task_name} (ETA: {eta})")
                        count += 1
            
            if total_scheduled > 5:
                print(f"  ... и еще {total_scheduled - 5}")
        else:
            print("✅ Нет запланированных задач")
        
        print()
        print("─" * 5)
        print("Проверка эскалаций")
        print("─" * 5)
        print()
        
        # Проверить наличие задач эскалации
        escalation_tasks = [
            "celery_app.escalation_tasks.check_ticket_reminder",
            "celery_app.escalation_tasks.check_ticket_escalation"
        ]
        
        all_tasks = []
        if registered:
            for tasks in registered.values():
                all_tasks.extend(tasks)
        
        for task_name in escalation_tasks:
            if task_name in all_tasks:
                print(f"✅ {task_name}")
            else:
                print(f"❌ {task_name} - НЕ ЗАРЕГИСТРИРОВАНА")
        
        print()
        print("✅ Celery работает корректно")
        return True
    
    except Exception as e:
        print(f"❌ Ошибка подключения к Celery: {e}")
        print()
        print("Возможные причины:")
        print("  1. Redis не запущен")
        print("  2. Celery worker не запущен")
        print("  3. Неправильная конфигурация в .env")
        print()
        return False

if __name__ == "__main__":
    check_celery_status()
