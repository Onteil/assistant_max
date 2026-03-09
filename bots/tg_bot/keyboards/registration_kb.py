"""
Registration Keyboards

Клавиатуры для процесса регистрации пользователей.
Включает кнопки для запроса контакта и отмены операции.
"""

from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bots.tg_bot.texts import (
    BTN_CANCEL,
    BTN_SHARE_PHONE,
    BTN_SKIP,
    BTN_ENTER_ANOTHER_KEY,
    BTN_CONTINUE_REGISTRATION,
)


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


async def get_skip_cancel_keyboard():
    """
    Создает клавиатуру с кнопками пропуска и отмены.
    
    Используется для опциональных шагов регистрации,
    где пользователь может пропустить ввод данных.
    
    Returns:
        ReplyKeyboardMarkup с кнопками пропуска и отмены
    """
    builder = ReplyKeyboardBuilder()
    
    # Кнопка пропуска
    builder.row(KeyboardButton(text=BTN_SKIP))
    
    # Кнопка отмены
    builder.row(KeyboardButton(text=BTN_CANCEL))
    
    return builder.as_markup(resize_keyboard=True)


async def get_key_conflict_keyboard():
    """
    Создает клавиатуру для выбора действия при конфликте ключа.
    
    Предлагает пользователю:
    - Ввести другой ключ Гранд-сметы
    - Продолжить регистрацию (создастся заявка на конфликт)
    
    Returns:
        ReplyKeyboardMarkup с кнопками выбора
    """
    builder = ReplyKeyboardBuilder()
    
    # Кнопка ввода другого ключа
    builder.row(KeyboardButton(text=BTN_ENTER_ANOTHER_KEY))
    
    # Кнопка продолжения регистрации
    builder.row(KeyboardButton(text=BTN_CONTINUE_REGISTRATION))
    
    return builder.as_markup(resize_keyboard=True)
