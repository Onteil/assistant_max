"""
Renewal Keyboards for MAX Bot

Клавиатуры для процесса продления подписки.
Включает кнопки для запроса продления и связи с менеджером.
"""

from maxapi.types.attachments.buttons import CallbackButton
from maxapi.types.attachments.attachment import ButtonsPayload
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from bots.max_bot.payloads import RenewalPayload
from database.models import SubscriptionStatus


async def get_subscription_status_keyboard(
    subscription_status: SubscriptionStatus
) -> ButtonsPayload:
    """
    Создает клавиатуру для отображения статуса подписки.
    
    Кнопки зависят от статуса подписки:
    - ACTIVE/EXPIRED: кнопка "Продлить"
    - NONE: кнопка "Связаться с менеджером"
    
    Args:
        subscription_status: Статус подписки пользователя (ACTIVE, EXPIRED, NONE)
    
    Returns:
        ButtonsPayload с соответствующей кнопкой
    
    Requirements: 2.1, 4.4
    """
    builder = InlineKeyboardBuilder()
    
    if subscription_status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED):
        # Для активной или истекшей подписки показываем кнопку "Продлить"
        builder.row(
            CallbackButton(
                text="🔄 Продлить",
                payload=RenewalPayload(action="renew").pack()
            )
        )
    else:
        # Для отсутствующей подписки показываем кнопку "Связаться с менеджером"
        builder.row(
            CallbackButton(
                text="👤 Связаться с менеджером",
                payload=RenewalPayload(action="contact_manager").pack()
            )
        )
    
    return builder.as_markup()


async def get_renewal_offer_keyboard() -> ButtonsPayload:
    """
    Создает клавиатуру для предложения продления в потоке техподдержки.
    
    Используется когда пользователь с неактивной подпиской пытается
    создать запрос в техподдержку.
    
    Кнопки:
    - "Связаться с менеджером" - создает заявку на продление
    - "Отмена" - отменяет действие
    
    Returns:
        ButtonsPayload с кнопками для продления
    
    Requirements: 4.4
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Связаться с менеджером"
    builder.row(
        CallbackButton(
            text="👤 Связаться с менеджером",
            payload=RenewalPayload(action="contact_manager").pack()
        )
    )
    
    # Кнопка "Отмена"
    builder.row(
        CallbackButton(
            text="❌ Отмена",
            payload=RenewalPayload(action="cancel").pack()
        )
    )
    
    return builder.as_markup()
