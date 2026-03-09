# Быстрый старт развертывания i-TAT Bot

Это краткое руководство для быстрого развертывания бота на чистом сервере Ubuntu/Debian.

## Требования

- Ubuntu 20.04+ или Debian 11+
- Root или sudo доступ
- Минимум 2GB RAM, 2 CPU cores
- 20GB свободного места на диске

## Шаг 1: Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка необходимых пакетов
sudo apt install -y python3 python3-venv python3-pip postgresql redis-server nginx git curl

# Настройка PostgreSQL
sudo -u postgres psql << EOF
CREATE DATABASE itat_bot;
CREATE USER itat_user WITH PASSWORD 'ChangeThisPassword123!';
GRANT ALL PRIVILEGES ON DATABASE itat_bot TO itat_user;
\q
EOF

# Запуск Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Настройка пароля Redis (рекомендуется)
sudo sed -i 's/# requirepass foobared/requirepass YourRedisPassword123!/' /etc/redis/redis.conf
sudo systemctl restart redis-server
```

## Шаг 2: Клонирование проекта

```bash
# Клонирование репозитория
cd /opt
sudo git clone https://github.com/aistrategiya/Aytat-bot.git i-tat-bot

# Установка прав доступа
sudo chown -R $USER:$USER /opt/i-tat-bot
cd /opt/i-tat-bot
```

## Шаг 3: Настройка Python окружения

```bash
# Создание виртуального окружения
python3 -m venv venv

# Активация виртуального окружения
source venv/bin/activate

# Обновление pip
pip install --upgrade pip

# Установка зависимостей
pip install -r requirements.txt
```

## Шаг 4: Настройка конфигурации

```bash
# Копирование шаблона конфигурации
cp .env.dist .env

# Редактирование конфигурации
nano .env
```

### Обязательные параметры в .env:

```bash
# Токены ботов
MAX_BOT_TOKEN="your_max_bot_token_here"
TG_BOT_TOKEN="your_telegram_bot_token_here"  # Опционально

# База данных
DB_URL="postgresql+asyncpg://itat_user:ChangeThisPassword123!@localhost/itat_bot"

# Redis
REDIS_HOST="localhost"
REDIS_PORT="6379"
REDIS_PASSWORD="YourRedisPassword123!"
REDIS="redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}"

# Webhook URL (ваш домен или IP)
HOST="https://your-domain.com"
WEBHOOK_PATH_MAX="/max/webhook"
WEBHOOK_PATH_MAIN="/telegram/webhook"

# i-TAT API
ITAT_API_BASE_URL="http://i1.i-tat.ru:33080/sa-001-itatka/hs/dispatcher/v1"
ITAT_API_USERNAME="dispatcher"
ITAT_API_PASSWORD="your_itat_api_password"

# Безопасность (сгенерируйте новые ключи!)
ADMIN_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
WEBHOOK_API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

# Учетные данные админ-панели (ОБЯЗАТЕЛЬНО ИЗМЕНИТЕ!)
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="SecurePassword123!"

# Начальные администраторы (JSON массив)
INITIAL_ADMINS='[{"max_user_id": 123456789, "tg_user_id": null, "full_name": "Иван Иванов", "position": "Администратор", "phone_number": "+79991234567"}]'

# Настройки сервера
PROJECT_HOST="0.0.0.0"
PROJECT_PORT="8453"
IS_LOCAL_BOT="False"
COUNT_WORKERS="4"
LOG_LEVEL="info"
```

### Генерация секретных ключей:

```bash
# Генерация ADMIN_SECRET_KEY
python3 -c "import secrets; print('ADMIN_SECRET_KEY=\"' + secrets.token_urlsafe(32) + '\"')"

# Генерация WEBHOOK_API_KEY
python3 -c "import secrets; print('WEBHOOK_API_KEY=\"' + secrets.token_urlsafe(32) + '\"')"
```

## Шаг 5: Инициализация базы данных

```bash
# Активация виртуального окружения (если не активировано)
source venv/bin/activate

# Применение миграций
alembic upgrade head
```

## Шаг 6: Установка systemd сервисов

```bash
# Запуск скрипта установки
cd /opt/i-tat-bot/deployment
sudo bash setup-services.sh
```

Скрипт автоматически:
- Создаст необходимые директории
- Установит права доступа
- Скопирует systemd сервисы
- Включит автозапуск
- Предложит запустить сервисы

## Шаг 7: Настройка Nginx

```bash
# Создание конфигурации Nginx
sudo nano /etc/nginx/sites-available/i-tat-bot
```

Вставьте следующую конфигурацию:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Замените на ваш домен

    # Временная конфигурация для получения SSL сертификата
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;  # Замените на ваш домен

    # SSL сертификаты (будут созданы Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL настройки
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Заголовки безопасности
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Основное приложение
    location / {
        proxy_pass http://127.0.0.1:8453;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Статические файлы
    location /static/ {
        alias /opt/i-tat-bot/api/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /opt/i-tat-bot/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # Максимальный размер загружаемых файлов
    client_max_body_size 50M;
}
```

```bash
# Активация конфигурации
sudo ln -s /etc/nginx/sites-available/i-tat-bot /etc/nginx/sites-enabled/

# Проверка конфигурации
sudo nginx -t

# Перезагрузка Nginx
sudo systemctl reload nginx
```

## Шаг 8: Получение SSL сертификата

```bash
# Установка Certbot
sudo apt install -y certbot python3-certbot-nginx

# Получение сертификата (замените на ваш домен)
sudo certbot --nginx -d your-domain.com

# Автоматическое обновление сертификата
sudo systemctl enable certbot.timer
```

## Шаг 9: Настройка Firewall

```bash
# Настройка UFW
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# Проверка статуса
sudo ufw status
```

## Шаг 10: Запуск сервисов

```bash
# Запуск всех сервисов
sudo systemctl start i-tat-bot
sudo systemctl start i-tat-celery-worker
sudo systemctl start i-tat-celery-beat

# Проверка статуса
sudo systemctl status i-tat-bot
sudo systemctl status i-tat-celery-worker
sudo systemctl status i-tat-celery-beat
```

## Проверка работоспособности

### 1. Проверка веб-приложения

```bash
# Локальная проверка
curl http://localhost:8453/

# Проверка через домен
curl https://your-domain.com/
```

### 2. Проверка админ-панели

Откройте в браузере: `https://your-domain.com/admin`

Войдите с учетными данными из `.env` (ADMIN_USERNAME и ADMIN_PASSWORD)

### 3. Проверка бота

Отправьте команду `/start` вашему MAX боту

### 4. Проверка Celery

```bash
cd /opt/i-tat-bot
source venv/bin/activate
python scripts/celery/check_celery_status.py
```

### 5. Проверка логов

```bash
# Логи FastAPI приложения
sudo journalctl -u i-tat-bot -f

# Логи Celery worker
sudo journalctl -u i-tat-celery-worker -f

# Логи Celery beat
sudo journalctl -u i-tat-celery-beat -f

# Все логи вместе
sudo journalctl -u i-tat-* -f
```

## Полезные команды

### Управление сервисами

```bash
# Перезапуск всех сервисов
sudo systemctl restart i-tat-bot i-tat-celery-worker i-tat-celery-beat

# Остановка всех сервисов
sudo systemctl stop i-tat-celery-beat i-tat-celery-worker i-tat-bot

# Просмотр статуса
sudo systemctl status i-tat-*
```

### Обновление кода

```bash
# Остановка сервисов
sudo systemctl stop i-tat-celery-beat i-tat-celery-worker i-tat-bot

# Обновление из GitHub
cd /opt/i-tat-bot
git pull origin main

# Обновление зависимостей
source venv/bin/activate
pip install -r requirements.txt

# Применение миграций
alembic upgrade head

# Запуск сервисов
sudo systemctl start i-tat-bot i-tat-celery-worker i-tat-celery-beat
```

### Резервное копирование

```bash
# Создание бэкапа базы данных
sudo -u postgres pg_dump itat_bot | gzip > ~/itat_bot_backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Бэкап медиа файлов
tar -czf ~/itat_bot_media_$(date +%Y%m%d_%H%M%S).tar.gz /opt/i-tat-bot/media/

# Бэкап конфигурации
cp /opt/i-tat-bot/.env ~/itat_bot_env_$(date +%Y%m%d_%H%M%S).backup
```

### Восстановление из бэкапа

```bash
# Восстановление базы данных
gunzip < itat_bot_backup_YYYYMMDD_HHMMSS.sql.gz | sudo -u postgres psql itat_bot

# Восстановление медиа файлов
sudo tar -xzf itat_bot_media_YYYYMMDD_HHMMSS.tar.gz -C /
```

## Мониторинг

### Проверка использования ресурсов

```bash
# Использование CPU и памяти
htop

# Использование диска
df -h

# Использование памяти
free -h

# Процессы бота
ps aux | grep -E "uvicorn|celery"
```

### Проверка подключений

```bash
# PostgreSQL подключения
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='itat_bot';"

# Redis подключения
redis-cli -a YourRedisPassword123! INFO clients
```

## Решение проблем

### Сервис не запускается

```bash
# Проверка логов
sudo journalctl -u i-tat-bot -n 100 --no-pager

# Проверка конфигурации
cd /opt/i-tat-bot
source venv/bin/activate
python -c "from constants import *; print('Config OK')"
```

### Celery не обрабатывает задачи

```bash
# Проверка подключения к Redis
redis-cli -a YourRedisPassword123! ping

# Очистка очередей Celery
cd /opt/i-tat-bot
source venv/bin/activate
python scripts/celery/clear_celery_redis.py
```

### Ошибки базы данных

```bash
# Проверка подключения
psql -h localhost -U itat_user -d itat_bot

# Проверка миграций
cd /opt/i-tat-bot
source venv/bin/activate
alembic current
alembic history
```

### Webhook не работает

```bash
# Проверка доступности webhook
curl -X POST https://your-domain.com/max/webhook

# Проверка логов Nginx
sudo tail -f /var/log/nginx/error.log

# Проверка логов приложения
sudo journalctl -u i-tat-bot -f | grep webhook
```

## Безопасность

### Обязательные действия после установки:

1. ✅ Измените пароли в `.env`:
   - ADMIN_PASSWORD
   - DB_URL (пароль базы данных)
   - REDIS_PASSWORD

2. ✅ Сгенерируйте новые секретные ключи:
   - ADMIN_SECRET_KEY
   - WEBHOOK_API_KEY

3. ✅ Настройте SSH ключи и отключите вход по паролю:
   ```bash
   sudo nano /etc/ssh/sshd_config
   # PasswordAuthentication no
   sudo systemctl restart sshd
   ```

4. ✅ Настройте автоматические обновления безопасности:
   ```bash
   sudo apt install unattended-upgrades
   sudo dpkg-reconfigure -plow unattended-upgrades
   ```

5. ✅ Установите fail2ban для защиты от брутфорса:
   ```bash
   sudo apt install fail2ban
   sudo systemctl enable fail2ban
   sudo systemctl start fail2ban
   ```

## Поддержка

- Документация: `/opt/i-tat-bot/docs/`
- Логи: `sudo journalctl -u i-tat-* -f`
- GitHub: https://github.com/aistrategiya/Aytat-bot

## Чек-лист после установки

- [ ] Все сервисы запущены и работают
- [ ] Админ-панель доступна и работает
- [ ] Бот отвечает на команды
- [ ] SSL сертификат установлен
- [ ] Firewall настроен
- [ ] Пароли изменены с дефолтных
- [ ] Настроено резервное копирование
- [ ] Логи проверены на ошибки
- [ ] Webhook настроен и работает
- [ ] Celery обрабатывает задачи

Готово! Ваш i-TAT Bot развернут и готов к работе. 🚀
