from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import TelegramObject

from constants import get_session


class DatabaseSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Создаем сессию и добавляем её в data
        async with get_session() as session:
            data["session"] = session
            result = await handler(event, data)

        # Закрываем сессию после выполнения хендлера
        await session.close()
        return result
