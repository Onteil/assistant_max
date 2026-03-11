"""
Main Menu Keyboards

Клавиатуры главного меню для зарегистрированных пользователей.
Предоставляет доступ ко всем основным функциям бота.
"""

from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bots.tg_bot.texts import (
    MENU_ARCHIVE,
    MENU_INVOICE,
    MENU_PROFILE,
    MENU_RATE_SERVICE,
    MENU_RENEWAL,
    MENU_SUPPORT,
)


async def get_main_menu_keyboard(active_tickets_count: int = 0):
    """
    Создает клавиатуру главного меню с всеми доступными функциями.
    
    Отображается для пользователей со статусом ACTIVE после регистрации.
    Включает все основные функции бота согласно требованиям.
    
    Args:
        active_tickets_count: Количество активных заявок клиента
    
    Returns:
        ReplyKeyboardMarkup с кнопками главного меню
    
    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 29.1, 29.3, AC-1.2, AC-1.3, TR-2
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
        # KeyboardButton(text=MENU_RATE_SERVICE)
        KeyboardButton(text=MENU_ARCHIVE)
    )
    
    # Третий ряд: Архив и Профиль
    builder.row(
        # KeyboardButton(text=MENU_ARCHIVE),
        KeyboardButton(text=MENU_PROFILE)
    )
    
    # Если есть активные заявки, добавить кнопку с количеством
    if active_tickets_count > 0:
        builder.row(
            KeyboardButton(text=f"📥 Активные обращения ({active_tickets_count})")
        )
    
    return builder.as_markup(resize_keyboard=True)
