# Celery Configuration

Структура файлов для работы с Celery в проекте.

## Структура папки `celery_app/`

```
celery_app/
├── __init__.py              # Экспорт app для удобного импорта
├── celery_config.py         # Конфигурация Celery приложения
├── nps_tasks.py             # Задачи для NPS опросов
├── renewal_tasks.py         # Задачи для напоминаний о подписке
├── escalation_tasks.py      # Задачи для эскалаций
├── broadcast_tasks.py       # Задачи для рассылок
├── ticket_notification_tasks.py  # Задачи для уведомлений о заявках
└── README.md                # Документация
```

### 1. `celery_config.py` - Конфигурация Celery
Основной файл конфигурации Celery приложения. Содержит:
- Создание экземпляра Celery
- Настройки брокера (Redis)
- Настройки таймзоны
- Конфигурацию периодических задач (Beat Schedule)
- Импорт модулей с задачами

### 2. `nps_tasks.py` - NPS опросы
Содержит задачи для системы NPS опросов:
- `send_nps_survey_task` - Отправка опроса пользователю
- `cleanup_old_surveys_task` - Очистка старых опросов (периодическая)

### 3. `renewal_tasks.py` - Напоминания о подписке
Содержит задачи для системы напоминаний о продлении:
- `check_upcoming_expirations_task` - Проверка истечений (периодическая)
- `send_renewal_reminder_task` - Отправка напоминания пользователю

### 4. `escalation_tasks.py` - Эскалации
Содержит задачи для системы эскалаций:
- `check_escalations_task` - Проверка просроченных тикетов
- `send_escalation_notification_task` - Отправка уведомления об эскалации

### 5. `broadcast_tasks.py` - Рассылки
Содержит задачи для системы массовых рассылок:
- `send_broadcast_task` - Отправка рассылки пользователям

### 6. `ticket_notification_tasks.py` - Уведомления о заявках
Содержит задачи для обработки заявок на счет и продление, созданных в нерабочее время:
- `process_pending_tickets_task` - Проверка и отправка уведомлений о заявках INVOICE и RENEWAL (периодическая)

**Примечание:** Заявки техподдержки (TECHNICAL_SUPPORT) не обрабатываются этой задачей, так как:
- В основное рабочее время уведомления отправляются сразу всем сотрудникам ТП
- В продленное время уведомление отправляется дежурному инженеру сразу
- В нерабочее время заявки просто ждут без уведомлений (согласно ТЗ раздел 7.1)

## Запуск Celery

### Локальный запуск

#### Запуск воркера
```bash
celery -A celery_app.celery_config worker --loglevel=info
```

#### Запуск Beat (планировщик периодических задач)
```bash
celery -A celery_app.celery_config beat --loglevel=info
```

#### Запуск воркера и Beat вместе
```bash
celery -A celery_app.celery_config worker --beat --loglevel=info
```

#### Для Windows
```bash
celery -A celery_app.celery_config worker --pool=solo --loglevel=info
```

### Запуск в Docker

#### Dockerfile для Celery Worker
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Запуск воркера
CMD ["celery", "-A", "celery_app.celery_config", "worker", "--loglevel=info"]
```

#### Dockerfile для Celery Beat
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Запуск планировщика
CMD ["celery", "-A", "celery_app.celery_config", "beat", "--loglevel=info"]
```

#### docker-compose.yml
```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  celery_worker:
    build:
      context: .
      dockerfile: Dockerfile.celery_worker
    depends_on:
      - redis
    environment:
      - REDIS=redis://redis:6379
      - CELERY_REDIS_DB_NUMBER=1
    volumes:
      - .:/app
    restart: unless-stopped

  celery_beat:
    build:
      context: .
      dockerfile: Dockerfile.celery_beat
    depends_on:
      - redis
    environment:
      - REDIS=redis://redis:6379
      - CELERY_REDIS_DB_NUMBER=1
    volumes:
      - .:/app
    restart: unless-stopped

  flower:
    image: mher/flower
    command: celery --broker=redis://redis:6379/1 flower --port=5555
    ports:
      - "5555:5555"
    depends_on:
      - redis
      - celery_worker
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/1

volumes:
  redis_data:
```

## Использование задач

### Вызов задачи асинхронно

#### NPS опрос
```python
from celery_app.nps_tasks import send_nps_survey_task
from datetime import datetime

# Отправить опрос немедленно
result = send_nps_survey_task.delay(
    user_id=1,
    survey_type='loyalty',
    trigger_event_id=12345,
    event_date=datetime.utcnow().isoformat()
)

# Или запланировать на определенное время
from datetime import timedelta
result = send_nps_survey_task.apply_async(
    args=[1, 'loyalty', 12345, datetime.utcnow().isoformat()],
    eta=datetime.utcnow() + timedelta(days=10)  # Через 10 дней
)
```

#### Напоминание о подписке
```python
from celery_app.renewal_tasks import send_renewal_reminder_task

# Отправить напоминание
result = send_renewal_reminder_task.delay(notification_event_id=1)
```

### Получение результата
```python
# Проверить статус
if result.ready():
    print(result.result)

# Дождаться результата (блокирующий вызов)
result_value = result.get(timeout=10)
```

## Мониторинг

### Flower - веб-интерфейс для мониторинга
```bash
pip install flower
celery -A celery_app.celery_config flower
```
Откройте http://localhost:5555 в браузере.

### Проверка активных задач
```bash
celery -A celery_app.celery_config inspect active
```

### Проверка зарегистрированных задач
```bash
celery -A celery_app.celery_config inspect registered
```

### Проверка статистики
```bash
celery -A celery_app.celery_config inspect stats
```

## Best Practices

1. **Разделение ответственности**:
   - `celery_config.py` - только конфигурация
   - `tasks.py` - только определения задач
   - `jobs.py` - бизнес-логика

2. **Логирование**: Используйте `get_task_logger(__name__)` для логирования в задачах

3. **Обработка ошибок**: Все задачи обернуты в try-except для корректной обработки ошибок

4. **Таймауты**: Настроены `task_time_limit` и `task_soft_time_limit` для предотвращения зависших задач

5. **Bind=True**: Позволяет получить доступ к контексту задачи через `self.request`

6. **Docker**: Используйте отдельные контейнеры для worker и beat

## Конфигурация

Основные параметры в `celery_config.py`:
- `broker` - URL Redis для очереди сообщений
- `backend` - URL Redis для хранения результатов
- `timezone` - Часовой пояс (Europe/Moscow)
- `task_time_limit` - Максимальное время выполнения задачи (30 мин)
- `result_expires` - Время хранения результатов (1 час)

## Периодические задачи

Настроены в `beat_schedule` в `celery_config.py`:

### Текущие периодические задачи:

1. **cleanup-old-nps-surveys-daily**
   - Задача: `celery_app.nps_tasks.cleanup_old_surveys`
   - Расписание: Ежедневно в 3:00
   - Очередь: `nps_surveys`
   - Описание: Удаляет опросы старше 90 дней

2. **check-upcoming-expirations**
   - Задача: `celery_app.renewal_tasks.check_upcoming_expirations`
   - Расписание: Ежедневно в 9:00
   - Очередь: `renewal_reminders`
   - Описание: Проверяет подписки, истекающие через 30 и 7 дней

3. **process-pending-tickets**
   - Задача: `celery_app.ticket_notification_tasks.process_pending_tickets`
   - Расписание: Ежедневно в 9:00 (начало рабочего дня)
   - Очередь: `ticket_notifications`
   - Описание: Обрабатывает заявки на счет (INVOICE) и продление (RENEWAL), созданные в нерабочее/продленное время, и отправляет уведомления менеджерам. Заявки техподдержки не обрабатываются, так как они либо отправляются сразу (в рабочее/продленное время), либо просто ждут (в нерабочее время)

### Добавление новой периодической задачи

Добавьте запись в `beat_schedule` в `celery_config.py`:

```python
app.conf.beat_schedule = {
    "my-periodic-task": {
        "task": "celery_app.my_tasks.my_task_name",
        "schedule": crontab(minute=0, hour=12),  # Ежедневно в 12:00
        "options": {"queue": "my_queue"},
    },
}
```
