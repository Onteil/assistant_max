"""
Main Menu Keyboards for MAX Bot

Клавиатуры главного меню для зарегистрированных пользователей.
Предоставляет доступ ко всем основным функциям бота.

Migrated from Telegram bot to MAX messenger.
"""

from maxapi.types import KeyboardButton
from maxapi.utils.reply_keyboard import ReplyKeyboardBuilder

from bots.max_bot.texts import (
    MENU_INVOICE,
    MENU_PROFILE,
    MENU_RATE_SERVICE,
    MENU_RENEWAL,
    MENU_SUPPORT,
)


async def get_main_menu_keyboard():
    """
    Создает клавиатуру главного меню с всеми доступными функциями.
    
    Отображается для пользователей со статусом ACTIVE после регистрации.
    Включает все основные функции бота согласно требованиям.
    
    Returns:
        ReplyKeyboardMarkup с кнопками главного меню
    
    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 29.1, 29.3
    """
    builder = ReplyKeyboardBuilder()

    # Первый ряд: Счет и Техподдержка
    builder.row(
        KeyboardButton(text=MENU_INVOICE),
        KeyboardButton(text=MENU_SUPPORT)
    )

    # Второй ряд: Продление и Оценка
    builder.row(
        KeyboardButton(text=MENU_RENEWAL),
        KeyboardButton(text=MENU_RATE_SERVICE)
    )

    # Третий ряд: Профиль
    builder.row(
        KeyboardButton(text=MENU_PROFILE)
    )

    return builder.as_markup(resize_keyboard=True)
