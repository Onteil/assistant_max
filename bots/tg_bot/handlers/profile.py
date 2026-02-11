"""
Profile Handler

Manages user profile display and management operations.
Allows users to view profile data, add organizations/keys, change phone, and toggle notifications.

Requirements: 16.1-16.7, 17.1-17.7, 18.1-18.8, 19.1-19.7, 20.1-20.5
"""

import logging
from datetime import datetime

import httpx
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import ProfileCallback
from bots.tg_bot.keyboards.profile_kb import get_profile_actions_keyboard
from bots.tg_bot.keyboards.registration_kb import get_cancel_keyboard
from bots.tg_bot.states import ProfileStates
from bots.tg_bot.texts import (
    ADD_KEY_CONFLICT,
    ADD_KEY_SUCCESS,
    BTN_CANCEL,
    ERROR_VALIDATION_EMAIL,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    ERROR_VALIDATION_PHONE,
    PROFILE_ADD_INN_PROMPT,
    PROFILE_ADD_KEY_PROMPT,
    PROFILE_CHANGE_PHONE_PROMPT,
    PROFILE_CHANGE_PHONE_SUBMITTED,
    PROFILE_INN_ADDED,
    PROFILE_INN_DUPLICATE,
    PROFILE_INFO,
    PROFILE_NOTIFICATIONS_DISABLED_DESC,
    PROFILE_NOTIFICATIONS_ENABLED_DESC,
    PROFILE_NOTIFICATIONS_OFF,
    PROFILE_NOTIFICATIONS_ON,
    PROFILE_NOTIFICATIONS_TOGGLED,
    PROFILE_NO_SUBSCRIPTION,
    PROFILE_ACTIVE_SUBSCRIPTION,
    PROFILE_EXPIRED_SUBSCRIPTION,
)
from database.models import KeyConflictStatus, TicketType, TicketStatus, Ticket
from services.i_tat_service import get_itat_client
from services.user_service import (
    add_user_key,
    add_user_organization,
    get_user_by_tg_id,
    get_user_keys,
    get_user_organizations,
)
from services.validation_service import (
    validate_gs_key,
    validate_inn,
    validate_phone_number,
)

logger = logging.getLogger(__name__)

router = Router(name="profile")


# ========== Profile Display ==========


@router.message(Command("profile"))
async def show_profile(message: Message, session: AsyncSession):
    """
    Display user profile with all associated data.
    
    Shows:
    - Full name, phone, registration date
    - All organizations with INN
    - All GS_Keys with status
    - Subscription status and expiry date
    - Notification preferences
    
    Requirements: 16.1-16.7
    """
    telegram_id = message.from_user.id
    
    try:
        # Get user data
        user = await get_user_by_tg_id(session, telegram_id)
        
        if not user:
            await message.answer(
                "❌ Пользователь не найден.\n"
                "Пожалуйста, пройдите регистрацию с помощью /start"
            )
            logger.warning(f"Profile requested for non-existent user: {telegram_id}")
            return
        
        # Get organizations
        organizations = await get_user_organizations(session, telegram_id)
        
        # Get keys
        keys = await get_user_keys(session, telegram_id)
        
        # Format organizations list
        if organizations:
            org_list = "\n".join([
                f"  • ИНН: {org.inn}" + (f" - {org.organization_name}" if org.organization_name else "")
                for org in organizations
            ])
        else:
            org_list = "  Нет добавленных организаций"
        
        # Format keys list
        if keys:
            key_list = "\n".join([
                f"  • {key.key_number}" + 
                (f" ⚠️ (на проверке)" if key.conflict_status == KeyConflictStatus.PENDING_REVIEW else "")
                for key in keys
            ])
        else:
            key_list = "  Нет добавленных ключей"
        
        # Format subscription status
        if user.subscription_status and user.subscription_status.value == "active":
            if user.subscription_end_date:
                expiry_str = user.subscription_end_date.strftime("%d.%m.%Y")
                subscription_status = PROFILE_ACTIVE_SUBSCRIPTION.format(expiry_date=expiry_str)
            else:
                subscription_status = "✅ Активна"
            subscription_details = ""
        elif user.subscription_status and user.subscription_status.value == "expired":
            if user.subscription_end_date:
                expiry_str = user.subscription_end_date.strftime("%d.%m.%Y")
                subscription_status = PROFILE_EXPIRED_SUBSCRIPTION.format(expiry_date=expiry_str)
            else:
                subscription_status = "⚠️ Истекла"
            subscription_details = ""
        else:
            subscription_status = PROFILE_NO_SUBSCRIPTION
            subscription_details = ""
        
        # Format notification status
        notification_status = (
            PROFILE_NOTIFICATIONS_ON if user.notification_preferences
            else PROFILE_NOTIFICATIONS_OFF
        )
        
        # Format registration date
        reg_date = user.created_at.strftime("%d.%m.%Y") if user.created_at else "Неизвестно"
        
        # Build profile message
        profile_text = PROFILE_INFO.format(
            full_name=user.full_name,
            phone=user.phone_number,
            registration_date=reg_date,
            organizations_count=len(organizations),
            organizations_list=org_list,
            keys_count=len(keys),
            keys_list=key_list,
            subscription_status=subscription_status,
            subscription_details=subscription_details,
            notification_status=notification_status
        )
        
        # Send profile with action buttons
        keyboard = await get_profile_actions_keyboard()
        await message.answer(
            profile_text,
            reply_markup=keyboard
        )
        
        logger.info(f"Profile displayed for user: {telegram_id}")
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error displaying profile for user {telegram_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при загрузке профиля.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Profile Actions ==========


@router.callback_query(ProfileCallback.filter())
async def handle_profile_action(
    callback: CallbackQuery,
    callback_data: ProfileCallback,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handle profile action button callbacks.
    
    Routes to appropriate handler based on action:
    - add_inn: Initiate INN addition flow
    - add_key: Initiate key addition flow
    - change_phone: Initiate phone change request flow
    - toggle_notif: Toggle notification preferences
    
    Requirements: 17.1, 18.1, 19.1, 20.1
    """
    action = callback_data.action
    telegram_id = callback.from_user.id
    
    try:
        if action == "add_inn":
            await add_organization(callback, state)
        
        elif action == "add_key":
            await add_gs_key(callback, state)
        
        elif action == "change_phone":
            await request_phone_change(callback, state)
        
        elif action == "toggle_notif":
            await toggle_notifications(callback, session, telegram_id)
        
        else:
            await callback.answer("❌ Неизвестное действие")
            logger.warning(f"Unknown profile action: {action} from user {telegram_id}")
    
    except Exception as e:
        logger.error(
            f"Error handling profile action {action} for user {telegram_id}: {e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# ========== Add Organization ==========


async def add_organization(callback: CallbackQuery, state: FSMContext):
    """
    Initiate INN addition flow.
    
    Sets state and prompts for INN input.
    
    Requirements: 17.1
    """
    await state.set_state(ProfileStates.adding_inn)
    await callback.message.edit_text(PROFILE_ADD_INN_PROMPT)
    await callback.answer()
    
    logger.info(f"User {callback.from_user.id} started INN addition flow")


@router.message(ProfileStates.adding_inn, F.text)
async def process_new_inn(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handle new INN input in profile management.
    
    Validates format, checks for duplicates, and creates organization association.
    
    Requirements: 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 22.1-22.5
    """
    inn = message.text.strip()
    telegram_id = message.from_user.id
    
    # Check for cancel
    if inn == BTN_CANCEL:
        await state.clear()
        await message.answer(
            "❌ Добавление организации отменено.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {telegram_id} cancelled INN addition")
        return
    
    # Validate INN format
    is_valid, error_message = validate_inn(inn)
    
    if not is_valid:
        await message.answer(
            ERROR_VALIDATION_INN.format(error_details=error_message)
        )
        logger.warning(f"User {telegram_id} provided invalid INN: {inn}")
        return
    
    # Add organization
    try:
        # Check if already exists for this user
        existing_orgs = await get_user_organizations(session, telegram_id)
        if any(org.inn == inn for org in existing_orgs):
            await message.answer(PROFILE_INN_DUPLICATE)
            await state.clear()
            logger.info(f"User {telegram_id} attempted to add duplicate INN: {inn}")
            return
        
        # Add organization
        organization = await add_user_organization(session, telegram_id, inn)
        await session.commit()
        
        # Clear state
        await state.clear()
        
        # Show success message
        await message.answer(
            PROFILE_INN_ADDED.format(inn=inn),
            reply_markup=ReplyKeyboardRemove()
        )
        
        logger.info(f"User {telegram_id} added organization: {inn}")
    
    except IntegrityError:
        # Organization already exists - this is fine
        await session.rollback()
        await state.clear()
        
        await message.answer(
            PROFILE_INN_ADDED.format(inn=inn),
            reply_markup=ReplyKeyboardRemove()
        )
        
        logger.info(f"User {telegram_id} added existing organization: {inn}")
    
    except SQLAlchemyError as e:
        await session.rollback()
        await state.clear()
        
        logger.error(
            f"Database error adding organization for user {telegram_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при добавлении организации.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )


# ========== Add GS_Key ==========


async def add_gs_key(callback: CallbackQuery, state: FSMContext):
    """
    Initiate GS_Key addition flow.
    
    Sets state and prompts for key input.
    
    Requirements: 18.1
    """
    await state.set_state(ProfileStates.adding_key)
    await callback.message.edit_text(PROFILE_ADD_KEY_PROMPT)
    await callback.answer()
    
    logger.info(f"User {callback.from_user.id} started key addition flow")


@router.message(ProfileStates.adding_key, F.text)
async def process_new_key(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handle new GS_Key input in profile management.
    
    Validates format, checks for conflicts via API, and creates key record.
    If conflict detected, creates admin ticket.
    
    Requirements: 18.2, 18.3, 18.4, 18.5, 18.6, 18.7, 18.8, 23.1-23.5
    """
    key_input = message.text.strip()
    telegram_id = message.from_user.id
    
    # Check for cancel
    if key_input == BTN_CANCEL:
        await state.clear()
        await message.answer(
            "❌ Добавление ключа отменено.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {telegram_id} cancelled key addition")
        return
    
    # Validate key format
    is_valid, result = validate_gs_key(key_input)
    
    if not is_valid:
        await message.answer(
            ERROR_VALIDATION_KEY.format(error_details=result)
        )
        logger.warning(f"User {telegram_id} provided invalid key format: {key_input}")
        return
    
    normalized_key = result
    
    # Check for conflict via API
    api_client = get_itat_client()
    conflict_detected = False
    
    try:
        conflict_response = await api_client.check_key_conflict(
            grand_key=normalized_key,
            telegram_id=telegram_id
        )
        
        if conflict_response.get("status") == "conflict":
            conflict_detected = True
            logger.warning(
                f"Key conflict detected for user {telegram_id}: "
                f"key={normalized_key}"
            )
    
    except httpx.HTTPStatusError as e:
        # HTTP error from API - log and continue with graceful degradation
        logger.error(
            f"API HTTP error checking key conflict for user {telegram_id}: "
            f"status={e.response.status_code}, error={e}",
            exc_info=True
        )
        # Continue without conflict check (graceful degradation)
    
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        # Network/timeout error - log and continue with graceful degradation
        logger.error(
            f"API connection error checking key conflict for user {telegram_id}: {e}",
            exc_info=True
        )
        # Continue without conflict check (graceful degradation)
    
    except Exception as e:
        logger.error(
            f"Unexpected error checking key conflict for user {telegram_id}: {e}",
            exc_info=True
        )
        # Continue without conflict check (graceful degradation)
    
    # Add key to user's profile
    try:
        # Get user for phone number (needed for ticket)
        user = await get_user_by_tg_id(session, telegram_id)
        
        conflict_status = (
            KeyConflictStatus.PENDING_REVIEW if conflict_detected
            else KeyConflictStatus.NONE
        )
        
        gs_key = await add_user_key(
            session,
            telegram_id,
            normalized_key,
            conflict_status
        )
        
        # Create admin ticket if conflict detected
        if conflict_detected:
            await create_key_conflict_ticket(
                session,
                telegram_id,
                normalized_key,
                user.phone_number if user else ""
            )
        
        await session.commit()
        
        # Clear state
        await state.clear()
        
        # Show appropriate message
        if conflict_detected:
            await message.answer(
                ADD_KEY_CONFLICT,
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await message.answer(
                ADD_KEY_SUCCESS.format(key_number=normalized_key),
                reply_markup=ReplyKeyboardRemove()
            )
        
        logger.info(
            f"User {telegram_id} added key: {normalized_key}, "
            f"conflict={conflict_detected}"
        )
    
    except IntegrityError:
        # Key already exists
        await session.rollback()
        await state.clear()
        
        await message.answer(
            "⚠️ Этот ключ уже добавлен в ваш профиль.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        logger.info(f"User {telegram_id} attempted to add duplicate key: {normalized_key}")
    
    except SQLAlchemyError as e:
        await session.rollback()
        await state.clear()
        
        logger.error(
            f"Database error adding key for user {telegram_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при добавлении ключа.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )


async def create_key_conflict_ticket(
    session: AsyncSession,
    telegram_id: int,
    key_number: str,
    phone_number: str
):
    """
    Create admin ticket for GS_Key conflict resolution.
    
    Requirements: 18.6, 18.7
    """
    try:
        ticket = Ticket(
            ticket_type=TicketType.RENEWAL,  # Using RENEWAL type for admin tasks
            ticket_status=TicketStatus.NEW,
            tg_user_id=telegram_id,
            description=(
                f"⚠️ Конфликт ключа при добавлении в профиль\n\n"
                f"Пользователь: {telegram_id}\n"
                f"Телефон: {phone_number}\n"
                f"Ключ: {key_number}\n\n"
                f"Требуется проверка и разрешение конфликта."
            ),
        )
        
        session.add(ticket)
        await session.flush()
        
        logger.info(
            f"Key conflict ticket created: ticket_id={ticket.id}, "
            f"user={telegram_id}, key={key_number}"
        )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Error creating key conflict ticket for user {telegram_id}: {e}",
            exc_info=True
        )
        # Don't raise - conflict ticket creation failure shouldn't block key addition


# ========== Phone Change Request ==========


async def request_phone_change(callback: CallbackQuery, state: FSMContext):
    """
    Initiate phone change request flow.
    
    Sets state and prompts for new phone number.
    
    Requirements: 19.1, 19.2
    """
    await state.set_state(ProfileStates.changing_phone)
    await callback.message.edit_text(PROFILE_CHANGE_PHONE_PROMPT)
    await callback.answer()
    
    logger.info(f"User {callback.from_user.id} started phone change request")


@router.message(ProfileStates.changing_phone, F.text)
async def process_phone_change_request(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handle phone change request.
    
    Validates new phone number and creates admin ticket for approval.
    Does not update phone_number in User table until admin approval.
    
    Requirements: 19.3, 19.4, 19.5, 19.6, 19.7, 21.1-21.5
    """
    new_phone = message.text.strip()
    telegram_id = message.from_user.id
    
    # Check for cancel
    if new_phone == BTN_CANCEL:
        await state.clear()
        await message.answer(
            "❌ Изменение телефона отменено.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {telegram_id} cancelled phone change request")
        return
    
    # Validate phone format
    is_valid, result = validate_phone_number(new_phone)
    
    if not is_valid:
        await message.answer(
            ERROR_VALIDATION_PHONE.format(error_details=result)
        )
        logger.warning(f"User {telegram_id} provided invalid phone format: {new_phone}")
        return
    
    normalized_phone = result
    
    # Get current user data
    try:
        user = await get_user_by_tg_id(session, telegram_id)
        
        if not user:
            await message.answer(
                "❌ Пользователь не найден.",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()
            return
        
        current_phone = user.phone_number
        
        # Create admin ticket for phone change approval
        ticket = Ticket(
            ticket_type=TicketType.RENEWAL,  # Using RENEWAL type for admin tasks
            ticket_status=TicketStatus.NEW,
            tg_user_id=telegram_id,
            description=(
                f"📱 Запрос на изменение номера телефона\n\n"
                f"Пользователь: {user.full_name}\n"
                f"Telegram ID: {telegram_id}\n"
                f"Текущий номер: {current_phone}\n"
                f"Новый номер: {normalized_phone}\n\n"
                f"Требуется одобрение администратора."
            ),
        )
        
        session.add(ticket)
        await session.commit()
        
        # Clear state
        await state.clear()
        
        # Show success message
        await message.answer(
            PROFILE_CHANGE_PHONE_SUBMITTED.format(
                current_phone=current_phone,
                new_phone=normalized_phone
            ),
            reply_markup=ReplyKeyboardRemove()
        )
        
        logger.info(
            f"Phone change request created: user={telegram_id}, "
            f"ticket_id={ticket.id}, old={current_phone}, new={normalized_phone}"
        )
    
    except SQLAlchemyError as e:
        await session.rollback()
        await state.clear()
        
        logger.error(
            f"Database error creating phone change request for user {telegram_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при создании запроса.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )


# ========== Toggle Notifications ==========


async def toggle_notifications(
    callback: CallbackQuery,
    session: AsyncSession,
    telegram_id: int
):
    """
    Toggle notification preferences.
    
    Flips notification_preferences boolean and updates database.
    Users with false preference are excluded from broadcast deliveries.
    
    Requirements: 20.2, 20.3, 20.4, 20.5
    """
    try:
        # Get user
        user = await get_user_by_tg_id(session, telegram_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            logger.warning(f"Toggle notifications for non-existent user: {telegram_id}")
            return
        
        # Toggle preference
        old_value = user.notification_preferences
        user.notification_preferences = not old_value
        
        await session.commit()
        
        # Determine status text
        new_status = (
            PROFILE_NOTIFICATIONS_ON if user.notification_preferences
            else PROFILE_NOTIFICATIONS_OFF
        )
        
        # Determine description
        description = (
            PROFILE_NOTIFICATIONS_ENABLED_DESC if user.notification_preferences
            else PROFILE_NOTIFICATIONS_DISABLED_DESC
        )
        
        # Show confirmation
        await callback.message.edit_text(
            PROFILE_NOTIFICATIONS_TOGGLED.format(
                status=new_status,
                description=description
            )
        )
        await callback.answer()
        
        logger.info(
            f"Notifications toggled for user {telegram_id}: "
            f"{old_value} -> {user.notification_preferences}"
        )
    
    except SQLAlchemyError as e:
        await session.rollback()
        
        logger.error(
            f"Database error toggling notifications for user {telegram_id}: {e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Произошла ошибка при обновлении настроек",
            show_alert=True
        )
