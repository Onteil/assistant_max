# Systemd Services Deployment Instructions

Эти unit-файлы соответствуют prod-конфигурации, проверенной 2026-07-07:

- `i-tat-bot.service`
- `i-tat-celery-worker.service`
- `i-tat-celery-beat.service`

В примерах используются пользователь `razrab`, группа `razrab` и рабочая директория `/home/razrab/i-tat-bot`. Если проект разворачивается в другой директории или под другим пользователем, замените эти значения перед копированием файлов в `/etc/systemd/system/`.

## Установка

```bash
sudo cp deployment/systemd/i-tat-bot.service /etc/systemd/system/
sudo cp deployment/systemd/i-tat-celery-worker.service /etc/systemd/system/
sudo cp deployment/systemd/i-tat-celery-beat.service /etc/systemd/system/
sudo cp deployment/logrotate/i-tat-celery /etc/logrotate.d/i-tat-celery

sudo mkdir -p /var/run/celery /var/log/celery /home/razrab/i-tat-bot/logs /home/razrab/i-tat-bot/media
sudo chown -R razrab:razrab /var/run/celery /var/log/celery /home/razrab/i-tat-bot/logs /home/razrab/i-tat-bot/media

sudo systemctl daemon-reload
sudo systemctl enable --now i-tat-bot i-tat-celery-worker i-tat-celery-beat
```

## Проверка

```bash
sudo systemctl status i-tat-bot
sudo systemctl status i-tat-celery-worker
sudo systemctl status i-tat-celery-beat

sudo journalctl -u i-tat-bot -f
sudo journalctl -u i-tat-celery-worker -f
sudo journalctl -u i-tat-celery-beat -f
```

## Обновление после изменения unit-файлов

```bash
sudo systemctl daemon-reload
sudo systemctl restart i-tat-bot i-tat-celery-worker i-tat-celery-beat
```
