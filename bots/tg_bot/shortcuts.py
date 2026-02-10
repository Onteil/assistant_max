"""
Shortcuts & Helper Functions

Паттерн: Переиспользуемые функции для частых операций
- Функции для форматирования сообщений
- Функции для валидации данных
- Функции для работы с пользователями
"""

from aiogram.types import Message, User


async def format_user_info(user: User) -> str:
    """
    Форматирует информацию о пользователе для отображения.

    Args:
        user: Объект пользователя Telegram

    Returns:
        Отформатированная строка с информацией
    """
    username = f"@{user.username}" if user.username else "Не указан"
    full_name = user.full_name or "Неизвестно"
    return f"👤 {full_name}\n🆔 {user.id}\n📝 {username}"


async def safe_delete_message(message: Message) -> bool:
    """
    Безопасно удаляет сообщение (не падает при ошибке).

    Args:
        message: Сообщение для удаления

    Returns:
        True если удалено успешно, False если ошибка
    """
    try:
        await message.delete()
        return True
    except Exception:
        return False
