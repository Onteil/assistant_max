"""
Скрипт для запуска Celery beat (планировщик периодических задач).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import subprocess
import sys

def start_beat():
    """Запустить Celery beat."""
    print("─" * 5)
    print("Запуск Celery Beat (планировщик)")
    print("─" * 5)
    print()
    print("Периодические задачи:")
    print("  - cleanup-old-nps-surveys-daily (3:00)")
    print("  - check-upcoming-expirations (9:00)")
    print()
    print("Для остановки нажмите Ctrl+C")
    print("─" * 5)
    print()
    
    try:
        # Запустить Celery beat
        subprocess.run([
            "celery",
            "-A", "celery_app.celery_config",
            "beat",
            "-l", "info"
        ])
    except KeyboardInterrupt:
        print("\n\n✅ Beat остановлен")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_beat()
