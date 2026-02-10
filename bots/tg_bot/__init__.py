"""
Telegram Bot Package

Паттерн: Централизованный экспорт роутеров
- Все роутеры собираются в handlers/__init__.py
- Главный роутер экспортируется для регистрации в main.py
"""

from .handlers import tg_bot_router

__all__ = [
    "tg_bot_router",
]
