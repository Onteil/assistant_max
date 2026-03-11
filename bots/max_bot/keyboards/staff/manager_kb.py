"""
Manager Interface Inline Keyboards for MAX Bot

Inline клавиатуры для интерфейса менеджера в MAX messenger.
В отличие от Telegram (reply keyboard), MAX использует inline keyboard.
"""

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from bots.max_bot.payloads import ManagerMenuActionPayload


def get_manager_menu_keyboard(is_admin: bool = False) -> Keyboard:
    """
    Создает главное меню менеджера с inline клавиатурой.
    
    В MAX используется inline keyboard вместо reply keyboard из Telegram.
    
    Args:
        is_admin: Флаг, является ли сотрудник администратором
    
    Returns:
        Keyboard с кнопками меню менеджера
    
    Requirements: Manager Interface
    """
    buttons = [
        # Row 1: Active Tickets
        [
            KeyboardButton(
                text="📥 Активные заявки",
                payload=ManagerMenuActionPayload(action="active_tickets").pack()
            )
        ],
        # Row 2: Archive
        [
            KeyboardButton(
                text="🗄 Архив обращений",
                payload=ManagerMenuActionPayload(action="archive").pack()
            )
        ]
    ]
    
    # Row 3: Admin Panel (only for administrators)
    if is_admin:
        buttons.append([
            KeyboardButton(
                text="🔐 Админ-панель",
                payload=ManagerMenuActionPayload(action="admin_panel").pack()
            )
        ])
    
    return Keyboard(buttons=buttons, inline=True)
