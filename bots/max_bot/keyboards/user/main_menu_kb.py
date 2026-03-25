"""
Main Menu Keyboards for MAX Bot

Клавиатуры главного меню для зарегистрированных пользователей.
Предоставляет доступ ко всем основным функциям бота.

Migrated from Telegram bot to MAX messenger.
"""

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from bots.max_bot.payloads import MainMenuActionPayload, DonePayload
from bots.max_bot.texts import (
    MENU_ARCHIVE,
    MENU_INVOICE,
    MENU_PROFILE,
    MENU_RENEWAL,
    MENU_SUPPORT,
)


async def get_main_menu_inline_keyboard(active_tickets_count: int = 0, show_done_button: bool = False):
    """
    Создает inline клавиатуру главного меню с всеми доступными функциями.
    
    Отображается для пользователей со статусом ACTIVE после регистрации.
    Включает все основные функции бота согласно требованиям.
    
    Args:
        active_tickets_count: Количество активных заявок клиента
        show_done_button: Показывать кнопку "✅ Готово" вверху клавиатуры
    
    Returns:
        Keyboard с inline кнопками главного меню
    
    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 29.1, 29.3, AC-1.2, AC-1.3, TR-2
    """
    buttons = [
        # Первый ряд: Счет и Техподдержка
        [
            KeyboardButton(text="💰 Получить счёт", payload=MainMenuActionPayload(action="invoice").pack()),
            KeyboardButton(text="🆘 Техподдержка", payload=MainMenuActionPayload(action="support").pack())
        ],
        # Второй ряд: Продление и Архив
        [
            # KeyboardButton(text="🔄 Продление", payload=MainMenuActionPayload(action="renewal").pack()),
            KeyboardButton(text="🗃️ Архив обращений", payload=MainMenuActionPayload(action="archive").pack())
        ],
        # Третий ряд: Профиль
        [
            KeyboardButton(text="👤 Мой профиль", payload=MainMenuActionPayload(action="profile").pack())
        ]
    ]

    # Если есть активные заявки, добавить кнопку с количеством
    if active_tickets_count > 0:
        buttons.insert(1, [
            KeyboardButton(
                text=f"📥 Активные обращения ({active_tickets_count})",
                payload=MainMenuActionPayload(action="active_tickets").pack()
            )
        ])

    # Кнопка "Готово" — добавляется первой, если запрошена
    if show_done_button:
        buttons.insert(0, [
            KeyboardButton(text="✅ Готово", payload=DonePayload().pack())
        ])

    return Keyboard(
        buttons=buttons,
        inline=True
    )


async def get_main_menu_keyboard():
    """
    Создает reply клавиатуру главного меню (deprecated).
    
    Используется для обратной совместимости.
    Рекомендуется использовать get_main_menu_inline_keyboard().
    
    Returns:
        Keyboard с кнопками главного меню
    """
    return Keyboard(
        buttons=[
            # Первый ряд: Счет и Техподдержка
            [
                KeyboardButton(text=MENU_INVOICE),
                KeyboardButton(text=MENU_SUPPORT)
            ],
            # Второй ряд: Продление и Архив
            [
                KeyboardButton(text=MENU_RENEWAL),
                KeyboardButton(text=MENU_ARCHIVE)
            ],
            # Третий ряд: Профиль
            [
                KeyboardButton(text=MENU_PROFILE)
            ]
        ],
        inline=False,
        one_time=False
    )
