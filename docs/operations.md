# Эксплуатация

## Подготовка сервера

Полная инструкция установки находится в [README](../README.md). Для production обязательны:

- Python 3.10.x и `venv`;
- PostgreSQL;
- Redis;
- FastAPI/Uvicorn;
- Celery worker;
- Celery beat;
- Nginx и systemd.

Готовые примеры:

- `deployment/systemd/i-tat-bot.service`;
- `deployment/systemd/i-tat-celery-worker.service`;
- `deployment/systemd/i-tat-celery-beat.service`;
- `deployment/nginx/i-tat-bot.conf`;
- `deployment/logrotate/i-tat-celery`;
- `deployment/journald/10-i-tat-log-limits.conf`.

Пути и пользователь в примерах соответствуют `/home/razrab/i-tat-bot` и пользователю `razrab`. На другом сервере их нужно заменить до копирования unit-файлов.

## Безопасные production-настройки

```dotenv
BOT_MODE=max
PROJECT_HOST=0.0.0.0
IS_LOCAL_BOT=False
DEBUG=False
LOG_LEVEL=info
USE_MOCK_ITAT_API=false
ENABLE_API_RETRY_DIAGNOSTICS=False
```

Секреты берутся из `.env`, который не хранится в Git. Единственный шаблон переменных — `.env.example`.

## Обновление кода

```bash
cd /home/razrab/i-tat-bot
git status --short
git fetch origin
git checkout main
git pull --ff-only origin main

source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python scripts/check_setup.py

sudo systemctl restart i-tat-bot i-tat-celery-worker i-tat-celery-beat
```

Перед `git pull` рабочее дерево должно быть чистым. Production remote должен указывать на GitHub. Для приватного репозитория серверу нужен deploy key или PAT с правом чтения.

## Проверка после обновления

```bash
git rev-parse --short HEAD
alembic current

sudo systemctl --no-pager --full status i-tat-bot
sudo systemctl --no-pager --full status i-tat-celery-worker
sudo systemctl --no-pager --full status i-tat-celery-beat

sudo journalctl -u i-tat-bot -n 100 --no-pager
sudo journalctl -u i-tat-celery-worker -n 100 --no-pager
sudo journalctl -u i-tat-celery-beat -n 100 --no-pager
sudo journalctl -p err --since "10 minutes ago" --no-pager

sudo nginx -t
curl -I http://127.0.0.1:8453/admin/
```

## Логи в реальном времени

```bash
sudo journalctl -u i-tat-bot -f
sudo journalctl -u i-tat-celery-worker -f
sudo journalctl -u i-tat-celery-beat -f
```

Одновременный просмотр трёх сервисов:

```bash
sudo journalctl -u i-tat-bot -u i-tat-celery-worker -u i-tat-celery-beat -f
```

Файловые журналы Celery:

```bash
sudo tail -f /var/log/celery/i-tat-worker.log
sudo tail -f /var/log/celery/i-tat-beat.log
```

## База данных

Для новой пустой БД используйте `alembic upgrade head`. Для переноса проверенной production-структуры без данных используйте `structure.sql` и последовательность baseline/stamp из [README](../README.md#восстановление-структуры-бд).

Перед миграцией production требуется резервная копия данных. `structure.sql` не является резервной копией данных.

## Автоматизированная проверка

```bash
python scripts/check_setup.py
pytest -q
```

`check_setup.py` проверяет окружение и подключения, но не изменяет данные. Тесты, которые обращаются к реальным MAX или i-TAT, должны запускаться отдельно и только с тестовыми сущностями.
