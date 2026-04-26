path = "tests/test_round_robin_and_escalation.py"
with open(path, encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    '"celery_app.escalation_tasks.get_setting"',
    '"services.settings_service.get_setting"',
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done. Occurrences:", content.count('"services.settings_service.get_setting"'))
