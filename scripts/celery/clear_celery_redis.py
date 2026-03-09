"""
Скрипт для очистки старых Celery данных из Redis.
Удаляет только beat schedule, не трогая другие данные.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import redis
from constants import REDIS, CELERY_REDIS_DB_NUMBER

def clear_celery_beat_schedule():
    """Очистить beat schedule из Redis."""
    try:
        # Подключиться к Redis
        redis_url = f"{REDIS}/{CELERY_REDIS_DB_NUMBER}"
        r = redis.from_url(redis_url, decode_responses=True)
        
        print(f"Подключение к Redis: {redis_url}")
        
        # Проверить подключение
        r.ping()
        print("✅ Подключение к Redis успешно")
        
        # Удалить beat schedule
        deleted = r.delete("celery-beat-schedule")
        if deleted:
            print(f"✅ Удален celery-beat-schedule")
        else:
            print("⚠️  celery-beat-schedule не найден (возможно, уже удален)")
        
        # Показать все ключи Celery
        celery_keys = r.keys("celery*")
        if celery_keys:
            print(f"\n📋 Найдено ключей Celery: {len(celery_keys)}")
            for key in celery_keys[:10]:  # Показать первые 10
                print(f"   - {key}")
            if len(celery_keys) > 10:
                print(f"   ... и еще {len(celery_keys) - 10}")
        else:
            print("\n✅ Ключей Celery не найдено")
        
        print("\n✅ Очистка завершена успешно")
        print("\nТеперь можно запустить Celery:")
        print("  celery -A celery_app.celery_config worker -l info --pool=solo -Q nps_surveys,renewal_reminders,escalations")
        
    except redis.ConnectionError as e:
        print(f"❌ Ошибка подключения к Redis: {e}")
        print("Убедитесь, что Redis запущен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Очистка Celery Beat Schedule из Redis")
    print("=" * 60)
    print()
    
    clear_celery_beat_schedule()
