"""
Profile Handler for MAX Bot

Handles user profile management including:
- /profile command to display user profile
- Add organization (INN)
- Add GS_Key with conflict detection
- Change phone number request
- Toggle notification preferences

Requirements: 4.1-4.16
"""

import logging
from datetime import datetime
from typing import Optional

from maxapi import F
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.keyboards.user.profile_kb import get_profile_keyboard
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.payloads import ProfileActionPayload
from bots.max_bot.states import ProfileStates
from bots.max_bot.texts import (
    ERROR_GENERAL,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    ERROR_VALIDATION_EMAIL,
    PROFILE_ADD_INN_PROMPT,
    PROFILE_ADD_KEY_PROMPT,
    PROFILE_CHANGE_PHONE_SUBMITTED,
    PROFILE_CHANGE_EMAIL_PROMPT,
    PROFILE_EMAIL_UPDATED,
    PROFILE_EMAIL_REMOVED,
    PROFILE_INN_ADDED,
    PROFILE_INN_DUPLICATE,
    PROFILE_NOTIFICATIONS_TOGGLED,
    PROFILE_NOTIFICATIONS_DISABLE_CONFIRM,
    PROFILE_NOTIFICATIONS_DISABLED_SUCCESS,
    PROFILE_NOTIFICATIONS_ENABLED_SUCCESS,
    ADD_KEY_SUCCESS,
    ADD_KEY_CONFLICT,
    BTN_CANCEL,
)
from database.models import KeyConflictStatus, TicketType
from services.i_tat_service import get_itat_client
from services.itat_retry_helper import call_itat_with_retry
from services.ticket_service import create_ticket
from services.user_service import (
    KeyAlreadyOwnedByUserError,
    KeyConflictError,
    add_user_key,
    add_user_organization,
    get_user_by_id,
    get_user_by_max_id,
    get_user_keys,
    get_user_organizations,
)
from services.validation_service import validate_gs_key, validate_inn

logger = logging.getLogger(__name__)


# ========== /profile Command Handler ==========


async def cmd_profile(
    event: MessageCreated | MessageCallback,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /profile command or callback - display user profile.
    
    Shows user profile with all data including:
    - Full name, phone, registration date
    - Organizations (first 10 with "show more" indicator)
    - GS_Keys with conflict status (first 10 with "show more" indicator)
    - Subscription status and expiry date
    - Notification preferences
    - Action buttons keyboard
    
    maxapi Pattern Notes:
    - Handles both MessageCreated and MessageCallback event types
    - Uses event.message.sender.user_id for MessageCreated events
    - Uses event.callback.user.user_id for MessageCallback events
    - Includes commands_info marker for automatic command registration
    
    Args:
        event: MessageCreated or MessageCallback event from maxapi
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    commands_info: Показать профиль пользователя
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
    """
    chat_id = event.message.recipient.chat_id
    # Get user_id based on event type (MessageCreated uses sender, MessageCallback uses callback.user)
    from maxapi.types import MessageCallback as MCType
    if isinstance(event, MCType):
        max_user_id = event.callback.user.user_id
    else:
        max_user_id = event.message.sender.user_id
    
    logger.info(f"Profile command: max_user_id={max_user_id}, chat_id={chat_id}")
    
    try:
        # Get user from database
        user = await get_user_by_max_id(session, max_user_id)
        
        if not user:
            logger.warning(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден. Пожалуйста, пройдите регистрацию командой /start",
                parse_mode="HTML"
            )
            return
        
        # Display profile
        await show_profile(chat_id, user.id, session, messenger_adapter)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in cmd_profile: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Unexpected error in cmd_profile: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def show_profile(
    chat_id: int,
    user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    message_id: Optional[int] = None
) -> None:
    """
    Display user profile with all data and action buttons.
    
    Formats and displays:
    - User information (name, phone, registration date)
    - Organizations with pagination indicator
    - GS_Keys with conflict status and pagination indicator
    - Subscription status and expiry
    - Notification preferences
    - Action buttons
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        message_id: Optional message ID for editing instead of sending new
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
    """
    logger.info(f"Displaying profile: user_id={user_id}, chat_id={chat_id}")
    
    try:
        # Get user data
        user = await get_user_by_id(session, user_id)
        if not user:
            logger.error(f"User not found: user_id={user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            return
        
        # Get organizations
        organizations = await get_user_organizations(session, user_id)
        
        # Get GS_Keys
        gs_keys = await get_user_keys(session, user_id)
        
        # Format profile text
        profile_text = _format_profile_text(user, organizations, gs_keys)
        
        # Get profile keyboard
        keyboard = get_profile_keyboard()
        
        # Send message (don't edit - always send new)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=profile_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error displaying profile: user_id={user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def show_organizations_list(
    chat_id: int,
    user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    page: int = 0
) -> None:
    """
    Display paginated list of user's organizations.
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        page: Current page number (0-indexed)
    """
    logger.info(f"Showing organizations list: user_id={user_id}, page={page}")
    
    try:
        # Get organizations
        organizations = await get_user_organizations(session, user_id)
        
        # Build message text
        total_count = len(organizations)
        items_per_page = 7
        
        if total_count > items_per_page:
            total_pages = (total_count + items_per_page - 1) // items_per_page
            current_page = max(0, min(page, total_pages - 1)) + 1
            pagination_info = f"\n\nСтраница {current_page} из {total_pages}"
        else:
            pagination_info = ""
        
        text = f"📋 <b>Мои организации</b>\n\nВсего организаций: {total_count}{pagination_info}"
        
        # Get keyboard
        from bots.max_bot.keyboards.user.profile_kb import get_organizations_list_keyboard
        keyboard = get_organizations_list_keyboard(organizations, page, items_per_page)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error showing organizations list: user_id={user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def show_keys_list(
    chat_id: int,
    user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    page: int = 0
) -> None:
    """
    Display paginated list of user's GS keys.
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        page: Current page number (0-indexed)
    """
    logger.info(f"Showing keys list: user_id={user_id}, page={page}")
    
    try:
        # Get keys
        gs_keys = await get_user_keys(session, user_id)
        
        # Build message text
        total_count = len(gs_keys)
        items_per_page = 7
        
        if total_count > items_per_page:
            total_pages = (total_count + items_per_page - 1) // items_per_page
            current_page = max(0, min(page, total_pages - 1)) + 1
            pagination_info = f"\n\nСтраница {current_page} из {total_pages}"
        else:
            pagination_info = ""
        
        text = f"🔑 <b>Мои ключи Гранд-сметы</b>\n\nВсего ключей: {total_count}{pagination_info}"
        
        # Get keyboard
        from bots.max_bot.keyboards.user.profile_kb import get_keys_list_keyboard
        keyboard = get_keys_list_keyboard(gs_keys, page, items_per_page)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error showing keys list: user_id={user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def delete_organization(
    chat_id: int,
    user_id: int,
    inn: str,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Delete organization from user profile.
    
    Removes organization from local database and updates i-TAT API.
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID
        inn: INN of organization to delete
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    logger.info(f"Deleting organization: user_id={user_id}, inn={inn}")
    
    try:
        # Get user with organizations
        from database.models import User
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        stmt = select(User).where(User.id == user_id).options(selectinload(User.organizations))
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            # Find and remove organization from user's organizations
            org_to_remove = None
            for org in user.organizations:
                if org.inn == inn:
                    org_to_remove = org
                    break
            
            if org_to_remove:
                user.organizations.remove(org_to_remove)
                await session.commit()
                
                # Update user assets via i-TAT API
                assets_response = await call_itat_with_retry(
                    session=session,
                    operation="update_user_assets",
                    payload=dict(
                        messenger="max",
                        user_id=user.max_user_id,
                        asset_type="inn",
                        action="remove",
                        value=inn,
                    ),
                    user_id=user.id,
                )
                if assets_response is not None:
                    logger.info(f"Assets removal result: {assets_response}")
                else:
                    logger.warning(f"update_user_assets (remove inn) queued for retry: user_id={user.id}, inn={inn}")
                
                # Log profile update to audit
                from bots.max_bot.utils.audit_logger import log_user_profile_updated
                await log_user_profile_updated(
                    user_id=user_id,
                    field="organization",
                    old_value=inn,
                    new_value="",  # Removed
                    max_user_id=user.max_user_id or 0
                )
                
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=f"✅ Организация с ИНН {inn} удалена из профиля.",
                    parse_mode="HTML"
                )
                logger.info(f"Organization removed from user: user_id={user_id}, inn={inn}")
            else:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=f"❌ Организация с ИНН {inn} не найдена.",
                    parse_mode="HTML"
                )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ Пользователь не найден.",
                parse_mode="HTML"
            )
        
        # Show organizations list again
        await show_organizations_list(chat_id, user_id, session, messenger_adapter)
    
    except Exception as e:
        logger.error(
            f"Error deleting organization: user_id={user_id}, inn={inn}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def delete_key(
    chat_id: int,
    user_id: int,
    key_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Delete GS key from user profile.
    
    Removes key from local database and updates i-TAT API.
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID
        key_id: ID of key to delete
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    logger.info(f"Deleting key: user_id={user_id}, key_id={key_id}")
    
    try:
        # Get user and key
        from database.models import GS_Key, User
        from sqlalchemy import select, and_
        from sqlalchemy.orm import selectinload
        
        # Get user with key
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.gs_keys))
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден.",
                parse_mode="HTML"
            )
            return
        
        # Find the key
        key = None
        for gs_key in user.gs_keys:
            if gs_key.id == key_id:
                key = gs_key
                break
        
        if key:
            key_number = key.key_number
            await session.delete(key)
            await session.commit()
            
            # Update user assets via i-TAT API
            assets_response = await call_itat_with_retry(
                session=session,
                operation="update_user_assets",
                payload=dict(
                    messenger="max",
                    user_id=user.max_user_id,
                    asset_type="grand_key",
                    action="remove",
                    value=key_number,
                ),
                user_id=user.id,
            )
            if assets_response is not None:
                logger.info(f"Assets removal result: {assets_response}")
            else:
                logger.warning(f"update_user_assets (remove key) queued for retry: user_id={user.id}, key={key_number}")
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"✅ Ключ {key_number} удален из профиля.",
                parse_mode="HTML"
            )
            logger.info(f"Key deleted: user_id={user_id}, key_id={key_id}")
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ Ключ не найден.",
                parse_mode="HTML"
            )
        
        # Show keys list again
        await show_keys_list(chat_id, user_id, session, messenger_adapter)
    
    except Exception as e:
        logger.error(
            f"Error deleting key: user_id={user_id}, key_id={key_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def show_disable_notifications_confirmation(
    chat_id: int,
    user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show confirmation dialog for disabling notifications.
    
    Warns user about what they will miss if they disable notifications.
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    logger.info(f"Showing disable notifications confirmation: user_id={user_id}")
    
    try:
        from bots.max_bot.payloads import ProfileActionPayload
        from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
        
        # Build confirmation keyboard
        buttons = [
            [
                KeyboardButton(
                    text="✅ Да, отключить",
                    payload=ProfileActionPayload(action="confirm_disable_notif").pack()
                )
            ],
            [
                KeyboardButton(
                    text="❌ Отмена",
                    payload=ProfileActionPayload(action="notifications_menu").pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=PROFILE_NOTIFICATIONS_DISABLE_CONFIRM,
            keyboard=keyboard,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error showing disable notifications confirmation: user_id={user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def show_notifications_menu(
    chat_id: int,
    user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show notifications and broadcasts management menu.
    
    Displays two toggles:
    - Notifications toggle
    - Broadcasts toggle
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    logger.info(f"Showing notifications menu: user_id={user_id}")
    
    try:
        # Get user
        user = await get_user_by_id(session, user_id)
        if not user:
            logger.error(f"User not found: user_id={user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            return
        
        # Get keyboard
        from bots.max_bot.keyboards.user.profile_kb import get_notifications_menu_keyboard
        keyboard = get_notifications_menu_keyboard(
            notifications_enabled=user.notification_preferences
        )
        
        # Build message text
        text = "🔔 <b>Управление уведомлениями</b>\n\n"
        
        if user.notification_preferences:
            text += "✅ Уведомления включены\n"
            text += "Вы получаете новости, акции и полезные советы.\n\n"
        else:
            text += "❌ Уведомления отключены\n"
            text += "Вы не получаете рассылки от бота.\n\n"
        
        text += "<i>Критические уведомления о заявках приходят всегда.</i>"
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error showing notifications menu: user_id={user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def show_delete_organization_confirmation(
    chat_id: int,
    user_id: int,
    inn: str,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show confirmation dialog for deleting organization.
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID
        inn: INN of organization to delete
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    logger.info(f"Showing delete organization confirmation: user_id={user_id}, inn={inn}")
    
    try:
        from bots.max_bot.payloads import ProfileConfirmDeleteOrgPayload, ProfileViewPayload
        from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
        
        # Build confirmation keyboard
        buttons = [
            [
                KeyboardButton(
                    text="✅ Да, удалить",
                    payload=ProfileConfirmDeleteOrgPayload(inn=inn).pack()
                )
            ],
            [
                KeyboardButton(
                    text="❌ Отмена",
                    payload=ProfileViewPayload(section="orgs", page=0).pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        text = f"⚠️ <b>Удаление организации</b>\n\nВы уверены, что хотите удалить организацию с ИНН <b>{inn}</b> из профиля?"
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error showing delete organization confirmation: user_id={user_id}, inn={inn}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def show_delete_key_confirmation(
    chat_id: int,
    user_id: int,
    key_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show confirmation dialog for deleting key.
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID
        key_id: ID of key to delete
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    logger.info(f"Showing delete key confirmation: user_id={user_id}, key_id={key_id}")
    
    try:
        from bots.max_bot.payloads import ProfileConfirmDeleteKeyPayload, ProfileViewPayload
        from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
        from database.models import GS_Key
        from sqlalchemy import select
        
        # Get key to show its number
        stmt = select(GS_Key).where(GS_Key.id == key_id)
        result = await session.execute(stmt)
        key = result.scalar_one_or_none()
        
        if not key:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ключ не найден.",
                parse_mode="HTML"
            )
            return
        
        # Build confirmation keyboard
        buttons = [
            [
                KeyboardButton(
                    text="✅ Да, удалить",
                    payload=ProfileConfirmDeleteKeyPayload(key_id=key_id).pack()
                )
            ],
            [
                KeyboardButton(
                    text="❌ Отмена",
                    payload=ProfileViewPayload(section="keys", page=0).pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        text = f"⚠️ <b>Удаление ключа</b>\n\nВы уверены, что хотите удалить ключ <b>{key.key_number}</b> из профиля?"
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error showing delete key confirmation: user_id={user_id}, key_id={key_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


def _format_profile_text(user, organizations: list, gs_keys: list) -> str:
    """
    Format profile information into display text.
    
    Args:
        user: User model instance
        organizations: List of Organization instances
        gs_keys: List of GS_Key instances
    
    Returns:
        Formatted profile text with HTML markup
    """
    # Header
    text = "👤 <b>Мой профиль</b>\n\n"
    
    # User information
    text += f"<b>ФИО:</b> {user.full_name or 'Не указано'}\n"
    text += f"<b>Телефон:</b> {user.phone_number}\n"
    
    # Email
    if user.email:
        text += f"<b>Email:</b> {user.email}\n"
    
    if user.created_at:
        reg_date = user.created_at.strftime("%d.%m.%Y")
        text += f"<b>Дата регистрации:</b> {reg_date}\n"
    
    text += "\n"
    
    # Organizations
    text += "<b>📋 Организации (ИНН):</b>\n"
    if organizations:
        display_orgs = organizations[:10]
        for org in display_orgs:
            text += f"  • {org.inn}\n"
        
        if len(organizations) > 10:
            text += f"  <i>... и еще {len(organizations) - 10}</i>\n"
    else:
        text += "  <i>Нет добавленных организаций</i>\n"
    
    text += "\n"
    
    # GS_Keys
    text += "<b>🔑 Ключи Гранд-сметы:</b>\n"
    if gs_keys:
        display_keys = gs_keys[:10]
        for key in display_keys:
            status_emoji = ""
            if key.conflict_status == KeyConflictStatus.PENDING_REVIEW:
                status_emoji = " ⚠️"
            elif key.conflict_status == KeyConflictStatus.RESOLVED:
                status_emoji = " ✅"
            
            text += f"  • {key.key_number}{status_emoji}\n"
        
        if len(gs_keys) > 10:
            text += f"  <i>... и еще {len(gs_keys) - 10}</i>\n"
    else:
        text += "  <i>Нет добавленных ключей</i>\n"
    
    text += "\n"
    
    # Subscription status
    from database.models import SubscriptionStatus
    text += "<b>📅 Подписка:</b> "
    if user.subscription_status == SubscriptionStatus.ACTIVE:
        if user.subscription_end_date:
            expiry = user.subscription_end_date.strftime("%d.%m.%Y")
            text += f"Активна до {expiry}\n"
        else:
            text += "Активна\n"
    elif user.subscription_status == SubscriptionStatus.EXPIRED:
        if user.subscription_end_date:
            expiry = user.subscription_end_date.strftime("%d.%m.%Y")
            text += f"Истекла {expiry}\n"
        else:
            text += "Истекла\n"
    else:
        text += "Отсутствует\n"
    
    text += "\n"
    
    # Notification preferences
    text += "<b>🔔 Уведомления:</b> "
    if user.notification_preferences:
        text += "Включены\n"
    else:
        text += "Выключены\n"
    
    return text


# ========== Profile Action Handlers ==========


async def handle_profile_callback(
    event: MessageCallback,
    payload: any,  # Can be any of the profile payload types
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle profile action callbacks.
    
    Processes different payload types:
    - ProfileActionPayload: Simple actions (toggle_notif, broadcasts, main_menu, back, cancel, noop)
    - ProfileViewPayload: View organizations or keys list
    - ProfileAddPayload: Add new INN or key
    - ProfileDeleteOrgPayload: Delete organization
    - ProfileDeleteKeyPayload: Delete key
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses different CallbackPayload classes for type-safe payload parsing
    - Payload automatically parsed by CallbackPayload.filter() decorator
    - Uses replace_message pattern: delete old + send new
    - Calls event.answer() to acknowledge callback
    - Sets FSM state using context.set_state() for multi-step flows
    
    Args:
        event: MessageCallback event from maxapi
        payload: One of ProfileActionPayload, ProfileViewPayload, ProfileAddPayload, 
                 ProfileDeleteOrgPayload, or ProfileDeleteKeyPayload (auto-parsed)
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 4.7, 4.10, 4.14, 4.15
    """
    from bots.max_bot.payloads import (
        ProfileActionPayload,
        ProfileViewPayload,
        ProfileAddPayload,
        ProfileDeleteOrgPayload,
        ProfileConfirmDeleteOrgPayload,
        ProfileDeleteKeyPayload,
        ProfileConfirmDeleteKeyPayload
    )
    
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Profile callback: max_user_id={max_user_id}, payload_type={type(payload).__name__}")
    
    try:
        # Check if this is a noop action FIRST - before answering or deleting
        is_noop = isinstance(payload, ProfileActionPayload) and payload.action == "noop"
        
        # Answer callback
        await event.answer()
        
        # If noop, just return without doing anything
        if is_noop:
            logger.debug(f"Noop action - ignoring: max_user_id={max_user_id}")
            return
        
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            logger.error(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            return
        
        # Delete old message (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Handle different payload types
        if isinstance(payload, ProfileViewPayload):
            # View organizations or keys list
            if payload.section == "orgs":
                await show_organizations_list(chat_id, user.id, session, messenger_adapter, payload.page)
            elif payload.section == "keys":
                await show_keys_list(chat_id, user.id, session, messenger_adapter, payload.page)
        
        elif isinstance(payload, ProfileAddPayload):
            # Add new INN or key
            if payload.item_type == "inn":
                await context.set_state(ProfileStates.adding_inn)
                from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
                keyboard = get_cancel_keyboard()
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=PROFILE_ADD_INN_PROMPT,
                    keyboard=keyboard,
                    parse_mode="HTML"
                )
            elif payload.item_type == "key":
                await context.set_state(ProfileStates.adding_key)
                from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
                keyboard = get_cancel_keyboard()
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=PROFILE_ADD_KEY_PROMPT,
                    keyboard=keyboard,
                    parse_mode="HTML"
                )
        
        elif isinstance(payload, ProfileDeleteOrgPayload):
            # Show confirmation for deleting organization
            await show_delete_organization_confirmation(
                chat_id, user.id, payload.inn, session, messenger_adapter
            )
        
        elif isinstance(payload, ProfileDeleteKeyPayload):
            # Show confirmation for deleting key
            await show_delete_key_confirmation(
                chat_id, user.id, payload.key_id, session, messenger_adapter
            )
        
        elif isinstance(payload, ProfileConfirmDeleteOrgPayload):
            # Confirmed - delete organization
            await delete_organization(chat_id, user.id, payload.inn, session, messenger_adapter)
        
        elif isinstance(payload, ProfileConfirmDeleteKeyPayload):
            # Confirmed - delete key
            await delete_key(chat_id, user.id, payload.key_id, session, messenger_adapter)
        
        elif isinstance(payload, ProfileActionPayload):
            # Handle simple actions
            action = payload.action
            
            if action == "notifications_menu":
                # Show notifications and broadcasts menu
                await show_notifications_menu(chat_id, user.id, session, messenger_adapter)
            
            elif action == "change_email":
                # Start email change flow
                await context.set_state(ProfileStates.changing_email)
                from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
                keyboard = get_cancel_keyboard()
                
                # Show current email if exists
                current_email_text = ""
                if user.email:
                    current_email_text = f"\n<i>Текущий email: {user.email}</i>\n"
                
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=PROFILE_CHANGE_EMAIL_PROMPT + current_email_text + "\n<i>Чтобы удалить email, введите: удалить</i>",
                    keyboard=keyboard,
                    parse_mode="HTML"
                )
            
            elif action == "change_phone":
                # Start phone change flow
                from bots.max_bot.handlers.user.phone_change import start_phone_change
                await start_phone_change(event, context, session, messenger_adapter)
            
            elif action == "toggle_notif":
                # Toggle notification preferences
                if user.notification_preferences:
                    # Show confirmation dialog for disabling notifications
                    await show_disable_notifications_confirmation(
                        chat_id, user.id, session, messenger_adapter
                    )
                else:
                    # Enable notifications without confirmation
                    user.notification_preferences = True
                    
                    logger.info(f"Notifications enabled: user_id={user.id}")
                    
                    await messenger_adapter.send_message(
                        chat_id=chat_id,
                        text=PROFILE_NOTIFICATIONS_ENABLED_SUCCESS,
                        parse_mode="HTML"
                    )
                    
                    # Show notifications menu again
                    await show_notifications_menu(chat_id, user.id, session, messenger_adapter)
            
            elif action == "confirm_disable_notif":
                # Confirmed - disable notifications
                user.notification_preferences = False
                
                logger.info(f"Notifications disabled: user_id={user.id}")
                
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=PROFILE_NOTIFICATIONS_DISABLED_SUCCESS,
                    parse_mode="HTML"
                )
                
                # Show notifications menu again
                await show_notifications_menu(chat_id, user.id, session, messenger_adapter)
            
            elif action == "main_menu":
                # Return to main menu
                await context.clear()
                
                # Show main menu with inline keyboard
                from services.ticket_service import get_user_active_tickets_count
                from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
                
                active_tickets_count = await get_user_active_tickets_count(session, user.id)
                keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
                
                from bots.max_bot.texts import MAIN_MENU_WELCOME_TEXT
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=MAIN_MENU_WELCOME_TEXT,
                    keyboard=keyboard,
                    parse_mode="HTML"
                )
            
            elif action == "back":
                # Return to profile view
                await show_profile(chat_id, user.id, session, messenger_adapter)
            
            elif action == "cancel":
                # Cancel current operation
                await context.clear()
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Действие отменено.",
                    parse_mode="HTML"
                )
                await show_profile(chat_id, user.id, session, messenger_adapter)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in handle_profile_callback: error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error in handle_profile_callback: error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_add_inn(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process new INN input for profile, validate, add organization.
    
    Validates INN format (10 or 12 digits).
    Checks INN availability via i-TAT API.
    Adds organization to user profile via i-TAT API and local database.
    Refreshes profile display with updated data.
    
    maxapi Pattern Notes:
    - Registered with FSM state filter: ProfileStates.adding_inn
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    - Clears FSM state using context.clear() after completion
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 4.7, 4.8, 4.9
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    inn = event.message.body.text.strip()
    
    logger.info(f"Processing add INN: max_user_id={max_user_id}, inn={inn}")
    
    # Validate INN format
    is_valid, error_msg = validate_inn(inn)
    
    if not is_valid:
        logger.warning(f"Invalid INN format: inn={inn}, error={error_msg}")
        from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
        keyboard = get_cancel_keyboard()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_INN.format(error_details=error_msg),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        return
    
    try:
        # Get user first
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            logger.error(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
    
        # Check for duplicate INN before calling i-TAT API
        existing_organizations = await get_user_organizations(session, user.id)
        existing_inns = [org.inn for org in existing_organizations]
        if inn in existing_inns:
            logger.info(f"Duplicate INN detected locally: user_id={user.id}, inn={inn}")
            await context.clear()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=PROFILE_INN_DUPLICATE,
                parse_mode="HTML"
            )
            await show_organizations_list(chat_id, user.id, session, messenger_adapter)
            return

        # Check INN with i-TAT API
        from services.i_tat_service import get_itat_client
        organization_name: str | None = None
        try:
            itat_client = get_itat_client()
            api_response = await itat_client.check_inn(
                messenger="max",
                user_id=user.max_user_id,
                inn=inn
            )
            logger.info(f"i-TAT API INN check successful: {api_response}")
            
            # New contract: {"status": "ok", "inn": "...", "exists": bool, "name": str|null}
            exists = api_response.get("exists")
            organization_name = api_response.get("name")

            if exists is False:
                logger.info(f"INN not found in 1C, requesting org name: inn={inn}")
                from bots.max_bot.texts import ENTER_ORG_NAME
                from bots.max_bot.keyboards.user.registration_kb import get_skip_keyboard
                await context.update_data(pending_inn=inn)
                await context.set_state(ProfileStates.adding_org_name)
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=ENTER_ORG_NAME.format(inn=inn),
                    keyboard=get_skip_keyboard(),
                    parse_mode="HTML"
                )
                return

            # Legacy fallback: old API returned is_valid field
            if exists is None and not api_response.get("is_valid", True):
                error_details = api_response.get("error_message", "INN не найден в базе данных")
                logger.warning(f"INN rejected by i-TAT API: inn={inn}, reason={error_details}")
                from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
                keyboard = get_cancel_keyboard()
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=f"❌ <b>Ошибка проверки ИНН</b>\n\n{error_details}\n\nПроверьте правильность введенного ИНН и попробуйте снова.",
                    keyboard=keyboard,
                    parse_mode="HTML"
                )
                return
                
        except Exception as api_error:
            logger.error(f"i-TAT API INN check error: {api_error}", exc_info=True)
            # Show error to testers for debugging
            from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
            keyboard = get_cancel_keyboard()
            error_type = type(api_error).__name__
            error_msg = str(api_error)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"⚠️ <b>Ошибка проверки ИНН через i-TAT API</b>\n\n"
                     f"<b>Тип ошибки:</b> {error_type}\n"
                     f"<b>Детали:</b> {error_msg}\n\n"
                     f"<i>Продолжаем с локальной валидацией...</i>",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            # Continue with local validation if API fails
            logger.info(f"Continuing with local INN validation due to API error")
        
        # Add organization to user profile locally
        await add_user_organization(session, user.id, inn, organization_name=organization_name)
        await session.commit()

        # Update user assets via i-TAT API
        assets_response = await call_itat_with_retry(
            session=session,
            operation="update_user_assets",
            payload=dict(
                messenger="max",
                user_id=user.max_user_id,
                asset_type="inn",
                action="add",
                value=inn,
            ),
            user_id=user.id,
        )
        if assets_response is not None:
            logger.info(f"Assets update result: {assets_response}")
        else:
            logger.warning(f"update_user_assets (add inn) queued for retry: user_id={user.id}, inn={inn}")
        
        logger.info(f"Organization added to profile: user_id={user.id}, inn={inn}")
        
        # Clear FSM state
        await context.clear()
        
        # Send success message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=PROFILE_INN_ADDED.format(inn=inn),
            parse_mode="HTML"
        )
        
        # Show organizations list
        await show_organizations_list(chat_id, user.id, session, messenger_adapter)
    
    except IntegrityError as e:
        logger.warning(
            f"Duplicate organization: user_id={user.id}, inn={inn}, error={e}",
            exc_info=True
        )
        await context.clear()
        
        # Send duplicate message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=PROFILE_INN_DUPLICATE,
            parse_mode="HTML"
        )
        
        # Show organizations list
        await show_organizations_list(chat_id, user.id, session, messenger_adapter)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error adding organization: inn={inn}, error={e}",
            exc_info=True
        )
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_add_inn_org_name(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process optional org name input after INN not found in 1C (profile flow).

    Saves INN + user-provided name, calls update_user_assets, shows success.
    """
    from bots.max_bot.texts import ENTER_ORG_NAME
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    org_name = event.message.body.text.strip()

    if len(org_name) > 100:
        from bots.max_bot.keyboards.user.registration_kb import get_skip_keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Название слишком длинное. Максимум 100 символов. Попробуйте ещё раз или нажмите «Пропустить»:",
            keyboard=get_skip_keyboard(),
            parse_mode="HTML"
        )
        return

    data = await context.get_data()
    inn = data.get("pending_inn")
    if not inn:
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
        await context.clear()
        return

    await _finalize_add_inn(chat_id, max_user_id, inn, org_name, context, session, messenger_adapter)


async def skip_add_inn_org_name(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle skip button during org name step in profile flow.
    Saves INN without a name and proceeds.
    """
    from bots.max_bot.payloads import RegistrationSkipPayload
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")

    data = await context.get_data()
    inn = data.get("pending_inn")
    if not inn:
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
        await context.clear()
        return

    await _finalize_add_inn(chat_id, max_user_id, inn, None, context, session, messenger_adapter)


async def _finalize_add_inn(
    chat_id: int,
    max_user_id: int,
    inn: str,
    organization_name: str | None,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Save INN (with optional name), call update_user_assets, show success."""
    try:
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
            await context.clear()
            return

        await add_user_organization(session, user.id, inn, organization_name=organization_name)
        await session.commit()

        assets_response = await call_itat_with_retry(
            session=session,
            operation="update_user_assets",
            payload=dict(
                messenger="max",
                user_id=user.max_user_id,
                asset_type="inn",
                action="add",
                value=inn,
            ),
            user_id=user.id,
        )
        if assets_response is not None:
            logger.info(f"Assets update result: {assets_response}")
        else:
            logger.warning(f"update_user_assets queued for retry: user_id={user.id}, inn={inn}")

        logger.info(f"Organization added to profile: user_id={user.id}, inn={inn}, name={organization_name}")
        await context.clear()

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=PROFILE_INN_ADDED.format(inn=inn),
            parse_mode="HTML"
        )
        await show_organizations_list(chat_id, user.id, session, messenger_adapter)

    except IntegrityError:
        await session.rollback()
        await context.clear()
        await messenger_adapter.send_message(chat_id=chat_id, text=PROFILE_INN_DUPLICATE, parse_mode="HTML")
        user = await get_user_by_max_id(session, max_user_id)
        if user:
            await show_organizations_list(chat_id, user.id, session, messenger_adapter)

    except SQLAlchemyError as e:
        logger.error(f"Database error in _finalize_add_inn: inn={inn}, error={e}", exc_info=True)
        await session.rollback()
        await context.clear()
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


async def process_add_key(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process new key input for profile, validate, check conflicts.
    
    Validates key format (XXXXX_XXXXX).
    Checks for key conflicts via i-TAT API.
    If conflict detected, creates KEY_CONFLICT ticket and flags key as PENDING_REVIEW.
    Adds key to user profile via i-TAT API and local database.
    Refreshes profile display with updated data.
    
    maxapi Pattern Notes:
    - Registered with FSM state filter: ProfileStates.adding_key
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    - Clears FSM state using context.clear() after completion
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 4.10, 4.11, 4.12, 4.13
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    key_number = event.message.body.text.strip()
    
    logger.info(f"Processing add key: max_user_id={max_user_id}, key={key_number}")
    
    # Validate GS_Key format
    is_valid, result = validate_gs_key(key_number)
    
    if not is_valid:
        logger.warning(f"Invalid GS_Key: key={key_number}, error={result}")
        from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
        keyboard = get_cancel_keyboard()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_KEY.format(error_details=result),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        return
    
    normalized_key = result
    
    try:
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            logger.error(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Check if user already has this key in DB
        existing_keys = await get_user_keys(session, user.id)
        if any(k.key_number == normalized_key for k in existing_keys):
            logger.warning(f"Duplicate key attempt: user_id={user.id}, key={normalized_key}")
            from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
            from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
            from bots.max_bot.payloads import ProfileViewPayload
            keyboard = Keyboard(
                buttons=[
                    [KeyboardButton(
                        text="⬅️ Назад к ключам",
                        payload=ProfileViewPayload(section="keys", page=0).pack()
                    )]
                ],
                inline=True
            )
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"⚠️ Ключ <b>{normalized_key}</b> уже добавлен в ваш профиль.",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        # Check for key conflicts via i-TAT API
        itat_client = get_itat_client()
        conflict_response = await itat_client.check_key_conflict(
            grand_key=normalized_key,
            user_id=user.max_user_id
        )
        
        logger.info(f"Key conflict check result: {conflict_response}")
        
        if conflict_response.get("status") == "conflict":
            # Conflict detected - create KEY_CONFLICT ticket and flag key
            owner_info = conflict_response.get("owner", "Неизвестный владелец")
            
            logger.warning(f"Key conflict detected: key={normalized_key}, owner={owner_info}")
            
            # Add key with PENDING_REVIEW status
            key = await add_user_key(
                session,
                user.id,
                normalized_key,
                KeyConflictStatus.PENDING_REVIEW
            )
            await session.commit()
            
            # Create KEY_CONFLICT ticket
            ticket_data = {
                "ticket_type": TicketType.KEY_CONFLICT,
                "user_id": user.id,
                "description": f"Конфликт ключа {normalized_key}. Текущий владелец: {owner_info}",
                "selected_key_ids": [key.id],
            }
            
            ticket = await create_ticket(session, ticket_data)
            await session.commit()
            
            logger.info(
                f"KEY_CONFLICT ticket created: ticket_id={ticket.id}, key={normalized_key}"
            )
            
            # Notify administrators about key conflict
            try:
                from bots.max_bot.utils.admin_notifications import notify_admins_key_conflict
                await notify_admins_key_conflict(session, user.id, normalized_key)
                logger.info(f"Key conflict notification sent for user_id={user.id}, key={normalized_key}")
            except Exception as notify_error:
                logger.error(
                    f"Failed to send key conflict notification for user_id={user.id}: {notify_error}",
                    exc_info=True
                )
            
            # Log ticket creation to I-TAT API
            try:
                from bots.max_bot.utils.itat_logging import log_ticket_creation_to_itat
                await log_ticket_creation_to_itat(session, ticket)
            except Exception as e:
                # Log error but don't fail ticket creation
                logger.error(
                    f"Failed to log key conflict ticket to I-TAT API: ticket_id={ticket.id}, error={e}",
                    exc_info=True
                )
            
            # Clear FSM state
            await context.clear()
            
            # Send conflict message
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ADD_KEY_CONFLICT.format(key=normalized_key),
                parse_mode="HTML"
            )
        
        else:
            # No conflict - add key normally
            await add_user_key(
                session,
                user.id,
                normalized_key,
                KeyConflictStatus.NONE
            )
            await session.commit()
            
            # Update user assets via i-TAT API
            assets_response = await call_itat_with_retry(
                session=session,
                operation="update_user_assets",
                payload=dict(
                    messenger="max",
                    user_id=user.max_user_id,
                    asset_type="grand_key",
                    action="add",
                    value=normalized_key,
                ),
                user_id=user.id,
            )
            if assets_response is not None:
                logger.info(f"Assets update result: {assets_response}")
            else:
                logger.warning(f"update_user_assets (add key) queued for retry: user_id={user.id}, key={normalized_key}")
            
            logger.info(f"GS_Key added to profile: user_id={user.id}, key={normalized_key}")
            
            # Clear FSM state
            await context.clear()
            
            # Send success message
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ADD_KEY_SUCCESS.format(key_number=normalized_key),
                parse_mode="HTML"
            )
        
        # Show keys list
        await show_keys_list(chat_id, user.id, session, messenger_adapter)
    
    except KeyAlreadyOwnedByUserError as e:
        logger.info(
            f"User tried to add their own key again: user_id={user.id}, key={normalized_key}"
        )
        await context.clear()
        from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
        from bots.max_bot.payloads import ProfileViewPayload
        keyboard = Keyboard(
            buttons=[
                [KeyboardButton(
                    text="⬅️ Назад к ключам",
                    payload=ProfileViewPayload(section="keys", page=0).pack()
                )]
            ],
            inline=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"ℹ️ Ключ <b>{normalized_key}</b> уже добавлен в ваш профиль. Вы не можете добавить свой же ключ повторно.",
            keyboard=keyboard,
            parse_mode="HTML"
        )

    except KeyConflictError as e:
        logger.warning(
            f"Key conflict (DB fallback): user_id={user.id}, key={normalized_key}, "
            f"owner_user_id={e.existing_user_id}"
        )
        await session.commit()
        await context.clear()

        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_key_conflict
            await notify_admins_key_conflict(session, user.id, normalized_key)
        except Exception as notify_error:
            logger.error(f"Failed to send key conflict notification: {notify_error}", exc_info=True)

        from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
        from bots.max_bot.payloads import ProfileViewPayload
        keyboard = Keyboard(
            buttons=[
                [KeyboardButton(
                    text="⬅️ Назад к ключам",
                    payload=ProfileViewPayload(section="keys", page=0).pack()
                )]
            ],
            inline=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ADD_KEY_CONFLICT.format(key=normalized_key),
            keyboard=keyboard,
            parse_mode="HTML"
        )

    except IntegrityError as e:
        logger.warning(
            f"Duplicate key: user_id={user.id}, key={normalized_key}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await context.clear()
        
        from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
        from bots.max_bot.payloads import ProfileViewPayload
        keyboard = Keyboard(
            buttons=[
                [KeyboardButton(
                    text="⬅️ Назад к ключам",
                    payload=ProfileViewPayload(section="keys", page=0).pack()
                )]
            ],
            inline=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"⚠️ Ключ <b>{normalized_key}</b> уже добавлен в ваш профиль.",
            keyboard=keyboard,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error processing add key: key={key_number}, error={e}",
            exc_info=True
        )
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def cancel_profile_action(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle cancellation during profile actions.
    
    Returns to profile view.
    Clears FSM state for profile actions.
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Clears FSM state using context.clear()
    - Shows main menu after cancellation (following maxapi patterns)
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 4.16
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    logger.info(f"Cancelling profile action: max_user_id={max_user_id}")
    
    try:
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            logger.error(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Clear FSM state
        await context.clear()
        
        # Send cancellation message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Действие отменено.",
            parse_mode="HTML"
        )
        
        # Show profile
        await show_profile(chat_id, user.id, session, messenger_adapter)
    
    except Exception as e:
        logger.error(
            f"Error cancelling profile action: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )




async def process_change_email(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process email change request.
    
    Validates new email and updates user profile.
    Allows removing email by entering "удалить".
    
    maxapi Pattern Notes:
    - Registered with FSM state filter: ProfileStates.changing_email
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    - Clears FSM state using context.clear() after completion
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    email_input = event.message.body.text.strip()
    
    logger.info(f"Processing email change: max_user_id={max_user_id}")
    
    try:
        # Get user
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            logger.error(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Check if user wants to remove email
        if email_input.lower() in ["удалить", "удали", "delete", "remove"]:
            user.email = None
            await session.commit()
            
            logger.info(f"Email removed: user_id={user.id}")
            
            await context.clear()
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=PROFILE_EMAIL_REMOVED,
                parse_mode="HTML"
            )
            
            # Show profile
            await show_profile(chat_id, user.id, session, messenger_adapter)
            return
        
        # Validate email format
        from services.validation_service import validate_email
        is_valid, result = validate_email(email_input)
        
        if not is_valid:
            logger.warning(f"Invalid email: email={email_input}, error={result}")
            from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
            keyboard = get_cancel_keyboard()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_VALIDATION_EMAIL.format(error_details=result),
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        normalized_email = result
        
        # Update email
        user.email = normalized_email
        await session.commit()
        
        logger.info(f"Email updated: user_id={user.id}, email={normalized_email}")
        
        # Clear FSM state
        await context.clear()
        
        # Send success message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=PROFILE_EMAIL_UPDATED.format(email=normalized_email),
            parse_mode="HTML"
        )
        
        # Show profile
        await show_profile(chat_id, user.id, session, messenger_adapter)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error updating email: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error processing email change: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
