"""Check task result for ticket #37."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import redis
import json

# Connect to Redis
r = redis.Redis(
    host='localhost',
    port=6999,
    password='12345678',
    db=0,
    decode_responses=True
)

# Task IDs from ticket #37
reminder_task_id = "32ccc9a0-5bd2-4109-9d1a-88111d8058d3"
escalation_task_id = "8e31ec37-3c94-4c42-a2fb-81852061d521"

print("=" * 60)
print("Проверка результатов задач для тикета #37")
print("=" * 60)

# Check reminder task
reminder_key = f"celery-task-meta-{reminder_task_id}"
if r.exists(reminder_key):
    result = r.get(reminder_key)
    data = json.loads(result)
    print(f"\n✅ Reminder Task ({reminder_task_id}):")
    print(f"   Status: {data.get('status')}")
    if data.get('status') == 'SUCCESS':
        print(f"   Result: {json.dumps(data.get('result'), indent=2, ensure_ascii=False)}")
    elif data.get('status') in ('FAILURE', 'RETRY'):
        print(f"   Error: {data.get('result', {}).get('exc_message')}")
        if data.get('traceback'):
            print(f"   Traceback (first 300 chars):")
            print(f"   {data.get('traceback')[:300]}")
else:
    print(f"\n⏰ Reminder Task еще не выполнена (ожидается через 10 минут)")

# Check escalation task
escalation_key = f"celery-task-meta-{escalation_task_id}"
if r.exists(escalation_key):
    result = r.get(escalation_key)
    data = json.loads(result)
    print(f"\n✅ Escalation Task ({escalation_task_id}):")
    print(f"   Status: {data.get('status')}")
    if data.get('status') == 'SUCCESS':
        print(f"   Result: {json.dumps(data.get('result'), indent=2, ensure_ascii=False)}")
    elif data.get('status') in ('FAILURE', 'RETRY'):
        print(f"   Error: {data.get('result', {}).get('exc_message')}")
else:
    print(f"\n⏰ Escalation Task еще не выполнена (ожидается через 20 минут)")

print("\n" + "=" * 60)
