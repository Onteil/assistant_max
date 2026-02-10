"""
Profile Management Keyboards

Клавиатуры для управления профилем пользователя.
Включает действия для добавления организаций, ключей, изменения телефона и настройки уведомлений.
"""

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bots.tg_bot.callback_datas import ProfileCallback
from bots.tg_bot.texts import (
    BTN_ADD_INN,
    BTN_ADD_KEY,
    BTN_CHANGE_PHONE,
    BTN_TOGGLE_NOTIFICATIONS,
)


async def get_profile_actions_keyboard():
    """
    Создает клавиатуру с действиями для управления профилем.
    
    Предоставляет кнопки для:
    - Добавления новой организации (ИНН)
    - Добавления нового ключа GS_Key
    - Изменения номера телефона
    - Переключения настроек уведомлений
    
    Returns:
        InlineKeyboardMarkup с кнопками действий профиля
    
    Requirements: 17.1, 18.1, 19.1, 20.1
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Добавить ИНН"
    builder.button(
        text=BTN_ADD_INN,
        callback_data=ProfileCallback(action="add_inn")
    )
    
    # Кнопка "Добавить ключ"
    builder.button(
        text=BTN_ADD_KEY,
        callback_data=ProfileCallback(action="add_key")
    )
    
    # Кнопка "Изменить телефон"
    builder.button(
        text=BTN_CHANGE_PHONE,
        callback_data=ProfileCallback(action="change_phone")
    )
    
    # Кнопка "Уведомления"
    builder.button(
        text=BTN_TOGGLE_NOTIFICATIONS,
        callback_data=ProfileCallback(action="toggle_notif")
    )
    
    # Размещаем по 2 кнопки в ряду для компактности
    builder.adjust(2)
    
    return builder.as_markup()
