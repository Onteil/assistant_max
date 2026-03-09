"""Check Celery task result in Redis."""
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

# Task IDs from ticket #36
reminder_task_id = "4aa19b95-7d5b-4562-aab7-c316b1161ea7"
escalation_task_id = "f1203d5b-c069-4ea3-adb8-a7a3f796b5e9"

print("=" * 60)
print("Проверка результатов задач для тикета #36")
print("=" * 60)

# Check reminder task
reminder_key = f"celery-task-meta-{reminder_task_id}"
if r.exists(reminder_key):
    result = r.get(reminder_key)
    data = json.loads(result)
    print(f"\n✅ Reminder Task ({reminder_task_id}):")
    print(f"   Status: {data.get('status')}")
    print(f"   Result: {data.get('result')}")
    if data.get('traceback'):
        print(f"   Traceback: {data.get('traceback')[:500]}...")
else:
    print(f"\n❌ Reminder Task не найдена в Redis")

# Check escalation task
escalation_key = f"celery-task-meta-{escalation_task_id}"
if r.exists(escalation_key):
    result = r.get(escalation_key)
    data = json.loads(result)
    print(f"\n✅ Escalation Task ({escalation_task_id}):")
    print(f"   Status: {data.get('status')}")
    print(f"   Result: {data.get('result')}")
    if data.get('traceback'):
        print(f"   Traceback: {data.get('traceback')[:500]}...")
else:
    print(f"\n❌ Escalation Task не найдена в Redis")

print("\n" + "=" * 60)
