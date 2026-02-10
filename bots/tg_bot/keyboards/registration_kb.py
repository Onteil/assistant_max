"""
Registration Keyboards

Клавиатуры для процесса регистрации пользователей.
Включает кнопки для запроса контакта и отмены операции.
"""

from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bots.tg_bot.texts import BTN_CANCEL, BTN_SHARE_PHONE


async def get_phone_request_keyboard():
    """
    Создает клавиатуру для запроса номера телефона.
    
    Использует request_contact=True для получения номера телефона
    через встроенную функцию Telegram.
    
    Returns:
        ReplyKeyboardMarkup с кнопкой отправки контакта и кнопкой отмены
    
    Requirements: 1.1, 29.1, 29.2
    """
    builder = ReplyKeyboardBuilder()
    
    # Кнопка запроса контакта с request_contact=True
    builder.row(KeyboardButton(text=BTN_SHARE_PHONE, request_contact=True))
    
    # Кнопка отмены
    builder.row(KeyboardButton(text=BTN_CANCEL))
    
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


async def get_cancel_keyboard():
    """
    Создает простую клавиатуру с кнопкой отмены.
    
    Используется во время многошаговых процессов регистрации
    для предоставления пользователю возможности отменить операцию.
    
    Returns:
        ReplyKeyboardMarkup с кнопкой отмены
    
    Requirements: 28.1, 29.1, 29.2
    """
    builder = ReplyKeyboardBuilder()
    
    # Кнопка отмены
    builder.row(KeyboardButton(text=BTN_CANCEL))
    
    return builder.as_markup(resize_keyboard=True)
