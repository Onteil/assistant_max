"""
Technical Support Keyboards for MAX Bot

Клавиатуры для процесса технической поддержки.
Включает выбор контекста ключа и предложение продления подписки.
"""

import math

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    RenewalActionPayload,
    KeyContextTogglePayload,
    KeyContextPagePayload,
    KeyContextActionPayload,
)

# Константы для пагинации
ITEMS_PER_PAGE = 7


def get_renewal_keyboard() -> Keyboard:
    """
    Создает клавиатуру для предложения продления подписки.
    
    Используется когда у пользователя истекла подписка на техподдержку.
    Предлагает оформить заявку на продление.
    
    Returns:
        Keyboard с кнопкой создания заявки
    
    Requirements: 7.2, 7.3
    """
    buttons = [
        [KeyboardButton(
            text="📝 Оформить заявку на продление",
            payload=RenewalActionPayload(action="renew").pack()
        )],
        [KeyboardButton(
            text="❌ Отмена",
            payload=RenewalActionPayload(action="cancel").pack()
        )]
    ]
    
    return Keyboard(buttons=buttons, inline=True)


def get_key_context_keyboard(
    keys: list,
    selected_key_ids: set[int],
    page: int = 0
) -> Keyboard:
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
        Keyboard с ключами, галочками и навигацией
    
    Requirements: 7.2, 7.3, 7.10
    """
    buttons = []
    
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
        if hasattr(key, 'conflict_status') and key.conflict_status and key.conflict_status.value == "pending_review":
            key_text += " ⚠️"
        
        buttons.append([KeyboardButton(
            text=key_text,
            payload=KeyContextTogglePayload(key_id=key.id).pack()
        )])
    
    # Кнопки пагинации (если страниц больше одной)
    if total_pages > 1:
        pagination_row = []
        
        if page > 0:
            pagination_row.append(KeyboardButton(
                text="◀️ Назад",
                payload=KeyContextPagePayload(page=page - 1).pack()
            ))
        
        pagination_row.append(KeyboardButton(
            text=f"{page + 1}/{total_pages}",
            payload={"action": "noop"}
        ))
        
        if page < total_pages - 1:
            pagination_row.append(KeyboardButton(
                text="Вперед ▶️",
                payload=KeyContextPagePayload(page=page + 1).pack()
            ))
        
        buttons.append(pagination_row)
    
    # Кнопка "Добавить другой ключ"
    buttons.append([KeyboardButton(
        text="➕ Другой ключ",
        payload=KeyContextActionPayload(action="add_new").pack()
    )])
    
    # Кнопка "Готово" (только если есть выбранные ключи)
    if selected_key_ids:
        buttons.append([KeyboardButton(
            text="✅ Готово",
            payload=KeyContextActionPayload(action="done").pack()
        )])
    
    # Кнопка "Не знаю / Пропустить"
    buttons.append([KeyboardButton(
        text="❓ Не знаю / Пропустить",
        payload=KeyContextActionPayload(action="skip").pack()
    )])
    
    # Кнопки навигации
    nav_row = [
        KeyboardButton(
            text="⬅️ Назад",
            payload=KeyContextActionPayload(action="back").pack()
        ),
        KeyboardButton(
            text="❌ Отмена",
            payload=KeyContextActionPayload(action="cancel").pack()
        )
    ]
    buttons.append(nav_row)
    
    return Keyboard(buttons=buttons, inline=True)


def get_problem_description_keyboard() -> Keyboard:
    """
    Создает клавиатуру для шага ввода описания проблемы.
    
    Предоставляет кнопки "Пропустить" и "Отмена".
    
    Returns:
        Keyboard с навигационными кнопками
    
    Requirements: 7.2, 7.3
    """
    buttons = [
        [KeyboardButton(
            text="⏭️️ Пропустить",
            payload=KeyContextActionPayload(action="skip_description").pack()
        )],
        [KeyboardButton(
            text="❌ Отмена",
            payload=KeyContextActionPayload(action="cancel").pack()
        )]
    ]
    
    return Keyboard(buttons=buttons, inline=True)


def get_add_key_keyboard() -> Keyboard:
    """
    Создает клавиатуру для шага добавления нового ключа.
    
    Предоставляет кнопки "Назад" и "Отмена".
    
    Returns:
        Keyboard с навигационными кнопками
    
    Requirements: 7.2, 7.3
    """
    buttons = [
        [
            KeyboardButton(
                text="⬅️ Назад",
                payload=KeyContextActionPayload(action="back_to_keys").pack()
            ),
            KeyboardButton(
                text="❌ Отмена",
                payload=KeyContextActionPayload(action="cancel").pack()
            )
        ]
    ]
    
    return Keyboard(buttons=buttons, inline=True)
