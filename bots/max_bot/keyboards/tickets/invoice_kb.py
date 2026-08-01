"""
Invoice Request Keyboards for MAX Bot

Клавиатуры для процесса запроса счетов.
Включает выбор организации, мультивыбор ключей и выбор способа доставки.
"""

import math
from typing import Optional

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    OrganizationSelectPayload,
    OrganizationPagePayload,
    OrganizationActionPayload,
    KeyTogglePayload,
    KeyPagePayload,
    KeyActionPayload,
    DeliveryMethodPayload,
    EmailConfirmPayload,
    InvoiceDescriptionNextPayload,
)
from database.models import KeyConflictStatus

# Константы для пагинации
ITEMS_PER_PAGE = 7


def get_organization_keyboard(organizations: list, page: int = 0) -> Keyboard:
    """
    Создает клавиатуру для выбора организации с поддержкой пагинации.
    
    Отображает список организаций пользователя с ИНН.
    Включает кнопки "Добавить новый ИНН" и "Пропустить".
    
    Args:
        organizations: Список объектов Organization из базы данных
        page: Текущая страница (начиная с 0)
    
    Returns:
        Keyboard с организациями и навигацией
    
    Requirements: 7.2, 7.3, 7.4, 7.9
    """
    buttons = []
    
    # Пагинация
    total_pages = math.ceil(len(organizations) / ITEMS_PER_PAGE) if organizations else 1
    start_index = page * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    orgs_on_page = organizations[start_index:end_index]
    
    # Кнопки организаций — одна кнопка: название если есть, иначе ИНН
    for org in orgs_on_page:
        label = org.organization_name if org.organization_name else f"ИНН: {org.inn}"
        buttons.append([KeyboardButton(
            text=label,
            payload=OrganizationSelectPayload(inn=org.inn).pack()
        )])
    
    # Кнопки пагинации (если страниц больше одной)
    if total_pages > 1:
        pagination_row = []
        
        if page > 0:
            pagination_row.append(KeyboardButton(
                text="◀️ Назад",
                payload=OrganizationPagePayload(page=page - 1).pack()
            ))
        
        pagination_row.append(KeyboardButton(
            text=f"{page + 1}/{total_pages}",
            payload={"action": "noop"}
        ))
        
        if page < total_pages - 1:
            pagination_row.append(KeyboardButton(
                text="Вперед ▶️",
                payload=OrganizationPagePayload(page=page + 1).pack()
            ))
        
        buttons.append(pagination_row)
    
    # Кнопка "Добавить новый ИНН"
    buttons.append([KeyboardButton(
        text="➕ Добавить новый ИНН",
        payload=OrganizationActionPayload(action="add_new").pack()
    )])
    
    # Кнопка "Пропустить"
    buttons.append([KeyboardButton(
        text="⏭️️ Пропустить",
        payload=OrganizationActionPayload(action="skip").pack()
    )])
    
    # Кнопка "Отмена"
    buttons.append([KeyboardButton(
        text="❌ Отмена",
        payload=OrganizationActionPayload(action="cancel").pack()
    )])
    
    return Keyboard(buttons=buttons, inline=True)


def get_key_selection_keyboard(
    keys: list,
    selected_key_ids: set[int],
    page: int = 0
) -> Keyboard:
    """
    Создает клавиатуру для мультивыбора ключей GS_Key с визуальными индикаторами.
    
    Поддерживает переключение выбора (toggle) с отображением галочек для выбранных ключей.
    Включает пагинацию для больших списков и кнопки управления.
    
    Args:
        keys: Список объектов GS_Key из базы данных
        selected_key_ids: Множество ID выбранных ключей
        page: Текущая страница (начиная с 0)
    
    Returns:
        Keyboard с ключами, галочками и навигацией
    
    Requirements: 7.2, 7.3, 7.4, 7.9, 7.10
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
        if key.conflict_status == KeyConflictStatus.PENDING_REVIEW:
            key_text += " ⚠️"
        
        buttons.append([KeyboardButton(
            text=key_text,
            payload=KeyTogglePayload(key_id=key.id).pack()
        )])
    
    # Кнопки пагинации (если страниц больше одной)
    if total_pages > 1:
        pagination_row = []
        
        if page > 0:
            pagination_row.append(KeyboardButton(
                text="◀️ Назад",
                payload=KeyPagePayload(page=page - 1).pack()
            ))
        
        pagination_row.append(KeyboardButton(
            text=f"{page + 1}/{total_pages}",
            payload={"action": "noop"}
        ))
        
        if page < total_pages - 1:
            pagination_row.append(KeyboardButton(
                text="Вперед ▶️",
                payload=KeyPagePayload(page=page + 1).pack()
            ))
        
        buttons.append(pagination_row)
    
    # Кнопка "Добавить еще ключ"
    buttons.append([KeyboardButton(
        text="➕ Добавить еще ключ",
        payload=KeyActionPayload(action="add_new").pack()
    )])
    
    # Кнопка "Готово" (только если есть выбранные ключи)
    if selected_key_ids:
        buttons.append([KeyboardButton(
            text="✅ Готово",
            payload=KeyActionPayload(action="done").pack()
        )])
    
    # Кнопка "Пропустить" (если нет выбранных ключей)
    if not selected_key_ids:
        buttons.append([KeyboardButton(
            text="⏭️️ Пропустить",
            payload=KeyActionPayload(action="skip").pack()
        )])
    
    # Кнопки навигации
    nav_row = [
        KeyboardButton(
            text="⬅️ Назад",
            payload=KeyActionPayload(action="back").pack()
        ),
        KeyboardButton(
            text="❌ Отмена",
            payload=KeyActionPayload(action="cancel").pack()
        )
    ]
    buttons.append(nav_row)
    
    return Keyboard(buttons=buttons, inline=True)


def get_delivery_keyboard() -> Keyboard:
    """
    Создает клавиатуру для выбора способа доставки счета.
    
    Предоставляет выбор между доставкой через MAX или Email.
    
    Returns:
        Keyboard с вариантами доставки
    
    Requirements: 7.2, 7.3, 7.4
    """
    buttons = [
        [
            KeyboardButton(
                text="💬 В чат",
                payload=DeliveryMethodPayload(method="telegram").pack()
            ),
            KeyboardButton(
                text="📧 На Email",
                payload=DeliveryMethodPayload(method="email").pack()
            )
        ],
        [
            KeyboardButton(
                text="⬅️ Назад",
                payload=DeliveryMethodPayload(method="back").pack()
            ),
            KeyboardButton(
                text="❌ Отмена",
                payload=DeliveryMethodPayload(method="cancel").pack()
            )
        ]
    ]
    
    return Keyboard(buttons=buttons, inline=True)


def get_invoice_confirmation_keyboard() -> Keyboard:
    """
    Создает клавиатуру для подтверждения заявки на счет.
    
    Предоставляет кнопки "Подтвердить", "Заполнить заново" и "Отмена".
    
    Returns:
        Keyboard с кнопками подтверждения
    
    Requirements: 7.2, 7.3, 7.4
    """
    buttons = [
        [KeyboardButton(
            text="✅ Подтвердить",
            payload=DeliveryMethodPayload(method="confirm").pack()
        )],
        [KeyboardButton(
            text="🔄 Заполнить заново",
            payload=DeliveryMethodPayload(method="restart").pack()
        )],
        [KeyboardButton(
            text="❌ Отмена",
            payload=DeliveryMethodPayload(method="cancel").pack()
        )]
    ]
    
    return Keyboard(buttons=buttons, inline=True)


def get_description_input_keyboard(has_content: bool = False) -> Keyboard:
    """
    Создает клавиатуру для шага ввода описания.

    Если пользователь уже ввёл текст или прикрепил файлы (has_content=True),
    показывает кнопку «➡️ Далее» для перехода к следующему шагу.
    Иначе показывает только «Пропустить», «Назад» и «Отмена».

    Args:
        has_content: True если пользователь уже ввёл описание или вложения

    Returns:
        Keyboard с навигационными кнопками

    Requirements: 7.2, 7.3
    """
    buttons = []

    if has_content:
        buttons.append([KeyboardButton(
            text="➡️ Далее",
            payload=InvoiceDescriptionNextPayload().pack()
        )])

    buttons.append([KeyboardButton(
        text="⏭️️ Пропустить",
        payload=KeyActionPayload(action="skip_description").pack()
    )])
    buttons.append([
        KeyboardButton(
            text="⬅️ Назад",
            payload=KeyActionPayload(action="back_to_keys").pack()
        ),
        KeyboardButton(
            text="❌ Отмена",
            payload=KeyActionPayload(action="cancel").pack()
        )
    ])

    return Keyboard(buttons=buttons, inline=True)


def get_email_confirm_keyboard() -> Keyboard:
    """
    Создает клавиатуру для подтверждения использования зарегистрированного email.
    
    Предоставляет кнопки "Да, всё верно", "Ввести другой", "Назад" и "Отмена".
    
    Returns:
        Keyboard с кнопками подтверждения
    
    Requirements: 7.2, 7.3
    """
    buttons = [
        [
            KeyboardButton(
                text="✅ Да, всё верно",
                payload=EmailConfirmPayload(action="use_registered").pack()
            )
        ],
        [
            KeyboardButton(
                text="✏️ Ввести другой",
                payload=EmailConfirmPayload(action="enter_new").pack()
            )
        ],
        [
            KeyboardButton(
                text="⬅️ Назад",
                payload=DeliveryMethodPayload(method="back").pack()
            ),
            KeyboardButton(
                text="❌ Отмена",
                payload=EmailConfirmPayload(action="cancel").pack()
            )
        ]
    ]
    
    return Keyboard(buttons=buttons, inline=True)


def get_email_input_keyboard() -> Keyboard:
    """
    Создает клавиатуру для шага ввода email.
    
    Предоставляет кнопки "Назад" и "Отмена".
    
    Returns:
        Keyboard с навигационными кнопками
    
    Requirements: 7.2, 7.3
    """
    buttons = [
        [
            KeyboardButton(
                text="⬅️ Назад",
                payload=DeliveryMethodPayload(method="back_to_delivery").pack()
            ),
            KeyboardButton(
                text="❌ Отмена",
                payload=DeliveryMethodPayload(method="cancel").pack()
            )
        ]
    ]
    
    return Keyboard(buttons=buttons, inline=True)
