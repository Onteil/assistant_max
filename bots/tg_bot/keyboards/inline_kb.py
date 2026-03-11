"""
Inline Keyboards

Паттерн: Динамическое создание клавиатур с пагинацией
- Используйте InlineKeyboardBuilder для гибкого построения
- Выносите константы (размеры страниц) в начало файла
- Создавайте переиспользуемые функции для пагинации
- Используйте callback_data фабрики для type-safety
"""

import math

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bots.tg_bot.callback_datas import ExampleItemCallback, ExampleNavigationCallback

# Константы для пагинации
ITEMS_PER_PAGE = 10


async def create_paginated_keyboard(
    items: list[dict],
    page: int = 0,
    callback_factory=ExampleItemCallback,
    items_per_page: int = ITEMS_PER_PAGE,
    buttons_per_row: int = 2,
):
    """
    Универсальная функция для создания клавиатуры с пагинацией.

    Args:
        items: Список элементов для отображения (dict с 'id' и 'name')
        page: Текущая страница (начиная с 0)
        callback_factory: Фабрика callback_data
        items_per_page: Количество элементов на странице
        buttons_per_row: Количество кнопок в ряду

    Returns:
        InlineKeyboardMarkup с пагинацией
    """
    builder = InlineKeyboardBuilder()

    # Пагинация
    total_pages = math.ceil(len(items) / items_per_page)
    start_index = page * items_per_page
    end_index = start_index + items_per_page
    items_on_page = items[start_index:end_index]

    # Создание кнопок для элементов
    for item in items_on_page:
        builder.button(text=item["name"], callback_data=callback_factory(action="select", item_id=item["id"]))
    builder.adjust(buttons_per_row)

    # Кнопки пагинации
    if total_pages > 1:
        pagination_row = []

        if page > 0:
            pagination_row.append(
                InlineKeyboardButton(text="⬅️", callback_data=callback_factory(action="view", page=page - 1).pack())
            )

        pagination_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))

        if page < total_pages - 1:
            pagination_row.append(
                InlineKeyboardButton(text="➡️", callback_data=callback_factory(action="view", page=page + 1).pack())
            )

        builder.row(*pagination_row)

    # Кнопка отмены
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data=callback_factory(action="cancel").pack()))

    return builder.as_markup()


async def create_confirmation_keyboard(confirm_callback: str, cancel_callback: str):
    """
    Создает клавиатуру подтверждения действия.

    Args:
        confirm_callback: Callback data для подтверждения
        cancel_callback: Callback data для отмены

    Returns:
        InlineKeyboardMarkup с кнопками подтверждения
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=confirm_callback),
        InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_callback),
    )

    return builder.as_markup()


async def create_navigation_keyboard(back_action: str = "back"):
    """
    Создает простую навигационную клавиатуру.

    Args:
        back_action: Action для кнопки "Назад"

    Returns:
        InlineKeyboardMarkup с навигацией
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data=ExampleNavigationCallback(action=back_action).pack())
    )

    return builder.as_markup()
