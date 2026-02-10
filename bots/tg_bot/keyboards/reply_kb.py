"""
Reply Keyboards

Паттерн: Создание reply клавиатур для быстрого доступа
- Используйте ReplyKeyboardBuilder для гибкости
- Всегда используйте resize_keyboard=True для адаптации
- Группируйте кнопки логически
"""

from aiogram.types import KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import ReplyKeyboardBuilder


async def create_main_menu_keyboard():
    """
    Создает главное меню с основными командами.

    Returns:
        ReplyKeyboardMarkup с главным меню
    """
    builder = ReplyKeyboardBuilder()

    buttons = ["📋 Каталог", "ℹ️ Информация", "⚙️ Настройки", "📞 Поддержка"]

    builder.row(*[KeyboardButton(text=text) for text in buttons], width=2)

    return builder.as_markup(resize_keyboard=True)


async def create_contact_keyboard():
    """
    Создает клавиатуру для запроса контакта.

    Returns:
        ReplyKeyboardMarkup с кнопкой отправки контакта
    """
    builder = ReplyKeyboardBuilder()

    builder.row(KeyboardButton(text="📱 Отправить контакт", request_contact=True))
    builder.row(KeyboardButton(text="❌ Отмена"))

    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def remove_keyboard():
    """
    Удаляет reply клавиатуру.

    Returns:
        ReplyKeyboardRemove
    """
    return ReplyKeyboardRemove()
