# Deployment Documentation Index

Навигация по документации развертывания i-TAT Bot.

## ⚠️ ВАЖНО: Архитектура развертывания

Проект i-TAT Bot развернут в специфической инфраструктуре:

### Двухуровневая архитектура с внешним Reverse Proxy

```
Интернет → assistant.i-tat.ru:443 (HTTPS)
    ↓
[Внешний Reverse Proxy на gitlab.i-tat.ru]
    ↓ SSL-терминация
    ↓ HTTP
10.10.100.3:8453 ← [i-TAT Bot на виртуалке]
```

**Ключевые особенности:**

1. **Внешний уровень** (управляется заказчиком):
   - Домен: `assistant.i-tat.ru`
   - Принимает HTTPS на порту 443
   - Выполняет SSL-терминацию
   - Пересылает HTTP на внутренний IP: `10.10.100.3:8453`

2. **Внутренний уровень** (наша виртуалка `10.10.100.3`):
   - Приложение слушает порт `8453`
   - Получает чистый HTTP от внешнего прокси
   - **Nginx НЕ нужен** (порты 80/443 заняты внешним прокси)

3. **Сетевые ограничения:**
   - Доступ только через PPTP VPN
   - SSH работает только внутри VPN-туннеля
   - Порт 8453 должен быть открыт для внешнего прокси

### Что это означает для развертывания:

- ✅ Используйте `install.sh` - он автоматически определит архитектуру
- ❌ НЕ устанавливайте Nginx на виртуалке (конфликт портов)
- ✅ Приложение слушает только порт 8453
- ✅ В `.env` используйте `HOST="https://assistant.i-tat.ru"`
- ✅ Webhook URL: `https://assistant.i-tat.ru/max/webhook`

## 🚀 Начало работы

### ⚠️ Перед установкой

**Проверьте вашу архитектуру:**

1. **Есть внешний reverse proxy?** (например, gitlab.i-tat.ru)
   - ✅ Да → Используйте режим "Внешний прокси" в `install.sh`
   - ❌ Нет → Используйте режим "Прямое подключение"

2. **Доступ к серверу:**
   - Через VPN? → Подключитесь к PPTP VPN перед началом
   - Прямой доступ? → Продолжайте установку

### Для быстрой установки

👉 **[install.sh](install.sh)** - Запустите этот скрипт для автоматической установки

```bash
# Если репозиторий уже клонирован
cd /opt/i-tat-bot/deployment
sudo bash install.sh

# Или скачайте напрямую
wget https://raw.githubusercontent.com/aistrategiya/Aytat-bot/main/deployment/install.sh
sudo bash install.sh
```

**Скрипт автоматически:**
- Определит архитектуру (внешний прокси или прямое подключение)
- Установит только необходимые компоненты
- Настроит правильные порты и конфигурацию
- Пропустит установку Nginx, если обнаружен внешний прокси

### Для ручной установки
👉 **[QUICK_START.md](QUICK_START.md)** - Пошаговое руководство

## 📖 Документация

### Основные документы

0. **[ARCHITECTURE.md](ARCHITECTURE.md)** - Архитектура инфраструктуры ⭐
   - Двухуровневая архитектура с внешним reverse proxy
   - Схема сетевой инфраструктуры
   - Конфигурация внешнего прокси
   - Особенности развертывания
   - Отладка и мониторинг

1. **[QUICK_START.md](QUICK_START.md)** - Быстрый старт
   - Требования к системе
   - Пошаговая установка
   - Настройка конфигурации
   - Проверка работоспособности
   - Решение проблем

2. **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Чек-лист развертывания
   - Предварительная подготовка
   - Установка системных пакетов
   - Настройка приложения
   - Установка сервисов
   - Настройка безопасности
   - Резервное копирование

3. **[COMMANDS_CHEATSHEET.md](COMMANDS_CHEATSHEET.md)** - Шпаргалка команд
   - Управление сервисами
   - Просмотр логов
   - Обновление приложения
   - Резервное копирование
   - Работа с базой данных
   - Отладка и мониторинг

4. **[README.md](README.md)** - Полная документация
   - Описание сервисов
   - Требования
   - Установка
   - Управление
   - Nginx конфигурация
   - Troubleshooting

### Скрипты

- **[install.sh](install.sh)** - Автоматическая установка с определением архитектуры
- **[setup-services.sh](setup-services.sh)** - Установка только systemd сервисов

### Конфигурационные файлы

- **[systemd/i-tat-bot.service](systemd/i-tat-bot.service)** - FastAPI приложение
- **[systemd/i-tat-celery-worker.service](systemd/i-tat-celery-worker.service)** - Celery worker
- **[systemd/i-tat-celery-beat.service](systemd/i-tat-celery-beat.service)** - Celery beat

## 🎯 Выбор документа по задаче

### Я хочу...

#### ...развернуть бота за внешним reverse proxy (assistant.i-tat.ru)
→ Используйте **[install.sh](install.sh)** и выберите режим "Внешний прокси"
→ Читайте раздел "Архитектура" выше ⬆️

#### ...быстро развернуть бота на новом сервере (прямое подключение)
→ Используйте **[install.sh](install.sh)** и выберите режим "Прямое подключение"

#### ...понять процесс установки пошагово
→ Читайте **[QUICK_START.md](QUICK_START.md)**

#### ...проверить, что ничего не забыл при установке
→ Используйте **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)**

#### ...найти команду для управления сервисами
→ Смотрите **[COMMANDS_CHEATSHEET.md](COMMANDS_CHEATSHEET.md)**

#### ...настроить Nginx или решить проблему
→ Читайте **[README.md](README.md)**

#### ...обновить приложение
→ Раздел "Обновление" в **[COMMANDS_CHEATSHEET.md](COMMANDS_CHEATSHEET.md#-обновление-приложения)**

#### ...создать резервную копию
→ Раздел "Резервное копирование" в **[COMMANDS_CHEATSHEET.md](COMMANDS_CHEATSHEET.md#-резервное-копирование)**

#### ...посмотреть логи
→ Раздел "Просмотр логов" в **[COMMANDS_CHEATSHEET.md](COMMANDS_CHEATSHEET.md#-просмотр-логов)**

#### ...решить проблему с сервисом
→ Раздел "Troubleshooting" в **[README.md](README.md#troubleshooting)** или "Экстренные ситуации" в **[COMMANDS_CHEATSHEET.md](COMMANDS_CHEATSHEET.md#-экстренные-ситуации)**

## 📋 Быстрые ссылки

### Конфигурация для внешнего прокси

```bash
# В .env файле
HOST="https://assistant.i-tat.ru"
PROJECT_PORT="8453"
WEBHOOK_PATH_MAX="/max/webhook"

# Внешний прокси должен быть настроен на:
# HTTPS assistant.i-tat.ru:443 → HTTP 10.10.100.3:8453
```

### Управление сервисами

```bash
# Запуск
sudo systemctl start i-tat-bot i-tat-celery-worker i-tat-celery-beat

# Остановка
sudo systemctl stop i-tat-celery-beat i-tat-celery-worker i-tat-bot

# Перезапуск
sudo systemctl restart i-tat-bot i-tat-celery-worker i-tat-celery-beat

# Статус
sudo systemctl status i-tat-*
```

### Просмотр логов

```bash
# Все сервисы
sudo journalctl -u i-tat-* -f

# Конкретный сервис
sudo journalctl -u i-tat-bot -f
```

### Обновление

```bash
cd /opt/i-tat-bot
sudo systemctl stop i-tat-celery-beat i-tat-celery-worker i-tat-bot
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl start i-tat-bot i-tat-celery-worker i-tat-celery-beat
```

### Проверка webhook

```bash
# Для внешнего прокси
curl -X POST https://assistant.i-tat.ru/max/webhook

# Для прямого подключения
curl -X POST http://localhost:8453/max/webhook
```

## 🔧 Особенности архитектуры

### Внешний Reverse Proxy

**Преимущества:**
- SSL управляется централизованно
- Единая точка входа для всех сервисов
- Упрощенная конфигурация на виртуалке

**Требования:**
- Внешний прокси должен передавать заголовки:
  - `X-Forwarded-For`
  - `X-Real-IP`
  - `X-Forwarded-Proto: https`
- Порт 8453 должен быть доступен от внешнего прокси
- Firewall должен разрешать трафик от IP внешнего прокси

**Конфигурация внешнего прокси (пример для Nginx):**

```nginx
server {
    listen 443 ssl http2;
    server_name assistant.i-tat.ru;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://10.10.100.3:8453;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### Firewall на виртуалке

```bash
# Разрешить SSH (только из VPN)
sudo ufw allow from 10.10.100.0/24 to any port 22

# Разрешить порт приложения от внешнего прокси
sudo ufw allow from <IP_gitlab.i-tat.ru> to any port 8453

# Включить firewall
sudo ufw enable
```

### Отладка подключения

```bash
# Проверить, что приложение слушает порт 8453
sudo netstat -tulpn | grep 8453

# Проверить доступность изнутри
curl http://localhost:8453/

# Проверить логи приложения
sudo journalctl -u i-tat-bot -f

# Проверить webhook события
sudo journalctl -u i-tat-bot | grep webhook
```

## 🔗 Связанная документация

- **[../docs/](../docs/)** - Документация проекта
- **[../README.md](../README.md)** - Основной README проекта
- **[../.env.dist](../.env.dist)** - Шаблон конфигурации

## 📞 Поддержка

- GitHub: https://github.com/aistrategiya/Aytat-bot
- Issues: https://github.com/aistrategiya/Aytat-bot/issues

## 🔄 Обновление документации

Последнее обновление: 2024-03-09

При обновлении документации:
1. Обновите дату выше
2. Добавьте изменения в соответствующие файлы
3. Обновите этот индекс при добавлении новых документов
