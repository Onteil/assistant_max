from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import CallbackQuery, TelegramObject, User
from aiolimiter import AsyncLimiter


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, default_rate: int = 1.6) -> None:
        self.limiters: dict[str, AsyncLimiter] = {}
        self.default_rate = default_rate

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        throttling_flag = get_flag(data["handler"], "rate_limit")
        if throttling_flag is None:
            throttling_flag = {}
        throttling_key = throttling_flag.get("key")
        throttling_rate = throttling_flag.get("rate", self.default_rate)

        if not throttling_key or not user:
            return await handler(event, data)

        limiter = self.limiters.setdefault(f"{user.id}:{throttling_key}", AsyncLimiter(1, throttling_rate))
        if limiter.has_capacity():
            async with limiter:
                return await handler(event, data)
        else:
            if isinstance(event, CallbackQuery):
                await event.answer("Не флуди! Подожди секунду!")
