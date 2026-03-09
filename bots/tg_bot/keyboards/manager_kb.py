"""
Manager Interface Reply Keyboards

Reply клавиатуры для интерфейса менеджера.
Включает главное меню менеджера и навигационные кнопки.
"""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bots.tg_bot.texts import (
    BTN_ACTIVE_TICKETS,
    BTN_ADMIN_PANEL,
    BTN_ARCHIVE_SEARCH,
    BTN_EMPLOYEE_SETTINGS,
)


async def get_manager_menu_keyboard(is_admin: bool = False, focused_ticket_id: int | None = None) -> ReplyKeyboardMarkup:
    """
    Создает главное меню менеджера с reply клавиатурой.
    
    Args:
        is_admin: Флаг, является ли сотрудник администратором
        focused_ticket_id: ID заявки в фокусе (если есть)
    
    Returns:
        ReplyKeyboardMarkup с кнопками меню менеджера
    
    Requirements: 1.1, 1.5, 1.6
    """
    builder = ReplyKeyboardBuilder()
    
    # Кнопка "Активные заявки"
    builder.button(text=BTN_ACTIVE_TICKETS)
    
    # Кнопка "Архив обращений"
    builder.button(text=BTN_ARCHIVE_SEARCH)
    
    # # Кнопка "Настройки"
    # builder.button(text=BTN_EMPLOYEE_SETTINGS)
    
    # Кнопка "Админ-панель" только для администраторов
    if is_admin:
        builder.button(text=BTN_ADMIN_PANEL)
    
    # Кнопка "Снять фокус" если менеджер в режиме фокуса
    if focused_ticket_id:
        builder.button(text=f"❌ Снять фокус с заявки #{focused_ticket_id}")
    
    # Размещаем по 2 кнопки в ряду
    builder.adjust(2)
    
    return builder.as_markup(resize_keyboard=True)
