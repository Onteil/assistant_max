"""
Renewal Keyboards

Клавиатуры для процесса продления подписки.
Включает кнопки для запроса продления и связи с менеджером.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bots.tg_bot.callback_datas import RenewalCallback
from bots.tg_bot.texts import BTN_CONTACT_MANAGER, BTN_RENEW
from database.models import SubscriptionStatus


async def get_subscription_status_keyboard(
    subscription_status: SubscriptionStatus
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для отображения статуса подписки.
    
    Кнопки зависят от статуса подписки:
    - ACTIVE/EXPIRED: кнопка "Продлить"
    - NONE: кнопка "Связаться с менеджером"
    
    Args:
        subscription_status: Статус подписки пользователя (ACTIVE, EXPIRED, NONE)
    
    Returns:
        InlineKeyboardMarkup с соответствующей кнопкой
    
    Requirements: 2.1, 4.4
    """
    builder = InlineKeyboardBuilder()
    
    if subscription_status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED):
        # Для активной или истекшей подписки показываем кнопку "Продлить"
        builder.button(
            text=BTN_RENEW,
            callback_data=RenewalCallback(action="renew")
        )
    else:
        # Для отсутствующей подписки показываем кнопку "Связаться с менеджером"
        builder.button(
            text=BTN_CONTACT_MANAGER,
            callback_data=RenewalCallback(action="contact_manager")
        )
    
    # Размещаем кнопку в один ряд
    builder.adjust(1)
    
    return builder.as_markup()


async def get_renewal_offer_keyboard() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для предложения продления в потоке техподдержки.
    
    Используется когда пользователь с неактивной подпиской пытается
    создать запрос в техподдержку.
    
    Кнопки:
    - "Связаться с менеджером" - создает заявку на продление
    - "Отмена" - отменяет действие
    
    Returns:
        InlineKeyboardMarkup с кнопками для продления
    
    Requirements: 4.4
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Связаться с менеджером"
    builder.button(
        text=BTN_CONTACT_MANAGER,
        callback_data=RenewalCallback(action="contact_manager")
    )
    
    # Кнопка "Отмена"
    builder.button(
        text="❌ Отмена",
        callback_data=RenewalCallback(action="cancel")
    )
    
    # Размещаем кнопки в один столбец
    builder.adjust(1)
    
    return builder.as_markup()
