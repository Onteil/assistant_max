"""
Проверка локальной настройки проекта после первичной установки.

Скрипт ничего не меняет в БД и не запускает ботов. Он проверяет:
- наличие ключевых файлов проекта;
- заполненность и формат `.env`;
- доступность PostgreSQL и Redis;
- состояние Alembic;
- синтаксис ключевых Python-файлов;
- наличие copy-paste примеров systemd/nginx.
"""

from __future__ import annotations

import argparse
import asyncio
import ast
import os
import py_compile
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

STARTUP_REQUIRED_KEYS = [
    "DB_URL",
    "PROJECT_HOST",
    "PROJECT_PORT",
    "IS_LOCAL_BOT",
    "COUNT_WORKERS",
    "DEBUG",
    "LOG_LEVEL",
    "ALLOWED_HOSTS",
    "HOST",
    "WEBHOOK_PATH_MAIN",
    "WEBHOOK_PATH_MAX",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS",
    "CELERY_REDIS_DB_NUMBER",
    "AIOGRAM_REDIS_DB_NUMBER",
]

INTEGER_KEYS = [
    "PROJECT_PORT",
    "COUNT_WORKERS",
    "REDIS_PORT",
    "CELERY_REDIS_DB_NUMBER",
    "AIOGRAM_REDIS_DB_NUMBER",
]

BOOLEAN_KEYS = [
    "IS_LOCAL_BOT",
    "DEBUG",
    "BOT_IN_RECONSTRUCTION",
]

SECURITY_RECOMMENDED_KEYS = [
    "WEBHOOK_API_KEY",
    "ADMIN_SECRET_KEY",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD",
]

PROJECT_FILES = [
    "main.py",
    "constants.py",
    "loaders.py",
    "requirements.txt",
    "pyproject.toml",
    "alembic.ini",
    "alembic/env.py",
    "structure.sql",
    ".env.example",
    "media",
    "deployment/systemd/i-tat-bot.service",
    "deployment/systemd/i-tat-celery-worker.service",
    "deployment/systemd/i-tat-celery-beat.service",
    "deployment/nginx/i-tat-bot.conf",
    "deployment/logrotate/i-tat-celery",
    "deployment/journald/10-i-tat-log-limits.conf",
]

PYTHON_FILES_TO_COMPILE = [
    "constants.py",
    "loaders.py",
    "main.py",
    "services/i_tat_service.py",
    "scripts/celery/check_celery_status.py",
]

BOT_MODE_ALIASES = {
    "all": "both",
    "both": "both",
    "telegram": "tg",
    "tg": "tg",
    "max": "max",
    "none": "none",
    "off": "none",
    "disabled": "none",
}


class Reporter:
    def __init__(self, strict: bool) -> None:
        self.strict = strict
        self.failures = 0
        self.warnings = 0

    def ok(self, message: str) -> None:
        print(f"[OK] {message}")

    def warn(self, message: str) -> None:
        self.warnings += 1
        print(f"[WARN] {message}")

    def fail(self, message: str) -> None:
        self.failures += 1
        print(f"[FAIL] {message}")

    def exit_code(self) -> int:
        if self.failures:
            return 1
        if self.strict and self.warnings:
            return 1
        return 0


def has_value(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


def parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None

    normalized = value.strip().strip('"').strip("'").lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def load_env(env_file: Path, reporter: Reporter) -> dict[str, str | None]:
    try:
        from dotenv import dotenv_values
    except ImportError:
        reporter.fail("Не установлен python-dotenv. Выполните `pip install -r requirements.txt`.")
        return {}

    if not env_file.exists():
        reporter.fail(f"Файл {env_file.name} не найден. Создайте его командой `Copy-Item .env.example .env`.")
        return {}

    values = dotenv_values(env_file)
    reporter.ok(f"Файл окружения найден: {env_file}")
    return dict(values)


def check_project_root(reporter: Reporter) -> None:
    if Path.cwd().resolve() != ROOT_DIR.resolve():
        reporter.warn(f"Скрипт лучше запускать из корня проекта: {ROOT_DIR}")

    missing = [path for path in PROJECT_FILES if not (ROOT_DIR / path).exists()]
    if missing:
        reporter.fail("Не найдены файлы проекта: " + ", ".join(missing))
    else:
        reporter.ok("Ключевые файлы проекта на месте")

    if (ROOT_DIR / ".env.dist").exists():
        reporter.warn("Найден `.env.dist`; актуальный шаблон должен быть только `.env.example`.")
    else:
        reporter.ok("`.env.dist` отсутствует, используется только `.env.example`")


def check_python_version(reporter: Reporter) -> None:
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 10):
        reporter.fail(f"Python {major}.{minor} не поддерживается, нужен Python 3.10+.")
    elif (major, minor) != (3, 10):
        reporter.warn(f"Используется Python {major}.{minor}; prod работает на Python 3.10.12.")
    else:
        reporter.ok(f"Версия Python подходит: {major}.{minor}.{sys.version_info.micro}")


def check_imports(reporter: Reporter) -> None:
    modules = [
        "alembic",
        "celery",
        "dotenv",
        "fastapi",
        "redis",
        "sqlalchemy",
        "uvicorn",
    ]
    missing: list[str] = []
    for module_name in modules:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(module_name)

    if missing:
        reporter.fail("Не установлены зависимости: " + ", ".join(missing))
    else:
        reporter.ok("Основные зависимости импортируются")


def check_env_values(env: dict[str, str | None], reporter: Reporter) -> None:
    if not env:
        return

    missing = [key for key in STARTUP_REQUIRED_KEYS if not has_value(env.get(key))]
    if missing:
        reporter.fail("Не заполнены обязательные переменные `.env`: " + ", ".join(missing))
    else:
        reporter.ok("Обязательные переменные `.env` для старта заполнены")

    for key in INTEGER_KEYS:
        value = env.get(key)
        if has_value(value):
            try:
                int(str(value))
            except ValueError:
                reporter.fail(f"`{key}` должен быть целым числом.")

    for key in BOOLEAN_KEYS:
        value = env.get(key)
        if has_value(value) and parse_bool(str(value)) is None:
            reporter.fail(f"`{key}` должен быть True/False.")

    allowed_hosts = env.get("ALLOWED_HOSTS")
    if has_value(allowed_hosts):
        try:
            parsed = ast.literal_eval(str(allowed_hosts))
            if not isinstance(parsed, list):
                reporter.fail("`ALLOWED_HOSTS` должен быть списком, например `[\"*\"]`.")
        except (SyntaxError, ValueError):
            reporter.fail("`ALLOWED_HOSTS` должен быть валидным Python-списком, например `[\"*\"]`.")

    db_url = env.get("DB_URL")
    if has_value(db_url) and not str(db_url).startswith("postgresql+asyncpg://"):
        reporter.warn("`DB_URL` лучше задавать в формате `postgresql+asyncpg://...`, как ожидает приложение.")

    redis_url = env.get("REDIS")
    if has_value(redis_url) and not str(redis_url).startswith(("redis://", "rediss://")):
        reporter.fail("`REDIS` должен начинаться с `redis://` или `rediss://`.")

    bot_mode = normalize_bot_mode(env, reporter)
    check_bot_tokens(bot_mode, env, reporter)
    check_itat_settings(env, reporter)
    check_recommended_security_keys(env, reporter)


def normalize_bot_mode(env: dict[str, str | None], reporter: Reporter) -> str:
    raw = str(env.get("BOT_MODE") or "").strip().lower()
    if raw:
        if raw not in BOT_MODE_ALIASES:
            reporter.fail("`BOT_MODE` должен быть одним из: tg, max, both, none.")
            return "invalid"
        mode = BOT_MODE_ALIASES[raw]
        reporter.ok(f"BOT_MODE={mode}")
        return mode

    has_tg = has_value(env.get("TG_BOT_TOKEN"))
    has_max = has_value(env.get("MAX_BOT_TOKEN"))
    if has_tg and has_max:
        mode = "both"
    elif has_max:
        mode = "max"
    elif has_tg:
        mode = "tg"
    else:
        mode = "none"

    reporter.warn(f"`BOT_MODE` не задан, приложение определит режим автоматически: {mode}.")
    return mode


def check_bot_tokens(bot_mode: str, env: dict[str, str | None], reporter: Reporter) -> None:
    if bot_mode == "invalid":
        return

    required_by_mode = {
        "tg": ["TG_BOT_TOKEN"],
        "max": ["MAX_BOT_TOKEN"],
        "both": ["TG_BOT_TOKEN", "MAX_BOT_TOKEN"],
        "none": [],
    }
    missing = [key for key in required_by_mode[bot_mode] if not has_value(env.get(key))]
    if missing:
        reporter.fail(f"Для BOT_MODE={bot_mode} не заполнены токены: " + ", ".join(missing))
    elif bot_mode == "none":
        reporter.warn("BOT_MODE=none: FastAPI/admin запустятся без ботов.")
    else:
        reporter.ok(f"Токены для BOT_MODE={bot_mode} заполнены")


def check_itat_settings(env: dict[str, str | None], reporter: Reporter) -> None:
    use_mock = parse_bool(str(env.get("USE_MOCK_ITAT_API") or "false"))
    if use_mock is True:
        reporter.ok("USE_MOCK_ITAT_API=true: реальные учетные данные i-TAT API не требуются")
        return

    missing = [key for key in ["ITAT_API_BASE_URL", "ITAT_API_USERNAME", "ITAT_API_PASSWORD"] if not has_value(env.get(key))]
    if missing:
        reporter.fail("Для реальных вызовов i-TAT API не заполнены: " + ", ".join(missing))
    else:
        reporter.ok("Настройки i-TAT API заполнены")


def check_recommended_security_keys(env: dict[str, str | None], reporter: Reporter) -> None:
    missing = [key for key in SECURITY_RECOMMENDED_KEYS if not has_value(env.get(key))]
    if missing:
        reporter.warn("Рекомендуется заполнить перед полноценным запуском: " + ", ".join(missing))
    else:
        reporter.ok("Ключи админки и webhook/API заполнены")


async def check_postgres(db_url: str | None, timeout: float, reporter: Reporter) -> None:
    if not has_value(db_url):
        reporter.fail("PostgreSQL не проверен: `DB_URL` пустой.")
        return

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError:
        reporter.fail("PostgreSQL не проверен: не установлены SQLAlchemy/asyncpg.")
        return

    engine = create_async_engine(str(db_url), pool_pre_ping=True)
    try:
        async def run_query() -> None:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

        await asyncio.wait_for(run_query(), timeout=timeout)
        reporter.ok("PostgreSQL доступен по DB_URL")
    except Exception as exc:  # noqa: BLE001
        reporter.fail(f"PostgreSQL недоступен: {exc.__class__.__name__}: {exc}")
    finally:
        await engine.dispose()


async def check_redis(redis_url: str | None, timeout: float, reporter: Reporter) -> None:
    if not has_value(redis_url):
        reporter.fail("Redis не проверен: `REDIS` пустой.")
        return

    try:
        from redis.asyncio import Redis
    except ImportError:
        reporter.fail("Redis не проверен: не установлен пакет `redis`.")
        return

    client = Redis.from_url(str(redis_url), socket_connect_timeout=timeout, socket_timeout=timeout)
    try:
        await asyncio.wait_for(client.ping(), timeout=timeout)
        reporter.ok("Redis доступен по REDIS")
    except Exception as exc:  # noqa: BLE001
        reporter.fail(f"Redis недоступен: {exc.__class__.__name__}: {exc}")
    finally:
        await client.aclose()


def run_command(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        args,
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def check_alembic(timeout: float, reporter: Reporter) -> None:
    heads = run_command([sys.executable, "-m", "alembic", "heads"], timeout)
    if heads.returncode != 0:
        reporter.fail("Alembic heads не выполняется: " + (heads.stderr or heads.stdout).strip())
        return

    head_revisions = [line.split()[0] for line in heads.stdout.splitlines() if line.strip()]
    if not head_revisions:
        reporter.fail("Alembic не вернул ни одной head-ревизии.")
        return

    reporter.ok("Alembic heads: " + ", ".join(head_revisions))

    current = run_command([sys.executable, "-m", "alembic", "current"], timeout)
    current_output = "\n".join(part for part in [current.stdout, current.stderr] if part).strip()
    if current.returncode != 0:
        reporter.fail("Alembic current не выполняется: " + current_output)
        return

    missing_heads = [revision for revision in head_revisions if revision not in current_output]
    if missing_heads:
        reporter.fail("БД не на head Alembic. Выполните `alembic upgrade head`.")
    else:
        reporter.ok("БД находится на актуальной Alembic head-ревизии")


def check_python_compile(reporter: Reporter) -> None:
    failed: list[str] = []
    for relative_path in PYTHON_FILES_TO_COMPILE:
        try:
            py_compile.compile(str(ROOT_DIR / relative_path), doraise=True)
        except py_compile.PyCompileError:
            failed.append(relative_path)

    if failed:
        reporter.fail("Ошибки синтаксиса в Python-файлах: " + ", ".join(failed))
    else:
        reporter.ok("Ключевые Python-файлы компилируются")


def check_deployment_examples(reporter: Reporter) -> None:
    nginx_config = ROOT_DIR / "deployment/nginx/i-tat-bot.conf"
    worker_service = ROOT_DIR / "deployment/systemd/i-tat-celery-worker.service"
    beat_service = ROOT_DIR / "deployment/systemd/i-tat-celery-beat.service"
    logrotate_config = ROOT_DIR / "deployment/logrotate/i-tat-celery"
    journald_config = ROOT_DIR / "deployment/journald/10-i-tat-log-limits.conf"

    if nginx_config.exists() and "assistant.i-tat.ru" in nginx_config.read_text(encoding="utf-8"):
        reporter.ok("Nginx example содержит prod-домен")
    else:
        reporter.fail("Nginx example отсутствует или не содержит prod-домен")

    worker_text = worker_service.read_text(encoding="utf-8") if worker_service.exists() else ""
    beat_text = beat_service.read_text(encoding="utf-8") if beat_service.exists() else ""

    if (
        "api_retries" in worker_text
        and "ticket_notifications" in worker_text
        and "--loglevel=info" in worker_text
        and "--concurrency=1" in worker_text
    ):
        reporter.ok("Celery worker systemd example похож на prod")
    else:
        reporter.fail("Celery worker systemd example не совпадает с ожидаемой prod-конфигурацией")

    if "celerybeat-schedule.db" in beat_text and "--loglevel=info" in beat_text:
        reporter.ok("Celery beat systemd example похож на prod")
    else:
        reporter.fail("Celery beat systemd example не совпадает с ожидаемой prod-конфигурацией")


    logrotate_text = (
        logrotate_config.read_text(encoding="utf-8")
        if logrotate_config.exists()
        else ""
    )
    if "daily" in logrotate_text and "rotate 14" in logrotate_text:
        reporter.ok("Celery logrotate example настроен")
    else:
        reporter.fail("Celery logrotate example отсутствует или некорректен")

    journald_text = (
        journald_config.read_text(encoding="utf-8")
        if journald_config.exists()
        else ""
    )
    if "SystemMaxUse=" in journald_text and "MaxRetentionSec=" in journald_text:
        reporter.ok("Journald limits example настроен")
    else:
        reporter.fail("Journald limits example отсутствует или некорректен")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка настройки i-TAT Bot после установки")
    parser.add_argument("--env-file", default=".env", help="Путь к env-файлу относительно корня проекта")
    parser.add_argument("--skip-db", action="store_true", help="Не проверять подключение к PostgreSQL")
    parser.add_argument("--skip-redis", action="store_true", help="Не проверять подключение к Redis")
    parser.add_argument("--skip-alembic", action="store_true", help="Не проверять Alembic current/head")
    parser.add_argument("--strict", action="store_true", help="Возвращать код 1 даже при предупреждениях")
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout для внешних проверок, секунд")
    args = parser.parse_args()

    reporter = Reporter(strict=args.strict)
    env_file = (ROOT_DIR / args.env_file).resolve()

    print("Проверка настройки i-TAT Bot")
    print(f"Корень проекта: {ROOT_DIR}")
    print()

    check_project_root(reporter)
    check_python_version(reporter)
    check_imports(reporter)

    env = load_env(env_file, reporter)
    check_env_values(env, reporter)
    check_python_compile(reporter)
    check_deployment_examples(reporter)

    if args.skip_db:
        reporter.warn("Проверка PostgreSQL пропущена")
    else:
        await check_postgres(env.get("DB_URL"), args.timeout, reporter)

    if args.skip_redis:
        reporter.warn("Проверка Redis пропущена")
    else:
        await check_redis(env.get("REDIS"), args.timeout, reporter)

    if args.skip_alembic:
        reporter.warn("Проверка Alembic пропущена")
    else:
        check_alembic(args.timeout, reporter)

    print()
    print(f"Итог: failures={reporter.failures}, warnings={reporter.warnings}")
    if reporter.exit_code() == 0:
        print("Настройка выглядит корректной.")
    else:
        print("Нужно исправить ошибки выше.")

    return reporter.exit_code()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
