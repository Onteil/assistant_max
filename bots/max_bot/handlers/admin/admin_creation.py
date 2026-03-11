"""
Admin Creation Handler for MAX Bot

Handles /make_admin command to create administrator accounts.
Collects phone number and full name, creates User and Staff_Member records.
"""

import logging
import re
from typing import Optional

from maxapi import F
from maxapi.context import MemoryContext
from maxapi.types import Command, MessageCallback, MessageCreated
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.keyboards.admin.admin_creation_kb import (
    get_admin_cancel_keyboard,
    get_admin_phone_keyboard,
)
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.payloads import AdminCreationCancelPayload
from bots.max_bot.states import AdminCreationStates
from bots.max_bot.texts import (
    ADMIN_CREATION_CANCELLED,
    ADMIN_CREATION_ENTER_FULL_NAME,
    ADMIN_CREATION_ENTER_PHONE,
    ADMIN_CREATION_INVALID_PHONE,
    ADMIN_CREATION_START,
    ADMIN_CREATION_SUCCESS,
    ERROR_GENERAL,
)
from database.models import RegistrationStatus, StaffRole
from services.employee_service import get_staff_by_max_user_id
from services.user_service import create_user, get_user_by_max_id, get_user_by_phone
from services.validation_service import validate_phone_number

logger = logging.getLogger(__name__)


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


async def cmd_make_admin(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /make_admin command to create administrator account.
    
    Initiates admin creation flow by requesting phone number.
    
    NOTE: Access control temporarily disabled for testing phase.
    TODO: Re-enable administrator check before production deployment.
    
    commands_info: Создать администратора системы
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    logger.info(f"cmd_make_admin called: chat_id={chat_id}, max_user_id={max_user_id}")
    
    # TODO: Uncomment before production
    # # Check if user is administrator
    # staff = await get_staff_by_max_user_id(session, max_user_id)
    # 
    # if not staff or staff.staff_role != StaffRole.ADMINISTRATOR:
    #     await messenger_adapter.send_message(
    #         chat_id=chat_id,
    #         text="❌ Эта команда доступна только администраторам.",
    #         parse_mode="HTML"
    #     )
    #     return
    
    # Set FSM state
    await context.set_state(AdminCreationStates.waiting_for_phone)
    
    # Send instructions
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=ADMIN_CREATION_START,
        keyboard=get_admin_phone_keyboard(),
        parse_mode="HTML"
    )


async def process_admin_phone_contact(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process shared contact for admin creation.
    
    Extracts phone number from contact attachment, validates format,
    checks if user already exists.
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    logger.info(f"process_admin_phone_contact called: chat_id={chat_id}")
    
    # Extract phone number from contact
    phone_number = _extract_phone_from_contact(event)
    
    if not phone_number:
        logger.warning(f"No phone number found in contact: chat_id={chat_id}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Не удалось получить контакт. Пожалуйста, используйте кнопку 'Поделиться номером'.",
            keyboard=get_admin_phone_keyboard(),
            parse_mode="HTML"
        )
        return
    
    logger.info(f"Processing admin phone: phone={phone_number}")
    
    # Validate phone number
    is_valid, result = validate_phone_number(phone_number)
    
    if not is_valid:
        logger.warning(f"Invalid phone number: phone={phone_number}, error={result}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"{ADMIN_CREATION_INVALID_PHONE}\n\n{result}",
            keyboard=get_admin_phone_keyboard(),
            parse_mode="HTML"
        )
        return
    
    normalized_phone = result
    
    # Check if phone already exists
    existing_user = await get_user_by_phone(session, normalized_phone)
    
    if existing_user:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"❌ Пользователь с номером {normalized_phone} уже существует в системе.",
            keyboard=get_admin_phone_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Store phone in context
    await context.update_data(phone_number=normalized_phone)
    
    # Transition to full name collection
    await context.set_state(AdminCreationStates.waiting_for_full_name)
    
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=ADMIN_CREATION_ENTER_FULL_NAME,
        keyboard=get_admin_cancel_keyboard(),
        parse_mode="HTML"
    )


async def process_admin_full_name(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process full name input and create admin account.
    
    Creates User record with ACTIVE status and Staff_Member record
    with ADMINISTRATOR role. Also creates MAX_Messenger_Data record
    for message delivery.
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    full_name = event.message.body.text.strip()
    
    logger.info(f"process_admin_full_name called: chat_id={chat_id}, full_name='{full_name}'")
    
    # Validate full name (minimum 2 words)
    name_parts = full_name.split()
    
    if len(name_parts) < 2:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Пожалуйста, введите полное имя (минимум Фамилия и Имя).",
            keyboard=get_admin_cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Get phone from context
    context_data = await context.get_data()
    phone_number = context_data.get("phone_number")
    
    if not phone_number:
        logger.error("Phone number not found in context")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
        await context.clear()
        return
    
    # Parse name parts
    last_name = name_parts[0]
    first_name = name_parts[1]
    middle_name = name_parts[2] if len(name_parts) > 2 else None
    
    try:
        # Create User record with ACTIVE status and MAX messenger data
        user_data = {
            "phone_number": phone_number,
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "middle_name": middle_name,
            "max_user_id": max_user_id,
        }
        
        user = await create_user(session, user_data)
        
        # Update registration status to ACTIVE
        user.registration_status = RegistrationStatus.ACTIVE
        await session.flush()
        
        logger.info(f"Admin user created: user_id={user.id}, phone={phone_number}, max_user_id={max_user_id}")
        
        # Create MAX_Messenger_Data record for message delivery
        from services.user_service import upsert_max_messenger_data
        
        await upsert_max_messenger_data(
            session=session,
            user_id=user.id,
            max_user_id=max_user_id,
            max_chat_id=chat_id
        )
        
        logger.info(f"MAX messenger data created for admin: user_id={user.id}, max_user_id={max_user_id}, chat_id={chat_id}")
        
        # Create Staff_Member record with ADMINISTRATOR role
        from database.models import Staff_Member
        
        staff = Staff_Member(
            max_user_id=max_user_id,
            max_chat_id=chat_id,
            full_name=full_name,
            position="Администратор",
            staff_role=StaffRole.ADMINISTRATOR,
            is_active=True
        )
        
        session.add(staff)
        await session.flush()
        await session.refresh(staff)
        
        logger.info(
            f"Admin staff member created: staff_id={staff.id}, user_id={user.id}, "
            f"max_user_id={max_user_id}, full_name={full_name}"
        )
        
        await session.commit()
        
        # Clear FSM state
        await context.clear()
        
        # Send success message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ADMIN_CREATION_SUCCESS.format(
                full_name=full_name,
                phone=phone_number,
                user_id=user.id,
                staff_id=staff.id
            ),
            parse_mode="HTML"
        )
    
    except IntegrityError as e:
        logger.error(
            f"Integrity error creating admin: phone={phone_number}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Ошибка: пользователь с таким номером уже существует.",
            parse_mode="HTML"
        )
        await context.clear()
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error creating admin: phone={phone_number}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
        await context.clear()


async def cancel_admin_creation_callback(
    event: MessageCallback,
    payload: AdminCreationCancelPayload,
    context: MemoryContext,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle admin creation cancellation via callback button.
    
    Args:
        event: MessageCallback event from maxapi
        payload: AdminCreationCancelPayload
        context: MemoryContext for FSM state management
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"cancel_admin_creation_callback called: chat_id={chat_id}")
    
    # Delete old message
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    # Clear FSM state
    await context.clear()
    
    # Send cancellation message
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=ADMIN_CREATION_CANCELLED,
        parse_mode="HTML"
    )


async def cancel_admin_creation_command(
    event: MessageCreated,
    context: MemoryContext,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle admin creation cancellation via /cancel command.
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    
    logger.info(f"cancel_admin_creation_command called: chat_id={chat_id}")
    
    # Clear FSM state
    await context.clear()
    
    # Send cancellation message
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=ADMIN_CREATION_CANCELLED,
        parse_mode="HTML"
    )
