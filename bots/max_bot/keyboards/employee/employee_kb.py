"""
Employee Interface Keyboards for MAX Bot

Reply keyboards for employee interface.
Includes main menu and navigation buttons.
"""

from maxapi.types import KeyboardButton, ReplyKeyboardMarkup

from bots.max_bot.texts import (
    BTN_ACTIVE_TICKETS,
    BTN_ADMIN_PANEL,
    BTN_ARCHIVE_SEARCH,
    BTN_EMPLOYEE_SETTINGS,
)


async def get_manager_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Create main manager menu with reply keyboard.
    
    Args:
        is_admin: Flag indicating if employee is administrator
    
    Returns:
        ReplyKeyboardMarkup with manager menu buttons
    
    Requirements: 1.1, 1.5, 1.6
    """
    buttons = []
    
    # Row 1: Active tickets and Archive search
    buttons.append([
        KeyboardButton(text=BTN_ACTIVE_TICKETS),
        KeyboardButton(text=BTN_ARCHIVE_SEARCH)
    ])
    
    # Row 2: Settings and Admin panel (if admin)
    row2 = [KeyboardButton(text=BTN_EMPLOYEE_SETTINGS)]
    if is_admin:
        row2.append(KeyboardButton(text=BTN_ADMIN_PANEL))
    buttons.append(row2)
    
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )
