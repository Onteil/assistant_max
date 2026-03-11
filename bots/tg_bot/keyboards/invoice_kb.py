"""
Invoice Request Keyboards

Клавиатуры для процесса запроса счетов.
Включает выбор организации, мультивыбор ключей и выбор способа доставки.
"""

import math

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bots.tg_bot.callback_datas import DeliveryCallback, KeyCallback, OrganizationCallback
from bots.tg_bot.texts import (
    BTN_ADD_ANOTHER_KEY,
    BTN_ADD_NEW_INN,
    BTN_DELIVERY_EMAIL,
    BTN_DELIVERY_TELEGRAM,
    BTN_DONE,
    BTN_SKIP,
)

# Константы для пагинации
ITEMS_PER_PAGE = 8


async def get_organization_keyboard(organizations: list, page: int = 0):
    """
    Создает клавиатуру для выбора организации с поддержкой пагинации.
    
    Отображает список организаций пользователя с ИНН.
    Включает кнопки "Добавить новый ИНН" и "Пропустить".
    
    Args:
        organizations: Список объектов Organization из базы данных
        page: Текущая страница (начиная с 0)
    
    Returns:
        InlineKeyboardMarkup с организациями и навигацией
    
    Requirements: 7.2, 7.3, 30.1-30.5, 31.1
    """
    builder = InlineKeyboardBuilder()
    
    # Пагинация
    total_pages = math.ceil(len(organizations) / ITEMS_PER_PAGE) if organizations else 1
    start_index = page * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    orgs_on_page = organizations[start_index:end_index]
    
    # Кнопки организаций
    for org in orgs_on_page:
        # Отображаем название организации и ИНН
        org_text = f"{org.organization_name or 'Организация'} (ИНН: {org.inn})"
        builder.button(
            text=org_text,
            callback_data=OrganizationCallback(action="select", inn=org.inn)
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
                    callback_data=OrganizationCallback(action="page", page=page - 1).pack()
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
                    callback_data=OrganizationCallback(action="page", page=page + 1).pack()
                )
            )
        
        builder.row(*pagination_row)
    
    # Кнопка "Добавить новый ИНН"
    builder.row(
        InlineKeyboardButton(
            text=BTN_ADD_NEW_INN,
            callback_data=OrganizationCallback(action="add_new").pack()
        )
    )
    
    # Кнопка "Пропустить"
    builder.row(
        InlineKeyboardButton(
            text=BTN_SKIP,
            callback_data=OrganizationCallback(action="skip").pack()
        )
    )
    
    # Кнопка "Отмена"
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=OrganizationCallback(action="cancel").pack()
        )
    )
    
    return builder.as_markup()


async def get_key_selection_keyboard(keys: list, selected_key_ids: set[int], page: int = 0):
    """
    Создает клавиатуру для мультивыбора ключей GS_Key с визуальными индикаторами.
    
    Поддерживает переключение выбора (toggle) с отображением галочек для выбранных ключей.
    Включает пагинацию для больших списков и кнопки управления.
    
    Args:
        keys: Список объектов GS_Key из базы данных
        selected_key_ids: Множество ID выбранных ключей
        page: Текущая страница (начиная с 0)
    
    Returns:
        InlineKeyboardMarkup с ключами, галочками и навигацией
    
    Requirements: 8.1, 8.2, 8.3, 8.5, 30.1-30.5, 31.2
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
    
    # Кнопка "Добавить еще ключ"
    builder.row(
        InlineKeyboardButton(
            text=BTN_ADD_ANOTHER_KEY,
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


async def get_delivery_method_keyboard():
    """
    Создает клавиатуру для выбора способа доставки счета.
    
    Предоставляет выбор между доставкой через Telegram или Email.
    
    Returns:
        InlineKeyboardMarkup с вариантами доставки
    
    Requirements: 9.3
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Telegram"
    builder.button(
        text=BTN_DELIVERY_TELEGRAM,
        callback_data=DeliveryCallback(method="telegram")
    )
    
    # Кнопка "Email"
    builder.button(
        text=BTN_DELIVERY_EMAIL,
        callback_data=DeliveryCallback(method="email")
    )
    
    # Размещаем кнопки в один ряд
    builder.adjust(2)
    
    # Кнопки навигации
    nav_row = []
    nav_row.append(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=DeliveryCallback(method="back").pack()
        )
    )
    nav_row.append(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=DeliveryCallback(method="cancel").pack()
        )
    )
    builder.row(*nav_row)
    
    return builder.as_markup()


async def get_email_input_keyboard():
    """
    Создает клавиатуру для шага ввода email.
    
    Предоставляет кнопки "Назад" и "Отмена".
    
    Returns:
        InlineKeyboardMarkup с навигационными кнопками
    
    Requirements: 9.4
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопки навигации
    nav_row = []
    nav_row.append(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=DeliveryCallback(method="back_to_delivery").pack()
        )
    )
    nav_row.append(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=DeliveryCallback(method="cancel").pack()
        )
    )
    builder.row(*nav_row)
    
    return builder.as_markup()


async def get_invoice_confirmation_keyboard():
    """
    Создает клавиатуру для подтверждения заявки на счет.
    
    Предоставляет кнопки "Подтвердить", "Заполнить заново" и "Отмена".
    
    Returns:
        InlineKeyboardMarkup с кнопками подтверждения
    
    Requirements: 9.5
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Подтвердить"
    builder.row(
        InlineKeyboardButton(
            text="✅ Подтвердить",
            callback_data=DeliveryCallback(method="confirm").pack()
        )
    )
    
    # Кнопка "Заполнить заново"
    builder.row(
        InlineKeyboardButton(
            text="🔄 Заполнить заново",
            callback_data=DeliveryCallback(method="restart").pack()
        )
    )
    
    # Кнопка "Отмена"
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=DeliveryCallback(method="cancel").pack()
        )
    )
    
    return builder.as_markup()


async def get_description_input_keyboard():
    """
    Создает клавиатуру для шага ввода описания.
    
    Предоставляет кнопки "Назад" и "Отмена".
    
    Returns:
        InlineKeyboardMarkup с навигационными кнопками
    
    Requirements: 9.2
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
