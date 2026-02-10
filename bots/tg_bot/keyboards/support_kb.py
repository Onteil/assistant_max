"""
Technical Support Keyboards

Клавиатуры для процесса технической поддержки.
Включает выбор контекста ключа и предложение продления подписки.
"""

import math

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bots.tg_bot.callback_datas import KeyCallback
from bots.tg_bot.texts import BTN_CONTACT_MANAGER, BTN_DONT_KNOW

# Константы для пагинации
ITEMS_PER_PAGE = 8


async def get_key_context_keyboard(keys: list, page: int = 0):
    """
    Создает клавиатуру для выбора ключа в контексте проблемы.
    
    Позволяет пользователю указать, с каким ключом связана проблема,
    или пропустить этот шаг, если не уверен.
    
    Args:
        keys: Список объектов GS_Key из базы данных
        page: Текущая страница (начиная с 0)
    
    Returns:
        InlineKeyboardMarkup с ключами и опцией "Не знаю / Пропустить"
    
    Requirements: 14.2, 14.4
    """
    builder = InlineKeyboardBuilder()
    
    # Пагинация
    total_pages = math.ceil(len(keys) / ITEMS_PER_PAGE) if keys else 1
    start_index = page * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    keys_on_page = keys[start_index:end_index]
    
    # Кнопки ключей
    for key in keys_on_page:
        key_text = key.key_number
        
        # Добавляем статус конфликта если есть
        if key.conflict_status.value == "pending_review":
            key_text += " ⚠️"
        
        builder.button(
            text=key_text,
            callback_data=KeyCallback(action="select", key_id=key.id)
        )
    
    # Размещаем по одной кнопке в ряду для читаемости
    builder.adjust(1)
    
    # Кнопки пагинации (если страниц больше одной)
    if total_pages > 1:
        pagination_row = []
        
        if page > 0:
            pagination_row.append(
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data=KeyCallback(action="page", page=page - 1).pack()
                )
            )
        
        pagination_row.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data="noop"
            )
        )
        
        if page < total_pages - 1:
            pagination_row.append(
                InlineKeyboardButton(
                    text="Вперед ▶️",
                    callback_data=KeyCallback(action="page", page=page + 1).pack()
                )
            )
        
        builder.row(*pagination_row)
    
    # Кнопка "Не знаю / Пропустить"
    builder.row(
        InlineKeyboardButton(
            text=BTN_DONT_KNOW,
            callback_data=KeyCallback(action="skip").pack()
        )
    )
    
    return builder.as_markup()


async def get_renewal_offer_keyboard():
    """
    Создает клавиатуру для предложения продления подписки.
    
    Используется когда у пользователя истекла подписка на техподдержку.
    Предлагает связаться с менеджером для продления.
    
    Returns:
        InlineKeyboardMarkup с кнопкой связи с менеджером
    
    Requirements: 12.3
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Связаться с менеджером"
    builder.button(
        text=BTN_CONTACT_MANAGER,
        callback_data=KeyCallback(action="contact_manager")
    )
    
    return builder.as_markup()
