"""
Subscription Renewal Handler

Manages subscription renewal requests from the main menu.
Displays subscription status and creates renewal tickets routed to assigned managers.

Requirements: 1.1-1.5, 2.1-2.7, 9.1-9.5, 10.1-10.3
"""

import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bots.tg_bot.callback_datas import RenewalCallback
from bots.tg_bot.keyboards.renewal_kb import get_subscription_status_keyboard
from bots.tg_bot.texts import (
    MENU_RENEWAL,
    RENEWAL_ERROR_CREATE_TICKET,
    RENEWAL_ERROR_NO_MANAGER,
    RENEWAL_TICKET_CREATED,
)
from database.models import Ticket, TicketStatus, TicketType
from services.renewal_service import (
    create_renewal_ticket,
    format_subscription_status,
)
from services.user_service import get_user_by_tg_id

logger = logging.getLogger(__name__)

router = Router(name="renewal")


# ========== Helper Functions ==========


async def has_active_renewal_ticket(session: AsyncSession, user_id: int) -> bool:
    """
    Check if user has an active RENEWAL ticket.
    
    Args:
        session: Database session
        user_id: User ID from database
    
    Returns:
        True if user has active RENEWAL ticket, False otherwise
    """
    stmt = select(Ticket).where(
        Ticket.user_id == user_id,
        Ticket.ticket_type == TicketType.RENEWAL,
        Ticket.ticket_status.in_([
            TicketStatus.NEW,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_CLIENT
        ])
    )
    
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


# ========== Entry Point ==========


@router.message(F.text == MENU_RENEWAL)
async def show_subscription_status(
    message: Message,
    session: AsyncSession
) -> None:
    """
    Display subscription status with renewal option.
    
    Shows:
    - ACTIVE: expiration date, renewal button
    - EXPIRED: expiration date, renewal button
    - NONE: no subscription message, contact manager button
    
    Requirements: 1.1-1.5, 9.1-9.4
    """
    telegram_id = message.from_user.id
    
    try:
        # Get user from database
        user = await get_user_by_tg_id(session, telegram_id)
        
        if not user:
            await message.answer(
                "❌ Пользователь не найден.\n"
                "Пожалуйста, пройдите регистрацию с помощью /start"
            )
            logger.warning(f"User {telegram_id} not found in database")
            return
        
        # Format subscription status message
        status_text = await format_subscription_status(user)
        
        # Get keyboard for subscription status
        keyboard = await get_subscription_status_keyboard(user.subscription_status)
        
        # Send status message with keyboard
        await message.answer(
            status_text,
            reply_markup=keyboard
        )
        
        logger.info(
            f"User {telegram_id} viewed subscription status: "
            f"status={user.subscription_status}"
        )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error loading subscription status for user {telegram_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при загрузке данных.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Renewal Request ==========


@router.callback_query(RenewalCallback.filter(F.action == "renew"))
async def handle_renewal_request(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot
) -> None:
    """
    Create RENEWAL ticket and route to manager.
    Checks if user already has active RENEWAL ticket.
    
    Requirements: 2.1-2.7
    """
    await _process_renewal_request(callback, session, bot)


@router.callback_query(RenewalCallback.filter(F.action == "renew_from_notification"))
async def handle_renewal_from_notification(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot
) -> None:
    """
    Create RENEWAL ticket from subscription expiration notification.
    Removes the button after processing.
    
    Requirements: 2.1-2.7
    """
    await _process_renewal_request(callback, session, bot, from_notification=True)


async def _process_renewal_request(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    from_notification: bool = False
) -> None:
    """
    Internal function to process renewal requests.
    
    Args:
        callback: Callback query from user
        session: Database session
        bot: Bot instance
        from_notification: If True, removes keyboard after processing
    """
    telegram_id = callback.from_user.id
    
    try:
        # Get user from database
        user = await get_user_by_tg_id(session, telegram_id)
        
        if not user:
            await callback.answer(
                "❌ Пользователь не найден",
                show_alert=True
            )
            logger.warning(f"User {telegram_id} not found in database")
            return
        
        # Check if user already has active RENEWAL ticket
        if await has_active_renewal_ticket(session, user.id):
            message_text = (
                "ℹ️ У вас уже есть активная заявка на продление подписки.\n\n"
                "Ваш менеджер получил уведомление и свяжется с вами в ближайшее время."
            )
            
            if from_notification:
                # Remove keyboard when from notification
                await callback.message.edit_text(message_text)
            else:
                await callback.message.edit_text(message_text)
            
            await callback.answer()
            logger.info(f"User {telegram_id} already has active RENEWAL ticket")
            return
        
        # Check if user has assigned manager
        if not user.default_manager_id:
            message_text = RENEWAL_ERROR_NO_MANAGER
            
            if from_notification:
                await callback.message.edit_text(message_text)
            else:
                await callback.message.edit_text(message_text)
            
            await callback.answer()
            logger.error(
                f"User {telegram_id} (user_id={user.id}) has no default_manager_id"
            )
            return
        
        # Create renewal ticket
        ticket = await create_renewal_ticket(session, user, bot)
        await session.commit()
        
        # Send confirmation to user (remove keyboard if from notification)
        confirmation_text = RENEWAL_TICKET_CREATED.format(ticket_id=ticket.id)
        await callback.message.edit_text(confirmation_text)
        await callback.answer()
        
        logger.info(
            f"Renewal ticket created: ticket_id={ticket.id}, "
            f"user_id={user.id}, manager_id={user.default_manager_id}, "
            f"from_notification={from_notification}"
        )
    
    except ValueError as e:
        # Business logic error (e.g., missing manager)
        await callback.message.edit_text(RENEWAL_ERROR_NO_MANAGER)
        await callback.answer()
        logger.error(
            f"Renewal ticket creation failed for user {telegram_id}: {e}",
            exc_info=True
        )
    
    except SQLAlchemyError as e:
        # Database error
        await session.rollback()
        logger.error(
            f"Database error creating renewal ticket for user {telegram_id}: {e}",
            exc_info=True
        )
        await callback.message.edit_text(RENEWAL_ERROR_CREATE_TICKET)
        await callback.answer()
    
    except Exception as e:
        # Unexpected error
        await session.rollback()
        logger.error(
            f"Unexpected error creating renewal ticket for user {telegram_id}: {e}",
            exc_info=True
        )
        await callback.message.edit_text(RENEWAL_ERROR_CREATE_TICKET)
        await callback.answer()
