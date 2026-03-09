# Архитектура развертывания i-TAT Bot

Техническое описание инфраструктуры и особенностей развертывания.

## 🏗️ Обзор архитектуры

Проект i-TAT Bot развернут в двухуровневой архитектуре с внешним reverse proxy.

### Схема инфраструктуры

```
┌─────────────────────────────────────────────────────────────┐
│                         Интернет                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS (443)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│          Внешний Reverse Proxy (gitlab.i-tat.ru)            │
│                                                               │
│  • Домен: assistant.i-tat.ru                                 │
│  • SSL-терминация (Let's Encrypt)                            │
│  • Управляется заказчиком                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP (без SSL)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Внутренняя сеть (10.10.100.0/24)               │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Виртуальная машина (10.10.100.3)                   │    │
│  │                                                       │    │
│  │  ┌─────────────────────────────────────────────┐    │    │
│  │  │  i-TAT Bot Application (порт 8453)          │    │    │
│  │  │  • FastAPI (uvicorn)                        │    │    │
│  │  │  • Celery Worker                            │    │    │
│  │  │  • Celery Beat                              │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  │                                                       │    │
│  │  ┌─────────────────────────────────────────────┐    │    │
│  │  │  PostgreSQL (порт 5432)                     │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  │                                                       │    │
│  │  ┌─────────────────────────────────────────────┐    │    │
│  │  │  Redis (порт 6379)                          │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  │                                                       │    │
│  │  Доступ: только через PPTP VPN                      │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 🔐 Сетевая безопасность

### Уровни доступа

1. **Публичный доступ:**
   - Домен: `assistant.i-tat.ru`
   - Протокол: HTTPS (порт 443)
   - Доступен из интернета

2. **Внутренний доступ:**
   - IP: `10.10.100.3`
   - Порт: `8453`
   - Доступен только от внешнего прокси

3. **Административный доступ:**
   - SSH: только через PPTP VPN
   - Сеть VPN: `10.10.100.0/24`

### Firewall правила

```bash
# Разрешить SSH только из VPN сети
sudo ufw allow from 10.10.100.0/24 to any port 22

# Разрешить порт приложения от внешнего прокси
sudo ufw allow from <IP_gitlab.i-tat.ru> to any port 8453

# Разрешить PostgreSQL только локально
sudo ufw allow from 127.0.0.1 to any port 5432

# Разрешить Redis только локально
sudo ufw allow from 127.0.0.1 to any port 6379

# Включить firewall
sudo ufw enable
```

## 🌐 Внешний Reverse Proxy

### Конфигурация (на стороне заказчика)

Внешний прокси должен быть настроен следующим образом:

```nginx
# /etc/nginx/sites-available/assistant.i-tat.ru
server {
    listen 443 ssl http2;
    server_name assistant.i-tat.ru;

    # SSL сертификаты (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/assistant.i-tat.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/assistant.i-tat.ru/privkey.pem;

    # SSL настройки
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Заголовки безопасности
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    # Проксирование на внутренний сервер
    location / {
        proxy_pass http://10.10.100.3:8453;
        
        # ВАЖНО: Передача заголовков
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        
        # Таймауты
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Буферизация
        proxy_buffering off;
        proxy_request_buffering off;
    }

    # Максимальный размер загружаемых файлов
    client_max_body_size 50M;
}

# Редирект HTTP → HTTPS
server {
    listen 80;
    server_name assistant.i-tat.ru;
    return 301 https://$server_name$request_uri;
}
```

### Важные заголовки

Внешний прокси **ОБЯЗАТЕЛЬНО** должен передавать следующие заголовки:

- `X-Forwarded-For` - IP адрес клиента
- `X-Real-IP` - Реальный IP клиента
- `X-Forwarded-Proto: https` - Протокол (для правильной генерации URL)
- `Host` - Оригинальный хост (assistant.i-tat.ru)

Без этих заголовков:
- ❌ Webhook URL будут генерироваться неправильно
- ❌ Логи не будут содержать реальные IP клиентов
- ❌ Редиректы могут работать некорректно

## 🖥️ Внутренний сервер (10.10.100.3)

### Конфигурация приложения

**Файл `.env`:**

```bash
# Webhook URL (внешний домен)
HOST="https://assistant.i-tat.ru"

# Порт приложения (внутренний)
PROJECT_HOST="0.0.0.0"
PROJECT_PORT="8453"

# Webhook пути
WEBHOOK_PATH_MAX="/max/webhook"
WEBHOOK_PATH_MAIN="/telegram/webhook"

# Количество воркеров
COUNT_WORKERS="4"

# Режим работы
IS_LOCAL_BOT="False"
```

### Почему НЕ нужен Nginx на виртуалке?

1. **Конфликт портов:**
   - Внешний прокси уже слушает порты 80/443
   - Установка Nginx на виртуалке приведет к конфликту

2. **Избыточность:**
   - SSL уже обрабатывается внешним прокси
   - Статические файлы можно отдавать через FastAPI
   - Дополнительный слой прокси не нужен

3. **Упрощение:**
   - Меньше компонентов = проще поддержка
   - Прямое подключение uvicorn быстрее

### Когда Nginx на виртуалке может быть полезен?

Только если нужно:
- Отдавать статические файлы эффективнее
- Настроить кэширование на уровне виртуалки
- Балансировать нагрузку между несколькими инстансами

В этом случае Nginx должен слушать **другой порт** (например, 8080) и проксировать на 8453.

## 🔄 Поток запросов

### Webhook от MAX messenger

```
1. MAX API → https://assistant.i-tat.ru/max/webhook
   ↓
2. Внешний прокси (gitlab.i-tat.ru)
   • SSL-терминация
   • Добавление заголовков X-Forwarded-*
   ↓
3. HTTP → http://10.10.100.3:8453/max/webhook
   ↓
4. FastAPI приложение
   • Парсинг webhook
   • Обработка через maxapi Dispatcher
   • Ответ HTTP 200 OK
   ↓
5. Ответ → Внешний прокси → MAX API
```

### Административный доступ

```
1. Администратор подключается к PPTP VPN
   ↓
2. SSH → 10.10.100.3:22
   ↓
3. Управление сервисами, просмотр логов
```

## 🛠️ Развертывание

### Автоматическая установка

Скрипт `install.sh` автоматически определяет архитектуру:

```bash
cd /opt/i-tat-bot/deployment
sudo bash install.sh
```

При запросе "У вас есть ВНЕШНИЙ reverse proxy?" ответьте **Yes**.

Скрипт:
- ✅ Установит Python, PostgreSQL, Redis
- ✅ Настроит приложение на порт 8453
- ✅ Создаст systemd сервисы
- ❌ НЕ будет устанавливать Nginx
- ❌ НЕ будет настраивать SSL

### Ручная установка

Следуйте инструкциям в `QUICK_START.md`, но:
- Пропустите установку Nginx
- Используйте `HOST="https://assistant.i-tat.ru"` в `.env`
- Убедитесь, что `PROJECT_PORT="8453"`

## 🧪 Тестирование

### Проверка доступности изнутри

```bash
# На виртуалке
curl http://localhost:8453/
# Должен вернуть ответ от FastAPI

curl -X POST http://localhost:8453/max/webhook
# Должен вернуть 405 Method Not Allowed (нужен POST с данными)
```

### Проверка доступности снаружи

```bash
# С любого компьютера в интернете
curl https://assistant.i-tat.ru/
# Должен вернуть ответ от FastAPI

curl -X POST https://assistant.i-tat.ru/max/webhook
# Должен вернуть 405 Method Not Allowed
```

### Проверка webhook

```bash
# Отправить тестовый webhook
curl -X POST https://assistant.i-tat.ru/max/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'

# Проверить логи на виртуалке
sudo journalctl -u i-tat-bot -n 50 | grep webhook
```

### Проверка заголовков

```bash
# На виртуалке, в логах приложения должны быть:
sudo journalctl -u i-tat-bot -f

# При запросе снаружи должны появиться заголовки:
# X-Forwarded-For: <реальный IP>
# X-Real-IP: <реальный IP>
# X-Forwarded-Proto: https
```

## 🐛 Отладка

### Проблема: Webhook не работает

**Проверьте:**

1. Приложение слушает порт 8453:
   ```bash
   sudo netstat -tulpn | grep 8453
   ```

2. Firewall разрешает трафик:
   ```bash
   sudo ufw status
   ```

3. Внешний прокси настроен правильно:
   ```bash
   # На внешнем прокси
   curl http://10.10.100.3:8453/
   ```

4. Логи приложения:
   ```bash
   sudo journalctl -u i-tat-bot -f
   ```

### Проблема: Неправильные URL в webhook

**Причина:** Внешний прокси не передает заголовок `X-Forwarded-Proto`.

**Решение:** Добавьте в конфигурацию внешнего прокси:
```nginx
proxy_set_header X-Forwarded-Proto https;
```

### Проблема: Не работает SSH

**Причина:** Не подключен VPN.

**Решение:** Подключитесь к PPTP VPN перед попыткой SSH.

## 📊 Мониторинг

### Проверка статуса сервисов

```bash
# Все сервисы
sudo systemctl status i-tat-*

# Конкретный сервис
sudo systemctl status i-tat-bot
```

### Просмотр логов

```bash
# Реальное время
sudo journalctl -u i-tat-bot -f

# Последние 100 строк
sudo journalctl -u i-tat-bot -n 100

# Поиск ошибок
sudo journalctl -u i-tat-bot | grep -i error
```

### Проверка подключений

```bash
# Активные подключения к приложению
sudo netstat -an | grep 8453

# Подключения к PostgreSQL
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='itat_bot';"

# Подключения к Redis
redis-cli -a YourPassword INFO clients
```

## 🔒 Безопасность

### Рекомендации

1. **Firewall:**
   - Разрешить только необходимые порты
   - Ограничить доступ по IP

2. **SSH:**
   - Использовать ключи вместо паролей
   - Отключить root login
   - Использовать нестандартный порт (опционально)

3. **База данных:**
   - Слушать только localhost
   - Использовать сильные пароли
   - Регулярные бэкапы

4. **Redis:**
   - Установить пароль
   - Слушать только localhost
   - Отключить опасные команды

5. **Приложение:**
   - Регулярно обновлять зависимости
   - Мониторить логи на подозрительную активность
   - Использовать сильные секретные ключи

## 📞 Контакты

- **Документация:** `/opt/i-tat-bot/docs/`
- **GitHub:** https://github.com/aistrategiya/Aytat-bot
- **Логи:** `sudo journalctl -u i-tat-* -f`

## 🔄 История изменений

- **2024-03-09:** Добавлено описание архитектуры с внешним reverse proxy
- **2024-03-09:** Обновлен скрипт установки для поддержки двух режимов
