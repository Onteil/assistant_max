"""
Invoice Request Handler for MAX Bot

Manages the invoice request conversation flow.
Migrated from Telegram bot to MAX messenger using maxapi.

Requirements: 7.1-7.6, 8.1-8.6, 9.1-9.5, 10.1-10.8, 11.1-11.5, 9.3, 9.5, 9.6, 9.7, 9.8
"""

import logging

import httpx
from maxapi import Bot
from maxapi.context import FSMContext
from maxapi.types import CallbackQuery, Message
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.callback_datas import (
    DeliveryCallback,
    KeyCallback,
    OrganizationCallback,
)
from bots.max_bot.keyboards.invoice_kb import (
    get_delivery_method_keyboard,
    get_key_selection_keyboard,
    get_organization_keyboard,
)
from bots.max_bot.states import InvoiceStates
from bots.max_bot.texts import (
    ADD_KEY_SUCCESS,
    BTN_CANCEL,
    ERROR_TEXT_TOO_LONG,
    ERROR_VALIDATION_EMAIL,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    INVOICE_ADD_NEW_INN,
    INVOICE_ADD_NEW_KEY,
    INVOICE_CREATED,
    INVOICE_ENTER_DESCRIPTION,
    INVOICE_ENTER_EMAIL,
    INVOICE_INN_ADDED,
    INVOICE_KEY_CONFLICT,
    INVOICE_PROCESSING,
    INVOICE_RESPONSE_TIME_EXTENDED,
    INVOICE_RESPONSE_TIME_NON_WORKING,
    INVOICE_RESPONSE_TIME_WORKING,
    INVOICE_SELECT_DELIVERY,
    INVOICE_SELECT_KEYS,
    INVOICE_SELECT_ORGANIZATION,
)
from database.models import DeliveryMethod, KeyConflictStatus, TicketType, WorkMode
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


# ========== Entry Point ==========


async def start_invoice_request(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Entry point for invoice request.
    
    Displays organization selection with user's existing organizations.
    Includes options to add new INN or skip organization selection.
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    
    Requirements: 7.1, 7.2, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id

    try:
        # Clear any existing state
        await state.clear()

        # Get user's organizations
        organizations = await get_user_organizations(session, user_id)

        # Set initial state
        await state.set_state(InvoiceStates.selecting_organization)
        await state.update_data(
            selected_key_ids=set(),
            current_page=0
        )

        # Display organization selection
        keyboard = await get_organization_keyboard(organizations, page=0)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_SELECT_ORGANIZATION,
            keyboard=keyboard,
            parse_mode="HTML"
        )

        logger.info(
            f"User {user_id} started invoice request, "
            f"{len(organizations)} organizations available"
        )

    except SQLAlchemyError as e:
        logger.error(
            f"Database error starting invoice request for user {user_id}: {e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке данных.\n"
                 "Пожалуйста, попробуйте позже.",
            keyboard=None,
            parse_mode="HTML"
        )


# ========== Organization Selection ==========


async def process_organization_selection(
    callback: CallbackQuery,
    callback_data: OrganizationCallback,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Handles organization selection from inline keyboard.
    
    Supports:
    - Selecting an organization
    - Adding new INN
    - Skipping organization selection
    - Pagination
    
    Migrated from Telegram bot to MAX messenger.
    Uses callback.from_user.user_id and callback.message.chat.chat_id.
    Uses maxapi's callback.answer() method.
    
    Requirements: 7.3, 7.4, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = callback.from_user.user_id
    action = callback_data.action

    try:
        if action == "select":
            # Organization selected
            inn = callback_data.inn
            await state.update_data(organization_inn=inn)

            # Move to key selection
            await proceed_to_key_selection(callback, state, session, user_id, messenger_adapter)

        elif action == "add_new":
            # User wants to add new INN
            await state.set_state(InvoiceStates.adding_new_inn)
            await messenger_adapter.edit_message(
                chat_id=callback.message.chat.chat_id,
                message_id=callback.message.message_id,
                text=INVOICE_ADD_NEW_INN,
                keyboard=None,
                parse_mode="HTML"
            )
            await callback.answer()

        elif action == "skip":
            # Skip organization selection
            await state.update_data(organization_inn=None)
            await proceed_to_key_selection(callback, state, session, user_id, messenger_adapter)

        elif action == "page":
            # Pagination
            page = callback_data.page
            organizations = await get_user_organizations(session, user_id)
            keyboard = await get_organization_keyboard(organizations, page=page)

            await messenger_adapter.edit_message(
                chat_id=callback.message.chat.chat_id,
                message_id=callback.message.message_id,
                text=INVOICE_SELECT_ORGANIZATION,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()

        else:
            await callback.answer(text="❌ Неизвестное действие", show_alert=False)

    except SQLAlchemyError as e:
        logger.error(
            f"Database error in organization selection for user {user_id}: {e}",
            exc_info=True
        )
        await callback.answer(text="❌ Произошла ошибка", show_alert=True)


async def proceed_to_key_selection(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user_id: int,
    messenger_adapter
):
    """Helper to move to key selection step."""
    await state.set_state(InvoiceStates.selecting_keys)

    # Get user's keys
    keys = await get_user_keys(session, user_id)

    # Get selected key IDs from state
    data = await state.get_data()
    selected_key_ids = data.get("selected_key_ids", set())

    # Display key selection
    keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
    await messenger_adapter.edit_message(
        chat_id=callback.message.chat.chat_id,
        message_id=callback.message.message_id,
        text=INVOICE_SELECT_KEYS,
        keyboard=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


async def process_new_inn(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Handles new INN input during invoice request.
    
    Validates format and adds organization to user's profile.
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    Uses maxapi's message.body.text for text content.
    
    Requirements: 7.4, 7.5, 22.1-22.5, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id
    inn = message.body.text.strip()

    # Check for cancel
    if inn == BTN_CANCEL:
        # Return to organization selection
        await state.set_state(InvoiceStates.selecting_organization)
        organizations = await get_user_organizations(session, user_id)
        keyboard = await get_organization_keyboard(organizations, page=0)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_SELECT_ORGANIZATION,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        return

    # Validate INN
    is_valid, error_message = validate_inn(inn)

    if not is_valid:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_INN.format(error_details=error_message),
            keyboard=None,
            parse_mode="HTML"
        )
        logger.warning(f"User {user_id} provided invalid INN: {inn}")
        return

    # Add organization
    try:
        await add_user_organization(session, user_id, inn)
        await session.commit()

        # Store in state
        await state.update_data(organization_inn=inn)

        # Show success and move to key selection
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_INN_ADDED,
            keyboard=None,
            parse_mode="HTML"
        )

        await state.set_state(InvoiceStates.selecting_keys)
        keys = await get_user_keys(session, user_id)
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())

        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_SELECT_KEYS,
            keyboard=keyboard,
            parse_mode="HTML"
        )

        logger.info(f"User {user_id} added new INN: {inn}")

    except IntegrityError:
        # INN already exists - this is fine, just use it
        await session.rollback()
        await state.update_data(organization_inn=inn)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_INN_ADDED,
            keyboard=None,
            parse_mode="HTML"
        )

        await state.set_state(InvoiceStates.selecting_keys)
        keys = await get_user_keys(session, user_id)
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())

        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_SELECT_KEYS,
            keyboard=keyboard,
            parse_mode="HTML"
        )

    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error adding INN for user {user_id}: {e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при добавлении организации.\n"
                 "Пожалуйста, попробуйте позже.",
            keyboard=None,
            parse_mode="HTML"
        )


# ========== Key Selection ==========


async def process_key_selection(
    callback: CallbackQuery,
    callback_data: KeyCallback,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Handles GS_Key multi-select with toggle functionality.
    
    Supports:
    - Toggling key selection (add/remove from selected set)
    - Adding new key
    - Completing selection (Done)
    - Pagination
    
    Migrated from Telegram bot to MAX messenger.
    Uses callback.from_user.user_id and callback.message.chat.chat_id.
    
    Requirements: 8.2, 8.3, 8.4, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = callback.from_user.user_id
    action = callback_data.action

    try:
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())

        if action == "toggle":
            # Toggle key selection
            key_id = callback_data.key_id

            if key_id in selected_key_ids:
                selected_key_ids.remove(key_id)
            else:
                selected_key_ids.add(key_id)

            await state.update_data(selected_key_ids=selected_key_ids)

            # Update keyboard
            keys = await get_user_keys(session, user_id)
            keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)

            await messenger_adapter.edit_message(
                chat_id=callback.message.chat.chat_id,
                message_id=callback.message.message_id,
                text=INVOICE_SELECT_KEYS,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()

        elif action == "add_new":
            # User wants to add new key
            await state.set_state(InvoiceStates.adding_new_key)
            await messenger_adapter.edit_message(
                chat_id=callback.message.chat.chat_id,
                message_id=callback.message.message_id,
                text=INVOICE_ADD_NEW_KEY,
                keyboard=None,
                parse_mode="HTML"
            )
            await callback.answer()

        elif action == "done":
            # Complete key selection
            if not selected_key_ids:
                await callback.answer(
                    text="⚠️ Выберите хотя бы один ключ",
                    show_alert=True
                )
                return

            # Move to description input
            await state.set_state(InvoiceStates.entering_description)
            await messenger_adapter.edit_message(
                chat_id=callback.message.chat.chat_id,
                message_id=callback.message.message_id,
                text=INVOICE_ENTER_DESCRIPTION,
                keyboard=None,
                parse_mode="HTML"
            )
            await callback.answer()

        elif action == "page":
            # Pagination
            page = callback_data.page
            keys = await get_user_keys(session, user_id)
            keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=page)

            await messenger_adapter.edit_message(
                chat_id=callback.message.chat.chat_id,
                message_id=callback.message.message_id,
                text=INVOICE_SELECT_KEYS,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()

        else:
            await callback.answer(text="❌ Неизвестное действие", show_alert=False)

    except SQLAlchemyError as e:
        logger.error(
            f"Database error in key selection for user {user_id}: {e}",
            exc_info=True
        )
        await callback.answer(text="❌ Произошла ошибка", show_alert=True)


async def process_new_key(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Handles new GS_Key input during invoice request.
    
    Validates format, checks for conflicts via API, and adds key to user's profile.
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    Uses maxapi's message.body.text for text content.
    
    Requirements: 8.4, 18.3, 23.1-23.5, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id
    key_input = message.body.text.strip()

    # Check for cancel
    if key_input == BTN_CANCEL:
        # Return to key selection
        await state.set_state(InvoiceStates.selecting_keys)
        keys = await get_user_keys(session, user_id)
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())

        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_SELECT_KEYS,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        return

    # Validate key format
    is_valid, result = validate_gs_key(key_input)

    if not is_valid:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_KEY.format(error_details=result),
            keyboard=None,
            parse_mode="HTML"
        )
        logger.warning(f"User {user_id} provided invalid key format: {key_input}")
        return

    normalized_key = result

    # Check for conflict via API
    api_client = get_itat_client()
    conflict_detected = False

    try:
        conflict_response = await api_client.check_key_conflict(
            grand_key=normalized_key,
            telegram_id=user_id
        )

        if conflict_response.get("status") == "conflict":
            conflict_detected = True
            logger.warning(
                f"Key conflict detected for user {user_id}: "
                f"key={normalized_key}"
            )

    except httpx.HTTPStatusError as e:
        # HTTP error from API - log and continue with graceful degradation
        logger.error(
            f"API HTTP error checking key conflict for user {user_id}: "
            f"status={e.response.status_code}, error={e}",
            exc_info=True
        )
        # Continue without conflict check (graceful degradation)

    except (httpx.TimeoutException, httpx.ConnectError) as e:
        # Network/timeout error - log and continue with graceful degradation
        logger.error(
            f"API connection error checking key conflict for user {user_id}: {e}",
            exc_info=True
        )
        # Continue without conflict check (graceful degradation)

    except Exception as e:
        logger.error(
            f"Unexpected error checking key conflict for user {user_id}: {e}",
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
            user_id,
            normalized_key,
            conflict_status
        )
        await session.commit()

        # Show appropriate message
        if conflict_detected:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_KEY_CONFLICT,
                keyboard=None,
                parse_mode="HTML"
            )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ADD_KEY_SUCCESS.format(key_number=normalized_key),
                keyboard=None,
                parse_mode="HTML"
            )

        # Return to key selection with new key selected
        await state.set_state(InvoiceStates.selecting_keys)

        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())
        selected_key_ids.add(gs_key.id)
        await state.update_data(selected_key_ids=selected_key_ids)

        keys = await get_user_keys(session, user_id)
        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_SELECT_KEYS,
            keyboard=keyboard,
            parse_mode="HTML"
        )

        logger.info(
            f"User {user_id} added new key: {normalized_key}, "
            f"conflict={conflict_detected}"
        )

    except IntegrityError:
        # Key already exists - this is fine
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="⚠️ Этот ключ уже добавлен в ваш профиль.",
            keyboard=None,
            parse_mode="HTML"
        )

        # Return to key selection
        await state.set_state(InvoiceStates.selecting_keys)
        keys = await get_user_keys(session, user_id)
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())

        keyboard = await get_key_selection_keyboard(keys, selected_key_ids, page=0)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_SELECT_KEYS,
            keyboard=keyboard,
            parse_mode="HTML"
        )

    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error adding key for user {user_id}: {e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при добавлении ключа.\n"
                 "Пожалуйста, попробуйте позже.",
            keyboard=None,
            parse_mode="HTML"
        )


# ========== Description Input ==========


async def process_description(
    message: Message,
    state: FSMContext,
    messenger_adapter
):
    """
    Handles invoice description text input.
    
    Validates length (max 1000 characters) and stores in FSM.
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    Uses maxapi's message.body.text for text content.
    
    Requirements: 9.1, 9.2, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id
    description = message.body.text.strip()

    # Check for cancel
    if description == BTN_CANCEL:
        await state.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Запрос счета отменен.",
            keyboard=None,
            parse_mode="HTML"
        )
        logger.info(f"User {user_id} cancelled invoice request at description step")
        return

    # Validate length
    max_length = 1000
    if len(description) > max_length:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_TEXT_TOO_LONG.format(
                max_length=max_length,
                actual_length=len(description)
            ),
            keyboard=None,
            parse_mode="HTML"
        )
        logger.warning(
            f"User {user_id} provided too long description: "
            f"{len(description)} chars"
        )
        return

    # Store description
    await state.update_data(description=description)

    # Move to delivery method selection
    await state.set_state(InvoiceStates.selecting_delivery)

    keyboard = await get_delivery_method_keyboard()
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=INVOICE_SELECT_DELIVERY,
        keyboard=keyboard,
        parse_mode="HTML"
    )

    logger.info(f"User {user_id} provided invoice description")


# ========== Delivery Method Selection ==========


async def process_delivery_method(
    callback: CallbackQuery,
    callback_data: DeliveryCallback,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    messenger_adapter
):
    """
    Handles delivery method selection (Telegram/Email).
    
    If Email selected, prompts for email address.
    If Telegram selected, proceeds to create ticket.
    Migrated from Telegram bot to MAX messenger.
    Uses callback.from_user.user_id and callback.message.chat.chat_id.
    
    Requirements: 9.3, 9.4, 9.5, 9.6, 9.7, 9.8
    """
    method = callback_data.method
    user_id = callback.from_user.user_id
    chat_id = callback.message.chat.chat_id

    if method == "telegram":
        # Telegram delivery - proceed to create ticket
        await state.update_data(
            delivery_method=DeliveryMethod.TELEGRAM,
            delivery_email=None
        )

        await messenger_adapter.edit_message(
            chat_id=chat_id,
            message_id=callback.message.message_id,
            text="⏳ Создаем заявку...",
            keyboard=None,
            parse_mode="HTML"
        )
        await callback.answer()

        # Create ticket
        await create_invoice_ticket(callback.message, state, session, bot, user_id, messenger_adapter)

    elif method == "email":
        # Email delivery - prompt for email
        await state.set_state(InvoiceStates.entering_email)
        await state.update_data(delivery_method=DeliveryMethod.EMAIL)

        await messenger_adapter.edit_message(
            chat_id=chat_id,
            message_id=callback.message.message_id,
            text=INVOICE_ENTER_EMAIL,
            keyboard=None,
            parse_mode="HTML"
        )
        await callback.answer()

    else:
        await callback.answer(text="❌ Неизвестный способ доставки", show_alert=False)


async def process_email(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    messenger_adapter
):
    """
    Handles email address input for email delivery.
    
    Validates email format and proceeds to create ticket.
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    Uses maxapi's message.body.text for text content.
    
    Requirements: 9.4, 24.1-24.5, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id
    email = message.body.text.strip()

    # Check for cancel
    if email == BTN_CANCEL:
        await state.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Запрос счета отменен.",
            keyboard=None,
            parse_mode="HTML"
        )
        logger.info(f"User {user_id} cancelled invoice request at email step")
        return

    # Validate email
    is_valid, error_message = validate_email(email)

    if not is_valid:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_EMAIL.format(error_details=error_message),
            keyboard=None,
            parse_mode="HTML"
        )
        logger.warning(f"User {user_id} provided invalid email: {email}")
        return

    # Store email
    await state.update_data(delivery_email=email)

    # Show processing message
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=INVOICE_PROCESSING,
        keyboard=None,
        parse_mode="HTML"
    )

    # Create ticket
    await create_invoice_ticket(message, state, session, bot, user_id, messenger_adapter)


# ========== Ticket Creation ==========


async def create_invoice_ticket(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    user_id: int,
    messenger_adapter
):
    """
    Creates invoice ticket with all collected data.
    
    Determines assigned manager, creates ticket record with associations,
    routes based on work mode, and sends notification to manager.
    Migrated from Telegram bot to MAX messenger.
    Uses message.chat.chat_id.
    
    Requirements: 10.1-10.8, 11.1-11.5, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    chat_id = message.chat.chat_id

    try:
        # Get all data from FSM
        data = await state.get_data()
        organization_inn = data.get("organization_inn")
        selected_key_ids = list(data.get("selected_key_ids", set()))
        description = data.get("description")
        delivery_method = data.get("delivery_method")
        delivery_email = data.get("delivery_email")

        # Determine assigned manager
        assigned_manager_id = await determine_assigned_manager(
            session,
            user_id,
            organization_inn
        )

        # Create ticket
        ticket_data = {
            "ticket_type": TicketType.INVOICE,
            "tg_user_id": user_id,
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

        # Send notification to manager if assigned
        if assigned_manager_id:
            await send_staff_notification(
                bot,
                assigned_manager_id,
                ticket,
                routing_info
            )

        # Clear FSM state
        await state.clear()

        # Determine response time message
        if work_mode == WorkMode.REGULAR:
            response_time_msg = INVOICE_RESPONSE_TIME_WORKING
        elif work_mode == WorkMode.EXTENDED:
            response_time_msg = INVOICE_RESPONSE_TIME_EXTENDED
        else:
            response_time_msg = INVOICE_RESPONSE_TIME_NON_WORKING

        # Get organization name for display
        org_display = organization_inn if organization_inn else "Не указана"

        # Get delivery method display
        delivery_display = (
            "Telegram" if delivery_method == DeliveryMethod.TELEGRAM
            else f"Email ({delivery_email})"
        )

        # Get manager name (stub for now)
        manager_name = "ваш менеджер"

        # Send success message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_CREATED.format(
                ticket_id=ticket.id,
                organization_name=org_display,
                delivery_method=delivery_display,
                manager_name=manager_name,
                response_time_message=response_time_msg
            ),
            keyboard=None,
            parse_mode="HTML"
        )

        logger.info(
            f"Invoice ticket created: ticket_id={ticket.id}, "
            f"user={user_id}, manager={assigned_manager_id}, "
            f"keys_count={len(selected_key_ids)}, work_mode={work_mode.value}"
        )

    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error creating invoice ticket for user {user_id}: {e}",
            exc_info=True
        )

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при создании заявки.\n"
                 "Пожалуйста, попробуйте позже.",
            keyboard=None,
            parse_mode="HTML"
        )

        await state.clear()

    except Exception as e:
        await session.rollback()
        logger.error(
            f"Unexpected error creating invoice ticket for user {user_id}: {e}",
            exc_info=True
        )

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла непредвиденная ошибка.\n"
                 "Пожалуйста, попробуйте позже.",
            keyboard=None,
            parse_mode="HTML"
        )

        await state.clear()
