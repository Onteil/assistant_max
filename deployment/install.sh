#!/bin/bash
# Автоматический скрипт установки i-TAT Bot
# Использование: sudo bash install.sh

set -e  # Выход при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Конфигурация
PROJECT_DIR="/opt/i-tat-bot"
REPO_URL="https://github.com/aistrategiya/Aytat-bot.git"
DB_NAME="itat_assistant"
DB_USER="itat_user"

# Функции для вывода
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "\n${BLUE}==== $1 ====${NC}\n"
}

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    print_error "Этот скрипт должен быть запущен с правами root (используйте sudo)"
    exit 1
fi

# Получение имени пользователя, который запустил sudo
REAL_USER=${SUDO_USER:-$USER}

print_step "Установка i-TAT Bot"
print_info "Репозиторий: $REPO_URL"
print_info "Директория: $PROJECT_DIR"
print_info "Пользователь: $REAL_USER"

# Шаг 1: Обновление системы
print_step "Шаг 1/10: Обновление системы"
apt update
apt upgrade -y

# Шаг 2: Установка зависимостей
print_step "Шаг 2/10: Установка системных пакетов"
apt install -y python3 python3-venv python3-pip postgresql redis-server git curl

# Nginx будет установлен позже, если нужен (в зависимости от архитектуры)

# Шаг 3: Настройка PostgreSQL
print_step "Шаг 3/10: Настройка PostgreSQL"

# Генерация случайного пароля для БД
DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)

print_info "Создание базы данных $DB_NAME..."
sudo -u postgres psql << EOF
-- Удаление существующей базы и пользователя (если есть)
DROP DATABASE IF EXISTS $DB_NAME;
DROP USER IF EXISTS $DB_USER;

-- Создание новой базы и пользователя
CREATE DATABASE $DB_NAME;
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOF

print_info "База данных создана. Пароль: $DB_PASSWORD"

# Шаг 4: Настройка Redis
print_step "Шаг 4/10: Настройка Redis"

# Генерация пароля для Redis
REDIS_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)

print_info "Настройка пароля Redis..."
sed -i "s/# requirepass foobared/requirepass $REDIS_PASSWORD/" /etc/redis/redis.conf
systemctl restart redis-server
systemctl enable redis-server

print_info "Redis настроен. Пароль: $REDIS_PASSWORD"

# Шаг 5: Клонирование репозитория
print_step "Шаг 5/10: Клонирование репозитория"

if [ -d "$PROJECT_DIR" ]; then
    print_warning "Директория $PROJECT_DIR уже существует"
    read -p "Удалить и клонировать заново? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$PROJECT_DIR"
    else
        print_error "Установка прервана"
        exit 1
    fi
fi

print_info "Клонирование из $REPO_URL..."
git clone "$REPO_URL" "$PROJECT_DIR"
chown -R $REAL_USER:$REAL_USER "$PROJECT_DIR"

# Шаг 6: Создание виртуального окружения
print_step "Шаг 6/10: Настройка Python окружения"

cd "$PROJECT_DIR"
sudo -u $REAL_USER python3 -m venv venv
sudo -u $REAL_USER bash -c "source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

print_info "Python окружение настроено"

# Шаг 7: Создание конфигурации
print_step "Шаг 7/10: Создание конфигурации"

# Генерация секретных ключей
ADMIN_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
WEBHOOK_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# Запрос обязательных параметров
print_info "Введите обязательные параметры:"

read -p "Домен или IP сервера (например, https://bot.example.com): " HOST
read -p "MAX Bot Token: " MAX_BOT_TOKEN
read -p "Telegram Bot Token (или Enter для пропуска): " TG_BOT_TOKEN
read -p "i-TAT API Username: " ITAT_USERNAME
read -sp "i-TAT API Password: " ITAT_PASSWORD
echo
read -p "Имя администратора: " ADMIN_NAME
read -p "MAX User ID администратора: " ADMIN_MAX_ID
read -p "Телефон администратора (+79991234567): " ADMIN_PHONE

# Создание .env файла
cat > "$PROJECT_DIR/.env" << EOF
# Токены ботов
MAX_BOT_TOKEN="$MAX_BOT_TOKEN"
TG_BOT_TOKEN="${TG_BOT_TOKEN:-}"
BOT_TOKEN="${TG_BOT_TOKEN:-}"
ACCESS_BOT_TOKEN="${TG_BOT_TOKEN:-}"

# Webhook
HOST="$HOST"
WEBHOOK_PATH="/bot{token}"
WEBHOOK_PATH_MAIN="/telegram/webhook"
WEBHOOK_PATH_MAX="/max/webhook"
WEBHOOK_URL="\${HOST}\${WEBHOOK_PATH}"

# База данных
DB_URL="postgresql+asyncpg://$DB_USER:$DB_PASSWORD@localhost/$DB_NAME"

# Redis
REDIS_HOST="localhost"
REDIS_PORT="6379"
REDIS_PASSWORD="$REDIS_PASSWORD"
REDIS="redis://:\${REDIS_PASSWORD}@\${REDIS_HOST}:\${REDIS_PORT}"
CELERY_REDIS_DB_NUMBER="0"
AIOGRAM_REDIS_DB_NUMBER="1"

# i-TAT API
ITAT_API_BASE_URL="http://i1.i-tat.ru:33080/sa-001-itatka/hs/dispatcher/v1"
ITAT_API_USERNAME="$ITAT_USERNAME"
ITAT_API_PASSWORD="$ITAT_PASSWORD"
USE_MOCK_ITAT_API="false"

# Безопасность
ADMIN_SECRET_KEY="$ADMIN_SECRET"
WEBHOOK_API_KEY="$WEBHOOK_API_KEY"
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="$(openssl rand -base64 16)"

# Начальные администраторы
INITIAL_ADMINS='[{"max_user_id": $ADMIN_MAX_ID, "tg_user_id": null, "full_name": "$ADMIN_NAME", "position": "Администратор", "phone_number": "$ADMIN_PHONE"}]'

# Настройки сервера
PROJECT_HOST="0.0.0.0"
PROJECT_PORT="8453"
IS_LOCAL_BOT="False"
COUNT_WORKERS="4"
LOG_LEVEL="info"
ALLOWED_HOSTS=["*"]

# Прочее
BOT_IN_RECONSTRUCTION="False"
ERROR_CHANNEL=""
HTTP_PROXY=""
HTTPS_PROXY=""
AIOGRAM_SECRET=""
GOOGLE_SERVICE_ACCOUNT_PATH="services/google/secret.json"
REGISTRATION_APPROVE_METHOD="bot"
EOF

chmod 600 "$PROJECT_DIR/.env"
chown $REAL_USER:$REAL_USER "$PROJECT_DIR/.env"

print_info "Конфигурация создана"
print_warning "Пароль админ-панели сохранен в .env (ADMIN_PASSWORD)"

# Шаг 8: Применение миграций
print_step "Шаг 8/10: Инициализация базы данных"

cd "$PROJECT_DIR"
sudo -u $REAL_USER bash -c "source venv/bin/activate && alembic upgrade head"

print_info "База данных инициализирована"

# Шаг 9: Установка systemd сервисов
print_step "Шаг 9/10: Установка systemd сервисов"

cd "$PROJECT_DIR/deployment"
bash setup-services.sh

# Шаг 10: Проверка архитектуры и настройка Nginx
print_step "Шаг 10/10: Настройка веб-сервера"

print_warning "ВАЖНО: Проверка архитектуры развертывания"
echo ""
echo "Ваша инфраструктура использует внешний reverse proxy?"
echo "  - Внешний прокси управляет SSL/HTTPS (порт 443)"
echo "  - Пересылает HTTP на внутренний IP:порт"
echo "  - Приложение слушает только внутренний порт (8453)"
echo ""
read -p "У вас есть ВНЕШНИЙ reverse proxy (например, на gitlab.i-tat.ru)? (y/n) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Режим: Внешний reverse proxy обнаружен"
    print_warning "Nginx НЕ будет установлен (порты 80/443 заняты внешним прокси)"
    print_info "Приложение будет слушать порт 8453 для внутренних запросов"
    
    # Удаляем nginx из установленных пакетов, если он был установлен
    if systemctl is-active --quiet nginx; then
        print_warning "Nginx уже запущен. Останавливаем..."
        systemctl stop nginx
        systemctl disable nginx
    fi
    
    print_info "✅ Конфигурация для внешнего прокси завершена"
    print_info "Убедитесь, что внешний прокси настроен на:"
    echo "  - Принимать HTTPS на assistant.i-tat.ru:443"
    echo "  - Пересылать на http://10.10.100.3:8453"
    echo "  - Передавать заголовки X-Forwarded-For, X-Real-IP, X-Forwarded-Proto"
else
    print_info "Режим: Прямое подключение (без внешнего прокси)"
    
    DOMAIN=$(echo $HOST | sed 's|https\?://||' | sed 's|/.*||')
    
    print_info "Настройка Nginx для домена: $DOMAIN"
    
    cat > /etc/nginx/sites-available/i-tat-bot << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        proxy_pass http://127.0.0.1:8453;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static/ {
        alias $PROJECT_DIR/api/static/;
        expires 30d;
    }

    location /media/ {
        alias $PROJECT_DIR/media/;
        expires 7d;
    }

echo -e "\n📝 Следующие шаги:"

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "1. Настройте внешний reverse proxy (gitlab.i-tat.ru):"
    echo "   - Принимать HTTPS на assistant.i-tat.ru:443"
    echo "   - Пересылать на http://10.10.100.3:8453"
    echo "   - Передавать заголовки: X-Forwarded-For, X-Real-IP, X-Forwarded-Proto"
    echo ""
    echo "2. Откройте порт 8453 на firewall (если нужно):"
    echo "   sudo ufw allow from <IP_внешнего_прокси> to any port 8453"
    echo ""
else
    echo "1. Настройте SSL сертификат:"
    echo "   sudo apt install certbot python3-certbot-nginx"
    echo "   sudo certbot --nginx -d $DOMAIN"
    echo ""
    echo "2. Настройте firewall:"
    echo "   sudo ufw allow 22/tcp"
    echo "   sudo ufw allow 80/tcp"
    echo "   sudo ufw allow 443/tcp"
    echo "   sudo ufw enable"
    echo ""
fi

echo "3. Проверьте статус сервисов:"
echo "   sudo systemctl status i-tat-bot"
echo "   sudo systemctl status i-tat-celery-worker"
echo "   sudo systemctl status i-tat-celery-beat"
echo ""
echo "4. Просмотрите логи:"
echo "   sudo journalctl -u i-tat-bot -f"
echo ""
echo "5. Откройте админ-панель:"
echo "   $HOST/admin"
echo "" Пользователь: $DB_USER"
echo "  Пароль: $DB_PASSWORD"
echo ""
echo "Redis:"
echo "  Пароль: $REDIS_PASSWORD"
echo ""
echo "Админ-панель:"
echo "  URL: $HOST/admin"
echo "  Логин: admin"
echo "  Пароль: $(grep ADMIN_PASSWORD $PROJECT_DIR/.env | cut -d'"' -f2)"
echo ""
echo "Секретные ключи:"
echo "  ADMIN_SECRET_KEY: $ADMIN_SECRET"
echo "  WEBHOOK_API_KEY: $WEBHOOK_API_KEY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -e "\n📝 Следующие шаги:"
echo "1. Настройте SSL сертификат:"
echo "   sudo apt install certbot python3-certbot-nginx"
echo "   sudo certbot --nginx -d $DOMAIN"
echo ""
echo "2. Настройте firewall:"
echo "   sudo ufw allow 22/tcp"
echo "   sudo ufw allow 80/tcp"
echo "   sudo ufw allow 443/tcp"
echo "   sudo ufw enable"
echo ""
echo "3. Проверьте статус сервисов:"
echo "   sudo systemctl status i-tat-bot"
echo "   sudo systemctl status i-tat-celery-worker"
echo "   sudo systemctl status i-tat-celery-beat"
echo ""
echo "4. Просмотрите логи:"
echo "   sudo journalctl -u i-tat-bot -f"
echo ""
echo "5. Откройте админ-панель:"
echo "   $HOST/admin"
echo ""

print_info "Документация: $PROJECT_DIR/deployment/"
print_info "Конфигурация: $PROJECT_DIR/.env"

echo -e "\n${GREEN}Готово! 🚀${NC}\n"
