"""
Subscription Renewal Handler for MAX Bot

Manages subscription renewal requests from the main menu.
Displays subscription status and creates renewal tickets routed to assigned managers.

Migrated from Telegram bot to MAX messenger.

Requirements: 1.1-1.5, 2.1-2.7, 9.1-9.5, 10.1-10.3
"""

import logging
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import RenewalActionPayload
from bots.max_bot.texts import (
    RENEWAL_ERROR_CREATE_TICKET,
    RENEWAL_ERROR_NO_MANAGER,
    RENEWAL_TICKET_CREATED,
    RENEWAL_STATUS_ACTIVE,
    RENEWAL_STATUS_ACTIVE_NO_DATE,
    RENEWAL_STATUS_EXPIRED,
    RENEWAL_STATUS_NONE,
)
from database.models import (
    Ticket,
    TicketStatus,
    TicketType,
    SubscriptionStatus,
    RegistrationStatus,
)
from services.user_service import get_user_by_max_id

logger = logging.getLogger(__name__)


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


async def format_subscription_status(user) -> str:
    """
    Format subscription status message based on user's subscription.
    
    Calculates days remaining/passed and formats message with emoji and HTML.
    
    Args:
        user: User object with subscription_status and subscription_end_date
    
    Returns:
        Formatted status message with HTML formatting
    """
    try:
        from datetime import datetime, timezone
        
        # Build message text based on subscription status
        if user.subscription_status == SubscriptionStatus.ACTIVE:
            # Check if expiration date is available
            if user.subscription_end_date:
                # Format expiration date
                expiry_date_str = user.subscription_end_date.strftime("%d.%m.%Y")
                
                # Calculate days remaining
                now = datetime.now(timezone.utc)
                # Ensure subscription_end_date is timezone-aware
                if user.subscription_end_date.tzinfo is None:
                    end_date = user.subscription_end_date.replace(tzinfo=timezone.utc)
                else:
                    end_date = user.subscription_end_date
                
                days_left = (end_date - now).days
                
                # Format days remaining text
                if days_left == 0:
                    days_left_str = "менее 1 дня"
                elif days_left == 1:
                    days_left_str = "1 день"
                elif 2 <= days_left <= 4:
                    days_left_str = f"{days_left} дня"
                else:
                    days_left_str = f"{days_left} дней"
                
                message_text = RENEWAL_STATUS_ACTIVE.format(
                    expiry_date=expiry_date_str,
                    days_left=days_left_str
                )
            else:
                # No expiration date - show simple active message
                message_text = RENEWAL_STATUS_ACTIVE_NO_DATE
        
        elif user.subscription_status == SubscriptionStatus.EXPIRED:
            # Format expiration date
            expiry_date_str = user.subscription_end_date.strftime("%d.%m.%Y") if user.subscription_end_date else "неизвестно"
            
            # Calculate days passed since expiration
            if user.subscription_end_date:
                now = datetime.now(timezone.utc)
                # Ensure subscription_end_date is timezone-aware
                if user.subscription_end_date.tzinfo is None:
                    end_date = user.subscription_end_date.replace(tzinfo=timezone.utc)
                else:
                    end_date = user.subscription_end_date
                
                days_passed = (now - end_date).days
                
                # Format days passed text
                if days_passed == 0:
                    days_passed_str = "менее 1 дня"
                elif days_passed == 1:
                    days_passed_str = "1 день"
                elif 2 <= days_passed <= 4:
                    days_passed_str = f"{days_passed} дня"
                else:
                    days_passed_str = f"{days_passed} дней"
            else:
                days_passed_str = "неизвестно"
            
            message_text = RENEWAL_STATUS_EXPIRED.format(
                expiry_date=expiry_date_str,
                days_passed=days_passed_str
            )
        
        else:  # SubscriptionStatus.NONE
            message_text = RENEWAL_STATUS_NONE
        
        return message_text
    
    except Exception as e:
        logger.error(
            f"Error formatting subscription status: user_id={user.id}, error={e}",
            exc_info=True
        )
        raise


def get_subscription_status_keyboard(subscription_status: SubscriptionStatus) -> Keyboard:
    """
    Create keyboard for subscription status display.
    
    Buttons depend on subscription status:
    - ACTIVE/EXPIRED: "Продлить" and "В меню" buttons
    - NONE: "Связаться с менеджером" and "В меню" buttons
    
    Args:
        subscription_status: User's subscription status
    
    Returns:
        Keyboard with appropriate buttons
    """
    from bots.max_bot.payloads import ProfileActionPayload
    
    buttons = []
    
    if subscription_status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED):
        # For active or expired subscription, show "Renew" button
        buttons.append([
            KeyboardButton(
                text="🔄 Продлить",
                payload=RenewalActionPayload(action="renew").pack()
            )
        ])
    else:
        # For no subscription, show "Contact Manager" button
        buttons.append([
            KeyboardButton(
                text="👤 Связаться с менеджером",
                payload=RenewalActionPayload(action="contact_manager").pack()
            )
        ])
    
    # Add "В меню" button for all cases
    buttons.append([
        KeyboardButton(
            text="🏠 В меню",
            payload=ProfileActionPayload(action="main_menu").pack()
        )
    ])
    
    return Keyboard(buttons=buttons, inline=True)


# ========== Entry Point ==========


async def show_subscription_status(
    event: MessageCallback | MessageCreated,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display subscription status with renewal option.
    
    Shows:
    - ACTIVE: expiration date, renewal button
    - EXPIRED: expiration date, renewal button
    - NONE: no subscription message, contact manager button
    
    Note: event.answer() and message deletion are handled by handle_main_menu_callback
    
    Args:
        event: Callback event from MAX
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 1.1-1.5, 9.1-9.4
    """
    chat_id = event.message.recipient.chat_id
    if isinstance(event, MessageCallback):
        max_user_id = event.callback.user.user_id
    else:
        max_user_id = event.message.sender.user_id
    
    try:
        # Get user from database
        user = await get_user_by_max_id(session, max_user_id)
        
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден.\nПожалуйста, пройдите регистрацию с помощью /start",
                parse_mode="HTML"
            )
            logger.warning(f"User {max_user_id} not found in database")
            return
        
        # Format subscription status message
        status_text = await format_subscription_status(user)
        
        # Get keyboard for subscription status
        keyboard = get_subscription_status_keyboard(user.subscription_status)
        
        # Send status message with keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=status_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"User {max_user_id} viewed subscription status: "
            f"status={user.subscription_status}"
        )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error loading subscription status for user {max_user_id}: {e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке данных.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )
