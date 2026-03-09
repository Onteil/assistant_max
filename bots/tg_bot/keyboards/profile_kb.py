"""
Profile Management Keyboards

Клавиатуры для управления профилем пользователя.
Включает действия для добавления организаций, ключей, изменения телефона и настройки уведомлений.
"""

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bots.tg_bot.callback_datas import ProfileCallback
from bots.tg_bot.texts import (
    BTN_ADD_INN,
    BTN_ADD_KEY,
    BTN_CHANGE_PHONE,
    BTN_TOGGLE_NOTIFICATIONS,
)


async def get_profile_actions_keyboard():
    """
    Создает клавиатуру с действиями для управления профилем.
    
    Предоставляет кнопки для:
    - Просмотра списка организаций
    - Просмотра списка ключей
    - Изменения номера телефона
    - Переключения настроек уведомлений
    
    Returns:
        InlineKeyboardMarkup с кнопками действий профиля
    
    Requirements: 17.1, 18.1, 19.1, 20.1
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Мои организации"
    builder.button(
        text="📊 Организации",
        callback_data=ProfileCallback(action="view_orgs", page=0)
    )
    
    # Кнопка "Мои ключи"
    builder.button(
        text="🔑 Ключи ГС",
        callback_data=ProfileCallback(action="view_keys", page=0)
    )
    
    # Кнопка "Изменить телефон"
    builder.button(
        text=BTN_CHANGE_PHONE,
        callback_data=ProfileCallback(action="change_phone")
    )
    
    # Кнопка "Уведомления"
    builder.button(
        text=BTN_TOGGLE_NOTIFICATIONS,
        callback_data=ProfileCallback(action="toggle_notif")
    )
    
    # Размещаем по 2 кнопки в ряду для компактности
    builder.adjust(2)
    
    return builder.as_markup()


async def get_organizations_list_keyboard(organizations: list, page: int = 0, items_per_page: int = 7):
    """
    Создает клавиатуру для списка организаций с кнопками удаления.
    
    Args:
        organizations: Список всех организаций пользователя
        page: Текущая страница (0-indexed)
        items_per_page: Количество элементов на странице
    
    Returns:
        InlineKeyboardMarkup с кнопками организаций и навигации
    """
    from bots.tg_bot.callback_datas import OrganizationCallback
    
    builder = InlineKeyboardBuilder()
    
    total_count = len(organizations)
    total_pages = (total_count + items_per_page - 1) // items_per_page if total_count > 0 else 1
    
    # Ensure page is within bounds
    page = max(0, min(page, total_pages - 1))
    
    # Get organizations for current page
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_orgs = organizations[start_idx:end_idx]
    
    # Create button for each organization with delete option
    for org in page_orgs:
        org_text = f"ИНН: {org.inn}"
        if org.organization_name:
            org_text += f" - {org.organization_name[:20]}"
        
        # Organization button with delete action
        builder.row(
            InlineKeyboardButton(
                text=org_text,
                callback_data=OrganizationCallback(action="delete", inn=org.inn).pack()
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=OrganizationCallback(action="delete", inn=org.inn).pack()
            )
        )
    
    # Кнопка "Добавить организацию"
    builder.row(InlineKeyboardButton(
        text="➕ Добавить организацию",
        callback_data=ProfileCallback(action="add_inn").pack()
    ))
    
    # Кнопки пагинации (только если больше 7 элементов)
    if total_count > items_per_page:
        buttons_row = []
        
        if page > 0:
            buttons_row.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=ProfileCallback(action="view_orgs", page=page - 1).pack()
            ))
        
        buttons_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="noop"
        ))
        
        if page < total_pages - 1:
            buttons_row.append(InlineKeyboardButton(
                text="➡️",
                callback_data=ProfileCallback(action="view_orgs", page=page + 1).pack()
            ))
        
        builder.row(*buttons_row)
    
    # Кнопка "Назад в профиль"
    builder.row(InlineKeyboardButton(
        text="🔙 Назад в профиль",
        callback_data=ProfileCallback(action="back").pack()
    ))
    
    return builder.as_markup()


async def get_keys_list_keyboard(keys: list, page: int = 0, items_per_page: int = 7):
    """
    Создает клавиатуру для списка ключей с кнопками удаления.
    
    Args:
        keys: Список всех ключей пользователя
        page: Текущая страница (0-indexed)
        items_per_page: Количество элементов на странице
    
    Returns:
        InlineKeyboardMarkup с кнопками ключей и навигации
    """
    from bots.tg_bot.callback_datas import KeyCallback
    
    builder = InlineKeyboardBuilder()
    
    total_count = len(keys)
    total_pages = (total_count + items_per_page - 1) // items_per_page if total_count > 0 else 1
    
    # Ensure page is within bounds
    page = max(0, min(page, total_pages - 1))
    
    # Get keys for current page
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_keys = keys[start_idx:end_idx]
    
    # Create button for each key with delete option
    for key in page_keys:
        key_text = key.key_number
        if key.conflict_status and key.conflict_status.value == "pending_review":
            key_text += " ⚠️"
        
        # Key button with delete action
        builder.row(
            InlineKeyboardButton(
                text=key_text,
                callback_data=KeyCallback(action="delete", key_id=key.id).pack()
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=KeyCallback(action="delete", key_id=key.id).pack()
            )
        )
    
    # Кнопка "Добавить ключ"
    builder.row(InlineKeyboardButton(
        text="➕ Добавить ключ",
        callback_data=ProfileCallback(action="add_key").pack()
    ))
    
    # Кнопки пагинации (только если больше 7 элементов)
    if total_count > items_per_page:
        buttons_row = []
        
        if page > 0:
            buttons_row.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=ProfileCallback(action="view_keys", page=page - 1).pack()
            ))
        
        buttons_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="noop"
        ))
        
        if page < total_pages - 1:
            buttons_row.append(InlineKeyboardButton(
                text="➡️",
                callback_data=ProfileCallback(action="view_keys", page=page + 1).pack()
            ))
        
        builder.row(*buttons_row)
    
    # Кнопка "Назад в профиль"
    builder.row(InlineKeyboardButton(
        text="🔙 Назад в профиль",
        callback_data=ProfileCallback(action="back").pack()
    ))
    
    return builder.as_markup()


async def get_cancel_profile_action_keyboard():
    """
    Создает inline клавиатуру с кнопкой отмены для операций профиля.
    
    Используется при добавлении ИНН, ключа или изменении телефона.
    
    Returns:
        InlineKeyboardMarkup с кнопкой "Отмена"
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="❌ Отмена",
        callback_data=ProfileCallback(action="cancel")
    )
    
    return builder.as_markup()



async def get_notifications_menu_keyboard(notifications_enabled: bool):
    """
    Создает клавиатуру для меню управления уведомлениями.
    
    Args:
        notifications_enabled: Текущий статус уведомлений
    
    Returns:
        InlineKeyboardMarkup с кнопками управления уведомлениями
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка переключения с индикатором текущего состояния
    if notifications_enabled:
        toggle_text = "🔴 Выключить уведомления"
    else:
        toggle_text = "🟢 Включить уведомления"
    
    builder.button(
        text=toggle_text,
        callback_data=ProfileCallback(action="toggle_notif")
    )
    
    # Кнопка "Назад в профиль"
    builder.button(
        text="🔙 Назад в профиль",
        callback_data=ProfileCallback(action="back")
    )
    
    builder.adjust(1)
    
    return builder.as_markup()
