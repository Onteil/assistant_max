"""
Registration Keyboards for MAX Bot

Клавиатуры для процесса регистрации пользователей.
Включает кнопки для запроса контакта и отмены операции.
"""

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    KeyConflictChoicePayload,
    RegistrationCancelPayload,
    RegistrationSkipPayload,
)


def get_phone_keyboard() -> Keyboard:
    """
    Создает клавиатуру для запроса номера телефона.
    
    Использует RequestContactButton для получения номера телефона
    через встроенную функцию MAX messenger.
    
    Returns:
        Keyboard с кнопкой отправки контакта и кнопкой отмены
    
    Requirements: 7.2, 7.3, 7.5, 7.6
    """
    return Keyboard(
        buttons=[
            [KeyboardButton(text="📱 Поделиться номером", button_type="contact")],
            [KeyboardButton(text="❌ Отмена", payload=RegistrationCancelPayload().pack())]
        ],
        inline=False,
        one_time=True
    )


def get_skip_keyboard() -> Keyboard:
    """
    Создает клавиатуру с кнопками пропуска и отмены.
    
    Используется для опциональных шагов регистрации,
    где пользователь может пропустить ввод данных.
    
    Returns:
        Keyboard с кнопками пропуска и отмены
    
    Requirements: 7.2, 7.3
    """
    return Keyboard(
        buttons=[
            [KeyboardButton(text="⏭️️ Пропустить", payload=RegistrationSkipPayload().pack())],
            [KeyboardButton(text="❌ Отмена", payload=RegistrationCancelPayload().pack())]
        ],
        inline=True
    )


def get_key_conflict_keyboard() -> Keyboard:
    """
    Создает клавиатуру для выбора действия при конфликте ключа.
    
    Предлагает пользователю:
    - Ввести другой ключ Гранд-сметы
    - Продолжить регистрацию (создастся заявка на конфликт)
    
    Returns:
        Keyboard с кнопками выбора
    
    Requirements: 7.2, 7.3, 7.5, 7.6
    """
    return Keyboard(
        buttons=[
            [KeyboardButton(
                text="🔑 Ввести другой ключ",
                payload=KeyConflictChoicePayload(action="retry").pack()
            )],
            [KeyboardButton(
                text="✅ Продолжить регистрацию",
                payload=KeyConflictChoicePayload(action="continue").pack()
            )]
        ],
        inline=True
    )


def get_cancel_keyboard() -> Keyboard:
    """
    Создает простую клавиатуру с кнопкой отмены.
    
    Используется во время многошаговых процессов регистрации
    для предоставления пользователю возможности отменить операцию.
    
    Returns:
        Keyboard с кнопкой отмены
    
    Requirements: 7.2, 7.3
    """
    return Keyboard(
        buttons=[
            [KeyboardButton(text="❌ Отмена", payload=RegistrationCancelPayload().pack())]
        ],
        inline=True
    )


def get_key_input_keyboard() -> Keyboard:
    """
    Создает клавиатуру для ввода ключа с кнопкой помощи.
    
    Предлагает пользователю:
    - Кнопку "Не знаю номер ключа" для показа подсказки
    - Кнопку отмены
    
    Returns:
        Keyboard с кнопками помощи и отмены
    
    Requirements: 7.2, 7.3
    """
    return Keyboard(
        buttons=[
            [KeyboardButton(text="❓ Не знаю номер ключа", payload={"action": "key_help"})],
            [KeyboardButton(text="❌ Отмена", payload=RegistrationCancelPayload().pack())]
        ],
        inline=True
    )
