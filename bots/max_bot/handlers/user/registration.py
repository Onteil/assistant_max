"""
Registration Handler for MAX Bot

Manages the user registration conversation flow.
Migrated from Telegram bot to MAX messenger using maxapi.

Requirements: 1.1-1.5, 2.1-2.7, 3.1-3.5, 4.1-4.5, 25.1-25.5, 9.3, 9.5, 9.6, 9.7, 9.8
"""

import logging

import httpx
from maxapi.context import FSMContext
from maxapi.types import Message
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.keyboards.main_menu_kb import get_main_menu_keyboard
from bots.max_bot.keyboards.registration_kb import (
    get_cancel_keyboard,
    get_phone_request_keyboard,
)
from bots.max_bot.states import RegistrationStates
from bots.max_bot.texts import (
    BTN_CANCEL,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    ERROR_VALIDATION_PHONE,
    MAIN_MENU,
    REGISTRATION_ENTER_INN,
    REGISTRATION_ENTER_KEY,
    REGISTRATION_KEY_CONFLICT,
    REGISTRATION_PENDING,
    REGISTRATION_PHONE_DUPLICATE,
    REGISTRATION_PHONE_SHARED,
    REGISTRATION_PROCESSING,
    REGISTRATION_START,
    REGISTRATION_SUBMITTED,
)
from database.models import KeyConflictStatus, TicketType, User
from services.i_tat_service import get_itat_client
from services.user_service import add_user_key, create_user, get_user_by_tg_id
from services.validation_service import (
    validate_gs_key,
    validate_inn,
    validate_phone_number,
)

logger = logging.getLogger(__name__)


# ========== Command Handlers ==========


async def cmd_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Entry point for /start command.
    
    Checks if user is already registered:
    - If registered and ACTIVE: show main menu
    - If registered and PENDING: show waiting message and block menu access
    - If not registered: start registration flow
    
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id (MAX API format).
    
    Requirements: 1.1, 5.4, 5.5, 6.1, 9.1, 9.2, 9.5, 9.6, 9.7
    """
    # Extract user_id and chat_id from MAX message
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id

    try:
        # Check if user exists
        user = await get_user_by_tg_id(session, user_id)

        if user:
            # User exists - check registration status
            if user.registration_status.value == "active":
                # Show main menu for active users
                main_menu_keyboard = await get_main_menu_keyboard()

                # Send message via messenger adapter
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=MAIN_MENU,
                    keyboard=None,  # TODO: Convert reply keyboard to abstraction
                    parse_mode="HTML"
                )
                logger.info(f"Active user {user_id} accessed main menu")

            elif user.registration_status.value == "pending":
                # Show pending message and block menu access
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=REGISTRATION_PENDING,
                    keyboard=None,
                    parse_mode="HTML"
                )
                logger.info(f"Pending user {user_id} blocked from menu access")

            else:  # rejected
                # Allow re-registration for rejected users
                await start_registration(message, state, messenger_adapter)

        else:
            # User doesn't exist - start registration
            await start_registration(message, state, messenger_adapter)

    except SQLAlchemyError as e:
        logger.error(
            f"Database error in cmd_start for user {user_id}: {e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при проверке регистрации.\n"
                 "Пожалуйста, попробуйте позже.",
            keyboard=None,
            parse_mode="HTML"
        )


async def start_registration(message: Message, state: FSMContext, messenger_adapter):
    """
    Start the registration flow by requesting phone number.
    
    Migrated from Telegram bot to MAX messenger.
    Uses maxapi's FSM state.clear() and state.set_state() methods.
    
    Requirements: 1.1, 29.1, 29.2, 9.5, 9.6
    """
    chat_id = message.chat.chat_id
    user_id = message.from_user.user_id

    # Clear FSM state using maxapi's state.clear() method
    await state.clear()
    await state.set_state(RegistrationStates.waiting_for_phone)

    # Create phone request keyboard
    keyboard = await get_phone_request_keyboard()

    # Send welcome message via messenger adapter
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=REGISTRATION_START,
        keyboard=keyboard,
        parse_mode="HTML"
    )

    logger.info(f"User {user_id} started registration flow")


# ========== Registration Flow Handlers ==========


async def process_phone_contact(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Handles phone number from contact button.
    
    Validates format, checks for duplicates, and stores in FSM.
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    
    Requirements: 1.2, 1.3, 1.4, 21.1-21.5, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    contact = message.contact
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id

    # Verify contact is from the user themselves
    if contact.user_id != user_id:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Пожалуйста, поделитесь своим собственным номером телефона.",
            keyboard=await get_phone_request_keyboard(),
            parse_mode="HTML"
        )
        return

    phone = contact.phone_number

    # Validate phone number format
    is_valid, result = validate_phone_number(phone)

    if not is_valid:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_PHONE.format(error_details=result),
            keyboard=await get_phone_request_keyboard(),
            parse_mode="HTML"
        )
        logger.warning(f"Invalid phone format from user {user_id}: {phone}")
        return

    normalized_phone = result

    # Check for duplicate phone number
    try:
        existing_user = await session.execute(
            select(User).where(User.phone_number == normalized_phone)
        )
        if existing_user.scalar_one_or_none():
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=REGISTRATION_PHONE_DUPLICATE,
                keyboard=None,
                parse_mode="HTML"
            )
            logger.warning(
                f"Duplicate phone registration attempt: {normalized_phone} "
                f"by user {user_id}"
            )
            await state.clear()
            return

    except SQLAlchemyError as e:
        logger.error(
            f"Database error checking phone duplicate for {user_id}: {e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при проверке номера телефона.\n"
                 "Пожалуйста, попробуйте позже.",
            keyboard=None,
            parse_mode="HTML"
        )
        await state.clear()
        return

    # Store phone in FSM and move to next step
    await state.update_data(phone_number=normalized_phone)
    await state.set_state(RegistrationStates.waiting_for_name)

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=REGISTRATION_PHONE_SHARED,
        keyboard=await get_cancel_keyboard(),
        parse_mode="HTML"
    )

    logger.info(f"User {user_id} provided phone: {normalized_phone}")


async def cancel_phone_input(message: Message, state: FSMContext, messenger_adapter):
    """
    Handle cancel during phone input.
    
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    
    Requirements: 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id

    await state.clear()
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="❌ Регистрация отменена.\n\nИспользуйте /start для начала регистрации.",
        keyboard=None,
        parse_mode="HTML"
    )
    logger.info(f"User {user_id} cancelled registration at phone step")


async def process_full_name(message: Message, state: FSMContext, messenger_adapter):
    """
    Handles full name input.
    
    Validates minimum length and stores in FSM.
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    Uses maxapi's message.body.text for text content.
    
    Requirements: 2.1, 2.2, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id
    full_name = message.body.text.strip()

    # Check for cancel
    if full_name == BTN_CANCEL:
        await state.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Регистрация отменена.\n\nИспользуйте /start для начала регистрации.",
            keyboard=None,
            parse_mode="HTML"
        )
        logger.info(f"User {user_id} cancelled registration at name step")
        return

    # Validate length
    if len(full_name) < 2:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Имя должно содержать минимум 2 символа.\n\n"
                 "Пожалуйста, введите ваше полное имя (Фамилия Имя):",
            keyboard=await get_cancel_keyboard(),
            parse_mode="HTML"
        )
        logger.warning(f"User {user_id} provided too short name: {full_name}")
        return

    # Store name in FSM and move to next step
    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.waiting_for_inn)

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=REGISTRATION_ENTER_INN,
        keyboard=await get_cancel_keyboard(),
        parse_mode="HTML"
    )

    logger.info(f"User {user_id} provided name: {full_name}")


async def process_inn(message: Message, state: FSMContext, messenger_adapter):
    """
    Handles INN input.
    
    Validates format (10 or 12 digits) and stores in FSM.
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    Uses maxapi's message.body.text for text content.
    
    Requirements: 2.3, 2.4, 22.1-22.5, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id
    inn = message.body.text.strip()

    # Check for cancel
    if inn == BTN_CANCEL:
        await state.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Регистрация отменена.\n\nИспользуйте /start для начала регистрации.",
            keyboard=None,
            parse_mode="HTML"
        )
        logger.info(f"User {user_id} cancelled registration at INN step")
        return

    # Validate INN format
    is_valid, error_message = validate_inn(inn)

    if not is_valid:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_INN.format(error_details=error_message),
            keyboard=await get_cancel_keyboard(),
            parse_mode="HTML"
        )
        logger.warning(f"User {user_id} provided invalid INN: {inn}")
        return

    # Store INN in FSM and move to next step
    await state.update_data(inn=inn)
    await state.set_state(RegistrationStates.waiting_for_key)

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=REGISTRATION_ENTER_KEY,
        keyboard=await get_cancel_keyboard(),
        parse_mode="HTML"
    )

    logger.info(f"User {user_id} provided INN: {inn}")


async def process_gs_key(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Handles GS_Key input.
    
    Validates format, checks for conflicts via CRM API, and stores in FSM.
    If conflict detected, creates admin ticket and flags key.
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    Uses maxapi's message.body.text for text content.
    
    Requirements: 2.5, 2.6, 3.1-3.5, 23.1-23.5, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id
    key_input = message.body.text.strip()

    # Check for cancel
    if key_input == BTN_CANCEL:
        await state.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Регистрация отменена.\n\nИспользуйте /start для начала регистрации.",
            keyboard=None,
            parse_mode="HTML"
        )
        logger.info(f"User {user_id} cancelled registration at key step")
        return

    # Validate GS_Key format
    is_valid, result = validate_gs_key(key_input)

    if not is_valid:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_KEY.format(error_details=result),
            keyboard=await get_cancel_keyboard(),
            parse_mode="HTML"
        )
        logger.warning(f"User {user_id} provided invalid key format: {key_input}")
        return

    normalized_key = result

    # Check for key conflict via CRM API
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
                f"key={normalized_key}, owner={conflict_response.get('owner')}"
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
        # Unexpected error - log but continue with registration
        logger.error(
            f"Unexpected error checking key conflict for user {user_id}: {e}",
            exc_info=True
        )
        # Continue without conflict check (graceful degradation)

    # Store key and conflict status in FSM
    await state.update_data(
        gs_key=normalized_key,
        key_conflict=conflict_detected
    )

    # Show conflict warning if detected
    if conflict_detected:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=REGISTRATION_KEY_CONFLICT,
            keyboard=None,
            parse_mode="HTML"
        )

    # Proceed to submit registration
    await submit_registration(message, state, session, messenger_adapter)


async def submit_registration(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    messenger_adapter
):
    """
    Submits complete registration data to CRM and creates User record.
    
    Creates User with PENDING status and associated GS_Key.
    If key conflict detected, creates admin ticket.
    Migrated from Telegram bot to MAX messenger.
    Uses message.from_user.user_id and message.chat.chat_id.
    
    Requirements: 4.1-4.5, 25.1-25.5, 9.3, 9.5, 9.6, 9.7, 9.8
    """
    user_id = message.from_user.user_id
    chat_id = message.chat.chat_id

    # Show processing message
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=REGISTRATION_PROCESSING,
        keyboard=None,
        parse_mode="HTML"
    )

    # Get all data from FSM
    data = await state.get_data()
    phone_number = data.get("phone_number")
    full_name = data.get("full_name")
    inn = data.get("inn")
    gs_key = data.get("gs_key")
    key_conflict = data.get("key_conflict", False)

    # Extract first and last name from full_name
    name_parts = full_name.split(maxsplit=1)
    last_name = name_parts[0] if len(name_parts) > 0 else ""
    first_name = name_parts[1] if len(name_parts) > 1 else ""

    # Submit to CRM API
    api_client = get_itat_client()
    api_success = False
    api_error_message = None

    try:
        api_response = await api_client.register_user(
            telegram_id=user_id,
            phone=phone_number,
            first_name=first_name,
            last_name=last_name,
            grand_key=gs_key
        )

        if api_response.get("status") == "ok":
            api_success = True
            logger.info(f"CRM registration successful for user {user_id}")
        else:
            logger.warning(
                f"CRM registration returned non-ok status for user {user_id}: "
                f"{api_response}"
            )

    except httpx.HTTPStatusError as e:
        # HTTP error from API - provide user-friendly message based on status code
        status_code = e.response.status_code
        logger.error(
            f"API HTTP error during registration for user {user_id}: "
            f"status={status_code}, error={e}",
            exc_info=True
        )

        if status_code == 400:
            api_error_message = "❌ Ошибка: неверные данные регистрации. Пожалуйста, проверьте введенную информацию."
        elif status_code == 404:
            api_error_message = "❌ Ошибка: ключ защиты не найден в системе. Проверьте правильность номера ключа."
        elif status_code == 409:
            api_error_message = "❌ Пользователь с такими данными уже зарегистрирован в системе."
        else:
            api_error_message = "❌ Ошибка при регистрации в системе. Попробуйте позже или обратитесь в поддержку."

    except (httpx.TimeoutException, httpx.ConnectError) as e:
        # Network/timeout error - provide user-friendly message
        logger.error(
            f"API connection error during registration for user {user_id}: {e}",
            exc_info=True
        )
        api_error_message = "❌ Не удалось связаться с сервером. Проверьте подключение к интернету и попробуйте позже."

    except Exception as e:
        # Unexpected error - log and continue with local registration (graceful degradation)
        logger.error(
            f"Unexpected error during registration for user {user_id}: {e}",
            exc_info=True
        )
        # Continue with local database creation

    # If API error occurred, inform user but continue with local registration
    if api_error_message:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"{api_error_message}\n\n"
                 "Ваша регистрация будет сохранена локально и синхронизирована позже.",
            keyboard=None,
            parse_mode="HTML"
        )

    # Create User record in database
    try:
        user_data = {
            "tg_user_id": user_id,
            "phone_number": phone_number,
            "full_name": full_name,
            "username": message.from_user.username if hasattr(message.from_user, 'username') else None,
            "first_name": message.from_user.first_name if hasattr(message.from_user, 'first_name') else None,
            "last_name": message.from_user.last_name if hasattr(message.from_user, 'last_name') else None,
        }

        user = await create_user(session, user_data)

        # Add organization association
        from services.user_service import add_user_organization
        await add_user_organization(session, user_id, inn)

        # Add GS_Key with conflict status
        conflict_status = (
            KeyConflictStatus.PENDING_REVIEW if key_conflict
            else KeyConflictStatus.NONE
        )

        await add_user_key(
            session,
            user_id,
            gs_key,
            conflict_status
        )

        # Create admin ticket if conflict detected
        if key_conflict:
            await create_conflict_ticket(
                session,
                user_id,
                gs_key,
                phone_number
            )

        # Commit transaction
        await session.commit()

        # Clear FSM state
        await state.clear()

        # Send success message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=REGISTRATION_SUBMITTED,
            keyboard=None,
            parse_mode="HTML"
        )

        logger.info(
            f"Registration completed for user {user_id}: "
            f"phone={phone_number}, key={gs_key}, conflict={key_conflict}"
        )

    except IntegrityError as e:
        await session.rollback()
        logger.error(
            f"Integrity error during registration for user {user_id}: {e}",
            exc_info=True
        )

        # Check if it's a duplicate phone error
        if "phone_number" in str(e):
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=REGISTRATION_PHONE_DUPLICATE,
                keyboard=None,
                parse_mode="HTML"
            )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Произошла ошибка при регистрации.\n"
                     "Возможно, эти данные уже используются.\n\n"
                     "Пожалуйста, попробуйте снова с /start",
                keyboard=None,
                parse_mode="HTML"
            )

        await state.clear()

    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error during registration for user {user_id}: {e}",
            exc_info=True
        )

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при сохранении регистрации.\n"
                 "Пожалуйста, попробуйте позже.",
            keyboard=None,
            parse_mode="HTML"
        )

        await state.clear()


async def create_conflict_ticket(
    session: AsyncSession,
    telegram_id: int,
    key_number: str,
    phone_number: str
):
    """
    Creates an admin ticket for GS_Key conflict resolution.
    
    Requirements: 3.2, 3.3
    """
    from database.models import Ticket, TicketStatus

    try:
        # Create ticket for admin review
        ticket = Ticket(
            ticket_type=TicketType.RENEWAL,  # Using RENEWAL type for admin tasks
            ticket_status=TicketStatus.NEW,
            tg_user_id=telegram_id,
            description=(
                f"⚠️ Конфликт ключа при регистрации\n\n"
                f"Пользователь: {telegram_id}\n"
                f"Телефон: {phone_number}\n"
                f"Ключ: {key_number}\n\n"
                f"Требуется проверка и разрешение конфликта."
            ),
            # assigned_staff_id will be set by admin or default manager
        )

        session.add(ticket)
        await session.flush()

        logger.info(
            f"Conflict ticket created: ticket_id={ticket.id}, "
            f"user={telegram_id}, key={key_number}"
        )

    except SQLAlchemyError as e:
        logger.error(
            f"Error creating conflict ticket for user {telegram_id}: {e}",
            exc_info=True
        )
        # Don't raise - conflict ticket creation failure shouldn't block registration
