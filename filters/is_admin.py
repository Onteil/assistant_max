from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from constants import ADMINS

router = Router()


class IsAdminFilter(Filter):
    async def __call__(self, message: Message | CallbackQuery) -> bool:
        return message.from_user.id in ADMINS
