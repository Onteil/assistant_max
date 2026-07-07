# i-TAT Bot - Шпаргалка команд

Быстрый справочник по управлению i-TAT Bot на сервере.

## 🚀 Быстрая установка

```bash
# Автоматическая установка
wget https://raw.githubusercontent.com/aistrategiya/Aytat-bot/main/deployment/install.sh
sudo bash install.sh
```

## 🔧 Управление сервисами

### Запуск

```bash
# Запустить все сервисы
sudo systemctl start i-tat-bot i-tat-celery-worker i-tat-celery-beat

# Запустить по отдельности
sudo systemctl start i-tat-bot
sudo systemctl start i-tat-celery-worker
sudo systemctl start i-tat-celery-beat
```

### Остановка

```bash
# Остановить все сервисы (в правильном порядке)
sudo systemctl stop i-tat-celery-beat i-tat-celery-worker i-tat-bot

# Остановить по отдельности
sudo systemctl stop i-tat-bot
sudo systemctl stop i-tat-celery-worker
sudo systemctl stop i-tat-celery-beat
```

### Перезапуск

```bash
# Перезапустить все сервисы
sudo systemctl restart i-tat-bot i-tat-celery-worker i-tat-celery-beat

# Перезапустить по отдельности
sudo systemctl restart i-tat-bot
sudo systemctl restart i-tat-celery-worker
sudo systemctl restart i-tat-celery-beat
```

### Статус

```bash
# Статус всех сервисов
sudo systemctl status i-tat-*

# Статус конкретного сервиса
sudo systemctl status i-tat-bot
sudo systemctl status i-tat-celery-worker
sudo systemctl status i-tat-celery-beat

# Проверка активности
systemctl is-active i-tat-bot
systemctl is-active i-tat-celery-worker
systemctl is-active i-tat-celery-beat
```

### Автозапуск

```bash
# Включить автозапуск
sudo systemctl enable i-tat-bot i-tat-celery-worker i-tat-celery-beat

# Отключить автозапуск
sudo systemctl disable i-tat-bot i-tat-celery-worker i-tat-celery-beat
```

## 📋 Просмотр логов

### Реальное время

```bash
# Все сервисы
sudo journalctl -u i-tat-* -f

# Конкретный сервис
sudo journalctl -u i-tat-bot -f
sudo journalctl -u i-tat-celery-worker -f
sudo journalctl -u i-tat-celery-beat -f
```

### Последние записи

```bash
# Последние 50 строк
sudo journalctl -u i-tat-bot -n 50

# Последние 100 строк
sudo journalctl -u i-tat-celery-worker -n 100

# Без пейджера (весь вывод сразу)
sudo journalctl -u i-tat-bot -n 50 --no-pager
```

### Фильтрация по времени

```bash
# Логи за сегодня
sudo journalctl -u i-tat-bot --since today

# Логи за последний час
sudo journalctl -u i-tat-bot --since "1 hour ago"

# Логи за период
sudo journalctl -u i-tat-bot --since "2024-03-09 10:00" --until "2024-03-09 12:00"
```

### Поиск в логах

```bash
# Поиск ошибок
sudo journalctl -u i-tat-bot | grep -i error

# Поиск webhook событий
sudo journalctl -u i-tat-bot | grep webhook

# Поиск конкретного пользователя
sudo journalctl -u i-tat-bot | grep "user_id=123456"
```

## 🔄 Обновление приложения

```bash
# Полный процесс обновления
cd /opt/i-tat-bot

# 1. Остановить сервисы
sudo systemctl stop i-tat-celery-beat i-tat-celery-worker i-tat-bot

# 2. Создать бэкап
sudo -u postgres pg_dump itat_bot > ~/backup_$(date +%Y%m%d_%H%M%S).sql

# 3. Обновить код
git fetch origin
git pull origin main

# 4. Обновить зависимости
source venv/bin/activate
pip install -r requirements.txt

# 5. Применить миграции
alembic upgrade head

# 6. Запустить сервисы
sudo systemctl start i-tat-bot i-tat-celery-worker i-tat-celery-beat

# 7. Проверить статус
sudo systemctl status i-tat-*
```

## 💾 Резервное копирование

### База данных

```bash
# Создать бэкап
sudo -u postgres pg_dump itat_bot > ~/itat_bot_backup_$(date +%Y%m%d_%H%M%S).sql

# Создать сжатый бэкап
sudo -u postgres pg_dump itat_bot | gzip > ~/itat_bot_backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Восстановить из бэкапа
sudo -u postgres psql itat_bot < ~/itat_bot_backup_20240309_120000.sql

# Восстановить из сжатого бэкапа
gunzip < ~/itat_bot_backup_20240309_120000.sql.gz | sudo -u postgres psql itat_bot
```

### Медиа файлы

```bash
# Создать архив медиа файлов
tar -czf ~/itat_bot_media_$(date +%Y%m%d_%H%M%S).tar.gz /opt/i-tat-bot/media/

# Восстановить медиа файлы
sudo tar -xzf ~/itat_bot_media_20240309_120000.tar.gz -C /
```

### Конфигурация

```bash
# Бэкап .env файла
cp /opt/i-tat-bot/.env ~/itat_bot_env_$(date +%Y%m%d_%H%M%S).backup

# Восстановить .env
sudo cp ~/itat_bot_env_20240309_120000.backup /opt/i-tat-bot/.env
sudo chmod 600 /opt/i-tat-bot/.env
```

## 🗄️ Работа с базой данных

### Подключение

```bash
# Подключиться к базе
sudo -u postgres psql itat_bot

# Подключиться от имени пользователя
psql -h localhost -U itat_user -d itat_bot
```

### Полезные SQL команды

```sql
-- Количество пользователей
SELECT COUNT(*) FROM users;

-- Количество тикетов
SELECT COUNT(*) FROM tickets;

-- Активные тикеты
SELECT COUNT(*) FROM tickets WHERE status = 'open';

-- Последние 10 пользователей
SELECT id, phone_number, registration_status, created_at 
FROM users 
ORDER BY created_at DESC 
LIMIT 10;

-- Статистика по тикетам
SELECT status, COUNT(*) 
FROM tickets 
GROUP BY status;
```

### Миграции

```bash
cd /opt/i-tat-bot
source venv/bin/activate

# Текущая версия БД
alembic current

# История миграций
alembic history

# Применить все миграции
alembic upgrade head

# Откатить одну миграцию
alembic downgrade -1

# Откатить до конкретной версии
alembic downgrade <revision_id>

# Создать новую миграцию
alembic revision --autogenerate -m "Description"
```

## 🔴 Redis

### Подключение

```bash
# Подключиться к Redis
redis-cli -a YourRedisPassword

# Проверка подключения
redis-cli -a YourRedisPassword ping
```

### Полезные команды Redis

```bash
# Информация о Redis
redis-cli -a YourRedisPassword INFO

# Количество ключей
redis-cli -a YourRedisPassword DBSIZE

# Список всех ключей (осторожно на продакшене!)
redis-cli -a YourRedisPassword KEYS "*"

# Очистить базу данных Celery (DB 0)
redis-cli -a YourRedisPassword -n 0 FLUSHDB

# Очистить базу данных Aiogram (DB 1)
redis-cli -a YourRedisPassword -n 1 FLUSHDB
```

### Celery в Redis

```bash
cd /opt/i-tat-bot
source venv/bin/activate

# Проверить статус Celery
python scripts/celery/check_celery_status.py

# Очистить очереди Celery
python scripts/celery/clear_celery_redis.py
```

## 🌐 Nginx

### Управление

```bash
# Проверить конфигурацию
sudo nginx -t

# Перезагрузить конфигурацию
sudo systemctl reload nginx

# Перезапустить Nginx
sudo systemctl restart nginx

# Статус Nginx
sudo systemctl status nginx
```

### Логи Nginx

```bash
# Access логи
sudo tail -f /var/log/nginx/access.log

# Error логи
sudo tail -f /var/log/nginx/error.log

# Последние 100 строк
sudo tail -n 100 /var/log/nginx/error.log
```

### SSL сертификаты

```bash
# Получить сертификат Let's Encrypt
sudo certbot --nginx -d your-domain.com

# Обновить сертификаты
sudo certbot renew

# Проверить срок действия
sudo certbot certificates

# Тестовое обновление (dry-run)
sudo certbot renew --dry-run
```

## 🔍 Мониторинг

### Использование ресурсов

```bash
# Процессы бота
ps aux | grep -E "uvicorn|celery"

# Использование CPU и памяти
htop

# Использование диска
df -h

# Использование памяти
free -h

# Использование сети
sudo netstat -tulpn | grep -E "8453|6379|5432"
```

### Подключения к базе данных

```bash
# Количество подключений
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='itat_bot';"

# Активные запросы
sudo -u postgres psql -c "SELECT pid, usename, application_name, state, query FROM pg_stat_activity WHERE datname='itat_bot';"
```

### Проверка портов

```bash
# Проверить открытые порты
sudo netstat -tulpn

# Проверить конкретный порт
sudo netstat -tulpn | grep 8453

# Проверить доступность приложения
curl http://localhost:8453/
```

## 🔥 Firewall (UFW)

```bash
# Статус firewall
sudo ufw status

# Включить firewall
sudo ufw enable

# Разрешить порты
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS

# Запретить порт
sudo ufw deny 8453/tcp

# Удалить правило
sudo ufw delete allow 80/tcp

# Сбросить все правила
sudo ufw reset
```

## 🐛 Отладка

### Проверка конфигурации

```bash
cd /opt/i-tat-bot
source venv/bin/activate

# Проверить импорт констант
python -c "from constants import *; print('Config OK')"

# Проверить подключение к БД
python -c "from constants import engine; print('DB OK')"

# Проверить Redis
python -c "import redis; r = redis.from_url('redis://:password@localhost:6379'); r.ping(); print('Redis OK')"
```

### Тестирование webhook

```bash
# Проверить доступность webhook
curl -X POST https://your-domain.com/max/webhook

# Проверить с данными
curl -X POST https://your-domain.com/max/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

### Проверка Celery

```bash
cd /opt/i-tat-bot
source venv/bin/activate

# Список активных задач
celery -A celery_app.celery_config inspect active

# Список запланированных задач
celery -A celery_app.celery_config inspect scheduled

# Список зарегистрированных задач
celery -A celery_app.celery_config inspect registered

# Статистика воркеров
celery -A celery_app.celery_config inspect stats
```

## 🔐 Безопасность

### Изменение паролей

```bash
# Изменить пароль БД
sudo -u postgres psql
ALTER USER itat_user WITH PASSWORD 'new_password';
\q

# Обновить в .env
sudo nano /opt/i-tat-bot/.env
# Изменить DB_URL

# Изменить пароль Redis
sudo nano /etc/redis/redis.conf
# Изменить requirepass
sudo systemctl restart redis-server

# Обновить в .env
sudo nano /opt/i-tat-bot/.env
# Изменить REDIS_PASSWORD
```

### Права доступа

```bash
# Проверить права на .env
ls -la /opt/i-tat-bot/.env

# Установить правильные права
sudo chmod 600 /opt/i-tat-bot/.env
sudo chown razrab:razrab /opt/i-tat-bot/.env

# Права на директории
sudo chown -R razrab:razrab /opt/i-tat-bot/media
sudo chown -R razrab:razrab /opt/i-tat-bot/logs
```

## 📊 Полезные скрипты

```bash
cd /opt/i-tat-bot
source venv/bin/activate

# Проверить статус Celery
python scripts/celery/check_celery_status.py

# Очистить Redis
python scripts/celery/clear_celery_redis.py

# Найти пользователя
python scripts/utils/find_test_user.py

# Добавить сотрудника
python scripts/utils/add_staff_member.py

# Проверить конкретного пользователя
python scripts/utils/check_specific_user.py
```

## 🆘 Экстренные ситуации

### Приложение не отвечает

```bash
# 1. Проверить статус
sudo systemctl status i-tat-bot

# 2. Проверить логи
sudo journalctl -u i-tat-bot -n 100

# 3. Перезапустить
sudo systemctl restart i-tat-bot

# 4. Проверить порт
sudo netstat -tulpn | grep 8453
```

### База данных недоступна

```bash
# 1. Проверить PostgreSQL
sudo systemctl status postgresql

# 2. Перезапустить PostgreSQL
sudo systemctl restart postgresql

# 3. Проверить подключения
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# 4. Проверить логи
sudo tail -f /var/log/postgresql/postgresql-*.log
```

### Redis недоступен

```bash
# 1. Проверить Redis
sudo systemctl status redis-server

# 2. Перезапустить Redis
sudo systemctl restart redis-server

# 3. Проверить подключение
redis-cli -a YourPassword ping

# 4. Проверить логи
sudo tail -f /var/log/redis/redis-server.log
```

### Celery не обрабатывает задачи

```bash
# 1. Проверить статус воркера
sudo systemctl status i-tat-celery-worker

# 2. Проверить логи
sudo journalctl -u i-tat-celery-worker -n 100

# 3. Очистить очереди
cd /opt/i-tat-bot
source venv/bin/activate
python scripts/celery/clear_celery_redis.py

# 4. Перезапустить воркер
sudo systemctl restart i-tat-celery-worker
```

### Полный перезапуск системы

```bash
# Остановить все
sudo systemctl stop i-tat-celery-beat
sudo systemctl stop i-tat-celery-worker
sudo systemctl stop i-tat-bot
sudo systemctl stop nginx

# Перезапустить зависимости
sudo systemctl restart postgresql
sudo systemctl restart redis-server

# Запустить все
sudo systemctl start nginx
sudo systemctl start i-tat-bot
sudo systemctl start i-tat-celery-worker
sudo systemctl start i-tat-celery-beat

# Проверить статус
sudo systemctl status i-tat-* nginx postgresql redis-server
```

## 📞 Контакты и поддержка

- Документация: `/opt/i-tat-bot/docs/`
- GitHub: https://github.com/aistrategiya/Aytat-bot
- Логи: `sudo journalctl -u i-tat-* -f`
