"""
Registration Handler

Manages the user registration conversation flow.
Collects phone number, full name, INN, and GS_Key through multi-step FSM.
Integrates with CRM API for registration submission and conflict detection.

Requirements: 1.1-1.5, 2.1-2.7, 3.1-3.5, 4.1-4.5, 25.1-25.5
"""

import logging
from typing import Any

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.keyboards.main_menu_kb import get_main_menu_keyboard
from bots.tg_bot.keyboards.registration_kb import (
    get_cancel_keyboard,
    get_phone_request_keyboard,
    get_skip_cancel_keyboard,
)
from bots.tg_bot.states import RegistrationStates
from bots.tg_bot.texts import (
    BTN_CANCEL,
    BTN_CONTINUE_REGISTRATION,
    BTN_ENTER_ANOTHER_KEY,
    BTN_SKIP,
    ERROR_API_UNAVAILABLE,
    ERROR_VALIDATION_EMAIL,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    ERROR_VALIDATION_PHONE,
    MAIN_MENU,
    REGISTRATION_ENTER_EMAIL,
    REGISTRATION_ENTER_INN,
    REGISTRATION_ENTER_KEY,
    REGISTRATION_INVALID_INN,
    REGISTRATION_KEY_CONFLICT,
    REGISTRATION_PENDING,
    REGISTRATION_PHONE_DUPLICATE,
    REGISTRATION_PHONE_SHARED,
    REGISTRATION_PROCESSING,
    REGISTRATION_START,
    REGISTRATION_SUBMITTED,
)
from database.models import KeyConflictStatus, RegistrationStatus, TicketType, User
from services.i_tat_service import ITatAPIClient, get_itat_client
from services.user_service import add_user_key, create_user, get_user_by_tg_id, get_user_by_id
from services.validation_service import (
    validate_email,
    validate_gs_key,
    validate_inn,
    validate_phone_number,
)

logger = logging.getLogger(__name__)

router = Router(name="registration")


# ========== Command Handlers ==========


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession):
    """
    Entry point for /start command.
    
    Checks if user is already registered:
    - If registered and ACTIVE: show main menu
    - If registered and PENDING: show waiting message and block menu access
    - If not registered: start registration flow
    
    Requirements: 1.1, 5.4, 5.5, 6.1
    """
    telegram_id = message.from_user.id
    
    try:
        # Check if user exists
        user = await get_user_by_tg_id(session, telegram_id)
        
        if user:
            # User exists - check registration status
            if user.registration_status.value == "active":
                # Show main menu for active users
                # Check for active tickets count
                from database.models import Ticket, TicketStatus
                from services.client_service import get_client_active_tickets
                
                active_tickets = await get_client_active_tickets(session, telegram_id)
                active_tickets_count = len(active_tickets)
                
                main_menu_keyboard = await get_main_menu_keyboard(active_tickets_count=active_tickets_count)
                await message.answer(
                    MAIN_MENU,
                    reply_markup=main_menu_keyboard
                )
                logger.info(f"Active user {telegram_id} accessed main menu")
            
            elif user.registration_status.value == "pending":
                # Show pending message and block menu access
                await message.answer(
                    REGISTRATION_PENDING,
                    reply_markup=ReplyKeyboardRemove()
                )
                logger.info(f"Pending user {telegram_id} blocked from menu access")
            
            else:  # rejected
                # Allow re-registration for rejected users
                await start_registration(message, state)
        
        else:
            # User doesn't exist - start registration
            await start_registration(message, state)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in cmd_start for user {telegram_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при проверке регистрации.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )


async def start_registration(message: Message, state: FSMContext):
    """
    Start the registration flow by requesting phone number.
    
    Requirements: 1.1, 29.1, 29.2
    """
    await state.clear()
    await state.set_state(RegistrationStates.waiting_for_phone)
    
    keyboard = await get_phone_request_keyboard()
    await message.answer(
        REGISTRATION_START,
        reply_markup=keyboard
    )
    
    logger.info(f"User {message.from_user.id} started registration flow")


# ========== Registration Flow Handlers ==========


@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_phone_contact(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handles phone number from contact button.
    
    NEW FLOW: Creates user in DB immediately to get user.id for later use.
    
    Validates format, checks for duplicates, creates User record, and stores in FSM.
    
    Requirements: 1.2, 1.3, 1.4, 21.1-21.5
    """
    contact = message.contact
    telegram_id = message.from_user.id
    
    # Verify contact is from the user themselves
    if contact.user_id != telegram_id:
        await message.answer(
            "❌ Пожалуйста, поделитесь своим собственным номером телефона.",
            reply_markup=await get_phone_request_keyboard()
        )
        return
    
    phone = contact.phone_number
    
    # Validate phone number format
    is_valid, result = validate_phone_number(phone)
    
    if not is_valid:
        await message.answer(
            ERROR_VALIDATION_PHONE.format(error_details=result),
            reply_markup=await get_phone_request_keyboard()
        )
        logger.warning(f"Invalid phone format from user {telegram_id}: {phone}")
        return
    
    normalized_phone = result
    
    # Check for duplicate phone number
    try:
        existing_user_result = await session.execute(
            select(User).where(User.phone_number == normalized_phone)
        )
        existing_user = existing_user_result.scalar_one_or_none()
        
        if existing_user:
            # Allow re-registration for rejected users
            if existing_user.registration_status == RegistrationStatus.REJECTED:
                logger.info(
                    f"Allowing re-registration for rejected user: {normalized_phone}, "
                    f"user_id={existing_user.id}"
                )
                # Reset user status to PENDING and update telegram_id
                existing_user.registration_status = RegistrationStatus.PENDING
                existing_user.tg_user_id = telegram_id
                existing_user.username = message.from_user.username
                await session.commit()
                
                # Store user_id in FSM and continue registration
                await state.update_data(
                    user_id=existing_user.id,
                    phone_number=normalized_phone,
                    telegram_id=telegram_id
                )
                await state.set_state(RegistrationStates.waiting_for_name)
                
                await message.answer(
                    REGISTRATION_PHONE_SHARED,
                    reply_markup=await get_cancel_keyboard()
                )
                
                logger.info(
                    f"User {telegram_id} re-registering with phone: {normalized_phone}, "
                    f"user_id={existing_user.id}"
                )
                return
            else:
                # User exists with non-rejected status - block registration
                await message.answer(
                    REGISTRATION_PHONE_DUPLICATE,
                    reply_markup=ReplyKeyboardRemove()
                )
                logger.warning(
                    f"Duplicate phone registration attempt: {normalized_phone} "
                    f"by user {telegram_id}, existing status: {existing_user.registration_status}"
                )
                await state.clear()
                return
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error checking phone duplicate for {telegram_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при проверке номера телефона.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return
    
    # CREATE USER IN DB NOW to get user.id
    try:
        user_data = {
            "tg_user_id": telegram_id,  # Set immediately when phone is shared
            "username": message.from_user.username,  # Save Telegram username
            "phone_number": normalized_phone,
            "full_name": "",  # Will be updated when user enters name
            "first_name": None,  # Will be updated when user enters name
            "last_name": None,  # Will be updated when user enters name
        }
        
        user = await create_user(session, user_data)
        await session.commit()
        
        logger.info(
            f"User created in DB: user_id={user.id}, tg_user_id={telegram_id}, "
            f"phone={normalized_phone}, username={message.from_user.username}"
        )
        
        # Store user_id and phone in FSM
        await state.update_data(
            user_id=user.id,
            phone_number=normalized_phone,
            telegram_id=telegram_id
        )
        await state.set_state(RegistrationStates.waiting_for_name)
        
        await message.answer(
            REGISTRATION_PHONE_SHARED,
            reply_markup=await get_cancel_keyboard()
        )
        
        logger.info(f"User {telegram_id} provided phone: {normalized_phone}, user_id={user.id}")
    
    except IntegrityError as e:
        await session.rollback()
        logger.error(
            f"Integrity error creating user: telegram_id={telegram_id}, error={e}",
            exc_info=True
        )
        
        if "phone_number" in str(e):
            await message.answer(
                REGISTRATION_PHONE_DUPLICATE,
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await message.answer(
                "❌ Произошла ошибка при регистрации.\n"
                "Пожалуйста, попробуйте позже.",
                reply_markup=ReplyKeyboardRemove()
            )
        
        await state.clear()
    
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error creating user: telegram_id={telegram_id}, error={e}",
            exc_info=True
        )
        
        await message.answer(
            "❌ Произошла ошибка при сохранении данных.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await state.clear()


@router.message(RegistrationStates.waiting_for_phone, F.text == BTN_CANCEL)
async def cancel_phone_input(message: Message, state: FSMContext):
    """Handle cancel during phone input."""
    await state.clear()
    await message.answer(
        "❌ Регистрация отменена.\n\nИспользуйте /start для начала регистрации.",
        reply_markup=ReplyKeyboardRemove()
    )
    logger.info(f"User {message.from_user.id} cancelled registration at phone step")


@router.message(RegistrationStates.waiting_for_name, F.text)
async def process_full_name(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handles full name input.
    
    Validates minimum length, updates User record, and stores in FSM.
    
    Requirements: 2.1, 2.2
    """
    full_name = message.text.strip()
    
    # Check for cancel
    if full_name == BTN_CANCEL:
        # Get user_id from FSM and delete the user record
        data = await state.get_data()
        user_id = data.get("user_id")
        
        if user_id:
            try:
                user = await get_user_by_id(session, user_id)
                if user:
                    await session.delete(user)
                    await session.commit()
                    logger.info(f"Deleted user {user_id} due to registration cancellation")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Error deleting user {user_id}: {e}", exc_info=True)
        
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\nИспользуйте /start для начала регистрации.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {message.from_user.id} cancelled registration at name step")
        return
    
    # Validate length
    if len(full_name) < 2:
        await message.answer(
            "❌ Имя должно содержать минимум 2 символа.\n\n"
            "Пожалуйста, введите ваше полное имя (Фамилия Имя):",
            reply_markup=await get_cancel_keyboard()
        )
        logger.warning(f"User {message.from_user.id} provided too short name: {full_name}")
        return
    
    # Split full_name into last_name and first_name
    name_parts = full_name.split(maxsplit=1)
    last_name = name_parts[0] if len(name_parts) > 0 else ""
    first_name = name_parts[1] if len(name_parts) > 1 else ""
    
    # Update user record with full_name, first_name, last_name
    data = await state.get_data()
    user_id = data.get("user_id")
    
    if not user_id:
        logger.error(f"No user_id in FSM for user {message.from_user.id}")
        await message.answer(
            "❌ Произошла ошибка. Пожалуйста, начните регистрацию заново с /start",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return
    
    try:
        user = await get_user_by_id(session, user_id)
        if not user:
            logger.error(f"User {user_id} not found in DB")
            await message.answer(
                "❌ Произошла ошибка. Пожалуйста, начните регистрацию заново с /start",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()
            return
        
        user.full_name = full_name
        user.first_name = first_name
        user.last_name = last_name
        await session.commit()
        
        logger.info(
            f"Updated user {user_id} with full_name: {full_name}, "
            f"first_name: {first_name}, last_name: {last_name}"
        )
    
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"Error updating user {user_id} with name: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при сохранении данных.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return
    
    # Store name in FSM and move to next step (email)
    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.waiting_for_email)
    
    await message.answer(
        REGISTRATION_ENTER_EMAIL,
        reply_markup=await get_skip_cancel_keyboard()
    )
    
    logger.info(f"User {message.from_user.id} (user_id={user_id}) provided name: {full_name}")

@router.message(RegistrationStates.waiting_for_email, F.text)
async def process_email(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handles email input (optional step).

    Validates email format if provided, or allows skip.
    Updates User record and stores in FSM.

    Requirements: Email collection step
    """
    email_input = message.text.strip()

    # Check for cancel
    if email_input == BTN_CANCEL:
        # Get user_id from FSM and delete the user record
        data = await state.get_data()
        user_id = data.get("user_id")

        if user_id:
            try:
                user = await get_user_by_id(session, user_id)
                if user:
                    await session.delete(user)
                    await session.commit()
                    logger.info(f"Deleted user {user_id} due to registration cancellation")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Error deleting user {user_id}: {e}", exc_info=True)

        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\nИспользуйте /start для начала регистрации.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {message.from_user.id} cancelled registration at email step")
        return

    # Check for skip
    email = None
    if email_input == BTN_SKIP:
        logger.info(f"User {message.from_user.id} skipped email input")
    else:
        # Validate email format
        is_valid, error_message = validate_email(email_input)

        if not is_valid:
            await message.answer(
                ERROR_VALIDATION_EMAIL.format(error_details=error_message),
                reply_markup=await get_skip_cancel_keyboard()
            )
            logger.warning(f"User {message.from_user.id} provided invalid email: {email_input}")
            return

        email = email_input

    # Update user record with email if provided
    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        logger.error(f"No user_id in FSM for user {message.from_user.id}")
        await message.answer(
            "❌ Произошла ошибка. Пожалуйста, начните регистрацию заново с /start",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return

    if email:
        try:
            user = await get_user_by_id(session, user_id)
            if not user:
                logger.error(f"User {user_id} not found in DB")
                await message.answer(
                    "❌ Произошла ошибка. Пожалуйста, начните регистрацию заново с /start",
                    reply_markup=ReplyKeyboardRemove()
                )
                await state.clear()
                return

            user.email = email
            await session.commit()

            logger.info(f"Updated user {user_id} with email: {email}")

        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Error updating user {user_id} with email: {e}", exc_info=True)
            await message.answer(
                "❌ Произошла ошибка при сохранении данных.\n"
                "Пожалуйста, попробуйте позже.",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()
            return

    # Store email in FSM and move to next step (INN)
    await state.update_data(email=email)
    await state.set_state(RegistrationStates.waiting_for_inn)

    await message.answer(
        REGISTRATION_ENTER_INN,
        reply_markup=await get_cancel_keyboard()
    )

    logger.info(f"User {message.from_user.id} (user_id={user_id}) provided email: {email or 'skipped'}")



@router.message(RegistrationStates.waiting_for_inn, F.text)
async def process_inn(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handles INN input.
    
    Validates format (10 or 12 digits) and stores in FSM.
    
    Requirements: 2.3, 2.4, 22.1-22.5
    """
    inn = message.text.strip()
    
    # Check for cancel
    if inn == BTN_CANCEL:
        # Get user_id from FSM and delete the user record
        data = await state.get_data()
        user_id = data.get("user_id")
        
        if user_id:
            try:
                user = await get_user_by_id(session, user_id)
                if user:
                    await session.delete(user)
                    await session.commit()
                    logger.info(f"Deleted user {user_id} due to registration cancellation")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Error deleting user {user_id}: {e}", exc_info=True)
        
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\nИспользуйте /start для начала регистрации.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {message.from_user.id} cancelled registration at INN step")
        return
    
    # Validate INN format
    is_valid, error_message = validate_inn(inn)
    
    if not is_valid:
        await message.answer(
            ERROR_VALIDATION_INN.format(error_details=error_message),
            reply_markup=await get_cancel_keyboard()
        )
        logger.warning(f"User {message.from_user.id} provided invalid INN: {inn}")
        return
    
    # Store INN in FSM and move to next step
    await state.update_data(inn=inn)
    await state.set_state(RegistrationStates.waiting_for_key)
    
    await message.answer(
        REGISTRATION_ENTER_KEY,
        reply_markup=await get_cancel_keyboard()
    )
    
    data = await state.get_data()
    user_id = data.get("user_id")
    logger.info(f"User {message.from_user.id} (user_id={user_id}) provided INN: {inn}")


@router.message(RegistrationStates.waiting_for_key, F.text)
async def process_gs_key(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handles GS_Key input.
    
    Validates format, checks for conflicts via CRM API, and stores in FSM.
    If conflict detected, creates admin ticket and flags key.
    
    Requirements: 2.5, 2.6, 3.1-3.5, 23.1-23.5
    """
    key_input = message.text.strip()
    telegram_id = message.from_user.id
    
    # Check for cancel
    if key_input == BTN_CANCEL:
        # Get user_id from FSM and delete the user record
        data = await state.get_data()
        user_id = data.get("user_id")
        
        if user_id:
            try:
                user = await get_user_by_id(session, user_id)
                if user:
                    await session.delete(user)
                    await session.commit()
                    logger.info(f"Deleted user {user_id} due to registration cancellation")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Error deleting user {user_id}: {e}", exc_info=True)
        
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\nИспользуйте /start для начала регистрации.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {telegram_id} cancelled registration at key step")
        return
    
    # Validate GS_Key format
    is_valid, result = validate_gs_key(key_input)
    
    if not is_valid:
        await message.answer(
            ERROR_VALIDATION_KEY.format(error_details=result),
            reply_markup=await get_cancel_keyboard()
        )
        logger.warning(f"User {telegram_id} provided invalid key format: {key_input}")
        return
    
    normalized_key = result
    
    # Get user_id from FSM
    data = await state.get_data()
    user_id = data.get("user_id")
    
    if not user_id:
        logger.error(f"No user_id in FSM for user {telegram_id}")
        await message.answer(
            "❌ Произошла ошибка. Пожалуйста, начните регистрацию заново с /start",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return
    
    # Check for key conflict via CRM API using user_id
    api_client = get_itat_client()
    conflict_detected = False
    
    try:
        conflict_response = await api_client.check_key_conflict(
            grand_key=normalized_key,
            user_id=user_id  # Use user_id instead of telegram_id
        )
        
        if conflict_response.get("status") == "conflict":
            conflict_detected = True
            logger.warning(
                f"Key conflict detected for user_id={user_id} (telegram_id={telegram_id}): "
                f"key={normalized_key}, owner={conflict_response.get('owner')}"
            )
    
    except httpx.HTTPStatusError as e:
        # HTTP error from API - log and continue with graceful degradation
        logger.error(
            f"API HTTP error checking key conflict for user_id={user_id}: "
            f"status={e.response.status_code}, error={e}",
            exc_info=True
        )
        # Continue without conflict check (graceful degradation)
    
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        # Network/timeout error - log and continue with graceful degradation
        logger.error(
            f"API connection error checking key conflict for user_id={user_id}: {e}",
            exc_info=True
        )
        # Continue without conflict check (graceful degradation)
    
    except Exception as e:
        # Unexpected error - log but continue with registration
        logger.error(
            f"Unexpected error checking key conflict for user_id={user_id}: {e}",
            exc_info=True
        )
        # Continue without conflict check (graceful degradation)
    
    logger.info(
        f"Key conflict check completed: "
        f"user_id={user_id}, key={normalized_key}, conflict={conflict_detected}"
    )
    
    # Store key and conflict status in FSM
    await state.update_data(
        gs_key=normalized_key,
        key_conflict=conflict_detected
    )
    
    # Show conflict warning if detected and ask for choice
    if conflict_detected:
        from bots.tg_bot.keyboards.registration_kb import get_key_conflict_keyboard
        
        await message.answer(
            REGISTRATION_KEY_CONFLICT,
            reply_markup=await get_key_conflict_keyboard()
        )
        await state.set_state(RegistrationStates.key_conflict_choice)
        logger.info(f"User {telegram_id} has key conflict, waiting for choice")
        return
    
    # No conflict - proceed to submit registration
    await submit_registration(message, state, session)


@router.message(RegistrationStates.key_conflict_choice, F.text)
async def process_key_conflict_choice(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handles user choice when key conflict is detected.
    
    Options:
    - Enter another key: Returns to waiting_for_key state
    - Continue registration: Proceeds with conflict ticket creation
    
    Requirements: 3.2, 3.3
    """
    from bots.tg_bot.texts import BTN_ENTER_ANOTHER_KEY, BTN_CONTINUE_REGISTRATION
    
    choice = message.text.strip()
    telegram_id = message.from_user.id
    
    if choice == BTN_ENTER_ANOTHER_KEY:
        # User wants to enter a different key
        logger.info(f"User {telegram_id} chose to enter another key")
        
        # Clear the conflicted key from FSM
        await state.update_data(gs_key=None, key_conflict=False)
        
        # Return to key input state
        await state.set_state(RegistrationStates.waiting_for_key)
        await message.answer(
            REGISTRATION_ENTER_KEY,
            reply_markup=await get_cancel_keyboard()
        )
        return
    
    elif choice == BTN_CONTINUE_REGISTRATION:
        # User wants to continue with conflict resolution
        logger.info(f"User {telegram_id} chose to continue registration with key conflict")
        
        # Proceed to submit registration (conflict ticket will be created)
        await submit_registration(message, state, session)
        return
    
    else:
        # Invalid choice - show options again
        from bots.tg_bot.keyboards.registration_kb import get_key_conflict_keyboard
        
        await message.answer(
            "⚠️ Пожалуйста, выберите один из предложенных вариантов:",
            reply_markup=await get_key_conflict_keyboard()
        )
        logger.warning(f"User {telegram_id} provided invalid choice: {choice}")
        return


async def submit_registration(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Submits complete registration data to CRM.
    
    NEW FLOW:
    1. Get existing User from FSM (created in process_phone_contact)
    2. Add organization and keys to existing user
    3. Call API with user.id
    4. Update user.tg_user_id after successful API registration
    
    Requirements: 4.1-4.5, 25.1-25.5
    """
    telegram_id = message.from_user.id
    
    # Show processing message
    await message.answer(
        REGISTRATION_PROCESSING,
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Get all data from FSM
    data = await state.get_data()
    user_id = data.get("user_id")
    phone_number = data.get("phone_number")
    full_name = data.get("full_name")
    inn = data.get("inn")
    gs_key = data.get("gs_key")
    key_conflict = data.get("key_conflict", False)
    
    # Validate user_id exists
    if not user_id:
        logger.error(f"No user_id in FSM for telegram_id={telegram_id}")
        await message.answer(
            "❌ Произошла ошибка. Пожалуйста, начните регистрацию заново с /start",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return
    
    # Extract first and last name from full_name
    name_parts = full_name.split(maxsplit=1)
    last_name = name_parts[0] if len(name_parts) > 0 else ""
    first_name = name_parts[1] if len(name_parts) > 1 else ""
    
    # STEP 1: Get existing user and add organization/keys
    user = None
    try:
        user = await get_user_by_id(session, user_id)
        
        if not user:
            logger.error(f"User {user_id} not found in DB for telegram_id={telegram_id}")
            await message.answer(
                "❌ Произошла ошибка. Пожалуйста, начните регистрацию заново с /start",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()
            return
        
        # Add organization association
        from services.user_service import add_user_organization
        await add_user_organization(session, user.id, inn)
        
        # Add GS_Key with conflict status
        conflict_status = (
            KeyConflictStatus.PENDING_REVIEW if key_conflict
            else KeyConflictStatus.NONE
        )
        
        await add_user_key(
            session,
            user.id,
            gs_key,
            conflict_status
        )
        
        # Create admin ticket if conflict detected
        if key_conflict:
            await create_conflict_ticket(
                session,
                user.id,
                gs_key,
                phone_number
            )
        
        # Commit changes
        await session.commit()
        
        logger.info(
            f"Organization and key added to user: user_id={user.id}, inn={inn}, "
            f"key={gs_key}, conflict={key_conflict}"
        )
    
    except IntegrityError as e:
        await session.rollback()
        logger.error(
            f"Integrity error during registration: user_id={user_id}, error={e}",
            exc_info=True
        )
        
        await message.answer(
            "❌ Произошла ошибка при регистрации.\n"
            "Возможно, эти данные уже используются.\n\n"
            "Пожалуйста, попробуйте снова с /start",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await state.clear()
        return
    
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error during registration: user_id={user_id}, error={e}",
            exc_info=True
        )
        
        await message.answer(
            "❌ Произошла ошибка при сохранении регистрации.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await state.clear()
        return
    
    # STEP 2: Submit to CRM API using bot DB user.id
    api_client = get_itat_client()
    api_success = False
    api_error_message = None
    
    try:
        api_response = await api_client.register_user(
            messenger="telegram",
            user_id=user.id,  # Use bot DB user.id instead of telegram_id
            phone=phone_number,
            name=first_name,
            surname=last_name,
            inn=inn,
            grand_key=gs_key
        )
        
        if api_response.get("status") == "ok":
            api_success = True
            logger.info(f"CRM registration successful for user_id={user.id}, telegram_id={telegram_id}")
        else:
            logger.warning(
                f"CRM registration returned non-ok status for user_id={user.id}: "
                f"{api_response}"
            )
    
    except httpx.HTTPStatusError as e:
        # HTTP error from API - provide user-friendly message based on status code
        status_code = e.response.status_code
        logger.error(
            f"API HTTP error during registration for user {telegram_id}: "
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
            f"API connection error during registration for user {telegram_id}: {e}",
            exc_info=True
        )
        api_error_message = "❌ Не удалось связаться с сервером. Проверьте подключение к интернету и попробуйте позже."
    
    except Exception as e:
        # Unexpected error - log but continue (graceful degradation)
        logger.error(
            f"Unexpected error during API registration for user_id={user.id}: {e}",
            exc_info=True
        )
        # Continue without API registration
    
    # Show error message if API registration failed
    if not api_success and api_error_message:
        await message.answer(
            f"{api_error_message}\n\n"
            "Ваша регистрация сохранена локально и будет синхронизирована позже.",
            reply_markup=ReplyKeyboardRemove()
        )
    
    # Clear FSM state
    await state.clear()
    
    # Send success message
    await message.answer(
        REGISTRATION_SUBMITTED,
        reply_markup=ReplyKeyboardRemove()
    )
    
    logger.info(
        f"Registration completed: user_id={user.id}, tg_user_id={telegram_id if api_success else 'pending'}, "
        f"phone={phone_number}, key={gs_key}, conflict={key_conflict}, api_success={api_success}"
    )
    
    # STEP 3: Notify administrators about new registration
    try:
        from bots.tg_bot.handlers.staff.registrations import handle_registration_notification
        
        await handle_registration_notification(session, user.id)
        logger.info(f"Admin notification sent for user_id={user.id}")
    except Exception as notify_error:
        # Don't fail registration if notification fails
        logger.error(
            f"Failed to send admin notification for user_id={user.id}: {notify_error}",
            exc_info=True
        )
    
    # STEP 4: If key conflict, notify administrators separately
    if key_conflict:
        try:
            await notify_admins_key_conflict(session, user.id, gs_key)
            logger.info(f"Key conflict notification sent for user_id={user.id}, key={gs_key}")
        except Exception as conflict_notify_error:
            logger.error(
                f"Failed to send key conflict notification for user_id={user.id}: {conflict_notify_error}",
                exc_info=True
            )


async def create_conflict_ticket(
    session: AsyncSession,
    user_id: int,
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
            user_id=user_id,
            description=(
                f"⚠️ Конфликт ключа при регистрации\n\n"
                f"Пользователь ID: {user_id}\n"
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
            f"user_id={user_id}, key={key_number}"
        )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Error creating conflict ticket for user_id={user_id}: {e}",
            exc_info=True
        )
        # Don't raise - conflict ticket creation failure shouldn't block registration


async def notify_admins_key_conflict(
    session: AsyncSession,
    new_user_id: int,
    key_number: str
):
    """
    Send key conflict notification to all administrators.
    
    Called when a key conflict is detected during registration.
    Notifies admins about the conflict with details of both users.
    
    Args:
        session: Database session
        new_user_id: ID of new user with conflicting key
        key_number: The conflicting GS_Key number
        
    Requirements: 3.2, 3.3
    """
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from bots.tg_bot.texts import ADMIN_KEY_CONFLICT_NOTIFICATION
    from constants import TG_BOT_TOKEN
    from datetime import datetime
    
    try:
        # Get new user details
        stmt = select(User).where(User.id == new_user_id).options(
            selectinload(User.gs_keys)
        )
        result = await session.execute(stmt)
        new_user = result.scalar_one_or_none()
        
        if not new_user:
            logger.error(f"New user {new_user_id} not found for key conflict notification")
            return
        
        # Find the current owner of the key (if exists in our DB)
        stmt = select(User).join(User.gs_keys).where(
            GS_Key.key_number == key_number,
            User.id != new_user_id,
            GS_Key.conflict_status == KeyConflictStatus.NONE
        ).options(selectinload(User.gs_keys))
        result = await session.execute(stmt)
        current_owner = result.scalar_one_or_none()
        
        # Query all administrators
        stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
            Staff_Member.is_active == True,
            Staff_Member.tg_user_id.isnot(None)
        )
        result = await session.execute(stmt)
        admins = result.scalars().all()
        
        if not admins:
            logger.warning("No active administrators found to send key conflict notification")
            return
        
        # Format conflict date in Moscow timezone
        from datetime import timezone, timedelta
        moscow_tz = timezone(timedelta(hours=3))
        conflict_date_moscow = datetime.now(moscow_tz)
        conflict_date = conflict_date_moscow.strftime("%d.%m.%Y %H:%M")
        
        # Format Telegram usernames
        new_user_telegram = f"@{new_user.username}" if new_user.username else "Не указан"
        current_owner_telegram = f"@{current_owner.username}" if current_owner and current_owner.username else "Не указан"
        
        # Format notification message
        message_text = ADMIN_KEY_CONFLICT_NOTIFICATION.format(
            new_user_name=new_user.full_name or "Не указано",
            new_user_phone=new_user.phone_number,
            new_user_telegram=new_user_telegram,
            key_number=key_number,
            current_owner_name=current_owner.full_name if current_owner else "Не найден в системе",
            current_owner_phone=current_owner.phone_number if current_owner else "Не указан",
            current_owner_telegram=current_owner_telegram,
            conflict_date=conflict_date
        )
        
        # Send notification to all administrators
        bot = Bot(token=TG_BOT_TOKEN)
        
        sent_count = 0
        for admin in admins:
            try:
                await bot.send_message(
                    chat_id=admin.tg_user_id,
                    text=message_text,
                    parse_mode=ParseMode.HTML
                )
                sent_count += 1
                logger.info(f"Sent key conflict notification to admin {admin.tg_user_id}")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send key conflict notification to admin {admin.tg_user_id}: {send_error}",
                    exc_info=True
                )
        
        logger.info(
            f"Key conflict notification sent: new_user_id={new_user_id}, "
            f"key={key_number}, admins_notified={sent_count}/{len(admins)}"
        )
        
    except Exception as e:
        logger.error(
            f"Error sending key conflict notification: new_user_id={new_user_id}, "
            f"key={key_number}, error={e}",
            exc_info=True
        )
