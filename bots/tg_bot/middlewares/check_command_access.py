from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from models.user import UserModel, UserRole
from sqlalchemy.orm import selectinload

from constants import CONTROLLED_COMMANDS, get_session

CONTROLLED_COMMAND_NAMES = {cmd.command.lstrip("/") for cmd in CONTROLLED_COMMANDS}


class PermissionCheckMiddleware(BaseMiddleware):
    """
    Middleware для проверки прав доступа.
    Автоматически извлекает команду из сообщения и проверяет права на нее.
    Пропускает все, что не является командой.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:

        # 1. Проверяем, что это вообще сообщение от пользователя
        if not isinstance(event, Message) or not event.text:
            # Если это не сообщение (например, CallbackQuery) или в нем нет текста,
            # то этот middleware ничего не делает.
            return await handler(event, data)

        # 2. Проверяем, является ли сообщение командой
        if not event.text.startswith("/"):
            # Это обычный текст, фото, и т.д. - пропускаем.
            return await handler(event, data)

        # 3. Извлекаем команду из текста
        # Например, из "/start args" получится "start"
        command_name = event.text.split()[0][1:].split("@")[0]

        if command_name not in CONTROLLED_COMMAND_NAMES:
            # Эта команда (например, /start) не входит в список контролируемых.
            # Пропускаем ее без проверки прав.
            return await handler(event, data)

        # 4. Получаем пользователя из БД
        # (Предполагается, что у вас есть UserDBMiddleware, который кладет db_user в data)
        db_user: UserModel | None = data.get("db_user")
        if not db_user:
            user = data.get("event_from_user")
            if not user:
                return await handler(event, data)
            async with get_session() as session:
                db_user = await UserModel.get_by_user_id(session, user.id)

        # 5. Проверяем права доступа

        # SUPER_ADMIN имеет доступ ко всему, дальнейшая проверка не нужна
        if db_user.role == UserRole.SUPER_ADMIN:
            return await handler(event, data)

        # Для обычного ADMIN'а нужна проверка
        if db_user.role == UserRole.ADMIN:
            has_permission = False
            async with get_session() as session:
                # Перезапрашиваем пользователя с его правами, чтобы они были актуальны
                user_with_perms = await session.get(
                    UserModel, db_user.id, options=[selectinload(UserModel.permissions)]
                )

                # Проверяем, есть ли у него разрешение на извлеченную команду
                for perm in user_with_perms.permissions:
                    if perm.command_name == command_name:
                        has_permission = True
                        break

            if has_permission:
                # Право есть, продолжаем выполнение
                return await handler(event, data)

        rejection_text = (
            f"❌ *Доступ к команде запрещен*\n\n"
            f"У вас нет прав для выполнения команды `/{command_name}`.\n\n"
            "Обратитесь к Главному администратору для получения доступа."
        )
        await event.answer(rejection_text, parse_mode="HTML")

        # Прерываем дальнейшую обработку
        return
