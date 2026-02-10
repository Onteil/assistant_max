"""
Handlers Package

Паттерн: Модульная организация обработчиков
- Разделяйте handlers по типам (commands, callbacks, messages)
- Каждый модуль имеет свой Router
- Все роутеры объединяются в главный tg_bot_router
"""

from aiogram import Router

from .callbacks import router as callbacks_router
from .cancel import router as cancel_router
from .commands import router as commands_router
from .invoice import router as invoice_router
from .messages import router as messages_router
from .profile import router as profile_router
from .registration import router as registration_router
from .support import router as support_router

# Главный роутер для всего бота
tg_bot_router = Router(name="tg_bot_main")

# Регистрация всех дочерних роутеров
# Cancel router should be first to handle /cancel in any state
# Registration router should be second to handle /start command
tg_bot_router.include_routers(
    cancel_router,
    registration_router,
    invoice_router,
    support_router,
    profile_router,
    commands_router,
    callbacks_router,
    messages_router
)

__all__ = ["tg_bot_router"]
