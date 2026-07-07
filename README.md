# i-TAT Bot

FastAPI-приложение с ботами Telegram/MAX, PostgreSQL, Redis и Celery-задачами для интеграции с i-TAT API.

## Актуальный статус

Проверено 2026-07-07:

- prod VM: `/home/razrab/i-tat-bot`
- prod branch: `main`
- prod commit: `1b3edc619e5e6f5265135908a74504c390bef8a7` (`1b3edc6 04 05 consultation fix in extended mode`)
- prod Python: `3.10.12`
- prod services: `i-tat-bot`, `i-tat-celery-worker`, `i-tat-celery-beat` активны

Локальная ветка `Main` на этой машине указывает на тот же commit `origin/main`, но remote отличается: локально используется GitHub, на prod используется GitLab `services/assistant_max.git`.

## Версия Python

Используйте Python `3.10.x`.

Причины:

- prod работает на Python `3.10.12`;
- `pyproject.toml` задает `requires-python = ">=3.10"`;
- Ruff настроен на `target-version = "py310"`.

README раньше указывал `Python 3.11+`, это было устаревшее требование. Python 3.11/3.12 может работать, но для воспроизводимого локального окружения под Windows/PyCharm используйте Python 3.10.

## Обязательные сервисы локально

Минимум для запуска FastAPI/admin:

- PostgreSQL: обязателен, приложение открывает соединение с БД при старте.
- Redis: не обязателен для FastAPI, если `IS_LOCAL_BOT=True`, но переменные Redis все равно должны быть заполнены.

Для полного локального режима:

- Redis: обязателен для Celery broker/backend.
- Celery worker: нужен для фоновых задач, очередей уведомлений, эскалаций, рассылок, retry и renewal.
- Celery beat: нужен только для периодических задач по расписанию.

На prod запущены все четыре компонента: PostgreSQL, Redis, FastAPI, Celery worker, Celery beat.

## Локальный запуск под Windows/PyCharm

### 1. Открыть проект

Откройте корень проекта в PyCharm:

```powershell
C:\Users\admin\Desktop\i-tat-bot
```

В PyCharm выберите интерпретатор Python 3.10 и создайте venv в папке проекта.

То же самое из PowerShell:

```powershell
py -3.10 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Запустить PostgreSQL и Redis

Можно использовать локальные сервисы Windows/WSL или Docker. Пример через Docker:

```powershell
docker run --name itat-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=itat_bot -p 5432:5432 -d postgres:16
docker run --name itat-redis -p 6379:6379 -d redis:7
```

Если контейнеры уже созданы:

```powershell
docker start itat-postgres itat-redis
```

### 3. Создать `.env`

```powershell
Copy-Item .env.example .env
```

Заполните значения в `.env`. Секреты в репозиторий не коммитятся.

Для локального запуска без реальных вызовов i-TAT API оставьте:

```dotenv
IS_LOCAL_BOT=True
USE_MOCK_ITAT_API=true
LOCAL_DEV=false
DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/itat_bot
REDIS=redis://localhost:6379
```

Запуск ботов контролируется переменной `BOT_MODE`:

- `BOT_MODE=max` - запускается только MAX-бот, `TG_BOT_TOKEN` можно оставить пустым.
- `BOT_MODE=tg` - запускается только Telegram-бот, нужен `TG_BOT_TOKEN`.
- `BOT_MODE=both` - запускаются оба бота, нужны оба токена.
- `BOT_MODE=none` - боты не инициализируются, остается FastAPI/admin/API.

Если `BOT_MODE` не задан, режим автоматически определяется по заполненным токенам. `BOT_TOKEN=${TG_BOT_TOKEN}` и `ACCESS_BOT_TOKEN=${TG_BOT_TOKEN}` больше не нужны для запуска проекта.

### 4. Применить миграции

`alembic.ini` должен находиться в корне проекта. Раньше он был локальным ignored-файлом, из-за чего свежий clone мог не содержать конфиг.

```powershell
alembic upgrade head
```

Или:

```powershell
.\scripts\migrate.ps1 upgrade
```

### 5. Проверить настройку

После заполнения `.env`, запуска PostgreSQL/Redis и применения миграций выполните:

```powershell
python scripts/check_setup.py
```

Скрипт ничего не изменяет в БД и не запускает ботов. Он проверяет `.env`, зависимости, подключение к PostgreSQL/Redis, Alembic current/head, ключевые Python-файлы и наличие prod-примеров systemd/nginx.

Если Redis или Alembic временно не нужны, проверку можно сузить:

```powershell
python scripts/check_setup.py --skip-redis --skip-alembic
```

### 6. Запустить FastAPI

В PowerShell:

```powershell
python main.py
```

Или через PyCharm Run Configuration:

- Type: Python
- Script path: `main.py`
- Working directory: корень проекта
- `.env` будет загружен автоматически через `python-dotenv`, если working directory установлен в корень проекта

Админка: `http://127.0.0.1:8453/admin`

### 7. Запустить Celery worker

В отдельном терминале:

```powershell
.\venv\Scripts\Activate.ps1
celery -A celery_app.celery_config worker --loglevel=debug --pool=solo --queues=nps_surveys,renewal_reminders,escalations,broadcasts,ticket_notifications,work_mode_monitor,api_retries
```

На Windows используется `--pool=solo`.

### 8. Запустить Celery beat

В отдельном терминале:

```powershell
.\venv\Scripts\Activate.ps1
celery -A celery_app.celery_config beat --loglevel=debug --scheduler=celery.beat:PersistentScheduler --schedule=celerybeat-schedule.db
```

Beat нужен только если проверяются периодические задачи.

## Правильный порядок запуска

Для полного локального запуска:

1. PostgreSQL.
2. Redis.
3. Установка зависимостей и заполнение `.env`.
4. `alembic upgrade head`.
5. Проверка настройки: `python scripts/check_setup.py`.
6. FastAPI: `python main.py`.
7. Celery worker: `celery -A celery_app.celery_config worker --loglevel=debug --pool=solo --queues=nps_surveys,renewal_reminders,escalations,broadcasts,ticket_notifications,work_mode_monitor,api_retries`.
8. Celery beat: `celery -A celery_app.celery_config beat --loglevel=debug --scheduler=celery.beat:PersistentScheduler --schedule=celerybeat-schedule.db`.

Для минимального запуска API/admin можно остановиться на пунктах 1-6.

## i-TAT API, VPN и SSH tunnel

VPN/SSH tunnel не нужен, если локально используется мок:

```dotenv
USE_MOCK_ITAT_API=true
LOCAL_DEV=false
```

Для реальных вызовов i-TAT API из локальной разработки нужен доступ в корпоративную сеть:

1. Подключите PPTP VPN.
2. Укажите в `.env`:

```dotenv
USE_MOCK_ITAT_API=false
LOCAL_DEV=true
ITAT_SSH_HOST=<ssh_host_inside_vpn>
ITAT_SSH_LOGIN=<ssh_login>
ITAT_SSH_PASSWORD=<ssh_password>
ITAT_SSH_SOCKS5_PORT=1080
```

При `LOCAL_DEV=true` приложение само поднимает локальный SOCKS5 tunnel через `services/ssh_tunnel.py`, а i-TAT HTTP-клиент отправляет запросы через `socks5://127.0.0.1:<ITAT_SSH_SOCKS5_PORT>`.

На Windows можно использовать helper:

```powershell
.\scripts\vpn-connect.ps1 status
.\scripts\vpn-connect.ps1 connect
```

Скрипт требует PowerShell от администратора и значения `ITAT_VPN_HOST`, `ITAT_VPN_LOGIN`, `ITAT_VPN_PASSWORD` в `.env`.

Если используется отдельный сервер-переходник, сначала поднимите VPN на нем штатным скриптом, затем подключайтесь к VM по SSH через доступный маршрут. Не храните VPN/SSH-пароли в README.

## Обязательные переменные `.env`

Для импорта и запуска приложения должны быть заполнены:

- `DB_URL`
- `PROJECT_HOST`
- `PROJECT_PORT`
- `IS_LOCAL_BOT`
- `COUNT_WORKERS`
- `DEBUG`
- `LOG_LEVEL`
- `ALLOWED_HOSTS`
- `HOST`
- `WEBHOOK_PATH_MAIN`
- `WEBHOOK_PATH_MAX`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS`
- `CELERY_REDIS_DB_NUMBER`
- `AIOGRAM_REDIS_DB_NUMBER`

Для реальной работы ботов также нужны токены выбранного режима:

- `TG_BOT_TOKEN`, если `BOT_MODE=tg` или `BOT_MODE=both`
- `MAX_BOT_TOKEN`, если `BOT_MODE=max` или `BOT_MODE=both`

Для интеграций также нужны:

- `ITAT_API_BASE_URL`
- `ITAT_API_USERNAME`
- `ITAT_API_PASSWORD`
- `USE_MOCK_ITAT_API`
- `WEBHOOK_API_KEY`
- `ADMIN_SECRET_KEY`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

Актуальный и единственный шаблон без секретов: `.env.example`.

## Alembic

Конфиг миграций находится в корне проекта:

```text
alembic.ini
```

Команды:

```powershell
alembic current
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic downgrade -1
```

`alembic/env.py` берет URL БД из `constants.DB_URL`, то есть из `.env`.

## Prod systemd и nginx

Актуальные copy-paste примеры лежат в проекте:

- `deployment/systemd/i-tat-bot.service`
- `deployment/systemd/i-tat-celery-worker.service`
- `deployment/systemd/i-tat-celery-beat.service`
- `deployment/nginx/i-tat-bot.conf`

Они сняты с prod 2026-07-07. В примерах зафиксированы prod-пути `/home/razrab/i-tat-bot`, пользователь `razrab`, домен `assistant.i-tat.ru` и порт приложения `8453`. Если сервер или пользователь другие, замените эти значения перед копированием в `/etc/systemd/system/` и `/etc/nginx/sites-available/`.

Основные команды из systemd:

```bash
uvicorn main:app --host 0.0.0.0 --port 8453 --workers 1 --timeout-keep-alive 30 --proxy-headers --forwarded-allow-ips "*"
celery -A celery_app.celery_config worker --loglevel=debug --pool=solo --queues=nps_surveys,renewal_reminders,escalations,broadcasts,ticket_notifications,work_mode_monitor,api_retries --concurrency=4 --max-tasks-per-child=1000 --time-limit=300 --soft-time-limit=240
celery -A celery_app.celery_config beat --loglevel=debug --scheduler=celery.beat:PersistentScheduler --schedule=/home/razrab/i-tat-bot/celerybeat-schedule.db
```

Копирование на сервер:

```bash
sudo cp deployment/systemd/i-tat-bot.service /etc/systemd/system/
sudo cp deployment/systemd/i-tat-celery-worker.service /etc/systemd/system/
sudo cp deployment/systemd/i-tat-celery-beat.service /etc/systemd/system/
sudo mkdir -p /var/run/celery /var/log/celery /home/razrab/i-tat-bot/logs /home/razrab/i-tat-bot/media
sudo chown -R razrab:razrab /var/run/celery /var/log/celery /home/razrab/i-tat-bot/logs /home/razrab/i-tat-bot/media
sudo systemctl daemon-reload
sudo systemctl enable --now i-tat-bot i-tat-celery-worker i-tat-celery-beat
```

Nginx:

```bash
sudo cp deployment/nginx/i-tat-bot.conf /etc/nginx/sites-available/i-tat-bot
sudo ln -sfn /etc/nginx/sites-available/i-tat-bot /etc/nginx/sites-enabled/i-tat-bot
sudo nginx -t
sudo systemctl reload nginx
```

## Проверки

```powershell
python scripts/check_setup.py
python -m py_compile constants.py main.py services/i_tat_service.py
pytest
ruff check .
```
