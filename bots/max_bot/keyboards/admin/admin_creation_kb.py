"""
Admin Creation Keyboards for MAX Bot

Клавиатуры для процесса создания администраторов.
"""

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from bots.max_bot.payloads import AdminCreationCancelPayload


def get_admin_phone_keyboard() -> Keyboard:
    """
    Создает клавиатуру для запроса номера телефона администратора.
    
    Returns:
        Keyboard с кнопкой отправки контакта и кнопкой отмены
    """
    return Keyboard(
        buttons=[
            [KeyboardButton(text="📱 Поделиться номером", button_type="contact")],
            [KeyboardButton(text="❌ Отмена", payload=AdminCreationCancelPayload().pack())]
        ],
        inline=False,
        one_time=True
    )


def get_admin_cancel_keyboard() -> Keyboard:
    """
    Создает клавиатуру с кнопкой отмены для создания администратора.
    
    Returns:
        Keyboard с кнопкой отмены
    """
    return Keyboard(
        buttons=[
            [KeyboardButton(text="❌ Отмена", payload=AdminCreationCancelPayload().pack())]
        ],
        inline=True
    )
