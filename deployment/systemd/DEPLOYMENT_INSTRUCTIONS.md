# Systemd Services Deployment Instructions

## Просмотр текущих systemd сервисов на сервере

Выполните эти команды на сервере, чтобы посмотреть текущую конфигурацию:

```bash
# Celery Worker
cat /etc/systemd/system/i-tat-celery-worker.service

# Celery Beat
cat /etc/systemd/system/i-tat-celery-beat.service

# FastAPI Bot (для справки)
cat /etc/systemd/system/i-tat-bot.service
```

## После получения вывода

Скопируйте вывод каждой команды и отправьте для анализа и редактирования.

---

## Что будет исправлено

1. **Worker**: Добавление очереди `work_mode_monitor` в список `--queues`
2. **Worker**: Изменение loglevel с `debug` на `info`
3. **Beat**: Изменение пользователя с `www-data` на `razrab`
4. **Beat**: Добавление переменных окружения `PYTHONPATH` и `TZ`
5. **Beat**: Добавление параметров `--scheduler` и `--schedule`
6. **Beat**: Исправление `ProtectHome` для доступа к рабочей директории

## Применение изменений

После редактирования файлов выполните:

```bash
# Остановить сервисы
sudo systemctl stop i-tat-celery-beat i-tat-celery-worker

# Перезагрузить конфигурацию
sudo systemctl daemon-reload

# Создать необходимые директории
sudo mkdir -p /var/run/celery /var/log/celery
sudo chown razrab:razrab /var/run/celery /var/log/celery

# Запустить сервисы
sudo systemctl start i-tat-celery-worker
sudo systemctl start i-tat-celery-beat

# Проверить статус
sudo systemctl status i-tat-celery-worker
sudo systemctl status i-tat-celery-beat

# Включить автозапуск (если еще не включено)
sudo systemctl enable i-tat-celery-worker
sudo systemctl enable i-tat-celery-beat
```

## Проверка логов

```bash
# Логи worker
sudo journalctl -u i-tat-celery-worker -f

# Логи beat
sudo journalctl -u i-tat-celery-beat -f

# Последние 100 строк
sudo journalctl -u i-tat-celery-worker -n 100
sudo journalctl -u i-tat-celery-beat -n 100
```
