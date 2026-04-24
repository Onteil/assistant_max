"""
Consultation Request Keyboards for MAX Bot

Клавиатуры для процесса запроса консультации.
Аналогично invoice flow, но без шага выбора способа доставки.
"""

import math

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    ConsultationKeyActionPayload,
    ConsultationKeyPagePayload,
    ConsultationKeyTogglePayload,
    ConsultationOrgActionPayload,
    ConsultationOrgPagePayload,
    ConsultationOrgSelectPayload,
    ConsultationDescriptionNextPayload,
)

ITEMS_PER_PAGE = 7


def get_consultation_organization_keyboard(organizations: list, page: int = 0) -> Keyboard:
    """
    Создает клавиатуру для выбора организации в потоке консультации.

    Args:
        organizations: Список объектов Organization из базы данных
        page: Текущая страница (начиная с 0)

    Returns:
        Keyboard с организациями и навигацией
    """
    buttons = []

    total_pages = math.ceil(len(organizations) / ITEMS_PER_PAGE) if organizations else 1
    start_index = page * ITEMS_PER_PAGE
    orgs_on_page = organizations[start_index:start_index + ITEMS_PER_PAGE]

    for org in orgs_on_page:
        if org.organization_name:
            org_text = f"{org.organization_name} | {org.inn}"
        else:
            org_text = f"ИНН: {org.inn}"
        buttons.append([KeyboardButton(
            text=org_text,
            payload=ConsultationOrgSelectPayload(inn=org.inn).pack()
        )])

    if total_pages > 1:
        pagination_row = []
        if page > 0:
            pagination_row.append(KeyboardButton(
                text="◀️ Назад",
                payload=ConsultationOrgPagePayload(page=page - 1).pack()
            ))
        pagination_row.append(KeyboardButton(
            text=f"{page + 1}/{total_pages}",
            payload={"action": "noop"}
        ))
        if page < total_pages - 1:
            pagination_row.append(KeyboardButton(
                text="Вперед ▶️",
                payload=ConsultationOrgPagePayload(page=page + 1).pack()
            ))
        buttons.append(pagination_row)

    buttons.append([KeyboardButton(
        text="➕ Добавить новый ИНН",
        payload=ConsultationOrgActionPayload(action="add_new").pack()
    )])
    buttons.append([KeyboardButton(
        text="⏭️️ Пропустить",
        payload=ConsultationOrgActionPayload(action="skip").pack()
    )])
    buttons.append([KeyboardButton(
        text="❌ Отмена",
        payload=ConsultationOrgActionPayload(action="cancel").pack()
    )])

    return Keyboard(buttons=buttons, inline=True)


def get_consultation_key_selection_keyboard(
    keys: list,
    selected_key_ids: set[int],
    page: int = 0
) -> Keyboard:
    """
    Создает клавиатуру для мультивыбора ключей в потоке консультации.

    Args:
        keys: Список объектов GS_Key из базы данных
        selected_key_ids: Множество ID выбранных ключей
        page: Текущая страница (начиная с 0)

    Returns:
        Keyboard с ключами, галочками и навигацией
    """
    buttons = []

    total_pages = math.ceil(len(keys) / ITEMS_PER_PAGE) if keys else 1
    start_index = page * ITEMS_PER_PAGE
    keys_on_page = keys[start_index:start_index + ITEMS_PER_PAGE]

    for key in keys_on_page:
        checkmark = "✅ " if key.id in selected_key_ids else ""
        key_text = f"{checkmark}{key.key_number}"
        buttons.append([KeyboardButton(
            text=key_text,
            payload=ConsultationKeyTogglePayload(key_id=key.id).pack()
        )])

    if total_pages > 1:
        pagination_row = []
        if page > 0:
            pagination_row.append(KeyboardButton(
                text="◀️ Назад",
                payload=ConsultationKeyPagePayload(page=page - 1).pack()
            ))
        pagination_row.append(KeyboardButton(
            text=f"{page + 1}/{total_pages}",
            payload={"action": "noop"}
        ))
        if page < total_pages - 1:
            pagination_row.append(KeyboardButton(
                text="Вперед ▶️",
                payload=ConsultationKeyPagePayload(page=page + 1).pack()
            ))
        buttons.append(pagination_row)

    buttons.append([KeyboardButton(
        text="➕ Добавить еще ключ",
        payload=ConsultationKeyActionPayload(action="add_new").pack()
    )])

    if selected_key_ids:
        buttons.append([KeyboardButton(
            text="✅ Готово",
            payload=ConsultationKeyActionPayload(action="done").pack()
        )])
    else:
        buttons.append([KeyboardButton(
            text="⏭️️ Пропустить",
            payload=ConsultationKeyActionPayload(action="skip").pack()
        )])

    buttons.append([
        KeyboardButton(
            text="⬅️ Назад",
            payload=ConsultationKeyActionPayload(action="back").pack()
        ),
        KeyboardButton(
            text="❌ Отмена",
            payload=ConsultationKeyActionPayload(action="cancel").pack()
        )
    ])

    return Keyboard(buttons=buttons, inline=True)


def get_consultation_description_keyboard(has_content: bool = False) -> Keyboard:
    """
    Создает клавиатуру для шага ввода описания вопроса консультации.

    Если пользователь уже ввёл текст или прикрепил файлы (has_content=True),
    показывает кнопку «➡️ Далее» для перехода к следующему шагу.
    Иначе показывает только «Пропустить», «Назад» и «Отмена».

    Args:
        has_content: True если пользователь уже ввёл описание или вложения

    Returns:
        Keyboard с навигационными кнопками
    """
    buttons = []

    if has_content:
        buttons.append([KeyboardButton(
            text="➡️ Далее",
            payload=ConsultationDescriptionNextPayload().pack()
        )])

    buttons.append([KeyboardButton(
        text="⏭️️ Пропустить",
        payload=ConsultationKeyActionPayload(action="skip_description").pack()
    )])
    buttons.append([
        KeyboardButton(
            text="⬅️ Назад",
            payload=ConsultationKeyActionPayload(action="back_to_keys").pack()
        ),
        KeyboardButton(
            text="❌ Отмена",
            payload=ConsultationKeyActionPayload(action="cancel").pack()
        )
    ])
    return Keyboard(buttons=buttons, inline=True)
