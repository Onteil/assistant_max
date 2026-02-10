# Celery Configuration

Структура файлов для работы с Celery в проекте.

## Структура папки `celery_app/`

```
celery_app/
├── __init__.py           # Экспорт app для удобного импорта
├── celery_config.py      # Конфигурация Celery приложения
├── tasks.py              # Определение всех задач
├── jobs.py               # Бизнес-логика задач
└── README.md             # Документация
```

### 1. `celery_config.py` - Конфигурация Celery
Основной файл конфигурации Celery приложения. Содержит:
- Создание экземпляра Celery
- Настройки брокера (Redis)
- Настройки таймзоны
- Конфигурацию периодических задач (Beat Schedule)

### 2. `tasks.py` - Определение задач
Содержит все Celery задачи с использованием декоратора `@shared_task`:
- `save_clipping_results_task` - Сохранение результатов клиппинга
- `create_posts_from_clips_task` - Создание постов из клипов
- `run_iec_cy_parser_task` - Периодический парсер (каждый час)

### 3. `jobs.py` - Бизнес-логика
Содержит асинхронную бизнес-логику, которая вызывается из задач:
- `save_results_task()` - Логика сохранения результатов
- `create_posts_task()` - Логика создания постов
- `run_iec_cy_parser()` - Логика парсера
- Обработчики инициализации и завершения воркера

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
```python
from celery_app.tasks import save_clipping_results_task

# Отправить задачу в очередь
result = save_clipping_results_task.delay(results_dict)

# Или с дополнительными параметрами
result = save_clipping_results_task.apply_async(
    args=[results_dict],
    countdown=10  # Выполнить через 10 секунд
)
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

Настроены в `beat_schedule`:
```python
'run-iec-cy-parser-every-hour': {
    'task': 'celery_app.tasks.run_iec_cy_parser_task',
    'schedule': crontab(minute=0, hour='*'),  # Каждый час
}
```

Для добавления новой периодической задачи добавьте запись в `beat_schedule` в `celery_config.py`.
