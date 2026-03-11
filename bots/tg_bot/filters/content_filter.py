from aiogram.filters import BaseFilter
from aiogram.types import Message


class ContentFilter(BaseFilter):  # [1]
    def __init__(self, filter_type: str | list):  # [2]
        self.filter_type = filter_type

    async def __call__(self, message: Message) -> bool:  # [3]
        return message.content_type in self.filter_type
