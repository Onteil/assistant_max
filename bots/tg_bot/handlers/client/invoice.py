"""
Invoice Request Handler

Manages the invoice request conversation flow.
Collects organization, GS_Keys, description, and delivery method through multi-step FSM.
Creates invoice tickets and routes to assigned managers.

Requirements: 7.1-7.6, 8.1-8.6, 9.1-9.5, 10.1-10.8, 11.1-11.5
"""

import logging
from typing import Any

import httpx
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bots.tg_bot.callback_datas import (
    DeliveryCallback,
    KeyCallback,
    OrganizationCallback,
)
from bots.tg_bot.keyboards.invoice_kb import (
    get_delivery_method_keyboard,
    get_key_selection_keyboard,
    get_organization_keyboard,
)
from bots.tg_bot.keyboards.registration_kb import get_cancel_keyboard
from bots.tg_bot.states import InvoiceStates
from bots.tg_bot.texts import (
    ADD_KEY_CONFLICT,
    ADD_KEY_SUCCESS,
    BTN_CANCEL,
    ERROR_TEXT_TOO_LONG,
    ERROR_VALIDATION_EMAIL,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    INVOICE_ADD_NEW_INN,
    INVOICE_ADD_NEW_KEY,
    INVOICE_CONFIRMATION,
    INVOICE_CREATED,
    INVOICE_CREATED_NO_MANAGER,
    INVOICE_ENTER_DESCRIPTION,
    INVOICE_ENTER_EMAIL,
    INVOICE_INN_ADDED,
    INVOICE_KEY_ADDED,
    INVOICE_KEY_CONFLICT,
    INVOICE_PROCESSING,
    INVOICE_RESPONSE_TIME_EXTENDED,
    INVOICE_RESPONSE_TIME_NON_WORKING,
    INVOICE_RESPONSE_TIME_WORKING,
    INVOICE_SELECT_DELIVERY,
    INVOICE_SELECT_KEYS,
    INVOICE_SELECT_ORGANIZATION,
)
from database.models import DeliveryMethod, GS_Key, KeyConflictStatus, TicketType, WorkMode
from services.i_tat_service import get_itat_client
from services.ticket_service import (
    create_ticket,
    determine_assigned_manager,
    get_current_work_mode,
    route_ticket,
    send_staff_notification,
)
from services.user_service import (
    add_user_key,
    add_user_organization,
    get_user_keys,
    get_user_organizations,
)
from services.validation_service import validate_email, validate_gs_key, validate_inn

logger = logging.getLogger(__name__)

router = Router(name="invoice")


# ========== Entry Point ==========


@router.message(Command("invoice"))
async def start_invoice_request(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Entry point for invoice request.
    
    Displays organization selection with user's existing organizations.
    Includes options to add new INN or skip organization selection.
    
    Requirements: 7.1, 7.2
    """
    telegram_id = message.from_user.id
    
    try:
        # Clear any existing state
        await state.clear()
        
        # Get user first to get user.id
        from services.user_service import get_user_by_tg_id
        user = await get_user_by_tg_id(session, telegram_id)
        
        if not user:
            await message.answer(
                "❌ Пользователь не найден.\n"
                "Пожалуйста, пройдите регистрацию с помощью /start"
            )
            return
        
        # Get user's organizations using user.id
        organizations = await get_user_organizations(session, user.id)
        
        # Set initial state
        await state.set_state(InvoiceStates.selecting_organization)
        await state.update_data(
            selected_key_ids=set(),
            current_page=0
        )
        
        # Display organization selection
        keyboard = await get_organization_keyboard(organizations, page=0)
        
        # Check if message has reply_markup (inline keyboard) - means it's from callback
        # and can be edited
        if message.reply_markup is not None:
            try:
                await message.edit_text(
                    INVOICE_SELECT_ORGANIZATION,
                    reply_markup=keyboard
                )
            except Exception:
                # If edit fails, send new message
                await message.answer(
                    INVOICE_SELECT_ORGANIZATION,
                    reply_markup=keyboard
                )
        else:
            # Regular message, send new
            await message.answer(
                INVOICE_SELECT_ORGANIZATION,
                reply_markup=keyboard
            )
        
        logger.info(
            f"User {telegram_id} started invoice request, "
            f"{len(organizations)} organizations available"
        )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error starting invoice request for user {telegram_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при загрузке данных.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )


# ========== Organization Selection ==========


@router.callback_query(
    InvoiceStates.selecting_organization,
    OrganizationCallback.filter()
)
async def process_organization_selection(
    callback: CallbackQuery,
    callback_data: OrganizationCallback,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handles organization selection from inline keyboard.
    
    Supports:
    - Selecting an organization
    - Adding new INN
    - Skipping organization selection
    - Pagination
    
    Requirements: 7.3, 7.4
    """
    telegram_id = callback.from_user.id
    action = callback_data.action
    
    try:
        if action == "cancel":
            # Cancel invoice request
            await state.clear()
            await callback.message.edit_text("❌ Запрос счета отменен.")
            await callback.answer()
            logger.info(f"User {telegram_id} cancelled invoice request")
            return
        
        elif action == "select":
            # Organization selected
            inn = callback_data.inn
            await state.update_data(organization_inn=inn)
            
            # Move to key selection
            await proceed_to_key_selection(callback, state, session, telegram_id)
        
        elif action == "add_new":
            # User wants to add new INN
            await state.set_state(InvoiceStates.adding_new_inn)
            await callback.message.edit_text(INVOICE_ADD_NEW_INN)
            await callback.answer()
        
        elif action == "skip":
            # Skip organization selection
            await state.update_data(organization_inn=None)
            await proceed_to_key_selection(callback, state, session, telegram_id)
        
        elif action == "page":
            # Pagination
            page = callback_data.page
            
            # Get user first
            from services.user_service import get_user_by_tg_id
            user = await get_user_by_tg_id(session, telegram_id)
            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            organizations = await get_user_organizations(session, user.id)
            keyboard = await get_organization_keyboard(organizations, page=page)
            
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer()
        
        else:
            await callback.answer("❌ Неизвестное действие")
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in organization selection for user {telegram_id}: {e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка", show_alert=True)


async def proceed_to_key_selection(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    telegram_id: int
):
    """Helper to move to key selection step."""
    await state.set_state(InvoiceStates.selecting_keys)
    
    # Get user first
    from services.user_service import get_user_by_tg_id
    user = await get_user_by_tg_id(session, telegram_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    # Get user's keys using user.id
    keys = await get_user_keys(session, user.id)
    
    # Get selected key IDs from state
    data = await state.get_data()
    selected_key_ids = data.get("selected_key_ids", set())
    
    # Display key selection
    keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
    await callback.message.edit_text(
        INVOICE_SELECT_KEYS,
        reply_markup=keyboard
    )
    await callback.answer()


@router.message(InvoiceStates.adding_new_inn, F.text)
async def process_new_inn(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handles new INN input during invoice request.
    
    Validates format and adds organization to user's profile.
    
    Requirements: 7.4, 7.5, 22.1-22.5
    """
    inn = message.text.strip()
    telegram_id = message.from_user.id
    
    # Get user first to get user.id
    from services.user_service import get_user_by_tg_id
    user = await get_user_by_tg_id(session, telegram_id)
    
    if not user:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "Пожалуйста, пройдите регистрацию с помощью /start"
        )
        await state.clear()
        return
    
    # Check for cancel
    if inn == BTN_CANCEL:
        # Return to organization selection
        await state.set_state(InvoiceStates.selecting_organization)
        organizations = await get_user_organizations(session, user.id)
        keyboard = await get_organization_keyboard(organizations, page=0)
        await message.answer(
            INVOICE_SELECT_ORGANIZATION,
            reply_markup=keyboard
        )
        return
    
    # Validate INN
    is_valid, error_message = validate_inn(inn)
    
    if not is_valid:
        await message.answer(
            ERROR_VALIDATION_INN.format(error_details=error_message)
        )
        logger.warning(f"User {telegram_id} provided invalid INN: {inn}")
        return
    
    # Add organization using user.id
    try:
        await add_user_organization(session, user.id, inn)
        await session.commit()
        
        # Store in state
        await state.update_data(organization_inn=inn)
        
        # Show success and move to key selection
        await message.answer(INVOICE_INN_ADDED)
        
        await state.set_state(InvoiceStates.selecting_keys)
        keys = await get_user_keys(session, user.id)
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())
        
        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
        await message.answer(
            INVOICE_SELECT_KEYS,
            reply_markup=keyboard
        )
        
        logger.info(f"User {telegram_id} (user_id={user.id}) added new INN: {inn}")
    
    except IntegrityError:
        # INN already exists - this is fine, just use it
        await session.rollback()
        await state.update_data(organization_inn=inn)
        
        await message.answer(INVOICE_INN_ADDED)
        
        await state.set_state(InvoiceStates.selecting_keys)
        keys = await get_user_keys(session, user.id)
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())
        
        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
        await message.answer(
            INVOICE_SELECT_KEYS,
            reply_markup=keyboard
        )
    
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error adding INN for user {telegram_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при добавлении организации.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Key Selection ==========


@router.callback_query(
    InvoiceStates.selecting_keys,
    KeyCallback.filter()
)
async def process_key_selection(
    callback: CallbackQuery,
    callback_data: KeyCallback,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handles GS_Key multi-select with toggle functionality.
    
    Supports:
    - Toggling key selection (add/remove from selected set)
    - Adding new key
    - Completing selection (Done)
    - Pagination
    - Back to previous step
    - Cancel
    
    Requirements: 8.2, 8.3, 8.4
    """
    telegram_id = callback.from_user.id
    action = callback_data.action
    
    try:
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())
        
        if action == "cancel":
            # Cancel invoice request
            await state.clear()
            await callback.message.edit_text("❌ Запрос счета отменен.")
            await callback.answer()
            logger.info(f"User {telegram_id} cancelled invoice request at keys step")
            return
        
        elif action == "back":
            # Go back to organization selection
            await state.set_state(InvoiceStates.selecting_organization)
            
            # Get user first
            from services.user_service import get_user_by_tg_id
            user = await get_user_by_tg_id(session, telegram_id)
            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            organizations = await get_user_organizations(session, user.id)
            keyboard = await get_organization_keyboard(organizations, page=0)
            
            await callback.message.edit_text(
                INVOICE_SELECT_ORGANIZATION,
                reply_markup=keyboard
            )
            await callback.answer()
            return
        
        elif action == "toggle":
            # Toggle key selection
            key_id = callback_data.key_id
            
            # Get user first
            from services.user_service import get_user_by_tg_id
            user = await get_user_by_tg_id(session, telegram_id)
            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            # Check if key is under review (PENDING_REVIEW status)
            from database.models import KeyConflictStatus
            key_result = await session.execute(
                select(GS_Key).where(GS_Key.id == key_id)
            )
            key = key_result.scalar_one_or_none()
            
            if key and key.conflict_status == KeyConflictStatus.PENDING_REVIEW:
                await callback.answer(
                    "⚠️ Этот ключ находится на проверке и не может быть выбран. Пожалуйста, выберите другой ключ.",
                    show_alert=True
                )
                return
            
            if key_id in selected_key_ids:
                selected_key_ids.remove(key_id)
            else:
                selected_key_ids.add(key_id)
            
            await state.update_data(selected_key_ids=selected_key_ids)
            
            # Update keyboard only (don't change text)
            keys = await get_user_keys(session, user.id)
            keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
            
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer()
        
        elif action == "add_new":
            # User wants to add new key
            await state.set_state(InvoiceStates.adding_new_key)
            await callback.message.edit_text(INVOICE_ADD_NEW_KEY)
            await callback.answer()
        
        elif action == "done":
            # Complete key selection
            if not selected_key_ids:
                await callback.answer(
                    "⚠️ Выберите хотя бы один ключ",
                    show_alert=True
                )
                return
            
            # Move to description input
            await state.set_state(InvoiceStates.entering_description)
            
            from bots.tg_bot.keyboards.invoice_kb import get_description_input_keyboard
            keyboard = await get_description_input_keyboard()
            
            await callback.message.edit_text(
                INVOICE_ENTER_DESCRIPTION,
                reply_markup=keyboard
            )
            await callback.answer()
        
        elif action == "page":
            # Pagination
            page = callback_data.page
            
            # Get user first
            from services.user_service import get_user_by_tg_id
            user = await get_user_by_tg_id(session, telegram_id)
            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            keys = await get_user_keys(session, user.id)
            keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=page)
            
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer()
        
        else:
            await callback.answer("❌ Неизвестное действие")
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in key selection for user {telegram_id}: {e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.message(InvoiceStates.adding_new_key, F.text)
async def process_new_key(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handles new GS_Key input during invoice request.
    
    Validates format, checks for conflicts via API, and adds key to user's profile.
    
    Requirements: 8.4, 18.3, 23.1-23.5
    """
    key_input = message.text.strip()
    telegram_id = message.from_user.id
    
    # Get user first to get user.id
    from services.user_service import get_user_by_tg_id
    user = await get_user_by_tg_id(session, telegram_id)
    
    if not user:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "Пожалуйста, пройдите регистрацию с помощью /start"
        )
        await state.clear()
        return
    
    # Check for cancel
    if key_input == BTN_CANCEL:
        # Return to key selection
        await state.set_state(InvoiceStates.selecting_keys)
        keys = await get_user_keys(session, user.id)
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())
        
        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
        await message.answer(
            INVOICE_SELECT_KEYS,
            reply_markup=keyboard
        )
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
            user_id=user.id
        )
        
        if conflict_response.get("status") == "conflict":
            conflict_detected = True
            logger.warning(
                f"Key conflict detected for user {telegram_id} (user_id={user.id}): "
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
        conflict_status = (
            KeyConflictStatus.PENDING_REVIEW if conflict_detected
            else KeyConflictStatus.NONE
        )
        
        gs_key = await add_user_key(
            session,
            user.id,
            normalized_key,
            conflict_status
        )
        await session.commit()
        
        # Show appropriate message
        if conflict_detected:
            await message.answer(INVOICE_KEY_CONFLICT)
        else:
            await message.answer(
                ADD_KEY_SUCCESS.format(key_number=normalized_key)
            )
        
        # Return to key selection with new key selected
        await state.set_state(InvoiceStates.selecting_keys)
        
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())
        selected_key_ids.add(gs_key.id)
        await state.update_data(selected_key_ids=selected_key_ids)
        
        keys = await get_user_keys(session, user.id)
        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
        
        await message.answer(
            INVOICE_SELECT_KEYS,
            reply_markup=keyboard
        )
        
        logger.info(
            f"User {telegram_id} (user_id={user.id}) added new key: {normalized_key}, "
            f"conflict={conflict_detected}"
        )
    
    except IntegrityError:
        # Key already exists - this is fine
        await session.rollback()
        await message.answer(
            "⚠️ Этот ключ уже добавлен в ваш профиль."
        )
        
        # Return to key selection
        await state.set_state(InvoiceStates.selecting_keys)
        keys = await get_user_keys(session, user.id)
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())
        
        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
        await message.answer(
            INVOICE_SELECT_KEYS,
            reply_markup=keyboard
        )
    
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error adding key for user {telegram_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при добавлении ключа.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Description Input ==========


@router.message(InvoiceStates.entering_description, F.text)
async def process_description(
    message: Message,
    state: FSMContext
):
    """
    Handles invoice description text input.
    
    Validates length (max 1000 characters) and stores in FSM.
    
    Requirements: 9.1, 9.2
    """
    description = message.text.strip()
    telegram_id = message.from_user.id
    
    # Validate length
    max_length = 1000
    if len(description) > max_length:
        from bots.tg_bot.keyboards.invoice_kb import get_description_input_keyboard
        keyboard = await get_description_input_keyboard()
        
        await message.answer(
            ERROR_TEXT_TOO_LONG.format(
                max_length=max_length,
                actual_length=len(description)
            ),
            reply_markup=keyboard
        )
        logger.warning(
            f"User {telegram_id} provided too long description: "
            f"{len(description)} chars"
        )
        return
    
    # Store description
    await state.update_data(description=description)
    
    # Move to delivery method selection
    await state.set_state(InvoiceStates.selecting_delivery)
    
    keyboard = await get_delivery_method_keyboard()
    await message.answer(
        INVOICE_SELECT_DELIVERY,
        reply_markup=keyboard
    )
    
    logger.info(f"User {telegram_id} provided invoice description")


@router.callback_query(
    InvoiceStates.entering_description,
    KeyCallback.filter()
)
async def process_description_navigation(
    callback: CallbackQuery,
    callback_data: KeyCallback,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handles navigation buttons on description input step.
    
    Supports back to key selection and cancel.
    
    Requirements: 9.2
    """
    action = callback_data.action
    telegram_id = callback.from_user.id
    
    if action == "cancel":
        # Cancel invoice request
        await state.clear()
        await callback.message.edit_text("❌ Запрос счета отменен.")
        await callback.answer()
        logger.info(f"User {telegram_id} cancelled invoice request at description step")
        return
    
    elif action == "back_to_keys":
        # Go back to key selection
        await state.set_state(InvoiceStates.selecting_keys)
        
        # Get user first
        from services.user_service import get_user_by_tg_id
        user = await get_user_by_tg_id(session, telegram_id)
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        keys = await get_user_keys(session, user.id)
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())
        
        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
        await callback.message.edit_text(
            INVOICE_SELECT_KEYS,
            reply_markup=keyboard
        )
        await callback.answer()
        return
    
    else:
        await callback.answer("❌ Неизвестное действие")


# ========== Delivery Method Selection ==========


@router.callback_query(
    InvoiceStates.selecting_delivery,
    DeliveryCallback.filter()
)
async def process_delivery_method(
    callback: CallbackQuery,
    callback_data: DeliveryCallback,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
):
    """
    Handles delivery method selection (Telegram/Email).
    
    If Email selected, prompts for email address.
    If Telegram selected, proceeds to create ticket.
    
    Requirements: 9.3, 9.4
    """
    method = callback_data.method
    telegram_id = callback.from_user.id
    
    if method == "cancel":
        # Cancel invoice request
        await state.clear()
        await callback.message.edit_text("❌ Запрос счета отменен.")
        await callback.answer()
        logger.info(f"User {telegram_id} cancelled invoice request at delivery step")
        return
    
    elif method == "back":
        # Go back to description input
        await state.set_state(InvoiceStates.entering_description)
        await callback.message.edit_text(INVOICE_ENTER_DESCRIPTION)
        await callback.answer()
        return
    
    elif method == "telegram":
        # Telegram delivery - show confirmation summary
        await state.update_data(
            delivery_method=DeliveryMethod.TELEGRAM,
            delivery_email=None
        )
        
        await show_invoice_confirmation(callback, state, session)
        await callback.answer()
    
    elif method == "email":
        # Email delivery - prompt for email
        await state.set_state(InvoiceStates.entering_email)
        await state.update_data(delivery_method=DeliveryMethod.EMAIL)
        
        from bots.tg_bot.keyboards.invoice_kb import get_email_input_keyboard
        keyboard = await get_email_input_keyboard()
        
        # Edit message and save message_id for later editing
        edited_msg = await callback.message.edit_text(
            INVOICE_ENTER_EMAIL,
            reply_markup=keyboard
        )
        await state.update_data(email_prompt_message_id=edited_msg.message_id)
        await callback.answer()
    
    else:
        await callback.answer("❌ Неизвестный способ доставки")


@router.callback_query(
    InvoiceStates.entering_email,
    DeliveryCallback.filter()
)
async def process_email_navigation(
    callback: CallbackQuery,
    callback_data: DeliveryCallback,
    state: FSMContext
):
    """
    Handles navigation buttons on email input step.
    
    Supports back to delivery selection and cancel.
    
    Requirements: 9.4
    """
    method = callback_data.method
    telegram_id = callback.from_user.id
    
    if method == "cancel":
        # Cancel invoice request
        await state.clear()
        await callback.message.edit_text("❌ Запрос счета отменен.")
        await callback.answer()
        logger.info(f"User {telegram_id} cancelled invoice request at email step")
        return
    
    elif method == "back_to_delivery":
        # Go back to delivery method selection
        await state.set_state(InvoiceStates.selecting_delivery)
        
        from bots.tg_bot.keyboards.invoice_kb import get_delivery_method_keyboard
        keyboard = await get_delivery_method_keyboard()
        
        await callback.message.edit_text(
            INVOICE_SELECT_DELIVERY,
            reply_markup=keyboard
        )
        await callback.answer()
        return
    
    else:
        await callback.answer("❌ Неизвестное действие")


@router.callback_query(
    InvoiceStates.confirming_invoice,
    DeliveryCallback.filter()
)
async def process_invoice_confirmation(
    callback: CallbackQuery,
    callback_data: DeliveryCallback,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
):
    """
    Handles invoice confirmation actions.
    
    Supports confirm, restart, and cancel.
    
    Requirements: 9.5
    """
    method = callback_data.method
    telegram_id = callback.from_user.id
    
    if method == "cancel":
        # Cancel invoice request
        await state.clear()
        await callback.message.edit_text("❌ Запрос счета отменен.")
        await callback.answer()
        logger.info(f"User {telegram_id} cancelled invoice request at confirmation")
        return
    
    elif method == "restart":
        # Restart invoice request from beginning
        await state.clear()
        await callback.message.edit_text("🔄 Начинаем заново...")
        await callback.answer()
        
        # Start new invoice request
        await start_invoice_request(callback.message, state, session)
        return
    
    elif method == "confirm":
        # Confirm and create ticket
        await callback.message.edit_text("⏳ Создаем заявку...")
        await callback.answer()
        
        # Create ticket
        await create_invoice_ticket(callback.message, state, session, bot, telegram_id)
    
    else:
        await callback.answer("❌ Неизвестное действие")


@router.message(InvoiceStates.entering_email, F.text)
async def process_email(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
):
    """
    Handles email address input for email delivery.
    
    Validates email format and shows confirmation summary.
    
    Requirements: 9.4, 24.1-24.5
    """
    email = message.text.strip()
    telegram_id = message.from_user.id
    
    # Validate email
    is_valid, error_message = validate_email(email)
    
    if not is_valid:
        from bots.tg_bot.keyboards.invoice_kb import get_email_input_keyboard
        keyboard = await get_email_input_keyboard()
        
        await message.answer(
            ERROR_VALIDATION_EMAIL.format(error_details=error_message),
            reply_markup=keyboard
        )
        logger.warning(f"User {telegram_id} provided invalid email: {email}")
        return
    
    # Store email
    await state.update_data(delivery_email=email)
    
    # Show confirmation summary
    await show_invoice_confirmation_message(message, state, session)


async def show_invoice_confirmation(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
):
    """Helper to show invoice confirmation summary."""
    await state.set_state(InvoiceStates.confirming_invoice)
    
    # Get all data from FSM
    data = await state.get_data()
    
    # Build summary
    summary_parts = []
    
    # Organization
    organization_inn = data.get("organization_inn")
    if organization_inn:
        summary_parts.append(f"<b>Организация:</b> ИНН {organization_inn}")
    else:
        summary_parts.append("<b>Организация:</b> Не указана")
    
    # Keys
    selected_key_ids = data.get("selected_key_ids", set())
    if selected_key_ids:
        from services.user_service import get_user_by_tg_id
        user = await get_user_by_tg_id(session, callback.from_user.id)
        if user:
            keys = await get_user_keys(session, user.id)
            key_numbers = [k.key_number for k in keys if k.id in selected_key_ids]
            summary_parts.append(f"<b>Ключи:</b> {', '.join(key_numbers)}")
    
    # Description
    description = data.get("description", "")
    if len(description) > 100:
        description = description[:100] + "..."
    summary_parts.append(f"<b>Описание:</b> {description}")
    
    # Delivery
    delivery_method = data.get("delivery_method")
    delivery_email = data.get("delivery_email")
    if delivery_method == DeliveryMethod.EMAIL and delivery_email:
        summary_parts.append(f"<b>Доставка:</b> Email ({delivery_email})")
    else:
        summary_parts.append("<b>Доставка:</b> Telegram")
    
    summary = "\n\n".join(summary_parts)
    
    from bots.tg_bot.keyboards.invoice_kb import get_invoice_confirmation_keyboard
    keyboard = await get_invoice_confirmation_keyboard()
    
    await callback.message.edit_text(
        INVOICE_CONFIRMATION.format(summary=summary),
        reply_markup=keyboard
    )


async def show_invoice_confirmation_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """Helper to show invoice confirmation summary (for message context)."""
    await state.set_state(InvoiceStates.confirming_invoice)
    
    # Get all data from FSM
    data = await state.get_data()
    
    # Build summary
    summary_parts = []
    
    # Organization
    organization_inn = data.get("organization_inn")
    if organization_inn:
        summary_parts.append(f"<b>Организация:</b> ИНН {organization_inn}")
    else:
        summary_parts.append("<b>Организация:</b> Не указана")
    
    # Keys
    selected_key_ids = data.get("selected_key_ids", set())
    if selected_key_ids:
        from services.user_service import get_user_by_tg_id
        user = await get_user_by_tg_id(session, message.from_user.id)
        if user:
            keys = await get_user_keys(session, user.id)
            key_numbers = [k.key_number for k in keys if k.id in selected_key_ids]
            summary_parts.append(f"<b>Ключи:</b> {', '.join(key_numbers)}")
    
    # Description
    description = data.get("description", "")
    if len(description) > 100:
        description = description[:100] + "..."
    summary_parts.append(f"<b>Описание:</b> {description}")
    
    # Delivery
    delivery_method = data.get("delivery_method")
    delivery_email = data.get("delivery_email")
    if delivery_method == DeliveryMethod.EMAIL and delivery_email:
        summary_parts.append(f"<b>Доставка:</b> Email ({delivery_email})")
    else:
        summary_parts.append("<b>Доставка:</b> Telegram")
    
    summary = "\n\n".join(summary_parts)
    
    from bots.tg_bot.keyboards.invoice_kb import get_invoice_confirmation_keyboard
    keyboard = await get_invoice_confirmation_keyboard()
    
    # Try to edit the email prompt message if we have its ID
    email_prompt_message_id = data.get("email_prompt_message_id")
    if email_prompt_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=email_prompt_message_id,
                text=INVOICE_CONFIRMATION.format(summary=summary),
                reply_markup=keyboard
            )
            return
        except Exception as e:
            logger.warning(f"Failed to edit email prompt message: {e}")
    
    # If edit fails or no message_id, send new message
    await message.answer(
        INVOICE_CONFIRMATION.format(summary=summary),
        reply_markup=keyboard
    )


# ========== Ticket Creation ==========


async def create_invoice_ticket(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    telegram_id: int
):
    """
    Creates invoice ticket with all collected data.
    
    Determines assigned manager, creates ticket record with associations,
    routes based on work mode, and sends notification to manager.
    
    Requirements: 10.1-10.8, 11.1-11.5
    """
    try:
        # Get all data from FSM
        data = await state.get_data()
        organization_inn = data.get("organization_inn")
        selected_key_ids = list(data.get("selected_key_ids", set()))
        description = data.get("description")
        delivery_method = data.get("delivery_method")
        delivery_email = data.get("delivery_email")
        
        # Get user to get user.id
        from services.user_service import get_user_by_tg_id
        user = await get_user_by_tg_id(session, telegram_id)
        
        if not user:
            await message.answer(
                "❌ Пользователь не найден.\n"
                "Пожалуйста, пройдите регистрацию с помощью /start"
            )
            await state.clear()
            return
        
        # Determine assigned manager (with admin fallback if no manager)
        assigned_manager_id, has_manager = await determine_assigned_manager(
            session,
            user.id,  # Use internal user.id
            assign_admin_if_no_manager=True  # Auto-assign admin if no manager
        )
        
        # Create ticket
        ticket_data = {
            "ticket_type": TicketType.INVOICE,
            "user_id": user.id,  # Use internal user.id
            "assigned_staff_id": assigned_manager_id,
            "organization_inn": organization_inn,
            "description": description,
            "delivery_method": delivery_method,
            "delivery_email": delivery_email,
            "selected_key_ids": selected_key_ids
        }
        
        ticket = await create_ticket(session, ticket_data)
        
        # Get current work mode
        work_mode = await get_current_work_mode(session)
        
        # Route ticket
        routing_info = await route_ticket(session, ticket, work_mode)
        
        # Commit transaction
        await session.commit()
        
        # Refresh ticket with user relationship for notification
        from sqlalchemy.orm import selectinload
        await session.refresh(ticket, ["user"])
        
        # Log ticket to I-TAT API
        try:
            api_client = get_itat_client()
            
            # Get user.id for API call
            from services.user_service import get_user_by_tg_id
            user = await get_user_by_tg_id(session, telegram_id)
            
            if user:
                # Map ticket type to API format
                ticket_type_map = {
                    TicketType.INVOICE: "Счет",
                    TicketType.TECHNICAL_SUPPORT: "Техподдержка",
                    TicketType.RENEWAL: "Продление"
                }
                
                await api_client.log_ticket(
                    ticket_id=f"TKT_{ticket.id}",
                    messenger="telegram",
                    user_id=user.id,
                    ticket_type=ticket_type_map.get(ticket.ticket_type, "Счет"),
                    status="Новое",
                    comment=f"Заявка создана через бот. Описание: {description[:100] if description else 'Не указано'}"
                )
                logger.info(f"Ticket logged to I-TAT API: ticket_id={ticket.id}")
        except Exception as e:
            # Log error but don't fail ticket creation
            logger.error(
                f"Failed to log ticket to I-TAT API: ticket_id={ticket.id}, error={e}",
                exc_info=True
            )
        
        # Send notification to manager if assigned (only in working hours)
        # In NON_WORKING mode, notifications will be sent by queue task at 9 AM
        if assigned_manager_id and work_mode != WorkMode.NON_WORKING:
            await send_staff_notification(
                bot,
                assigned_manager_id,
                ticket,
                routing_info,
                session
            )
            logger.info(
                f"Manager notification sent immediately: ticket_id={ticket.id}, "
                f"manager_id={assigned_manager_id}, work_mode={work_mode.value}"
            )
        elif assigned_manager_id:
            logger.info(
                f"Invoice ticket queued for next working period: ticket_id={ticket.id}, "
                f"manager_id={assigned_manager_id}, work_mode={work_mode.value}"
            )
        
        # Clear FSM state
        await state.clear()
        
        # Get manager name and position from employee record
        manager_name = "ваш менеджер"
        manager_position = "Менеджер"
        if has_manager and assigned_manager_id:
            from database.models import Staff_Member
            from sqlalchemy import select
            
            stmt = select(Staff_Member).where(Staff_Member.id == assigned_manager_id)
            result = await session.execute(stmt)
            manager = result.scalar_one_or_none()
            if manager:
                manager_name = manager.full_name
                manager_position = manager.position or "Менеджер"
        
        # Format response time message based on work mode
        if work_mode == WorkMode.NON_WORKING:
            response_time_msg = INVOICE_RESPONSE_TIME_NON_WORKING
        else:
            response_time_msg = INVOICE_RESPONSE_TIME_WORKING
        
        # Send success message
        # Use different message template based on whether user has assigned manager
        if has_manager:
            message_text = INVOICE_CREATED.format(
                ticket_id=ticket.id,
                manager_name=manager_name,
                manager_position=manager_position,
                response_time_message=response_time_msg
            )
        else:
            message_text = INVOICE_CREATED_NO_MANAGER.format(
                ticket_id=ticket.id,
                response_time_message=response_time_msg
            )
        
        await message.answer(
            message_text,
            reply_markup=ReplyKeyboardRemove()
        )
        
        logger.info(
            f"Invoice ticket created: ticket_id={ticket.id}, "
            f"user_id={user.id}, tg_user_id={telegram_id}, manager={assigned_manager_id}, "
            f"keys_count={len(selected_key_ids)}, work_mode={work_mode.value}"
        )
    
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error creating invoice ticket for user {telegram_id}: {e}",
            exc_info=True
        )
        
        await message.answer(
            "❌ Произошла ошибка при создании заявки.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await state.clear()
    
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Unexpected error creating invoice ticket for user {telegram_id}: {e}",
            exc_info=True
        )
        
        await message.answer(
            "❌ Произошла непредвиденная ошибка.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await state.clear() 