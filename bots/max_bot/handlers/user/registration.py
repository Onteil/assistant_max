"""
Registration Handler for MAX Bot

Handles user registration flow including:
- /start command with deep link parsing
- Phone number collection via RequestContactButton
- Full name, email, INN, and GS_Key collection
- Key conflict detection and resolution
- Registration submission to i-TAT API

Requirements: 1.1-1.16, 8.10
"""

import logging
import os
import re
from typing import Optional

from maxapi import F
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.callback_datas import KeyConflictCallback
from bots.max_bot.payloads import (
    KeyConflictChoicePayload,
    RegistrationCancelPayload,
    RegistrationSkipPayload,
)
from bots.max_bot.keyboards.user.registration_kb import (
    get_cancel_keyboard,
    get_key_conflict_keyboard,
    get_key_input_keyboard,
    get_phone_keyboard,
    get_skip_keyboard,
)
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.states import RegistrationStates
from bots.max_bot.texts import (
    ERROR_GENERAL,
    ERROR_VALIDATION_EMAIL,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    ERROR_VALIDATION_PHONE,
    FLOW_CANCELLED,
    REGISTRATION_ENTER_EMAIL,
    REGISTRATION_ENTER_INN,
    REGISTRATION_ENTER_KEY,
    REGISTRATION_KEY_CONFLICT,
    REGISTRATION_PENDING,
    REGISTRATION_PHONE_SHARED,
    REGISTRATION_START,
    REGISTRATION_SUBMITTED,
)
from database.models import KeyConflictStatus, RegistrationStatus
from services.i_tat_service import NonRetryableAPIError, get_itat_client
from services.itat_retry_helper import call_itat_with_retry
from services.user_service import (
    KeyConflictError,
    add_user_key,
    add_user_organization,
    create_user,
    get_user_by_id,
    get_user_by_max_id,
    get_user_by_tg_id,
    update_user_status,
)
from services.validation_service import (
    validate_email,
    validate_gs_key,
    validate_inn,
    validate_phone_number,
)
from constants import BASE_DIR

logger = logging.getLogger(__name__)


# ========== Helper Functions ==========


def _extract_phone_from_contact(event: MessageCreated) -> Optional[str]:
    """
    Extract phone number from contact attachment in MAX message.
    
    maxapi does not provide built-in contact parsing utilities. Contacts arrive
    as attachments with type='contact' and payload.vcf_info containing VCF format
    string (e.g., "TEL;TYPE=cell:79196977974").
    
    This function parses the VCF format to extract the phone number.
    
    Args:
        event: MessageCreated event from MAX
    
    Returns:
        Phone number string with + prefix, or None if not found
    
    Note:
        Manual VCF parsing is required because maxapi library does not provide
        contact parsing utilities. See docs/reports/contact-handling-analysis.md
    """
    if not event.message.body or not hasattr(event.message.body, 'attachments'):
        return None
    
    if not event.message.body.attachments:
        return None
    
    for attachment in event.message.body.attachments:
        # Check if this is a contact attachment
        if not hasattr(attachment, 'type') or attachment.type != 'contact':
            continue
        
        # Extract phone from VCF format
        if not hasattr(attachment, 'payload') or not hasattr(attachment.payload, 'vcf_info'):
            continue
        
        vcf_info = attachment.payload.vcf_info
        logger.debug(f"Parsing VCF info: {vcf_info}")
        
        # Parse VCF to extract phone number
        # Format: TEL;TYPE=cell:79196977974
        tel_match = re.search(r'TEL[^:]*:(\+?\d+)', vcf_info)
        if tel_match:
            phone_number = tel_match.group(1)
            # Add + prefix if not present
            if not phone_number.startswith('+'):
                phone_number = '+' + phone_number
            logger.info(f"Phone extracted from VCF: {phone_number}")
            return phone_number
    
    return None


# ========== /start Command Handler ==========


async def cmd_start(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /start command - check registration status and route accordingly.
    
    Routes user based on registration status:
    - ACTIVE: Show main menu with inline keyboard
    - PENDING: Show waiting message
    - Not registered: Start registration flow
    
    Also parses deep links from message text (e.g., /start param123).
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    - Includes commands_info marker for automatic command registration
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    commands_info: Запускает бота и начинает регистрацию
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 8.10, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    message_text = event.message.body.text or ""
    
    logger.info(f"🎯 cmd_start CALLED: max_user_id={max_user_id}, chat_id={chat_id}, text='{message_text}'")
    
    try:
        # Parse deep link parameter if present
        deep_link_param = None
        if len(message_text.split()) > 1:
            deep_link_param = message_text.split()[1]
            logger.info(f"Deep link parameter detected: {deep_link_param}")
        
        # Check if user is registered (use MAX user ID)
        user = await get_user_by_max_id(session, max_user_id)
        
        if user:
            # User exists - update/create MAX messenger data
            from services.user_service import upsert_max_messenger_data
            await upsert_max_messenger_data(
                session=session,
                user_id=user.id,
                max_user_id=max_user_id,
                max_chat_id=chat_id
            )
            await session.commit()
            
            # Route based on status
            if user.registration_status == RegistrationStatus.ACTIVE:
                # Get active tickets count
                from services.ticket_service import get_user_active_tickets_count
                active_tickets_count = await get_user_active_tickets_count(session, user.id)
                
                # Show main menu with inline keyboard
                from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
                keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
                
                from bots.max_bot.texts import MAIN_MENU_WELCOME_TEXT
                logger.info(f"Active user accessed bot: user_id={user.id}, active_tickets={active_tickets_count}")
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=MAIN_MENU_WELCOME_TEXT,
                    keyboard=keyboard,
                    parse_mode="HTML"
                )
            
            elif user.registration_status == RegistrationStatus.PENDING:
                # Show waiting message
                logger.info(f"Pending user accessed bot: user_id={user.id}")
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=REGISTRATION_PENDING,
                    parse_mode="HTML"
                )
            
            else:
                # Rejected or other status - start new registration
                logger.info(f"User with status {user.registration_status.value} starting registration: user_id={user.id}")
                await start_registration(event, context, messenger_adapter, session)
        
        else:
            # User not registered - start registration flow
            logger.info(f"New user starting registration: max_user_id={max_user_id}")
            await start_registration(event, context, messenger_adapter, session)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in cmd_start: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Unexpected error in cmd_start: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


# ========== Registration Flow Handlers ==========


async def start_registration(
    event: MessageCreated,
    context: MemoryContext,
    messenger_adapter: MAXMessengerAdapter,
    session: AsyncSession
) -> None:
    """
    Initiate registration flow by requesting phone number.
    
    Displays welcome message and phone request keyboard with RequestContactButton.
    
    maxapi Pattern Notes:
    - Sets FSM state using context.set_state()
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        messenger_adapter: MAXMessengerAdapter for sending messages
        session: AsyncSession for database operations
    
    Requirements: 1.5
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    logger.info(f"Starting registration flow: chat_id={chat_id}")
    
    # Get or create user
    user = await get_user_by_max_id(session, max_user_id)
    if user:
        # Log registration started
        from bots.max_bot.utils.audit_logger import log_user_registration_started
        await log_user_registration_started(user.id, max_user_id)
    
    # Set FSM state
    await context.set_state(RegistrationStates.waiting_for_phone)
    
    # Send welcome message with phone request
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=REGISTRATION_START,
        keyboard=get_phone_keyboard(),
        parse_mode="HTML"
    )


async def process_phone_contact(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process shared contact, validate phone, create User record.
    
    Extracts phone number from contact attachment using VCF parsing.
    maxapi does not provide built-in contact parsing utilities, so manual
    VCF parsing is required. Contact attachments arrive with type='contact'
    and payload.vcf_info containing VCF format string (e.g., "TEL;TYPE=cell:79196977974").
    
    Validates phone number format (Russian +7XXXXXXXXXX).
    Creates User record in database immediately after validation.
    Stores user_id in FSM context data.
    
    maxapi Pattern Notes:
    - Registered with FSM state filter: RegistrationStates.waiting_for_phone
    - Uses event.message.sender.user_id for user identification
    - Manual VCF parsing required (no built-in contact handling in maxapi)
    - Sets next FSM state using context.set_state()
    - Stores data using context.update_data()
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 1.6, 1.7
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    logger.info(f"process_phone_contact called: chat_id={chat_id}, max_user_id={max_user_id}")
    
    # Extract phone number from contact attachment
    phone_number = _extract_phone_from_contact(event)
    
    if not phone_number:
        logger.warning(f"No phone number found in message: chat_id={chat_id}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Не удалось получить контакт. Пожалуйста, используйте кнопку 'Поделиться номером'.",
            keyboard=get_phone_keyboard(),
            parse_mode="HTML"
        )
        return
    
    logger.info(f"Processing phone contact: max_user_id={max_user_id}, phone={phone_number}")
    
    # Validate phone number
    is_valid, result = validate_phone_number(phone_number)
    
    if not is_valid:
        logger.warning(f"Invalid phone number: phone={phone_number}, error={result}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"{ERROR_VALIDATION_PHONE}\n\n{result}",
            keyboard=get_phone_keyboard(),
            parse_mode="HTML"
        )
        return
    
    normalized_phone = result
    
    try:
        # Check for orphaned max_messenger_data record
        # This can happen if User was deleted but max_messenger_data remained
        from sqlalchemy import select
        from database.models import MAX_Messenger_Data
        
        result_check = await session.execute(
            select(MAX_Messenger_Data).where(
                MAX_Messenger_Data.max_user_id == max_user_id
            )
        )
        orphaned_max_data = result_check.scalar_one_or_none()
        
        if orphaned_max_data:
            # Check if corresponding user exists
            orphaned_user = await get_user_by_id(session, orphaned_max_data.user_id)
            
            if not orphaned_user:
                # Orphaned record found - delete it
                logger.warning(
                    f"Found orphaned max_messenger_data: id={orphaned_max_data.id}, "
                    f"max_user_id={max_user_id}, user_id={orphaned_max_data.user_id}. Deleting..."
                )
                await session.delete(orphaned_max_data)
                await session.flush()
                logger.info(f"Orphaned max_messenger_data deleted: id={orphaned_max_data.id}")
        
        # Create User record immediately
        user_data = {
            "max_user_id": max_user_id,
            "max_chat_id": chat_id,  # Add MAX chat ID for message sending
            "phone_number": normalized_phone,
            "full_name": "",  # Will be filled in next step
            "username": getattr(event.message.sender, 'username', None),
            "first_name": getattr(event.message.sender, 'first_name', None),
            "last_name": getattr(event.message.sender, 'last_name', None),
        }
        
        user = await create_user(session, user_data)
        await session.commit()
        
        logger.info(f"User record created: user_id={user.id}, phone={normalized_phone}, chat_id={chat_id}")
        
        # Store user_id in FSM context
        await context.update_data(
            user_id=user.id,
            phone_number=normalized_phone
        )
        
        # Transition to name collection state
        await context.set_state(RegistrationStates.waiting_for_name)
        
        # Send confirmation and request full name
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"{REGISTRATION_PHONE_SHARED}\n\n"
                 f"📝 Теперь введите ваше полное имя:",
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML"
        )
    
    except IntegrityError as e:
        logger.error(
            f"Phone number already exists: phone={normalized_phone}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Этот номер телефона уже зарегистрирован. "
                 "Если это ваш номер, обратитесь в поддержку.",
            parse_mode="HTML"
        )
        await context.clear()
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error creating user: phone={normalized_phone}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
        await context.clear()


async def process_full_name(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process full name input, parse into first/last/middle names, proceed to INN.
    
    Parses input in format: "Фамилия Имя Отчество" or "Фамилия Имя"
    - Last name (required)
    - First name (required)
    - Middle name (optional)
    
    Validates minimum 2 words (last name + first name).
    Updates User record with parsed names and constructs full_name.
    Transitions to INN collection state.
    
    maxapi Pattern Notes:
    - Registered with FSM state filter: RegistrationStates.waiting_for_name
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    - Retrieves context data using context.get_data()
    - Sets next FSM state using context.set_state()
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 1.8
    """
    chat_id = event.message.recipient.chat_id
    full_name_input = event.message.body.text.strip()
    
    logger.info(f"Processing full name: chat_id={chat_id}, input='{full_name_input}'")
    
    # Parse name into parts
    name_parts = full_name_input.split()
    
    # Validate minimum 2 parts (last name + first name)
    if len(name_parts) < 2:
        logger.warning(f"Full name too short: input='{full_name_input}'")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Пожалуйста, укажите минимум фамилию и имя.\n\n"
                 "<b>Формат: Фамилия Имя Отчество</b>\n"
                 "<i>(Отчество необязательно)</i>\n\n"
                 "Попробуйте еще раз:",
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Parse components
    last_name = name_parts[0]
    first_name = name_parts[1]
    middle_name = name_parts[2] if len(name_parts) >= 3 else None
    
    # Construct full_name
    if middle_name:
        full_name = f"{last_name} {first_name} {middle_name}"
    else:
        full_name = f"{last_name} {first_name}"
    
    logger.info(f"Parsed name: last='{last_name}', first='{first_name}', middle='{middle_name}'")
    
    try:
        # Get user_id from context
        data = await context.get_data()
        user_id = data.get("user_id")
        
        if not user_id:
            logger.error(f"No user_id in context: chat_id={chat_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Update User record with parsed names
        user = await get_user_by_id(session, user_id)
        if not user:
            logger.error(f"User not found: user_id={user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        user.last_name = last_name
        user.first_name = first_name
        user.middle_name = middle_name
        user.full_name = full_name
        await session.commit()
        
        logger.info(f"Full name updated: user_id={user_id}, full_name='{full_name}'")
        
        # Store full name in context
        await context.update_data(full_name=full_name)
        
        # Transition to email collection state
        await context.set_state(RegistrationStates.waiting_for_email)
        logger.info(f"State set to waiting_for_email for user_id={user_id}, chat_id={chat_id}")
        
        # Send email request
        try:
            message_id = await messenger_adapter.send_message(
                chat_id=chat_id,
                text=REGISTRATION_ENTER_EMAIL,
                keyboard=get_skip_keyboard(),
                parse_mode="HTML"
            )
            logger.info(f"Email request sent successfully: user_id={user_id}, message_id={message_id}")
        except Exception as send_error:
            logger.error(
                f"Failed to send email request: user_id={user_id}, chat_id={chat_id}, error={send_error}",
                exc_info=True
            )
            raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error updating full name: user_id={user_id}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_email_registration(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process email input (optional step), validate format, update User record.
    
    Validates email format if provided.
    Updates User record with email.
    Transitions to INN collection state.
    
    maxapi Pattern Notes:
    - Registered with FSM state filter: RegistrationStates.waiting_for_email
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    - Retrieves context data using context.get_data()
    - Sets next FSM state using context.set_state()
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: Email collection step
    """
    chat_id = event.message.recipient.chat_id
    email_input = event.message.body.text.strip()
    
    logger.info(f"Processing email: chat_id={chat_id}, input='{email_input}'")
    
    # Validate email format
    is_valid, error_msg = validate_email(email_input)
    
    if not is_valid:
        logger.warning(f"Invalid email: email={email_input}, error={error_msg}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"❌ <b>Неверный формат email</b>\n\n{error_msg}\n\nПопробуйте еще раз или нажмите 'Пропустить':",
            keyboard=get_skip_keyboard(),
            parse_mode="HTML"
        )
        return
    
    try:
        # Get user_id from context
        data = await context.get_data()
        user_id = data.get("user_id")
        
        if not user_id:
            logger.error(f"No user_id in context: chat_id={chat_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Update User record with email
        user = await get_user_by_id(session, user_id)
        if not user:
            logger.error(f"User not found: user_id={user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        user.email = email_input
        await session.commit()
        
        logger.info(f"Email updated: user_id={user_id}, email={email_input}")
        
        # Store email in context
        await context.update_data(email=email_input)
        
        # Transition to INN collection state
        await context.set_state(RegistrationStates.waiting_for_inn)
        
        # Send INN request
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=REGISTRATION_ENTER_INN,
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML"
        )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error updating email: user_id={user_id}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def skip_email(
    event: MessageCallback,
    payload: RegistrationSkipPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle skip button callback during email collection step.
    
    Skips email collection and proceeds to INN collection.
    Deletes old message with buttons before sending new message.
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses RegistrationSkipPayload for type-safe callback parsing
    - Uses replace_message pattern (delete old + send new)
    - Sets next FSM state using context.set_state()
    
    Args:
        event: MessageCallback event from maxapi
        payload: Parsed registration skip payload
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: Email collection step (optional)
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Skipping email: chat_id={chat_id}, max_user_id={max_user_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id from context
        data = await context.get_data()
        user_id = data.get("user_id")
        
        if not user_id:
            logger.error(f"No user_id in context: chat_id={chat_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Store None for email in context (skipped)
        await context.update_data(email=None)
        
        # Transition to INN collection state
        await context.set_state(RegistrationStates.waiting_for_inn)
        
        # Send INN request
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=REGISTRATION_ENTER_INN,
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML"
        )
        
        logger.info(f"Email skipped, proceeding to INN: user_id={user_id}")
    
    except Exception as e:
        logger.error(
            f"Error skipping email: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_inn(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process INN input, validate format, add organization, proceed to key.
    
    Validates INN format (10 or 12 digits).
    Adds organization to user profile.
    Transitions to key collection state.
    
    maxapi Pattern Notes:
    - Registered with FSM state filter: RegistrationStates.waiting_for_inn
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    - Sets next FSM state using context.set_state()
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 1.10
    """
    chat_id = event.message.recipient.chat_id
    inn = event.message.body.text.strip()
    
    logger.info(f"Processing INN: chat_id={chat_id}, inn={inn}")
    
    # Validate INN format
    is_valid, error_msg = validate_inn(inn)
    
    if not is_valid:
        logger.warning(f"Invalid INN format: inn={inn}, error={error_msg}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_INN.format(error_details=error_msg),
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Check INN with i-TAT API
    from services.i_tat_service import get_itat_client
    try:
        itat_client = get_itat_client()
        api_response = await itat_client.check_inn(
            messenger="max",
            inn=inn
        )
        logger.info(f"i-TAT API INN check successful: {api_response}")
        
        # Check if INN is valid according to i-TAT
        if not api_response.get("is_valid", True):
            error_details = api_response.get("error_message", "INN не найден в базе данных")
            logger.warning(f"INN rejected by i-TAT API: inn={inn}, reason={error_details}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Ошибка проверки ИНН</b>\n\n{error_details}\n\nПроверьте правильность введенного ИНН и попробуйте снова.",
                keyboard=get_cancel_keyboard(),
                parse_mode="HTML"
            )
            return
            
    except Exception as api_error:
        logger.error(f"i-TAT API INN check error: {api_error}")
        # Continue with local validation if API fails
        logger.info(f"Continuing with local INN validation due to API error")
    
    try:
        # Get user_id from context
        data = await context.get_data()
        user_id = data.get("user_id")
        
        if not user_id:
            logger.error(f"No user_id in context: chat_id={chat_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Add organization to user profile
        await add_user_organization(session, user_id, inn)
        await session.commit()
        
        logger.info(f"Organization added: user_id={user_id}, inn={inn}")
        
        # Store INN in context
        await context.update_data(inn=inn)
        
        # Transition to key collection state
        await context.set_state(RegistrationStates.waiting_for_key)
        
        # Send key request
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=REGISTRATION_ENTER_KEY,
            keyboard=get_key_input_keyboard(),
            parse_mode="HTML"
        )
    
    except IntegrityError as e:
        logger.warning(
            f"Organization already exists: user_id={user_id}, inn={inn}, error={e}",
            exc_info=True
        )
        await session.rollback()
        # Continue anyway - organization already associated
        await context.update_data(inn=inn)
        await context.set_state(RegistrationStates.waiting_for_key)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=REGISTRATION_ENTER_KEY,
            keyboard=get_key_input_keyboard(),
            parse_mode="HTML"
        )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error adding organization: user_id={user_id}, inn={inn}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_gs_key(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process GS_Key input, validate format, check conflicts, proceed to submission.
    
    Validates GS_Key format (XXXXX_XXXXX).
    Checks for key conflicts via i-TAT API using user_id.
    Displays conflict resolution options if conflict detected.
    Stores key with appropriate conflict status.
    
    maxapi Pattern Notes:
    - Registered with FSM state filter: RegistrationStates.waiting_for_key
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    - Retrieves context data using context.get_data()
    - Stores data using context.update_data()
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 1.11, 1.12, 1.13
    """
    chat_id = event.message.recipient.chat_id
    key_number = event.message.body.text.strip()
    
    logger.info(f"Processing GS_Key: chat_id={chat_id}, key={key_number}")
    
    # Validate GS_Key format
    is_valid, result = validate_gs_key(key_number)
    
    if not is_valid:
        logger.warning(f"Invalid GS_Key: key={key_number}, error={result}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_KEY.format(error_details=result),
            keyboard=get_key_input_keyboard(),
            parse_mode="HTML"
        )
        return
    
    normalized_key = result
    
    try:
        # Get user_id from context
        data = await context.get_data()
        user_id = data.get("user_id")
        
        if not user_id:
            logger.error(f"No user_id in context: chat_id={chat_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Check if user already has this key in DB
        from services.user_service import get_user_keys
        existing_keys = await get_user_keys(session, user_id)
        if any(k.key_number == normalized_key for k in existing_keys):
            logger.warning(f"Duplicate key in registration: user_id={user_id}, key={normalized_key}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"⚠️ Ключ <b>{normalized_key}</b> уже добавлен в ваш профиль. Введите другой ключ или продолжите регистрацию.",
                keyboard=get_key_input_keyboard(),
                parse_mode="HTML"
            )
            return
        
        # Check for key conflicts via i-TAT API
        from services.i_tat_service import get_itat_client
        itat_client = get_itat_client()
        conflict_response = await itat_client.check_key_conflict(
            grand_key=normalized_key
        )
        
        logger.info(f"Key conflict check result: {conflict_response}")
        
        if conflict_response.get("status") == "conflict":
            # Conflict detected - offer resolution options
            owner_info = conflict_response.get("owner", "Неизвестный владелец")
            
            logger.warning(f"Key conflict detected: key={normalized_key}, owner={owner_info}")
            
            # Store conflict info in context
            await context.update_data(
                key_number=normalized_key,
                has_conflict=True,
                conflict_owner=owner_info
            )
            
            # Display conflict resolution keyboard
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=REGISTRATION_KEY_CONFLICT.format(owner=owner_info),
                keyboard=get_key_conflict_keyboard(),
                parse_mode="HTML"
            )
        
        else:
            # No conflict - add key and proceed to submission
            await add_user_key(
                session,
                user_id,
                normalized_key,
                KeyConflictStatus.NONE
            )
            await session.commit()
            
            logger.info(f"GS_Key added without conflict: user_id={user_id}, key={normalized_key}")
            
            # Store key in context
            await context.update_data(
                key_number=normalized_key,
                has_conflict=False
            )
            
            # Submit registration
        await submit_registration(context, session, messenger_adapter, chat_id, user_id)
    
    except KeyConflictError as e:
        logger.warning(
            f"Key conflict (DB fallback) in registration: user_id={user_id}, "
            f"key={normalized_key}, owner_user_id={e.existing_user_id}"
        )
        await session.commit()

        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_key_conflict
            await notify_admins_key_conflict(session, user_id, normalized_key)
        except Exception as notify_error:
            logger.error(f"Failed to send key conflict notification: {notify_error}", exc_info=True)

        # Store conflict info and show conflict resolution keyboard (same as i-TAT conflict flow)
        await context.update_data(
            key_number=normalized_key,
            has_conflict=True,
            conflict_owner="Другой пользователь",
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=REGISTRATION_KEY_CONFLICT.format(owner="Другой пользователь"),
            keyboard=get_key_conflict_keyboard(),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(
            f"Error processing GS_Key: key={key_number}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def show_key_help(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show help message about where to find GS_Key number.
    
    Displays detailed instructions with text and image showing where to find
    the key number in GRANS-Smeta program, documents, or packaging.
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Answers callback to acknowledge button press
    - Stays in same FSM state (waiting_for_key)
    
    Args:
        event: MessageCallback event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    logger.info(f"Showing key help: max_user_id={max_user_id}, chat_id={chat_id}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Send help text with explanation
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "📸 Отправляем вам изображения с информацией о том, "
                "где можно узнать номер ключа ГРАНД-Сметы:"
            ),
            parse_mode="HTML"
        )
        
        # Send first instruction image
        instruction_1_path = os.path.join(BASE_DIR, "instruction_1.jpg")
        await messenger_adapter.send_photo(
            chat_id=chat_id,
            photo_path=instruction_1_path,
        )
        
        # Send second instruction image
        instruction_2_path = os.path.join(BASE_DIR, "instruction_2.jpg")
        await messenger_adapter.send_photo(
            chat_id=chat_id,
            photo_path=instruction_2_path,
        )
        
        # Send prompt again with keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Введите номер ключа или нажмите кнопку помощи снова:",
            keyboard=get_key_input_keyboard(),
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error showing key help: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_key_conflict_choice(
    event: MessageCallback,
    payload: KeyConflictChoicePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle user choice when key conflict detected (retry or continue).
    
    If retry: Return to key input state.
    If continue: Add key with PENDING_REVIEW status and proceed to submission.
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses KeyConflictChoicePayload for type-safe callback parsing
    - Retrieves context data using context.get_data()
    - Sets FSM state using context.set_state()
    
    Args:
        event: MessageCallback event from maxapi
        payload: Parsed key conflict choice payload
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 1.13
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    
    logger.info(f"Processing key conflict choice: chat_id={chat_id}, action={payload.action}")
    
    try:
        # Get data from context
        data = await context.get_data()
        user_id = data.get("user_id")
        key_number = data.get("key_number")
        
        if not user_id or not key_number:
            logger.error(f"Missing data in context: user_id={user_id}, key={key_number}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        if payload.action == "retry":
            # Return to key input state
            logger.info(f"User chose to retry key input: user_id={user_id}")
            
            await context.set_state(RegistrationStates.waiting_for_key)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="🔑 Введите другой ключ Гранд-сметы (формат: 00001_00011):",
                keyboard=get_cancel_keyboard(),
                parse_mode="HTML"
            )
        
        elif payload.action == "continue":
            # Add key with PENDING_REVIEW status and proceed
            logger.info(f"User chose to continue with conflict: user_id={user_id}, key={key_number}")
            
            await add_user_key(
                session,
                user_id,
                key_number,
                KeyConflictStatus.PENDING_REVIEW
            )
            await session.commit()
            
            logger.info(f"GS_Key added with PENDING_REVIEW: user_id={user_id}, key={key_number}")
            
            # Notify administrators about key conflict
            try:
                from bots.max_bot.utils.admin_notifications import notify_admins_key_conflict
                await notify_admins_key_conflict(session, user_id, key_number)
                logger.info(f"Key conflict notification sent for user_id={user_id}, key={key_number}")
            except Exception as notify_error:
                logger.error(
                    f"Failed to send key conflict notification for user_id={user_id}: {notify_error}",
                    exc_info=True
                )
            
            # Submit registration
            await submit_registration(context, session, messenger_adapter, chat_id, user_id)
    
    except Exception as e:
        logger.error(
            f"Error processing key conflict choice: action={payload.action}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def submit_registration(
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    chat_id: int,
    user_id: int
) -> None:
    """
    Submit registration to i-TAT API, set status to PENDING.
    
    Submits all collected data to i-TAT API.
    Sets user status to PENDING after submission.
    Displays waiting message to user.
    Logs registration completion.
    
    maxapi Pattern Notes:
    - Clears FSM state using context.clear() after completion
    - Retrieves context data using context.get_data()
    
    Args:
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
        chat_id: Chat ID for sending messages
        user_id: Internal user ID
    
    Requirements: 1.14, 1.15
    """
    logger.info(f"Submitting registration: user_id={user_id}")
    
    try:
        # Get user data
        user = await get_user_by_id(session, user_id)
        if not user:
            logger.error(f"User not found for submission: user_id={user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Get context data
        data = await context.get_data()
        key_number = data.get("key_number")
        inn = data.get("inn", "")
        
        # Submit to i-TAT API
        response = await call_itat_with_retry(
            session=session,
            operation="register_user",
            payload=dict(
                messenger="max",
                user_id=user.max_user_id,
                phone=user.phone_number,
                name=user.first_name or "",
                surname=user.last_name or "",
                inn=inn,
                grand_key=key_number or "",
                email=user.email,
            ),
            user_id=user.id,
        )

        if response is not None:
            logger.info(f"i-TAT registration response: {response}")
        else:
            logger.warning(
                f"register_user queued for retry: user_id={user.id}, "
                f"proceeding with PENDING status"
            )

        # Set user status to PENDING regardless — retry will sync with i-TAT later
        await update_user_status(session, user_id, RegistrationStatus.PENDING)
        await session.commit()
        
        # Log registration completion to audit
        from bots.max_bot.utils.audit_logger import log_user_registration_completed
        await log_user_registration_completed(user_id, user.max_user_id)

        # Notify administrators about new registration
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_new_registration
            await notify_admins_new_registration(session, user_id, inn=inn, key_number=key_number)
            logger.info(f"New registration notification sent for user_id={user_id}")
        except Exception as notify_error:
            logger.error(
                f"Failed to send new registration notification for user_id={user_id}: {notify_error}",
                exc_info=True
            )
        
        logger.info(f"Registration submitted successfully: user_id={user_id}")
        
        # Clear FSM state
        await context.clear()
        
        # Display waiting message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=REGISTRATION_SUBMITTED,
            parse_mode="HTML"
        )
    
    except NonRetryableAPIError as e:
        if e.status_code == 409:
            logger.warning(
                f"Registration conflict (409): user already registered in i-TAT: user_id={user_id}"
            )
            await context.clear()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "⚠️ <b>Вы уже зарегистрированы в системе.</b>\n\n"
                    "Ваша учётная запись уже существует в i-TAT. "
                    "Если вы не можете войти или возникли проблемы — "
                    "пожалуйста, обратитесь в поддержку."
                ),
                parse_mode="HTML"
            )
        else:
            logger.error(
                f"Non-retryable API error submitting registration: user_id={user_id}, "
                f"status={e.status_code}, error={e}",
                exc_info=True
            )
            await session.rollback()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(
            f"Error submitting registration: user_id={user_id}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


# ========== Cancellation Handler ==========


async def cancel_registration_callback(
    event: MessageCallback,
    payload: RegistrationCancelPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle cancellation callback during registration flow.
    
    Deletes old message with buttons.
    Deletes partially created User record if exists.
    Clears FSM state completely.
    Shows main menu (like /start command for unregistered users).
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses RegistrationCancelPayload for type-safe callback parsing
    - Retrieves context data using context.get_data()
    - Clears FSM state using context.clear()
    - Uses replace_message pattern (delete old + send new)
    
    Args:
        event: MessageCallback event from maxapi
        payload: Parsed registration cancel payload
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 1.16
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Cancelling registration (callback): chat_id={chat_id}, max_user_id={max_user_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id from context
        data = await context.get_data()
        user_id = data.get("user_id")
        
        if user_id:
            # Delete partially created User record
            user = await get_user_by_id(session, user_id)
            if user and user.registration_status == RegistrationStatus.PENDING:
                await session.delete(user)
                await session.commit()
                logger.info(f"Deleted partial user record: user_id={user_id}")
        
        # Clear FSM state
        await context.clear()
        
        # Show cancellation message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=FLOW_CANCELLED,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error cancelling registration: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def cancel_registration(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle cancellation during registration flow.
    
    Deletes partially created User record if exists.
    Clears FSM state completely.
    Displays cancellation message.
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Retrieves context data using context.get_data()
    - Clears FSM state using context.clear()
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 1.16
    """
    chat_id = event.message.recipient.chat_id
    
    logger.info(f"Cancelling registration: chat_id={chat_id}")
    
    try:
        # Get user_id from context
        data = await context.get_data()
        user_id = data.get("user_id")
        
        if user_id:
            # Delete partially created User record
            user = await get_user_by_id(session, user_id)
            if user and user.registration_status == RegistrationStatus.PENDING:
                await session.delete(user)
                await session.commit()
                logger.info(f"Deleted partial user record: user_id={user_id}")
        
        # Clear FSM state
        await context.clear()
        
        # Display cancellation message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=FLOW_CANCELLED,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error cancelling registration: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
