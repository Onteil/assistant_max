from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiolimiter import AsyncLimiter

from constants import CONFIGS


class BotInReconstruction(BaseMiddleware):
    def __init__(self, default_rate: int = 1.6) -> None:
        self.limiters: dict[str, AsyncLimiter] = {}
        self.default_rate = default_rate

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if CONFIGS["BOT_ON_RECONSTRUCTION"]:
            await event.answer("Бот временно на реконструкции")
            return
        return await handler(event, data)
