import asyncio

from aiogram import BaseMiddleware
from aiogram.types import Message


class AlbumMiddleware(BaseMiddleware):
    """Middleware для обработки альбомов медиа, включая одиночные фото."""

    def __init__(self, latency: int | float = 0.5):
        """
        Латентность может быть настроена для правильной обработки альбомов при высокой нагрузке.
        """
        super().__init__()
        self.latency = latency
        self.album_data = {}

    async def __call__(self, handler, event: Message, data: dict):
        # Если у сообщения есть media_group_id, это часть альбома
        if event.media_group_id:
            if event.media_group_id in self.album_data:
                self.album_data[event.media_group_id].append(event)
                return  # Пропускаем обработку текущего сообщения

            # Создаем новый альбом и ждем другие сообщения
            self.album_data[event.media_group_id] = [event]
            await asyncio.sleep(self.latency)

            # Устанавливаем флаг последнего сообщения
            data["is_last"] = True
            data["album"] = self.album_data.pop(event.media_group_id)
        else:
            # Если media_group_id нет, обрабатываем одиночное фото как альбом из одного элемента
            data["is_last"] = True
            data["album"] = [event]

        await handler(event, data)
