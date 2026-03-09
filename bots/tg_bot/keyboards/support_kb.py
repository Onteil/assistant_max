"""
Technical Support Keyboards

Клавиатуры для процесса технической поддержки.
Включает выбор контекста ключа и предложение продления подписки.
"""

import math

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bots.tg_bot.callback_datas import KeyCallback
from bots.tg_bot.texts import BTN_CONTACT_MANAGER, BTN_DONE, BTN_DONT_KNOW

# Константы для пагинации
ITEMS_PER_PAGE = 8


async def get_key_context_keyboard(keys: list, selected_key_ids: set[int], page: int = 0):
    """
    Создает клавиатуру для мультивыбора ключей в контексте проблемы.
    
    Поддерживает переключение выбора (toggle) с отображением галочек для выбранных ключей.
    Позволяет пользователю указать, с какими ключами связана проблема,
    или пропустить этот шаг, если не уверен.
    
    Args:
        keys: Список объектов GS_Key из базы данных
        selected_key_ids: Множество ID выбранных ключей
        page: Текущая страница (начиная с 0)
    
    Returns:
        InlineKeyboardMarkup с ключами, галочками и навигацией
    
    Requirements: 14.2, 14.4
    """
    builder = InlineKeyboardBuilder()
    
    # Пагинация
    total_pages = math.ceil(len(keys) / ITEMS_PER_PAGE) if keys else 1
    start_index = page * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    keys_on_page = keys[start_index:end_index]
    
    # Кнопки ключей с галочками для выбранных
    for key in keys_on_page:
        # Добавляем галочку если ключ выбран
        checkmark = "✅ " if key.id in selected_key_ids else ""
        key_text = f"{checkmark}{key.key_number}"
        
        # Добавляем статус конфликта если есть
        if key.conflict_status.value == "pending_review":
            key_text += " ⚠️"
        
        builder.button(
            text=key_text,
            callback_data=KeyCallback(action="toggle", key_id=key.id)
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
    
    # Кнопка "Добавить другой ключ"
    builder.row(
        InlineKeyboardButton(
            text="➕ Другой ключ",
            callback_data=KeyCallback(action="add_new").pack()
        )
    )
    
    # Кнопка "Готово" (только если есть выбранные ключи)
    if selected_key_ids:
        builder.row(
            InlineKeyboardButton(
                text=BTN_DONE,
                callback_data=KeyCallback(action="done").pack()
            )
        )
    
    # Кнопка "Не знаю / Пропустить"
    builder.row(
        InlineKeyboardButton(
            text=BTN_DONT_KNOW,
            callback_data=KeyCallback(action="skip").pack()
        )
    )
    
    # Кнопки навигации
    nav_row = []
    nav_row.append(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=KeyCallback(action="back").pack()
        )
    )
    nav_row.append(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=KeyCallback(action="cancel").pack()
        )
    )
    builder.row(*nav_row)
    
    return builder.as_markup()


async def get_renewal_offer_keyboard():
    """
    Создает клавиатуру для предложения продления подписки.
    
    Используется когда у пользователя истекла подписка на техподдержку.
    Предлагает оформить заявку на продление.
    
    Returns:
        InlineKeyboardMarkup с кнопкой создания заявки
    
    Requirements: 12.3, 4.6, 4.8
    """
    from bots.tg_bot.callback_datas import RenewalCallback
    from bots.tg_bot.texts import BTN_CREATE_RENEWAL_REQUEST
    
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Оформить заявку на продление"
    builder.row(
        InlineKeyboardButton(
            text=BTN_CREATE_RENEWAL_REQUEST,
            callback_data=RenewalCallback(action="contact_manager").pack()
        )
    )
    
    return builder.as_markup()



async def get_problem_description_keyboard():
    """
    Создает клавиатуру для шага ввода описания проблемы.
    
    Предоставляет кнопку "Отмена".
    
    Returns:
        InlineKeyboardMarkup с навигационной кнопкой
    
    Requirements: 13.1-13.6
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Отмена"
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=KeyCallback(action="cancel").pack()
        )
    )
    
    return builder.as_markup()


async def get_add_key_keyboard():
    """
    Создает клавиатуру для шага добавления нового ключа.
    
    Предоставляет кнопки "Назад" и "Отмена".
    
    Returns:
        InlineKeyboardMarkup с навигационными кнопками
    
    Requirements: 14.3
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопки навигации
    nav_row = []
    nav_row.append(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=KeyCallback(action="back_to_keys").pack()
        )
    )
    nav_row.append(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=KeyCallback(action="cancel").pack()
        )
    )
    builder.row(*nav_row)
    
    return builder.as_markup()
