"""
Registration Handler

Manages the user registration conversation flow.
Collects phone number, full name, INN, and GS_Key through multi-step FSM.
Integrates with CRM API for registration submission and conflict detection.

Requirements: 1.1-1.5, 2.1-2.7, 3.1-3.5, 4.1-4.5, 25.1-25.5
"""

import logging
from typing import Any

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
)
from bots.tg_bot.states import RegistrationStates
from bots.tg_bot.texts import (
    BTN_CANCEL,
    ERROR_API_UNAVAILABLE,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    ERROR_VALIDATION_PHONE,
    MAIN_MENU,
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
from database.models import KeyConflictStatus, TicketType, User
from services.i_tat_service import ITatAPIClient, get_itat_client
from services.user_service import add_user_key, create_user, get_user_by_tg_id
from services.validation_service import (
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
    tg_user_id = message.from_user.id
    
    try:
        # Check if user exists
        user = await get_user_by_tg_id(session, tg_user_id)
        
        if user:
            # User exists - check registration status
            if user.registration_status.value == "active":
                # Show main menu for active users
                main_menu_keyboard = await get_main_menu_keyboard()
                await message.answer(
                    MAIN_MENU,
                    reply_markup=main_menu_keyboard
                )
                logger.info(f"Active user {tg_user_id} accessed main menu")
            
            elif user.registration_status.value == "pending":
                # Show pending message and block menu access
                await message.answer(
                    REGISTRATION_PENDING,
                    reply_markup=ReplyKeyboardRemove()
                )
                logger.info(f"Pending user {tg_user_id} blocked from menu access")
            
            else:  # rejected
                # Allow re-registration for rejected users
                await start_registration(message, state)
        
        else:
            # User doesn't exist - start registration
            await start_registration(message, state)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in cmd_start for user {tg_user_id}: {e}",
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
    
    Validates format, checks for duplicates, and stores in FSM.
    
    Requirements: 1.2, 1.3, 1.4, 21.1-21.5
    """
    contact = message.contact
    tg_user_id = message.from_user.id
    
    # Verify contact is from the user themselves
    if contact.user_id != tg_user_id:
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
        logger.warning(f"Invalid phone format from user {tg_user_id}: {phone}")
        return
    
    normalized_phone = result
    
    # Check for duplicate phone number
    try:
        existing_user = await session.execute(
            select(User).where(User.phone_number == normalized_phone)
        )
        if existing_user.scalar_one_or_none():
            await message.answer(
                REGISTRATION_PHONE_DUPLICATE,
                reply_markup=ReplyKeyboardRemove()
            )
            logger.warning(
                f"Duplicate phone registration attempt: {normalized_phone} "
                f"by user {tg_user_id}"
            )
            await state.clear()
            return
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error checking phone duplicate for {tg_user_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при проверке номера телефона.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return
    
    # Store phone in FSM and move to next step
    await state.update_data(phone_number=normalized_phone)
    await state.set_state(RegistrationStates.waiting_for_name)
    
    await message.answer(
        REGISTRATION_PHONE_SHARED,
        reply_markup=await get_cancel_keyboard()
    )
    
    logger.info(f"User {tg_user_id} provided phone: {normalized_phone}")


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
async def process_full_name(message: Message, state: FSMContext):
    """
    Handles full name input.
    
    Validates minimum length and stores in FSM.
    
    Requirements: 2.1, 2.2
    """
    full_name = message.text.strip()
    
    # Check for cancel
    if full_name == BTN_CANCEL:
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
    
    # Store name in FSM and move to next step
    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.waiting_for_inn)
    
    await message.answer(
        REGISTRATION_ENTER_INN,
        reply_markup=await get_cancel_keyboard()
    )
    
    logger.info(f"User {message.from_user.id} provided name: {full_name}")


@router.message(RegistrationStates.waiting_for_inn, F.text)
async def process_inn(message: Message, state: FSMContext):
    """
    Handles INN input.
    
    Validates format (10 or 12 digits) and stores in FSM.
    
    Requirements: 2.3, 2.4, 22.1-22.5
    """
    inn = message.text.strip()
    
    # Check for cancel
    if inn == BTN_CANCEL:
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
    
    logger.info(f"User {message.from_user.id} provided INN: {inn}")


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
    tg_user_id = message.from_user.id
    
    # Check for cancel
    if key_input == BTN_CANCEL:
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\nИспользуйте /start для начала регистрации.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {tg_user_id} cancelled registration at key step")
        return
    
    # Validate GS_Key format
    is_valid, result = validate_gs_key(key_input)
    
    if not is_valid:
        await message.answer(
            ERROR_VALIDATION_KEY.format(error_details=result),
            reply_markup=await get_cancel_keyboard()
        )
        logger.warning(f"User {tg_user_id} provided invalid key format: {key_input}")
        return
    
    normalized_key = result
    
    # Get phone from FSM for conflict check
    data = await state.get_data()
    phone = data.get("phone_number", "")
    
    # Check for key conflict via CRM API
    api_client = get_itat_client()
    conflict_detected = False
    
    try:
        conflict_response = await api_client.check_key_conflict(
            key_number=normalized_key,
            telegram_id=tg_user_id,
            phone=phone
        )
        
        if conflict_response.get("status") == "conflict":
            conflict_detected = True
            logger.warning(
                f"Key conflict detected for user {tg_user_id}: "
                f"key={normalized_key}, owner_phone={conflict_response.get('owner_phone')}"
            )
    
    except Exception as e:
        # API failure - log but continue with registration
        logger.error(
            f"API error checking key conflict for user {tg_user_id}: {e}",
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
        await message.answer(
            REGISTRATION_KEY_CONFLICT,
            reply_markup=ReplyKeyboardRemove()
        )
    
    # Proceed to submit registration
    await submit_registration(message, state, session)


async def submit_registration(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Submits complete registration data to CRM and creates User record.
    
    Creates User with PENDING status and associated GS_Key.
    If key conflict detected, creates admin ticket.
    
    Requirements: 4.1-4.5, 25.1-25.5
    """
    tg_user_id = message.from_user.id
    
    # Show processing message
    await message.answer(
        REGISTRATION_PROCESSING,
        reply_markup=ReplyKeyboardRemove()
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
    surname = name_parts[0] if len(name_parts) > 0 else ""
    name = name_parts[1] if len(name_parts) > 1 else ""
    
    # Submit to CRM API
    api_client = get_itat_client()
    api_success = False
    
    try:
        api_response = await api_client.register_user(
            tg_user_id=tg_user_id,
            phone=phone_number,
            name=name,
            surname=surname,
            inn=inn,
            grand_key=gs_key
        )
        
        if api_response.get("status") == "ok":
            api_success = True
            logger.info(f"CRM registration successful for user {tg_user_id}")
        else:
            logger.warning(
                f"CRM registration returned non-ok status for user {tg_user_id}: "
                f"{api_response}"
            )
    
    except Exception as e:
        # API failure - log and continue with local registration (graceful degradation)
        logger.error(
            f"API error during registration for user {tg_user_id}: {e}",
            exc_info=True
        )
        # Continue with local database creation
    
    # Create User record in database
    try:
        user_data = {
            "tg_user_id": tg_user_id,
            "phone_number": phone_number,
            "full_name": full_name,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
        }
        
        user = await create_user(session, user_data)
        
        # Add organization association
        from services.user_service import add_user_organization
        await add_user_organization(session, tg_user_id, inn)
        
        # Add GS_Key with conflict status
        conflict_status = (
            KeyConflictStatus.PENDING_REVIEW if key_conflict
            else KeyConflictStatus.NONE
        )
        
        await add_user_key(
            session,
            tg_user_id,
            gs_key,
            conflict_status
        )
        
        # Create admin ticket if conflict detected
        if key_conflict:
            await create_conflict_ticket(
                session,
                tg_user_id,
                gs_key,
                phone_number
            )
        
        # Commit transaction
        await session.commit()
        
        # Clear FSM state
        await state.clear()
        
        # Send success message
        await message.answer(
            REGISTRATION_SUBMITTED,
            reply_markup=ReplyKeyboardRemove()
        )
        
        logger.info(
            f"Registration completed for user {tg_user_id}: "
            f"phone={phone_number}, key={gs_key}, conflict={key_conflict}"
        )
    
    except IntegrityError as e:
        await session.rollback()
        logger.error(
            f"Integrity error during registration for user {tg_user_id}: {e}",
            exc_info=True
        )
        
        # Check if it's a duplicate phone error
        if "phone_number" in str(e):
            await message.answer(
                REGISTRATION_PHONE_DUPLICATE,
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await message.answer(
                "❌ Произошла ошибка при регистрации.\n"
                "Возможно, эти данные уже используются.\n\n"
                "Пожалуйста, попробуйте снова с /start",
                reply_markup=ReplyKeyboardRemove()
            )
        
        await state.clear()
    
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error during registration for user {tg_user_id}: {e}",
            exc_info=True
        )
        
        await message.answer(
            "❌ Произошла ошибка при сохранении регистрации.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await state.clear()


async def create_conflict_ticket(
    session: AsyncSession,
    tg_user_id: int,
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
            tg_user_id=tg_user_id,
            description=(
                f"⚠️ Конфликт ключа при регистрации\n\n"
                f"Пользователь: {tg_user_id}\n"
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
            f"user={tg_user_id}, key={key_number}"
        )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Error creating conflict ticket for user {tg_user_id}: {e}",
            exc_info=True
        )
        # Don't raise - conflict ticket creation failure shouldn't block registration
