# from typing import Any, Awaitable, Callable, Dict
# from aiogram import BaseMiddleware
# from aiogram.types import TelegramObject, Message, CallbackQuery
# from constants import ADMINS, get_session

# class AdminCheckMiddleware(BaseMiddleware):
#     """
#     Middleware для проверки прав администратора.
#     Отправляет сообщение с ID пользователя, если у него нет доступа.
#     """
#     async def __call__(
#         self,
#         handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
#         event: TelegramObject,
#         data: Dict[str, Any]
#     ) -> Any:
#         user = data.get("event_from_user")

#         if user is None:
#             return await handler(event, data)

#         is_admin = False
#         # Открываем сессию для получения данных о пользователе из БД
#         async with get_session() as session:
#             # Получаем пользователя из БД
#             db_user = await UserModel.get_by_user_id(session, user.id)

#             # Проверяем, существует ли пользователь в БД и имеет ли он нужную роль

#             if db_user and db_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
#                 is_admin = True
#                 # ВАЖНО: передаем объект пользователя из БД дальше в хендлеры
#                 # Это позволит не делать повторных запросов к базе
#                 data["db_user"] = db_user

#         if is_admin:
#             data["is_admin"] = True
#             return await handler(event, data)
#         else:
#             # <<< НАЧАЛО ИЗМЕНЕНИЙ >>>

#             # Формируем сообщение об отказе с ID пользователя
#             rejection_text = (
#                 "❌ *Доступ запрещен*\n\n"
#                 "У вас нет прав для выполнения этого действия.\n\n"
#                 "Если вы считаете, что это ошибка, сообщите ваш ID "
#                 "Главному администратору для предоставления доступа.\n\n"
#                 f"*Ваш Telegram ID:* ```{user.id}```"
#             )

#             # Определяем, как ответить пользователю
#             if isinstance(event, Message):
#                 await event.answer(rejection_text, parse_mode="Markdown")
#             elif isinstance(event, CallbackQuery):
#                 await event.message.answer(rejection_text, parse_mode="Markdown")
#                 await event.answer("Доступ запрещен.", show_alert=True)

#             # <<< КОНЕЦ ИЗМЕНЕНИЙ >>>

#             # Прерываем дальнейшую обработку
#             return
