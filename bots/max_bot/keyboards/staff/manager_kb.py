"""
Manager Interface Inline Keyboards for MAX Bot

Inline клавиатуры для интерфейса менеджера в MAX messenger.
В отличие от Telegram (reply keyboard), MAX использует inline keyboard.
"""

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from bots.max_bot.payloads import ManagerMenuActionPayload


def get_manager_menu_keyboard(
    is_admin: bool = False,
    is_manager: bool = False,
    new_tickets_count: int = 0
) -> Keyboard:
    """
    Создает главное меню менеджера с inline клавиатурой.
    
    В MAX используется inline keyboard вместо reply keyboard из Telegram.
    
    Args:
        is_admin: Флаг, является ли сотрудник администратором
        is_manager: Флаг, является ли сотрудник менеджером
        new_tickets_count: Количество новых заявок (не взятых в работу)
    
    Returns:
        Keyboard с кнопками меню менеджера
    
    Requirements: Manager Interface
    """
    # Format active tickets button text with count if there are new tickets
    active_tickets_text = "📥 Активные заявки"
    if new_tickets_count > 0:
        active_tickets_text = f"📥 Активные заявки ({new_tickets_count})"
    
    buttons = [
        # Row 1: Active Tickets
        [
            KeyboardButton(
                text=active_tickets_text,
                payload=ManagerMenuActionPayload(action="active_tickets").pack()
            )
        ],
        # Row 2: Archive
        [
            KeyboardButton(
                text="🗃️ Архив обращений",
                payload=ManagerMenuActionPayload(action="archive").pack()
            )
        ]
    ]
    
    # Row 3: Transfer clients (only for managers)
    if is_manager:
        buttons.append([
            KeyboardButton(
                text="👥 Передача клиентов",
                payload=ManagerMenuActionPayload(action="transfer_clients").pack()
            )
        ])
    
    # Row 4: Admin Panel (only for administrators)
    if is_admin:
        buttons.append([
            KeyboardButton(
                text="🔐 Админ-панель",
                payload=ManagerMenuActionPayload(action="admin_panel").pack()
            )
        ])
    
    return Keyboard(buttons=buttons, inline=True)
