import multiprocessing
import os
from ast import literal_eval
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from aiogram.types import BotCommand
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker

load_dotenv(override=True)

# Import Base from database.models to ensure single source of truth
from database.models import Base

DB_URL = os.getenv("DB_URL")
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")


MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")

_raw_bot_mode = os.getenv("BOT_MODE", "").strip().lower()
_bot_mode_aliases = {
    "all": "both",
    "both": "both",
    "telegram": "tg",
    "tg": "tg",
    "max": "max",
    "none": "none",
    "off": "none",
    "disabled": "none",
}

if _raw_bot_mode:
    if _raw_bot_mode not in _bot_mode_aliases:
        raise ValueError("BOT_MODE must be one of: tg, max, both, none")
    BOT_MODE = _bot_mode_aliases[_raw_bot_mode]
elif TG_BOT_TOKEN and MAX_BOT_TOKEN:
    BOT_MODE = "both"
elif MAX_BOT_TOKEN:
    BOT_MODE = "max"
elif TG_BOT_TOKEN:
    BOT_MODE = "tg"
else:
    BOT_MODE = "none"

ENABLE_TG_BOT = BOT_MODE in {"tg", "both"} and bool(TG_BOT_TOKEN)
ENABLE_MAX_BOT = BOT_MODE in {"max", "both"} and bool(MAX_BOT_TOKEN)

HOST = os.getenv("HOST")

REDIS = os.getenv("REDIS")

ERROR_CHANNEL = os.getenv("ERROR_CHANNEL")
BOT_IN_RECONSTRUCTION = True if os.getenv("BOT_IN_RECONSTRUCTION") == "True" else False
PROJECT_HOST = os.getenv("PROJECT_HOST")
PROJECT_PORT = int(os.getenv("PROJECT_PORT"))
IS_LOCAL_BOT = literal_eval(os.getenv("IS_LOCAL_BOT"))
COUNT_WORKERS = int(os.getenv("COUNT_WORKERS"))


DEBUG = literal_eval(os.getenv("DEBUG"))
SQL_ECHO = DEBUG and IS_LOCAL_BOT

# Webhook paths - MAX webhook is the primary webhook after migration
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")
WEBHOOK_PATH_MAIN = os.getenv("WEBHOOK_PATH_MAIN")  # MAX webhook path (primary)
WEBHOOK_PATH_MAX = os.getenv("WEBHOOK_PATH_MAX")    # Alias for MAX webhook path
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

LOG_LEVEL = os.getenv("LOG_LEVEL")
ALLOWED_HOSTS = literal_eval(os.getenv("ALLOWED_HOSTS"))
CELERY_REDIS_DB_NUMBER = int(os.getenv("CELERY_REDIS_DB_NUMBER"))
AIOGRAM_REDIS_DB_NUMBER = int(os.getenv("AIOGRAM_REDIS_DB_NUMBER"))

AIOGRAM_SECRET = os.getenv("AIOGRAM_SECRET")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))

# 1С/CRM API настройки
ITAT_API_BASE_URL = os.getenv("ITAT_API_BASE_URL", "https://api.i-tat.ru")
ITAT_API_USERNAME = os.getenv("ITAT_API_USERNAME", "")
ITAT_API_PASSWORD = os.getenv("ITAT_API_PASSWORD", "")

# Локальная разработка: изолированное подключение через VPN + SSH SOCKS5 туннель
LOCAL_DEV = os.getenv("LOCAL_DEV", "false").lower() == "true"
ITAT_SSH_HOST = os.getenv("ITAT_SSH_HOST", "")
ITAT_SSH_LOGIN = os.getenv("ITAT_SSH_LOGIN", "")
ITAT_SSH_PASSWORD = os.getenv("ITAT_SSH_PASSWORD", "")
ITAT_SSH_SOCKS5_PORT = int(os.getenv("ITAT_SSH_SOCKS5_PORT", "1080"))
ITAT_VPN_HOST = os.getenv("ITAT_VPN_HOST", "")

# Registration Approval Method
# Options: "bot" (approve in bot), "crm" (approve via 1C/CRM webhook)
REGISTRATION_APPROVE_METHOD = os.getenv("REGISTRATION_APPROVE_METHOD", "bot").lower()

# CRM Webhook API Key for authentication
WEBHOOK_API_KEY = os.getenv("WEBHOOK_API_KEY", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ALLOWED_UPDATES = ["message", "callback_query", "inline_query", "chat_member", "my_chat_member", "photo", "video"]

# Admin Access
admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMINS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip().isdigit()]
AUTH_COOKIE_NAME = "admin_session"

CONFIGS = {
    "BOT_ON_RECONSTRUCTION": BOT_IN_RECONSTRUCTION,
}


# ========== Database Configuration ==========

# Create async engine with connection pooling
engine = create_async_engine(
    DB_URL,
    echo=SQL_ECHO,
    pool_size=10,  # Connection pool size
    max_overflow=20,  # Maximum overflow connections
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async generator for database sessions (for FastAPI Depends).
    
    Usage in FastAPI:
        @router.post("/endpoint")
        async def endpoint(session: Annotated[AsyncSession, Depends(get_session)]):
            result = await session.execute(query)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


CONTROLLED_COMMANDS = [
    # BotCommand(command="/new_publish", description="Создание публикации"),
    # BotCommand(command="/t", description="Пост из видео"),
    # BotCommand(command="/clip_manager", description="Клипы"),
    # BotCommand(command="/schedule_manager", description="Планировщик"),
    # BotCommand(command="/rewrite_manager", description="Рерайт старых постов"),
    # BotCommand(command="/prompt_manager", description="Управление промптами"),
    # BotCommand(command="/social_manager", description="Управление соц. сетями"),
    # BotCommand(command="/admin_manager", description="Управление администраторами"),
    # BotCommand(command="/cover_manager", description="Управление стилем обложек"),
    # BotCommand(command="/ai_news", description="AI Новости"),
]

# --- Все команды, которые будут установлены для бота ---
# Включают в себя контролируемые и общие команды
ALL_BOT_COMMANDS = [
    BotCommand(command="/start", description="Начать использование"),
    # *CONTROLLED_COMMANDS, # Распаковываем список контролируемых команд
    # BotCommand(command="/generation", description="Режим генерации текста"),
    # BotCommand(command="/mod_test", description="Тестирование модерации"),
    # BotCommand(command="/ai_test", description="Тестирование AI Новостей"),
    # BotCommand(command="/clear_state", description="Перезагрузка бота"),
]


# Определяем, работаем ли мы на сервере
SERVER_MODE = not IS_LOCAL_BOT

# ============================================================================
# ГЛАВНЫЕ НАСТРОЙКИ ПРОИЗВОДИТЕЛЬНОСТИ
# ============================================================================

if SERVER_MODE:
    # --- Настройки для продакшен-сервера (стабильность в приоритете) ---

    # СКОЛЬКО ПАРАЛЛЕЛЬНЫХ ПРОЦЕССОВ ЗАПУСКАТЬ ОДНОВРЕМЕННО.
    # Главный параметр для защиты CPU. 2-4 - безопасное значение для общего сервера.
    MAX_PARALLEL_WORKERS = 1

else:
    # --- Настройки для локальной разработки (скорость в приоритете) ---

    # Используем все доступные ядра
    MAX_PARALLEL_WORKERS = multiprocessing.cpu_count() or 4


ESCALATION_REMINDER_TIMEOUT = 600
ESCALATION_TIMEOUT = 1200
