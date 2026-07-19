# i-TAT Bot Deployment Guide

This directory contains systemd service files and deployment scripts for the i-TAT Bot application.

## 🚀 Быстрая установка

Для автоматической установки на чистом сервере:

```bash
# Скачайте и запустите скрипт установки
wget https://raw.githubusercontent.com/aistrategiya/Aytat-bot/main/deployment/install.sh
sudo bash install.sh
```

Или клонируйте репозиторий и запустите:

```bash
cd /opt
sudo git clone https://github.com/aistrategiya/Aytat-bot.git i-tat-bot
cd i-tat-bot/deployment
sudo bash install.sh
```

Скрипт автоматически:
- Установит все зависимости
- Настроит PostgreSQL и Redis
- Создаст конфигурацию
- Применит миграции базы данных
- Установит systemd сервисы
- Настроит Nginx

## 📚 Документация

- **install.sh** - Автоматический скрипт установки (рекомендуется)
- **QUICK_START.md** - Пошаговое руководство для ручной установки
- **DEPLOYMENT_CHECKLIST.md** - Чек-лист для проверки всех шагов
- **COMMANDS_CHEATSHEET.md** - Шпаргалка по командам управления
- **README.md** (этот файл) - Полная документация по развертыванию
- **systemd/** - Файлы systemd сервисов
- **nginx/i-tat-bot.conf** - актуальный пример nginx site config с prod
- **setup-services.sh** - Скрипт установки systemd сервисов

## Services

The application consists of three systemd services:

1. **i-tat-bot.service** - FastAPI application (main.py)
   - Runs uvicorn with 1 worker on port 8453
   - Handles webhooks from Telegram and MAX messengers
   - Serves admin panel and API endpoints

2. **i-tat-celery-worker.service** - Celery worker
   - Processes background tasks
   - Queues: celery, nps_surveys, renewal_reminders, escalations, broadcasts, ticket_notifications, work_mode_monitor, api_retries
   - Pool: solo (Windows-compatible)
   - Concurrency: 4

3. **i-tat-celery-beat.service** - Celery beat scheduler
   - Schedules periodic tasks
   - Runs daily cleanup and reminder tasks
   - Depends on celery worker service

## Prerequisites

Before deploying, ensure you have:

1. **System packages installed:**
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip postgresql redis-server nginx
   ```

2. **PostgreSQL database created:**
   ```bash
   sudo -u postgres psql
   CREATE DATABASE itat_bot;
   CREATE USER itat_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE itat_bot TO itat_user;
   \q
   ```

3. **Redis server running:**
   ```bash
   sudo systemctl start redis-server
   sudo systemctl enable redis-server
   ```

4. **Project deployed to server:**
   ```bash
   cd /opt
   sudo git clone https://github.com/aistrategiya/Aytat-bot.git i-tat-bot
   sudo chown -R $USER:$USER /opt/i-tat-bot
   cd i-tat-bot
   ```

5. **Virtual environment created:**
   ```bash
   cd /opt/i-tat-bot
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

6. **Environment variables configured:**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your configuration
   ```

7. **Database migrations applied:**
   ```bash
   source venv/bin/activate
   alembic upgrade head
   ```

## Installation

Run the setup script to install and configure all services:

```bash
cd /opt/i-tat-bot/deployment
sudo bash setup-services.sh
```

The script will:
- Create necessary directories (/var/run/celery, /var/log/celery)
- Set correct ownership and permissions
- Install systemd service files
- Enable services to start on boot
- Optionally start services immediately

## Manual Installation

If you prefer to install services manually:

```bash
# Copy service files
sudo cp systemd/*.service /etc/systemd/system/

# Create directories
sudo mkdir -p /var/run/celery /var/log/celery
sudo chown razrab:razrab /var/run/celery /var/log/celery

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable i-tat-bot
sudo systemctl enable i-tat-celery-worker
sudo systemctl enable i-tat-celery-beat
```

## Service Management

### Start Services

```bash
# Start in correct order
sudo systemctl start i-tat-bot
sudo systemctl start i-tat-celery-worker
sudo systemctl start i-tat-celery-beat
```

### Stop Services

```bash
# Stop in reverse order
sudo systemctl stop i-tat-celery-beat
sudo systemctl stop i-tat-celery-worker
sudo systemctl stop i-tat-bot
```

### Restart Services

```bash
sudo systemctl restart i-tat-bot
sudo systemctl restart i-tat-celery-worker
sudo systemctl restart i-tat-celery-beat
```

### Check Status

```bash
sudo systemctl status i-tat-bot
sudo systemctl status i-tat-celery-worker
sudo systemctl status i-tat-celery-beat
```

### View Logs

```bash
# Real-time logs
sudo journalctl -u i-tat-bot -f
sudo journalctl -u i-tat-celery-worker -f
sudo journalctl -u i-tat-celery-beat -f

# Last 100 lines
sudo journalctl -u i-tat-bot -n 100
sudo journalctl -u i-tat-celery-worker -n 100
sudo journalctl -u i-tat-celery-beat -n 100

# Logs since today
sudo journalctl -u i-tat-bot --since today
```

## Nginx Configuration

Prod nginx example is stored in `deployment/nginx/i-tat-bot.conf`. Current prod config:

```nginx
server {
    listen 80;
    server_name assistant.i-tat.ru;

    proxy_connect_timeout 600;
    proxy_send_timeout 600;
    proxy_read_timeout 600;
    send_timeout 600;

    location / {
        proxy_pass http://127.0.0.1:8453;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        # proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /static/ {
        alias /home/razrab/i-tat-bot/api/static/;
        expires 1d;
        access_log off;
    }

    # Медиа
    location /media/ {
        alias /home/razrab/i-tat-bot/media/;
        allow all;
    }
}
```

Save to `/etc/nginx/sites-available/i-tat-bot` and enable:

```bash
sudo cp deployment/nginx/i-tat-bot.conf /etc/nginx/sites-available/i-tat-bot
sudo ln -sfn /etc/nginx/sites-available/i-tat-bot /etc/nginx/sites-enabled/i-tat-bot
sudo nginx -t
sudo systemctl reload nginx
```

## Troubleshooting

### Service won't start

1. Check service status:
   ```bash
   sudo systemctl status i-tat-bot
   ```

2. Check logs:
   ```bash
   sudo journalctl -u i-tat-bot -n 50
   ```

3. Verify configuration:
   ```bash
   cd /opt/i-tat-bot
   source venv/bin/activate
   python -c "from constants import *; print('Config OK')"
   ```

### Celery tasks not executing

1. Check worker is running:
   ```bash
   sudo systemctl status i-tat-celery-worker
   ```

2. Check Redis connection:
   ```bash
   redis-cli ping
   ```

3. Inspect Celery:
   ```bash
   cd /opt/i-tat-bot
   source venv/bin/activate
   celery -A celery_app.celery_config inspect active
   celery -A celery_app.celery_config inspect scheduled
   ```

### Database connection errors

1. Check PostgreSQL is running:
   ```bash
   sudo systemctl status postgresql
   ```

2. Test connection:
   ```bash
   psql -h localhost -U itat_user -d itat_bot
   ```

3. Verify DATABASE_URL in .env

### Permission errors

```bash
# Fix ownership
sudo chown -R razrab:razrab /home/razrab/i-tat-bot/media
sudo chown -R razrab:razrab /home/razrab/i-tat-bot/logs
sudo chown -R razrab:razrab /var/log/celery
sudo chown -R razrab:razrab /var/run/celery
```

## Monitoring

### Check service health

```bash
# All services status
sudo systemctl status i-tat-* --no-pager

# Check if services are active
systemctl is-active i-tat-bot
systemctl is-active i-tat-celery-worker
systemctl is-active i-tat-celery-beat
```

### Monitor resource usage

```bash
# CPU and memory usage
sudo systemctl status i-tat-bot | grep -E "Memory|CPU"
sudo systemctl status i-tat-celery-worker | grep -E "Memory|CPU"

# Detailed process info
ps aux | grep -E "uvicorn|celery"
```

### Check Celery queues

```bash
cd /opt/i-tat-bot
source venv/bin/activate
python scripts/celery/check_celery_status.py
```

## Updates and Maintenance

### Update application code

```bash
# Stop services
sudo systemctl stop i-tat-celery-beat
sudo systemctl stop i-tat-celery-worker
sudo systemctl stop i-tat-bot

# Update code from GitHub
cd /opt/i-tat-bot
git fetch origin
git pull origin main  # or master, depending on your branch

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Restart services
sudo systemctl start i-tat-bot
sudo systemctl start i-tat-celery-worker
sudo systemctl start i-tat-celery-beat
```

### Clear Celery queues

```bash
cd /opt/i-tat-bot
source venv/bin/activate
python scripts/celery/clear_celery_redis.py
```

### Backup database

```bash
# Create backup
sudo -u postgres pg_dump itat_bot > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore backup
sudo -u postgres psql itat_bot < backup_20260309_120000.sql
```

## Security Considerations

1. **Change default credentials** in .env:
   - ADMIN_USERNAME
   - ADMIN_PASSWORD
   - WEBHOOK_API_KEY
   - ADMIN_SECRET_KEY

2. **Use HTTPS** with valid SSL certificates (Let's Encrypt)

3. **Firewall configuration:**
   ```bash
   sudo ufw allow 22/tcp   # SSH
   sudo ufw allow 80/tcp   # HTTP
   sudo ufw allow 443/tcp  # HTTPS
   sudo ufw enable
   ```

4. **Restrict database access** to localhost only

5. **Set Redis password** in redis.conf and update .env

6. **Regular updates:**
   ```bash
   sudo apt update && sudo apt upgrade
   ```

## Service Configuration

### Change project directory

If your project is not in `/opt/i-tat-bot`, edit service files:

```bash
sudo nano /etc/systemd/system/i-tat-bot.service
# Update WorkingDirectory and Environment paths

sudo systemctl daemon-reload
sudo systemctl restart i-tat-bot
```

### Change service user

To run services as a different user:

```bash
sudo nano /etc/systemd/system/i-tat-bot.service
# Change User= and Group= lines

sudo systemctl daemon-reload
sudo systemctl restart i-tat-bot
```

### Adjust worker concurrency

Edit celery worker service:

```bash
sudo nano /etc/systemd/system/i-tat-celery-worker.service
# Change --concurrency=4 to desired number

sudo systemctl daemon-reload
sudo systemctl restart i-tat-celery-worker
```

## Support

For issues and questions:
- Check logs: `sudo journalctl -u i-tat-bot -n 100`
- Review documentation in `docs/`
- Check project README.md
