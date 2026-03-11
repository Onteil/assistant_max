import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

logger = logging.getLogger(__name__)


class StateClearerMiddleware(BaseMiddleware):
    """
    Мидлварь для сброса состояния при получении глобальных команд (/start, /cancel и т.д.)
    независимо от текущего состояния. Эта мидлварь обрабатывает ТОЛЬКО объекты Message.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],  # event теперь Message
        event: Message,  # event теперь Message
        data: dict[str, Any],
    ) -> Any:

        # Поскольку мидлварь регистрируется на dp.message.outer_middleware,
        # event здесь всегда будет Message.
        # Поэтому проверки event.message и event.text не нужны,
        # достаточно проверить, что message.text существует и начинается с '/'.
        if event.text and event.text.startswith("/"):
            command_text = event.text.strip()
            print(command_text)
            global_commands = ["/clear_state"]  # Ваш список команд

            if command_text in global_commands:
                state: FSMContext = data.get("state")
                if state:
                    current_state = await state.get_state()
                    if current_state:
                        logger.info(
                            f"Middleware: User {event.from_user.id} used global command {command_text}. Clearing state {current_state}."
                        )
                        await state.clear()

        # Передаем управление следующему хэндлеру/мидлвари
        return await handler(event, data)
