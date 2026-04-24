"""
Profile Keyboards for MAX Bot

Keyboard builders for profile management interface.

Requirements: 4.6
"""

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton


def get_profile_keyboard() -> Keyboard:
    """
    Build profile action keyboard.
    
    Provides buttons for:
    - Organizations (view/manage)
    - GS_Keys (view/manage)
    - Change Email
    - Notifications and Broadcasts (manage subscriptions in one menu)
    - Return to main menu
    
    Layout:
    - Row 1: Organizations | Keys
    - Row 2: Change Email
    - Row 3: Notifications & Broadcasts
    - Row 4: Main Menu
    
    Returns:
        Keyboard with profile action buttons
    
    Requirements: 4.6
    """
    from bots.max_bot.payloads import ProfileViewPayload, ProfileActionPayload
    
    buttons = [
        # Row 1: Organizations and Keys
        [
            KeyboardButton(
                text="📋 Организации",
                payload=ProfileViewPayload(section="orgs", page=0).pack()
            ),
            KeyboardButton(
                text="🔑 Ключи",
                payload=ProfileViewPayload(section="keys", page=0).pack()
            )
        ],
        # Row 2: Change Email and Phone
        [
            KeyboardButton(
                text="📧 Изменить Email",
                payload=ProfileActionPayload(action="change_email").pack()
            ),
            KeyboardButton(
                text="📱 Изменить телефон",
                payload=ProfileActionPayload(action="change_phone").pack()
            )
        ],
        # Row 3: Notifications & Broadcasts (combined)
        [
            KeyboardButton(
                text="🔔 Уведомления и рассылки",
                payload=ProfileActionPayload(action="notifications_menu").pack()
            )
        ],
        # Row 4: Main Menu
        [
            KeyboardButton(
                text="🏠 В меню",
                payload=ProfileActionPayload(action="main_menu").pack()
            )
        ],
    ]
    
    return Keyboard(buttons=buttons, inline=True)



def get_organizations_list_keyboard(organizations: list, page: int = 0, items_per_page: int = 7) -> Keyboard:
    """
    Build keyboard for organizations list with pagination.
    
    Shows list of user's organizations with options to:
    - View/delete each organization
    - Add new organization
    - Navigate pages (if more than items_per_page)
    - Return to profile
    
    Args:
        organizations: List of Organization model instances
        page: Current page number (0-indexed)
        items_per_page: Number of items per page
    
    Returns:
        Keyboard with organization buttons and navigation
    """
    from bots.max_bot.payloads import (
        ProfileAddPayload,
        ProfileDeleteOrgPayload,
        ProfileViewPayload,
        ProfileActionPayload
    )
    
    total_count = len(organizations)
    total_pages = (total_count + items_per_page - 1) // items_per_page if total_count > 0 else 1
    page = max(0, min(page, total_pages - 1))
    
    # Get organizations for current page
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_orgs = organizations[start_idx:end_idx]
    
    buttons = []
    
    # Organization buttons
    for org in page_orgs:
        if org.organization_name:
            org_text = f"{org.organization_name} | {org.inn}"
        else:
            org_text = f"ИНН: {org.inn}"
        
        buttons.append([
            KeyboardButton(
                text=org_text,
                payload=ProfileActionPayload(action="noop").pack()  # Inactive button
            ),
            KeyboardButton(
                text="🗑",
                payload=ProfileDeleteOrgPayload(inn=org.inn).pack()
            )
        ])
    
    # Add organization button
    buttons.append([
        KeyboardButton(
            text="➕ Добавить организацию",
            payload=ProfileAddPayload(item_type="inn").pack()
        )
    ])
    
    # Pagination (if needed)
    if total_count > items_per_page:
        pagination_row = []
        
        if page > 0:
            pagination_row.append(
                KeyboardButton(
                    text="⬅️",
                    payload=ProfileViewPayload(section="orgs", page=page - 1).pack()
                )
            )
        
        pagination_row.append(
            KeyboardButton(
                text=f"{page + 1}/{total_pages}",
                payload=ProfileActionPayload(action="noop").pack()
            )
        )
        
        if page < total_pages - 1:
            pagination_row.append(
                KeyboardButton(
                    text="➡️",
                    payload=ProfileViewPayload(section="orgs", page=page + 1).pack()
                )
            )
        
        buttons.append(pagination_row)
    
    # Back to profile button
    buttons.append([
        KeyboardButton(
            text="⬅️ Назад в профиль",
            payload=ProfileActionPayload(action="back").pack()
        )
    ])
    
    return Keyboard(buttons=buttons, inline=True)


def get_keys_list_keyboard(keys: list, page: int = 0, items_per_page: int = 7) -> Keyboard:
    """
    Build keyboard for keys list with pagination.
    
    Shows list of user's GS keys with options to:
    - View/delete each key
    - Add new key
    - Navigate pages (if more than items_per_page)
    - Return to profile
    
    Args:
        keys: List of GS_Key model instances
        page: Current page number (0-indexed)
        items_per_page: Number of items per page
    
    Returns:
        Keyboard with key buttons and navigation
    """
    from bots.max_bot.payloads import (
        ProfileAddPayload,
        ProfileDeleteKeyPayload,
        ProfileViewPayload,
        ProfileActionPayload
    )
    from database.models import KeyConflictStatus
    
    total_count = len(keys)
    total_pages = (total_count + items_per_page - 1) // items_per_page if total_count > 0 else 1
    page = max(0, min(page, total_pages - 1))
    
    # Get keys for current page
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_keys = keys[start_idx:end_idx]
    
    buttons = []
    
    # Key buttons
    for key in page_keys:
        key_text = key.key_number
        if key.conflict_status == KeyConflictStatus.PENDING_REVIEW:
            key_text += " ⚠️"
        
        buttons.append([
            KeyboardButton(
                text=key_text,
                payload=ProfileActionPayload(action="noop").pack()  # Inactive button
            ),
            KeyboardButton(
                text="🗑",
                payload=ProfileDeleteKeyPayload(key_id=key.id).pack()
            )
        ])
    
    # Add key button
    buttons.append([
        KeyboardButton(
            text="➕ Добавить ключ",
            payload=ProfileAddPayload(item_type="key").pack()
        )
    ])
    
    # Pagination (if needed)
    if total_count > items_per_page:
        pagination_row = []
        
        if page > 0:
            pagination_row.append(
                KeyboardButton(
                    text="⬅️",
                    payload=ProfileViewPayload(section="keys", page=page - 1).pack()
                )
            )
        
        pagination_row.append(
            KeyboardButton(
                text=f"{page + 1}/{total_pages}",
                payload=ProfileActionPayload(action="noop").pack()
            )
        )
        
        if page < total_pages - 1:
            pagination_row.append(
                KeyboardButton(
                    text="➡️",
                    payload=ProfileViewPayload(section="keys", page=page + 1).pack()
                )
            )
        
        buttons.append(pagination_row)
    
    # Back to profile button
    buttons.append([
        KeyboardButton(
            text="⬅️ Назад в профиль",
            payload=ProfileActionPayload(action="back").pack()
        )
    ])
    
    return Keyboard(buttons=buttons, inline=True)


def get_cancel_keyboard() -> Keyboard:
    """
    Build cancel keyboard for profile input flows.
    
    Used during:
    - Adding new INN
    - Adding new key
    
    Returns:
        Keyboard with cancel button
    """
    from bots.max_bot.payloads import ProfileActionPayload
    
    buttons = [
        [
            KeyboardButton(
                text="❌ Отмена",
                payload=ProfileActionPayload(action="cancel").pack()
            )
        ]
    ]
    
    return Keyboard(buttons=buttons, inline=True)



def get_notifications_menu_keyboard(notifications_enabled: bool) -> Keyboard:
    """
    Build keyboard for notifications menu.
    
    Shows:
    - Notifications toggle
    - Back to profile button
    
    Args:
        notifications_enabled: Current notifications status
    
    Returns:
        Keyboard with toggle button
    """
    from bots.max_bot.payloads import ProfileActionPayload
    
    # Notification toggle button
    notif_text = "🟢 Уведомления: ВКЛ" if notifications_enabled else "🔴 Уведомления: ВЫКЛ"
    notif_action = "toggle_notif"
    
    buttons = [
        [
            KeyboardButton(
                text=notif_text,
                payload=ProfileActionPayload(action=notif_action).pack()
            )
        ],
        [
            KeyboardButton(
                text="⬅️ Назад в профиль",
                payload=ProfileActionPayload(action="back").pack()
            )
        ],
    ]
    
    return Keyboard(buttons=buttons, inline=True)
