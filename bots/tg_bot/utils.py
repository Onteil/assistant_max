"""
Utility Functions

Паттерн: Вспомогательные функции общего назначения
- Функции для работы с текстом
- Функции для работы с датами
- Функции для валидации
"""

import re
from datetime import datetime


def validate_email(email: str) -> bool:
    """
    Проверяет корректность email адреса.

    Args:
        email: Email для проверки

    Returns:
        True если email валиден
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def format_datetime(dt: datetime, format_str: str = "%d.%m.%Y %H:%M") -> str:
    """
    Форматирует datetime в строку.

    Args:
        dt: Объект datetime
        format_str: Формат вывода

    Returns:
        Отформатированная строка
    """
    return dt.strftime(format_str)


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Обрезает текст до указанной длины.

    Args:
        text: Исходный текст
        max_length: Максимальная длина
        suffix: Суффикс для обрезанного текста

    Returns:
        Обрезанный текст
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix
