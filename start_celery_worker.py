"""
Скрипт для запуска Celery worker на Windows.
Использует правильные параметры для Windows (--pool=solo).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import subprocess
import sys
import os

def start_worker():
    """Запустить Celery worker."""
    # Добавить project root в PYTHONPATH
    project_root = os.path.abspath(os.getcwd())
    os.environ['PYTHONPATH'] = project_root
    
    print("─" * 5)
    print("Запуск Celery Worker")
    print("─" * 5)
    print()
    print("Очереди: nps_surveys, renewal_reminders, escalations, broadcasts, ticket_notifications, work_mode_monitor")
    print("Pool: solo (для Windows)")
    print(f"Python: {sys.executable}")
    print(f"PYTHONPATH: {project_root}")
    print()
    
    # Проверить, что мы в корневой директории проекта
    if not os.path.exists("celery_app"):
        print("❌ Ошибка: celery_app не найден")
        print("   Запустите скрипт из корневой директории проекта")
        sys.exit(1)
    
    print(f"Рабочая директория: {os.getcwd()}")
    print()
    print("Для остановки нажмите Ctrl+C")
    print("─" * 5)
    print()
    
    try:
        # Запустить Celery worker через текущий Python (из venv)
        subprocess.run([
            sys.executable,  # Использовать Python из venv
            "-m", "celery",
            "-A", "celery_app.celery_config",
            "worker",
            "-l", "info",
            "--pool=solo",  # Для Windows
            "-Q", "escalations,nps_surveys,renewal_reminders,broadcasts,ticket_notifications,work_mode_monitor"
        ])
    except KeyboardInterrupt:
        print("\n\n✅ Worker остановлен")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_worker()
