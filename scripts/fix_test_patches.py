"""Fix incorrect patch paths in test_round_robin_and_escalation.py"""
import re

path = "tests/test_round_robin_and_escalation.py"
with open(path, encoding="utf-8") as f:
    content = f.read()

# 1. get_current_work_mode is imported locally inside the async function:
#    from services.calendar_service import get_current_work_mode
#    So patch the source module.
content = content.replace(
    '"celery_app.escalation_tasks.get_current_work_mode"',
    '"services.calendar_service.get_current_work_mode"',
)

# 2. MAXBot is imported locally as: from maxapi import Bot as MAXBot
#    Patch the name in the module where it's used (local import means
#    we need to patch the original location).
content = content.replace(
    '"celery_app.escalation_tasks.MAXBot"',
    '"maxapi.Bot"',
)

# 3. schedule_technical_support_monitoring in ticket_notification_tasks
#    is imported as: from celery_app.escalation_tasks import schedule_technical_support_monitoring
#    Patch the definition location.
content = content.replace(
    '"celery_app.ticket_notification_tasks.schedule_technical_support_monitoring"',
    '"celery_app.escalation_tasks.schedule_technical_support_monitoring"',
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Replacements done.")
print("  get_current_work_mode occurrences:", content.count("services.calendar_service.get_current_work_mode"))
print("  maxapi.Bot occurrences:", content.count('"maxapi.Bot"'))
print("  schedule_technical_support_monitoring (escalation_tasks):", content.count('"celery_app.escalation_tasks.schedule_technical_support_monitoring"'))
