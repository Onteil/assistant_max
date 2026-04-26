"""
Invoice Request Handler for MAX Bot

Handles invoice request flow including:
- /invoice command to initiate flow
- Organization selection with pagination
- Key selection with multi-select toggle
- Description and delivery method collection
- Invoice ticket creation and manager notification

Requirements: 2.1-2.16
"""

import logging
from typing import Optional

from maxapi import F
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.callback_datas import DeliveryCallback, KeyCallback, OrganizationCallback
from bots.max_bot.payloads import (
    OrganizationSelectPayload,
    OrganizationPagePayload,
    OrganizationActionPayload,
    KeyTogglePayload,
    KeyPagePayload,
    KeyActionPayload,
    DeliveryMethodPayload,
    EmailConfirmPayload,
    InvoiceDescriptionNextPayload,
)
from bots.max_bot.keyboards.tickets.invoice_kb import (
    get_delivery_keyboard,
    get_description_input_keyboard,
    get_email_confirm_keyboard,
    get_email_input_keyboard,
    get_invoice_confirmation_keyboard,
    get_key_selection_keyboard,
    get_organization_keyboard,
)
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.states import InvoiceStates
from bots.max_bot.texts import (
    ERROR_GENERAL,
    ERROR_TEXT_TOO_LONG,
    ERROR_VALIDATION_EMAIL,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    FLOW_CANCELLED,
    INVOICE_ADD_NEW_INN,
    INVOICE_CONFIRMATION,
    INVOICE_CONFIRM_EMAIL,
    INVOICE_CREATED,
    INVOICE_CREATED_NO_MANAGER,
    INVOICE_ENTER_DESCRIPTION,
    INVOICE_ENTER_EMAIL,
    INVOICE_INN_ADDED,
    INVOICE_INN_DUPLICATE,
    INVOICE_KEY_ADDED,
    INVOICE_KEY_CONFLICT,
    get_invoice_non_working_hours_message,
    INVOICE_RESPONSE_TIME_WORKING,
    INVOICE_SELECT_DELIVERY,
    INVOICE_SELECT_KEYS,
    INVOICE_SELECT_ORGANIZATION,
)
from database.models import DeliveryMethod, KeyConflictStatus, RegistrationStatus, Ticket, TicketType, User
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
from services.validation_service import validate_email, validate_gs_key, validate_inn

logger = logging.getLogger(__name__)


# ========== Helper Functions ==========


async def get_user_id_with_fallback(
    context: MemoryContext,
    max_user_id: int,
    session: AsyncSession,
    chat_id: int,
    messenger_adapter: MAXMessengerAdapter
) -> Optional[int]:
    """
    Get user_id from FSM context with database fallback.
    
    First tries to get user_id from FSM context. If not found,
    queries database using MAX user ID and restores context.
    
    Args:
        context: FSM context
        max_user_id: MAX messenger user ID
        session: Database session
        chat_id: Chat ID for error messages
        messenger_adapter: Messenger adapter for error messages
    
    Returns:
        User ID (database primary key) or None if user not found
    """
    # Try to get from context first
    data = await context.get_data()
    user_id = data.get("user_id")
    
    if user_id:
        return user_id
    
    # Fallback: get from database
    logger.warning(f"No user_id in context, trying database lookup: chat_id={chat_id}, max_user_id={max_user_id}")
    user = await get_user_by_max_id(session, max_user_id)
    
    if not user:
        logger.error(f"User not found in database: max_user_id={max_user_id}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Пользователь не найден. Пожалуйста, пройдите регистрацию командой /start",
            parse_mode="HTML"
        )
        await context.clear()
        return None
    
    # Restore context data for the flow
    await context.update_data(
        user_id=user.id,
        selected_inn=None,
        selected_keys=[],
        description=None,
        attachments=[],
        delivery_method=None,
        delivery_email=None
    )
    await context.set_state(InvoiceStates.selecting_organization)
    
    return user.id


async def get_user_id_with_fallback_from_message(
    context: MemoryContext,
    event: MessageCreated,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> Optional[int]:
    """
    Get user_id from FSM context with database fallback for message handlers.
    
    Args:
        context: FSM context
        event: Message event from MAX
        session: Database session
        messenger_adapter: Messenger adapter for error messages
    
    Returns:
        User ID (database primary key) or None if user not found
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    return await get_user_id_with_fallback(
        context=context,
        max_user_id=max_user_id,
        session=session,
        chat_id=chat_id,
        messenger_adapter=messenger_adapter
    )


# ========== /invoice Command Handler ==========


async def cmd_invoice(
    event: MessageCreated | MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /invoice command or callback - initiate invoice request flow.
    
    Displays organization selection with pagination (7 per page).
    User can select existing organization, add new INN, or skip.
    
    Args:
        event: Message or callback event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    commands_info: Запросить счет на оплату
    
    Requirements: 2.1
    """
    chat_id = event.message.recipient.chat_id
    # Get user_id based on event type (MessageCreated uses sender, MessageCallback uses callback.user)
    from maxapi.types import MessageCallback as MCType
    if isinstance(event, MCType):
        max_user_id = event.callback.user.user_id
    else:
        max_user_id = event.message.sender.user_id
    
    logger.info(f"User initiated invoice request: max_user_id={max_user_id}, chat_id={chat_id}")
    
    try:
        # Get user from database
        user = await get_user_by_max_id(session, max_user_id)
        
        if not user:
            logger.error(f"User not found for invoice request: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден. Пожалуйста, пройдите регистрацию командой /start",
                parse_mode="HTML"
            )
            return
        
        # Initialize FSM context
        await context.update_data(
            user_id=user.id,
            selected_inn=None,
            selected_keys=[],
            description=None,
            attachments=[],
            delivery_method=None,
            delivery_email=None
        )
        
        # Set FSM state
        await context.set_state(InvoiceStates.selecting_organization)
        
        # Show organization selection
        await show_organization_selection(
            chat_id=chat_id,
            user_id=user.id,
            page=0,
            session=session,
            messenger_adapter=messenger_adapter
        )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in cmd_invoice: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Unexpected error in cmd_invoice: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def show_organization_selection(
    chat_id: int,
    user_id: int,
    page: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    message_id: Optional[int] = None
) -> None:
    """
    Display organization selection with pagination.
    
    Shows user's existing organizations with inline keyboard.
    Includes pagination (7 per page), add new, skip, and cancel buttons.
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID (primary key)
        page: Current page number (0-indexed)
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        message_id: Optional message ID for editing (instead of sending new)
    
    Requirements: 2.2, 2.3
    """
    logger.info(f"Showing organization selection: user_id={user_id}, page={page}")
    
    try:
        # Get user organizations
        organizations = await get_user_organizations(session, user_id)
        
        # Build keyboard
        keyboard = get_organization_keyboard(organizations, page)
        
        # Send or edit message with keyboard
        if message_id:
            await messenger_adapter.edit_message(
                chat_id=chat_id,
                message_id=message_id,
                text=INVOICE_SELECT_ORGANIZATION,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_SELECT_ORGANIZATION,
                keyboard=keyboard,
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(
            f"Error showing organization selection: user_id={user_id}, page={page}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


# ========== Organization Callback Handlers ==========


async def handle_organization_select_callback(
    event: MessageCallback,
    payload: OrganizationSelectPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle organization selection by INN.
    
    Stores the selected INN and proceeds to key selection.
    
    Args:
        event: Callback event from MAX
        payload: Parsed organization selection payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.3
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Organization selected: chat_id={chat_id}, inn={payload.inn}, message_id={message_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback(
            context=context,
            max_user_id=user_id_from_callback,
            session=session,
            chat_id=chat_id,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        # Store selected INN and proceed to key selection
        await context.update_data(selected_inn=payload.inn)
        await context.set_state(InvoiceStates.selecting_keys)
        
        # Show key selection
        await show_key_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=set(),
            page=0,
            session=session,
            messenger_adapter=messenger_adapter,
            message_id=None
        )
    
    except Exception as e:
        logger.error(
            f"Error handling organization selection: inn={payload.inn}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_organization_page_callback(
    event: MessageCallback,
    payload: OrganizationPagePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle organization list pagination.
    
    Navigates to a different page of organizations.
    
    Args:
        event: Callback event from MAX
        payload: Parsed organization pagination payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.3
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Organization pagination: chat_id={chat_id}, page={payload.page}, message_id={message_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback(
            context=context,
            max_user_id=user_id_from_callback,
            session=session,
            chat_id=chat_id,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        # Show organization selection for the requested page
        await show_organization_selection(
            chat_id=chat_id,
            user_id=user_id,
            page=payload.page,
            session=session,
            messenger_adapter=messenger_adapter,
            message_id=None
        )
    
    except Exception as e:
        logger.error(
            f"Error handling organization pagination: page={payload.page}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_organization_action_callback(
    event: MessageCallback,
    payload: OrganizationActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle organization-related actions (add_new, skip, cancel).
    
    Actions:
    - add_new: Prompt for new INN input
    - skip: Proceed to key selection without organization
    - cancel: Cancel invoice flow
    
    Args:
        event: Callback event from MAX
        payload: Parsed organization action payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.4, 2.5
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Organization action: chat_id={chat_id}, action={payload.action}, message_id={message_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback(
            context=context,
            max_user_id=user_id_from_callback,
            session=session,
            chat_id=chat_id,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        if payload.action == "add_new":
            # Prompt for new INN input
            logger.info(f"User adding new INN: user_id={user_id}")
            
            await context.set_state(InvoiceStates.adding_new_inn)
            
            # Import cancel keyboard
            from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_ADD_NEW_INN,
                keyboard=get_cancel_keyboard(),
                parse_mode="HTML"
            )
        
        elif payload.action == "skip":
            # Proceed to key selection without organization
            logger.info(f"User skipped organization selection: user_id={user_id}")
            
            await context.update_data(selected_inn=None)
            await context.set_state(InvoiceStates.selecting_keys)
            
            # Show key selection
            await show_key_selection(
                chat_id=chat_id,
                user_id=user_id,
                selected_keys=set(),
                page=0,
                session=session,
                messenger_adapter=messenger_adapter,
                message_id=None
            )
        
        elif payload.action == "cancel":
            # Cancel invoice flow
            logger.info(f"User cancelled invoice flow: user_id={user_id}")
            await cancel_invoice_flow(event, context, session, messenger_adapter)
    
    except Exception as e:
        logger.error(
            f"Error handling organization action: action={payload.action}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_new_inn(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process new INN input, validate, add to user organizations.
    
    Validates INN format (10 or 12 digits).
    Adds organization to user profile.
    Proceeds to key selection.
    
    Args:
        event: Message event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.4, 2.5
    """
    chat_id = event.message.recipient.chat_id
    inn = event.message.body.text.strip()
    
    logger.info(f"Processing new INN: chat_id={chat_id}, inn={inn}")
    
    # Validate INN format
    is_valid, error_msg = validate_inn(inn)
    
    if not is_valid:
        logger.warning(f"Invalid INN format: inn={inn}, error={error_msg}")
        from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_INN.format(error_details=error_msg),
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Check for duplicate INN before calling i-TAT API
    max_user_id = event.message.sender.user_id
    user_id_for_check = await get_user_id_with_fallback_from_message(
        context=context,
        event=event,
        session=session,
        messenger_adapter=messenger_adapter
    )
    if user_id_for_check:
        existing_organizations = await get_user_organizations(session, user_id_for_check)
        existing_inns = [org.inn for org in existing_organizations]
        if inn in existing_inns:
            logger.info(f"Duplicate INN detected locally: user_id={user_id_for_check}, inn={inn}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_INN_DUPLICATE,
                parse_mode="HTML"
            )
            # Treat as if INN was just added — proceed to key selection
            await context.update_data(selected_inn=inn)
            await context.set_state(InvoiceStates.selecting_keys)
            await show_key_selection(
                chat_id=chat_id,
                user_id=user_id_for_check,
                selected_keys=set(),
                page=0,
                session=session,
                messenger_adapter=messenger_adapter
            )
            return

    # Check INN with i-TAT API
    from services.i_tat_service import get_itat_client
    try:
        # Get max_user_id from event for API call
        max_user_id = event.message.sender.user_id
        
        itat_client = get_itat_client()
        api_response = await itat_client.check_inn(
            messenger="max",
            user_id=max_user_id,
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
            await context.set_state(InvoiceStates.adding_org_name)
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
            from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Ошибка проверки ИНН</b>\n\n{error_details}\n\nПроверьте правильность введенного ИНН и попробуйте снова.",
                keyboard=get_cancel_keyboard(),
                parse_mode="HTML"
            )
            return
            
    except Exception as api_error:
        logger.error(f"i-TAT API INN check error: {api_error}", exc_info=True)
        organization_name = None
        # Show error to testers for debugging
        error_type = type(api_error).__name__
        error_msg = str(api_error)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"⚠️ <b>Ошибка проверки ИНН через i-TAT API</b>\n\n"
                 f"<b>Метод:</b> POST /assets/check_inn\n"
                 f"<b>Тип ошибки:</b> {error_type}\n"
                 f"<b>Детали:</b> {error_msg}\n\n"
                 f"<i>Продолжаем с локальной валидацией...</i>",
            parse_mode="HTML"
        )
        # Continue with local validation if API fails
        logger.info(f"Continuing with local INN validation due to API error")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback_from_message(
            context=context,
            event=event,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        # Get user to access max_user_id for API calls
        user = await get_user_by_id(session, user_id)
        if not user:
            logger.error(f"User not found: user_id={user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            return
        
        # Add organization to user profile
        await add_user_organization(session, user_id, inn, organization_name=organization_name)
        
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
            logger.warning(f"update_user_assets queued for retry: user_id={user.id}, inn={inn}")
        
        await session.commit()
        
        logger.info(f"Organization added: user_id={user_id}, inn={inn}")
        
        # Store INN in context
        await context.update_data(selected_inn=inn)
        
        # Transition to key selection state
        await context.set_state(InvoiceStates.selecting_keys)
        
        # Show key selection
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_INN_ADDED,
            parse_mode="HTML"
        )
        
        await show_key_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=set(),
            page=0,
            session=session,
            messenger_adapter=messenger_adapter
        )
    
    except IntegrityError as e:
        logger.warning(
            f"Organization already exists: user_id={user_id}, inn={inn}, error={e}",
            exc_info=True
        )
        await session.rollback()
        # Continue anyway - organization already associated
        await context.update_data(selected_inn=inn)
        await context.set_state(InvoiceStates.selecting_keys)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_INN_ADDED,
            parse_mode="HTML"
        )
        
        await show_key_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=set(),
            page=0,
            session=session,
            messenger_adapter=messenger_adapter
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


async def process_invoice_org_name(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process optional org name input after INN not found in 1C (invoice flow).
    Saves INN + name, then proceeds to key selection.
    """
    chat_id = event.message.recipient.chat_id
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

    await _finalize_invoice_inn(chat_id, inn, org_name, context, session, messenger_adapter, event)


async def skip_invoice_org_name(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle skip button during org name step in invoice flow.
    Saves INN without a name and proceeds to key selection.
    """
    chat_id = event.message.recipient.chat_id
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

    await _finalize_invoice_inn(chat_id, inn, None, context, session, messenger_adapter, event)


async def _finalize_invoice_inn(
    chat_id: int,
    inn: str,
    organization_name: str | None,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    event,
) -> None:
    """Save INN (with optional name), call update_user_assets, proceed to key selection."""
    try:
        user_id = await get_user_id_with_fallback_from_message(
            context=context,
            event=event,
            session=session,
            messenger_adapter=messenger_adapter
        )
        if not user_id:
            return

        user = await get_user_by_id(session, user_id)
        if not user:
            await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
            return

        await add_user_organization(session, user_id, inn, organization_name=organization_name)

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

        await session.commit()
        logger.info(f"Organization added (invoice): user_id={user_id}, inn={inn}, name={organization_name}")

        await context.update_data(selected_inn=inn)
        await context.set_state(InvoiceStates.selecting_keys)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_INN_ADDED,
            parse_mode="HTML"
        )
        await show_key_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=set(),
            page=0,
            session=session,
            messenger_adapter=messenger_adapter
        )

    except IntegrityError:
        await session.rollback()
        await context.update_data(selected_inn=inn)
        await context.set_state(InvoiceStates.selecting_keys)
        await messenger_adapter.send_message(chat_id=chat_id, text=INVOICE_INN_ADDED, parse_mode="HTML")
        await show_key_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=set(),
            page=0,
            session=session,
            messenger_adapter=messenger_adapter
        )

    except SQLAlchemyError as e:
        logger.error(f"Database error in _finalize_invoice_inn: inn={inn}, error={e}", exc_info=True)
        await session.rollback()
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


# ========== Key Selection Handlers ==========


async def show_key_selection(
    chat_id: int,
    user_id: int,
    selected_keys: set[int],
    page: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    message_id: Optional[int] = None
) -> None:
    """
    Display key selection with multi-select toggle and pagination.
    
    Shows user's GS_Keys with checkmarks for selected items.
    Prevents selection of PENDING_REVIEW keys with warning.
    
    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID (primary key)
        selected_keys: Set of selected key IDs
        page: Current page number (0-indexed)
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        message_id: Optional message ID for editing (instead of sending new)
    
    Requirements: 2.6, 2.7, 2.8
    """
    logger.info(f"Showing key selection: user_id={user_id}, page={page}, selected={len(selected_keys)}")
    
    try:
        # Get user keys
        keys = await get_user_keys(session, user_id)
        
        # Build keyboard
        keyboard = get_key_selection_keyboard(keys, selected_keys, page)
        
        # Send or edit message
        if message_id:
            await messenger_adapter.edit_message(
                chat_id=chat_id,
                message_id=message_id,
                text=INVOICE_SELECT_KEYS,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_SELECT_KEYS,
                keyboard=keyboard,
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(
            f"Error showing key selection: user_id={user_id}, page={page}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_key_toggle_callback(
    event: MessageCallback,
    payload: KeyTogglePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle key toggle callback (select/deselect a key).
    
    Updates the selection state and refreshes the keyboard.
    
    Args:
        event: Callback event from MAX
        payload: Parsed key toggle payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.6
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Key toggle: chat_id={chat_id}, key_id={payload.key_id}, message_id={message_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback(
            context=context,
            max_user_id=user_id_from_callback,
            session=session,
            chat_id=chat_id,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        # Get selected keys from context
        data = await context.get_data()
        selected_keys = set(data.get("selected_keys", []))
        
        # Get key to check conflict status
        keys = await get_user_keys(session, user_id)
        key = next((k for k in keys if k.id == payload.key_id), None)
        
        if not key:
            logger.error(f"Key not found: key_id={payload.key_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            return
        
        # Prevent selection of PENDING_REVIEW keys
        if key.conflict_status == KeyConflictStatus.PENDING_REVIEW:
            logger.warning(f"Attempted to select PENDING_REVIEW key: key_id={payload.key_id}")
            return
        
        # Toggle selection
        if payload.key_id in selected_keys:
            selected_keys.remove(payload.key_id)
            logger.info(f"Key deselected: key_id={payload.key_id}")
        else:
            selected_keys.add(payload.key_id)
            logger.info(f"Key selected: key_id={payload.key_id}")
        
        # Update context
        await context.update_data(selected_keys=list(selected_keys))
        
        # Refresh keyboard
        await show_key_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=selected_keys,
            page=0,
            session=session,
            messenger_adapter=messenger_adapter,
            message_id=None
        )
    
    except Exception as e:
        logger.error(
            f"Error handling key toggle: key_id={payload.key_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_key_page_callback(
    event: MessageCallback,
    payload: KeyPagePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle key list pagination.
    
    Navigates to a different page of keys.
    
    Args:
        event: Callback event from MAX
        payload: Parsed key pagination payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.6
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Key pagination: chat_id={chat_id}, page={payload.page}, message_id={message_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback(
            context=context,
            max_user_id=user_id_from_callback,
            session=session,
            chat_id=chat_id,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        # Get selected keys from context
        data = await context.get_data()
        selected_keys = set(data.get("selected_keys", []))
        
        # Show key selection for the requested page
        await show_key_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=selected_keys,
            page=payload.page,
            session=session,
            messenger_adapter=messenger_adapter,
            message_id=None
        )
    
    except Exception as e:
        logger.error(
            f"Error handling key pagination: page={payload.page}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_key_action_callback(
    event: MessageCallback,
    payload: KeyActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle key-related actions (add_new, done, skip, back, back_to_keys, skip_description, cancel).
    
    Actions:
    - add_new: Prompt for new key input
    - done: Proceed to description with selected keys
    - skip: Proceed to description without keys
    - back: Return to organization selection
    - back_to_keys: Return to key selection (from description input)
    - skip_description: Skip description and proceed to delivery selection
    - cancel: Cancel invoice flow
    
    Args:
        event: Callback event from MAX
        payload: Parsed key action payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.7, 2.8, 2.9
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Key action: chat_id={chat_id}, action={payload.action}, message_id={message_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback(
            context=context,
            max_user_id=user_id_from_callback,
            session=session,
            chat_id=chat_id,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        # Get selected keys from context
        data = await context.get_data()
        selected_keys = set(data.get("selected_keys", []))
        
        if payload.action == "add_new":
            # Prompt for new key input
            logger.info(f"User adding new key: user_id={user_id}")
            
            await context.set_state(InvoiceStates.adding_new_key)
            
            # Import cancel keyboard
            from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="🔑 Введите новый ключ Гранд-сметы (формат: 00001_00011):",
                keyboard=get_cancel_keyboard(),
                parse_mode="HTML"
            )
        
        elif payload.action == "done":
            # Proceed to description with selected keys
            logger.info(f"User completed key selection: user_id={user_id}, keys={len(selected_keys)}")
            
            await context.set_state(InvoiceStates.entering_description)
            
            # Check if user already has content from a previous visit to this step
            ctx_data = await context.get_data()
            has_content = bool(ctx_data.get("description")) or bool(ctx_data.get("attachments"))
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_ENTER_DESCRIPTION,
                keyboard=get_description_input_keyboard(has_content=has_content),
                parse_mode="HTML"
            )
        
        elif payload.action == "skip":
            # Proceed to description without keys
            logger.info(f"User skipped key selection: user_id={user_id}")
            
            await context.update_data(selected_keys=[])
            await context.set_state(InvoiceStates.entering_description)
            
            # Check if user already has content from a previous visit to this step
            ctx_data = await context.get_data()
            has_content = bool(ctx_data.get("description")) or bool(ctx_data.get("attachments"))
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_ENTER_DESCRIPTION,
                keyboard=get_description_input_keyboard(has_content=has_content),
                parse_mode="HTML"
            )
        
        elif payload.action == "back":
            # Return to organization selection
            logger.info(f"User returned to organization selection: user_id={user_id}")
            
            await context.set_state(InvoiceStates.selecting_organization)
            
            await show_organization_selection(
                chat_id=chat_id,
                user_id=user_id,
                page=0,
                session=session,
                messenger_adapter=messenger_adapter,
                message_id=None
            )
        
        elif payload.action == "back_to_keys":
            # Return to key selection (from description input)
            logger.info(f"User returned to key selection: user_id={user_id}")
            
            await context.set_state(InvoiceStates.selecting_keys)
            
            await show_key_selection(
                chat_id=chat_id,
                user_id=user_id,
                selected_keys=selected_keys,
                page=0,
                session=session,
                messenger_adapter=messenger_adapter,
                message_id=None
            )
        
        elif payload.action == "skip_description":
            # Skip description and proceed to delivery selection
            logger.info(f"User skipped description: user_id={user_id}")
            
            await context.update_data(description="Без описания")
            await context.set_state(InvoiceStates.selecting_delivery)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_SELECT_DELIVERY,
                keyboard=get_delivery_keyboard(),
                parse_mode="HTML"
            )
        
        elif payload.action == "cancel":
            # Cancel invoice flow
            logger.info(f"User cancelled invoice flow: user_id={user_id}")
            await cancel_invoice_flow(event, context, session, messenger_adapter)
    
    except Exception as e:
        logger.error(
            f"Error handling key action: action={payload.action}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def cancel_add_new_inn(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle cancel button when user is adding a new INN.
    
    Returns user to organization selection screen.
    
    Args:
        event: Callback event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.4
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"User cancelled adding new INN: chat_id={chat_id}, message_id={message_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback(
            context=context,
            max_user_id=user_id_from_callback,
            session=session,
            chat_id=chat_id,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        # Return to organization selection state
        await context.set_state(InvoiceStates.selecting_organization)
        
        # Show organization selection
        await show_organization_selection(
            chat_id=chat_id,
            user_id=user_id,
            page=0,
            session=session,
            messenger_adapter=messenger_adapter,
            message_id=None
        )
    
    except Exception as e:
        logger.error(
            f"Error cancelling add new INN: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def cancel_add_new_key(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle cancel button when user is adding a new key.
    
    Returns user to key selection screen with current selections preserved.
    
    Args:
        event: Callback event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.9
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"User cancelled adding new key: chat_id={chat_id}, message_id={message_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback(
            context=context,
            max_user_id=user_id_from_callback,
            session=session,
            chat_id=chat_id,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        # Get selected keys from context
        data = await context.get_data()
        selected_keys = set(data.get("selected_keys", []))
        
        # Return to key selection state
        await context.set_state(InvoiceStates.selecting_keys)
        
        # Show key selection with current selections
        await show_key_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=selected_keys,
            page=0,
            session=session,
            messenger_adapter=messenger_adapter,
            message_id=None
        )
    
    except Exception as e:
        logger.error(
            f"Error cancelling add new key: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_new_key(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process new key input, validate format, check conflicts.
    
    Validates GS_Key format (XXXXX_XXXXX).
    Checks for key conflicts via i-TAT API.
    Adds key to user profile.
    Returns to key selection.
    
    Args:
        event: Message event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.9
    """
    data = await context.get_data()
    chat_id = event.message.recipient.chat_id
    key_number = event.message.body.text.strip()
    
    logger.info(f"Processing new key: chat_id={chat_id}, key={key_number}")
    
    # Validate GS_Key format
    is_valid, result = validate_gs_key(key_number)
    
    if not is_valid:
        logger.warning(f"Invalid GS_Key: key={key_number}, error={result}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_KEY.format(error_details=result),
            parse_mode="HTML"
        )
        return
    
    normalized_key = result
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback_from_message(
            context=context,
            event=event,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        # Get user to access max_user_id for API calls
        user = await get_user_by_id(session, user_id)
        if not user:
            logger.error(f"User not found: user_id={user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
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
        
        conflict_status = KeyConflictStatus.NONE
        if conflict_response.get("status") == "conflict":
            conflict_status = KeyConflictStatus.PENDING_REVIEW
            owner_info = conflict_response.get("owner", "Неизвестный владелец")
            logger.warning(f"Key conflict detected: key={normalized_key}, owner={owner_info}")
        
        # Add key to user profile
        await add_user_key(session, user_id, normalized_key, conflict_status)
        
        # Update user assets via i-TAT API (only if no conflict)
        if conflict_status == KeyConflictStatus.NONE:
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
                logger.warning(f"update_user_assets queued for retry: user_id={user.id}, key={normalized_key}")

        await session.commit()
        
        logger.info(f"GS_Key added: user_id={user_id}, key={normalized_key}, conflict={conflict_status.value}")
        
        # Notify administrators if key conflict detected
        if conflict_status == KeyConflictStatus.PENDING_REVIEW:
            try:
                from bots.max_bot.utils.admin_notifications import notify_admins_key_conflict
                await notify_admins_key_conflict(session, user_id, normalized_key)
                logger.info(f"Key conflict notification sent for user_id={user_id}, key={normalized_key}")
            except Exception as notify_error:
                logger.error(
                    f"Failed to send key conflict notification for user_id={user_id}: {notify_error}",
                    exc_info=True
                )
        
        # Return to key selection state
        await context.set_state(InvoiceStates.selecting_keys)
        
        # Show confirmation
        if conflict_status == KeyConflictStatus.PENDING_REVIEW:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_KEY_CONFLICT,
                parse_mode="HTML"
            )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_KEY_ADDED,
                parse_mode="HTML"
            )
        
        # Show key selection again
        selected_keys = set(data.get("selected_keys", []))
        await show_key_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=selected_keys,
            page=0,
            session=session,
            messenger_adapter=messenger_adapter
        )
    
    except KeyAlreadyOwnedByUserError:
        logger.info(f"User tried to add their own key again: user_id={user_id if 'user_id' in dir() else '?'}, key={key_number}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="ℹ️ Этот ключ уже добавлен в ваш профиль. Вы не можете добавить свой же ключ повторно.",
            parse_mode="HTML"
        )
    except KeyConflictError as e:
        logger.warning(
            f"Key conflict (DB fallback) in invoice: key={key_number}, "
            f"owner_user_id={e.existing_user_id}"
        )
        await session.commit()
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_key_conflict
            await notify_admins_key_conflict(session, user_id, normalized_key)
        except Exception as notify_error:
            logger.error(f"Failed to send key conflict notification: {notify_error}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_KEY_CONFLICT,
            parse_mode="HTML"
        )
        # Return to key selection so user can continue
        await context.set_state(InvoiceStates.selecting_keys)
        selected_keys = set(data.get("selected_keys", []))
        await show_key_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=selected_keys,
            page=0,
            session=session,
            messenger_adapter=messenger_adapter
        )
    except Exception as e:
        logger.error(
            f"Error processing new key: key={key_number}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


# ========== Description and Delivery Handlers ==========


async def process_description(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process invoice description (text, photo, voice, document).
    
    Accumulates description and attachments in FSM context across multiple messages.
    Shows updated keyboard with "Далее" button after first message received.
    User must click "Далее" to proceed to delivery selection.
    
    Validates text length (max 2000 characters).
    Handles photo, voice, and document attachments.
    Stores description and attachments in FSM context.
    
    Args:
        event: Message event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.10, 2.11
    """
    chat_id = event.message.recipient.chat_id
    
    logger.info(f"Processing invoice description: chat_id={chat_id}")
    
    try:
        # Get existing attachments from context
        data = await context.get_data()
        attachments = data.get("attachments") or []
        has_description = bool(data.get("description"))
        
        # Handle text message
        if event.message.body and event.message.body.text:
            description = event.message.body.text.strip()
            
            # Validate text length
            if len(description) > 2000:
                logger.warning(f"Description too long: length={len(description)}")
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=ERROR_TEXT_TOO_LONG.format(max_length=2000, actual_length=len(description)),
                    keyboard=get_description_input_keyboard(has_content=has_description or bool(attachments)),
                    parse_mode="HTML"
                )
                return
            
            # Append to existing description (user may send multiple messages)
            existing_description = data.get("description") or ""
            combined = (existing_description + "\n" + description).strip() if existing_description else description
            await context.update_data(description=combined)
            has_description = True
            logger.info(f"Invoice description stored: chat_id={chat_id}, length={len(combined)}")
        
        # Handle attachments (photo, voice, document)
        if event.message.body and event.message.body.attachments:
            for attachment in event.message.body.attachments:
                logger.info(
                    f"Invoice description attachment: chat_id={chat_id}, "
                    f"type={attachment.type!r}, payload={attachment.payload!r}"
                )
                if attachment.type == "image":
                    photo_url = attachment.payload.url
                    caption = event.message.body.text if event.message.body else None
                    attachments.append({
                        "type": "image",
                        "url": photo_url,
                        "caption": caption
                    })
                    logger.info(f"Invoice photo attachment added: chat_id={chat_id}")
                
                elif attachment.type in ("voice", "audio_video_note"):
                    voice_url = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                    attachments.append({
                        "type": "voice",
                        "url": voice_url
                    })
                    logger.info(f"Invoice voice attachment added: chat_id={chat_id}, url={voice_url}")
                
                elif attachment.type == "audio":
                    audio_url = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                    attachments.append({
                        "type": "voice",
                        "url": audio_url
                    })
                    logger.info(f"Invoice audio attachment added: chat_id={chat_id}, url={audio_url}")
                
                elif attachment.type == "file":
                    file_url = attachment.payload.url
                    file_name = attachment.payload.name if hasattr(attachment.payload, 'name') else "document"
                    from services.validation_service import classify_file_type
                    file_type = classify_file_type(file_name)
                    attachments.append({
                        "type": "document",
                        "url": file_url,
                        "file_name": file_name,
                        "file_type": file_type.value
                    })
                    logger.info(f"Invoice document attachment added: chat_id={chat_id}, file={file_name}")
            
            logger.info(f"Saving attachments to context: chat_id={chat_id}, count={len(attachments)}, data={attachments}")
            await context.update_data(attachments=attachments)
        
        # Check if we received any content in this message
        has_content = has_description or bool(attachments)
        
        if has_content:
            # Show confirmation with updated keyboard (now with "Далее" button)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="✅ Принято. Можете добавить ещё сообщения или нажмите «Далее» для продолжения.",
                keyboard=get_description_input_keyboard(has_content=True),
                parse_mode="HTML"
            )
        else:
            # No content received yet — wait for input
            logger.info(f"No content received yet: chat_id={chat_id}")
    
    except Exception as e:
        logger.error(
            f"Error processing invoice description: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_invoice_description_next(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Далее" button click in invoice description step.

    Transitions to delivery selection state after user confirms
    they are done entering description and attachments.

    Requirements: 2.10, 2.11
    """
    chat_id = event.message.recipient.chat_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    logger.info(f"Invoice description next: chat_id={chat_id}")

    try:
        data = await context.get_data()
        description = data.get("description")
        attachments = data.get("attachments") or []

        if not description and not attachments:
            # Nothing accumulated — ask to enter something
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="⚠️ Пожалуйста, введите описание или прикрепите файл перед тем как продолжить.",
                keyboard=get_description_input_keyboard(has_content=False),
                parse_mode="HTML"
            )
            return

        # Delete old message with buttons
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete description message: {e}")

        # Transition to delivery selection state
        await context.set_state(InvoiceStates.selecting_delivery)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_SELECT_DELIVERY,
            keyboard=get_delivery_keyboard(),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(
            f"Error handling invoice description next: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_delivery_callback(
    event: MessageCallback,
    payload: DeliveryMethodPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle delivery method selection and confirmation callbacks.
    
    Delivery methods:
    - telegram: Proceed to confirmation
    - email: Prompt for email address
    - back: Return to description input
    - back_to_delivery: Return to delivery selection (from email input)
    - cancel: Cancel invoice flow
    
    Confirmation methods:
    - confirm: Create invoice ticket
    - restart: Return to organization selection
    - cancel: Cancel invoice flow
    
    Args:
        event: Callback event from MAX
        payload: Parsed delivery method payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.11, 2.12, 2.13, 2.14, 2.15
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Delivery callback: chat_id={chat_id}, method={payload.method}, message_id={message_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback(
            context=context,
            max_user_id=user_id_from_callback,
            session=session,
            chat_id=chat_id,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        # Handle delivery method selection
        if payload.method == "telegram":
            # Store delivery method and proceed to confirmation
            logger.info(f"Telegram delivery selected: user_id={user_id}")
            
            await context.update_data(
                delivery_method=DeliveryMethod.TELEGRAM,
                delivery_email=None
            )
            
            # Show confirmation
            await show_invoice_confirmation(chat_id, context, session, messenger_adapter)
        
        elif payload.method == "email":
            # Check if user has registered email
            logger.info(f"Email delivery selected: user_id={user_id}")
            
            # Get user from database to check for registered email
            user = await get_user_by_max_id(session, user_id_from_callback)
            
            if not user:
                logger.error(f"User not found: max_user_id={user_id_from_callback}")
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=ERROR_GENERAL,
                    parse_mode="HTML"
                )
                await context.clear()
                return
            
            await context.update_data(delivery_method=DeliveryMethod.EMAIL)
            
            # If user has registered email, ask for confirmation
            if user.email:
                logger.info(f"User has registered email: {user.email}")
                await context.set_state(InvoiceStates.confirming_email)
                
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=INVOICE_CONFIRM_EMAIL.format(email=user.email),
                    keyboard=get_email_confirm_keyboard(),
                    parse_mode="HTML"
                )
            else:
                # No registered email, prompt for input
                logger.info(f"User has no registered email, prompting for input")
                await context.set_state(InvoiceStates.entering_email)
                
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=INVOICE_ENTER_EMAIL,
                    keyboard=get_email_input_keyboard(),
                    parse_mode="HTML"
                )
        
        elif payload.method == "back":
            # Return to description input
            logger.info(f"User returned to description: user_id={user_id}")
            
            await context.set_state(InvoiceStates.entering_description)
            
            # Check if user already has content
            ctx_data = await context.get_data()
            has_content = bool(ctx_data.get("description")) or bool(ctx_data.get("attachments"))
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_ENTER_DESCRIPTION,
                keyboard=get_description_input_keyboard(has_content=has_content),
                parse_mode="HTML"
            )
        
        elif payload.method == "back_to_delivery":
            # Return to delivery selection (from email input)
            logger.info(f"User returned to delivery selection: user_id={user_id}")
            
            await context.set_state(InvoiceStates.selecting_delivery)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_SELECT_DELIVERY,
                keyboard=get_delivery_keyboard(),
                parse_mode="HTML"
            )
        
        # Handle confirmation callbacks
        elif payload.method == "confirm":
            # Create invoice ticket
            logger.info(f"User confirmed invoice: user_id={user_id}")
            await create_invoice_ticket(context, session, messenger_adapter, chat_id, user_id)
        
        elif payload.method == "restart":
            # Return to organization selection
            logger.info(f"User restarting invoice flow: user_id={user_id}")
            
            # Reset context data
            await context.update_data(
                selected_inn=None,
                selected_keys=[],
                description=None,
                delivery_method=None,
                delivery_email=None
            )
            
            await context.set_state(InvoiceStates.selecting_organization)
            
            await show_organization_selection(
                chat_id=chat_id,
                user_id=user_id,
                page=0,
                session=session,
                messenger_adapter=messenger_adapter,
                message_id=None
            )
        
        elif payload.method == "cancel":
            # Cancel invoice flow
            logger.info(f"User cancelled invoice flow: user_id={user_id}")
            await cancel_invoice_flow(event, context, session, messenger_adapter)
    
    except Exception as e:
        logger.error(
            f"Error handling delivery callback: method={payload.method}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_email_confirm_callback(
    event: MessageCallback,
    payload: EmailConfirmPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle email confirmation callback.
    
    Actions:
    - use_registered: Use email from registration, proceed to confirmation
    - enter_new: Prompt for new email address
    - cancel: Cancel invoice flow
    
    Args:
        event: Callback event from MAX
        payload: Parsed email confirmation payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.12
    """
    chat_id = event.message.recipient.chat_id
    user_id_from_callback = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Email confirm callback: chat_id={chat_id}, action={payload.action}, message_id={message_id}")
    
    # Delete old message with buttons
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback(
            context=context,
            max_user_id=user_id_from_callback,
            session=session,
            chat_id=chat_id,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        if payload.action == "use_registered":
            # Use registered email
            logger.info(f"User confirmed registered email: user_id={user_id}")
            
            # Get user from database
            user = await get_user_by_max_id(session, user_id_from_callback)
            
            if not user or not user.email:
                logger.error(f"User or email not found: max_user_id={user_id_from_callback}")
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=ERROR_GENERAL,
                    parse_mode="HTML"
                )
                return
            
            # Store email in context
            await context.update_data(delivery_email=user.email)
            
            # Show confirmation
            await show_invoice_confirmation(chat_id, context, session, messenger_adapter)
        
        elif payload.action == "enter_new":
            # Prompt for new email
            logger.info(f"User wants to enter new email: user_id={user_id}")
            
            await context.set_state(InvoiceStates.entering_email)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_ENTER_EMAIL,
                keyboard=get_email_input_keyboard(),
                parse_mode="HTML"
            )
        
        elif payload.action == "cancel":
            # Cancel invoice flow
            logger.info(f"User cancelled invoice flow: user_id={user_id}")
            await cancel_invoice_flow(event, context, session, messenger_adapter)
    
    except Exception as e:
        logger.error(
            f"Error handling email confirm callback: action={payload.action}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_email(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process email input, validate format, proceed to confirmation.
    
    Validates email format.
    Stores email in FSM context.
    Displays invoice confirmation.
    
    Args:
        event: Message event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.12
    """
    chat_id = event.message.recipient.chat_id
    email = event.message.body.text.strip()
    
    logger.info(f"Processing email: chat_id={chat_id}, email={email}")
    
    # Validate email format
    is_valid, error_msg = validate_email(email)
    
    if not is_valid:
        logger.warning(f"Invalid email: email={email}, error={error_msg}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_EMAIL.format(error_details=error_msg),
            keyboard=get_email_input_keyboard(),
            parse_mode="HTML"
        )
        return
    
    try:
        # Get user_id with fallback to database lookup
        user_id = await get_user_id_with_fallback_from_message(
            context=context,
            event=event,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        if not user_id:
            return  # Error already handled in helper function
        
        max_user_id = event.message.sender.user_id
        
        # Get user from database
        user = await get_user_by_max_id(session, max_user_id)
        
        if not user:
            logger.error(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            return
        
        # Store email in context
        await context.update_data(delivery_email=email)
        
        # Save email to database if user doesn't have one
        if not user.email:
            logger.info(f"Saving email to database: user_id={user.id}, email={email}")
            user.email = email
            await session.commit()
            logger.info(f"Email saved successfully: user_id={user.id}")
        
        # Show confirmation
        await show_invoice_confirmation(chat_id, context, session, messenger_adapter)
    
    except Exception as e:
        logger.error(
            f"Error processing email: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def _forward_attachments_to_staff(
    messenger_adapter: MAXMessengerAdapter,
    session: AsyncSession,
    ticket_id: int,
    staff_id: int,
    attachments: list,
    user_name: str
) -> None:
    """
    Forward FSM attachments (photo/voice/document) to a staff member's chat.
    
    Called after send_staff_notification to deliver files attached by the client
    during the invoice description step.
    
    Resolves chat_id via get_staff_chat_id (Staff_Member.max_chat_id first,
    then MAX_Messenger_Data fallback).
    """
    import uuid
    from pathlib import Path
    from bots.max_bot.utils.staff_chat_resolver import get_staff_chat_id
    
    if not attachments:
        return
    
    # Resolve chat_id with proper fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
    staff_chat_id = await get_staff_chat_id(session, staff_id)
    
    if not staff_chat_id:
        logger.warning(
            f"No MAX chat_id found for staff: staff_id={staff_id}, "
            f"skipping attachment forwarding for ticket_id={ticket_id}"
        )
        return
    
    caption = f"📎 Вложение к заявке #{ticket_id} от {user_name}"

    for attachment in attachments:
        att_type = attachment.get("type")
        file_url = attachment.get("url")

        if not file_url:
            continue

        try:
            temp_dir = Path("media/temp")
            temp_dir.mkdir(parents=True, exist_ok=True)

            if att_type == "image":
                # Images — download and send as photo
                unique_name = f"invoice_{ticket_id}_{uuid.uuid4()}.jpg"
                try:
                    local_path = await messenger_adapter.download_file(
                        file_url=file_url,
                        destination=f"media/temp/{unique_name}"
                    )
                    await messenger_adapter.send_photo(
                        chat_id=staff_chat_id,
                        photo_path=local_path,
                        caption=caption,
                        parse_mode="HTML"
                    )
                    try:
                        Path(local_path).unlink()
                    except Exception:
                        pass
                except Exception as img_error:
                    logger.error(f"Failed to send image: {img_error}")
                    # Fallback to link
                    notify_text = f"{caption}\n\n📷 <a href=\"{file_url}\">Скачать изображение</a>"
                    await messenger_adapter.send_message(
                        chat_id=staff_chat_id,
                        text=notify_text,
                        parse_mode="HTML"
                    )
            elif att_type == "voice":
                # Voice — download and send as document (same as client→manager pattern)
                unique_name = f"invoice_{ticket_id}_{uuid.uuid4()}.ogg"
                try:
                    local_path = await messenger_adapter.download_file(
                        file_url=file_url,
                        destination=f"media/temp/{unique_name}"
                    )
                    await messenger_adapter.send_document(
                        chat_id=staff_chat_id,
                        document_path=local_path,
                        caption=caption,
                        parse_mode="HTML"
                    )
                    try:
                        Path(local_path).unlink()
                    except Exception:
                        pass
                except Exception as voice_error:
                    logger.error(f"Failed to send voice: {voice_error}")
                    # Fallback to link
                    notify_text = f"{caption}\n\n🎤 <a href=\"{file_url}\">Голосовое сообщение</a>"
                    await messenger_adapter.send_message(
                        chat_id=staff_chat_id,
                        text=notify_text,
                        parse_mode="HTML"
                    )
            else:
                # Documents/files — send link to avoid .bin filename issues
                notify_text = f"{caption}\n\n📎 <a href=\"{file_url}\">Скачать файл</a>"
                await messenger_adapter.send_message(
                    chat_id=staff_chat_id,
                    text=notify_text,
                    parse_mode="HTML"
                )

            logger.info(
                f"Invoice attachment forwarded to staff: ticket_id={ticket_id}, "
                f"staff_chat_id={staff_chat_id}, type={att_type}"
            )

        except Exception as e:
            logger.error(
                f"Failed to forward invoice attachment to staff: ticket_id={ticket_id}, "
                f"type={att_type}, error={e}",
                exc_info=True
            )


# ========== Confirmation and Ticket Creation ==========


async def show_invoice_confirmation(
    chat_id: int,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display confirmation summary with all invoice details.
    
    Shows organization, keys, description, and delivery method.
    Provides confirm, restart, and cancel buttons.
    
    Args:
        chat_id: Chat ID for sending messages
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.13
    """
    logger.info(f"Showing invoice confirmation: chat_id={chat_id}")
    
    try:
        # Get data from context
        data = await context.get_data()
        user_id = data.get("user_id")
        selected_inn = data.get("selected_inn")
        selected_keys = data.get("selected_keys", [])
        description = data.get("description")
        attachments = data.get("attachments") or []
        delivery_method = data.get("delivery_method")
        delivery_email = data.get("delivery_email")
        
        # Build confirmation message with emoji and formatting
        confirmation_text = "📋 <b>Подтверждение заявки на счет</b>\n\n"
        
        # Organization(s) - formatted as numbered list if multiple
        if selected_inn:
            # Check if there are multiple organizations (comma-separated)
            orgs = [org.strip() for org in selected_inn.split(',') if org.strip()]
            if len(orgs) > 1:
                confirmation_text += "🏢 <b>Организации:</b>\n"
                for idx, org in enumerate(orgs, 1):
                    confirmation_text += f"   {idx}. {org}\n"
            else:
                confirmation_text += f"🏢 <b>Организация:</b> {selected_inn}\n"
        else:
            confirmation_text += "🏢 <b>Организация:</b> Не указана\n"
        
        # GS Keys - formatted as numbered list if multiple
        if selected_keys:
            # Get key details
            keys = await get_user_keys(session, user_id)
            key_numbers = [k.key_number for k in keys if k.id in selected_keys]
            if len(key_numbers) > 1:
                confirmation_text += "🔑 <b>Ключи ГС:</b>\n"
                for idx, key_num in enumerate(key_numbers, 1):
                    confirmation_text += f"   {idx}. {key_num}\n"
            else:
                confirmation_text += f"🔑 <b>Ключ ГС:</b> {key_numbers[0]}\n"
        else:
            confirmation_text += "🔑 <b>Ключи:</b> Не указаны\n"
        
        # Description
        if description and description.strip() and description.strip() != "Без описания":
            confirmation_text += f"\n📝 <b>Описание:</b>\n{description}\n"
        else:
            confirmation_text += "\n📝 <b>Описание:</b> Без описания\n"
        
        # Attachments
        if attachments:
            att_types = {"image": "🖼 фото", "voice": "🎤 голосовое", "document": "📄 файл"}
            att_summary = ", ".join(
                att_types.get(a.get("type", ""), "файл") for a in attachments
            )
            confirmation_text += f"📎 <b>Вложения:</b> {len(attachments)} ({att_summary})\n"
        
        # Delivery method
        if delivery_method == DeliveryMethod.TELEGRAM:
            confirmation_text += "\n📦 <b>Способ доставки:</b> 💬 В чат\n"
        elif delivery_method == DeliveryMethod.EMAIL:
            confirmation_text += f"\n📦 <b>Способ доставки:</b> 📧 На Email\n"
            confirmation_text += f"   └─ <b>Email:</b> {delivery_email}\n"
        
        confirmation_text += "\n✅ <b>Подтвердите заявку или заполните заново.</b>"
        
        # Send confirmation
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=confirmation_text,
            keyboard=get_invoice_confirmation_keyboard(),
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Error showing invoice confirmation: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )




async def create_invoice_ticket(
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    chat_id: int,
    user_id: int
) -> None:
    """
    Create INVOICE ticket, route to assigned manager, send notification.
    
    Creates ticket with all collected data.
    Routes ticket to assigned manager based on organization.
    Sends notification to manager via adapter.
    Displays success message to user.
    
    Args:
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        chat_id: Chat ID for sending messages
        user_id: Internal user ID (primary key)
    
    Requirements: 2.14, 2.15
    """
    logger.info(f"Creating invoice ticket: user_id={user_id}")
    
    try:
        # Get data from context
        data = await context.get_data()
        selected_inn = data.get("selected_inn")
        selected_keys = data.get("selected_keys", [])
        description = data.get("description")
        attachments = data.get("attachments") or []
        delivery_method = data.get("delivery_method")
        delivery_email = data.get("delivery_email")
        
        # Get user to determine assigned manager
        user = await get_user_by_id(session, user_id)
        if not user:
            logger.error(f"User not found for ticket creation: user_id={user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Determine assigned manager (with admin fallback if no manager)
        from services.ticket_service import determine_assigned_manager
        
        assigned_staff_id, has_manager = await determine_assigned_manager(
            session=session,
            user_id=user_id,
            assign_admin_if_no_manager=True  # Auto-assign admin if no manager
        )
        
        # Create ticket
        ticket_data = {
            "ticket_type": TicketType.INVOICE,
            "user_id": user_id,
            "assigned_staff_id": assigned_staff_id,
            "organization_inn": selected_inn,
            "description": description,
            "delivery_method": delivery_method,
            "delivery_email": delivery_email,
            "selected_key_ids": selected_keys
        }
        
        ticket = await create_ticket(session, ticket_data)
        await session.commit()
        
        logger.info(
            f"Invoice ticket created: ticket_id={ticket.id}, user_id={user_id}, "
            f"assigned_staff={assigned_staff_id}, has_manager={has_manager}"
        )
        
        # Save description and attachments to DB so they appear in ticket history
        # and Celery queue task can forward attachments in non-working hours
        if description or attachments:
            logger.info(
                f"Calling save_initial_ticket_attachments: ticket_id={ticket.id}, "
                f"user_id={user_id}, attachments_count={len(attachments)}, has_description={bool(description)}"
            )
            try:
                from services.ticket_service import save_initial_ticket_attachments
                await save_initial_ticket_attachments(
                    session=session,
                    ticket_id=ticket.id,
                    user_id=user_id,
                    attachments=attachments,
                    description=description,
                )
                await session.commit()
                logger.info(f"Successfully saved and committed ticket data for ticket_id={ticket.id}")
            except Exception as e:
                logger.error(
                    f"Failed to save initial ticket data for invoice ticket: "
                    f"ticket_id={ticket.id}, error={e}",
                    exc_info=True
                )
        
        # Log ticket creation to I-TAT API
        try:
            from bots.max_bot.utils.itat_logging import log_ticket_creation_to_itat
            await log_ticket_creation_to_itat(session, ticket)
        except Exception as e:
            # Log error but don't fail ticket creation
            logger.error(
                f"Failed to log invoice ticket to I-TAT API: ticket_id={ticket.id}, error={e}",
                exc_info=True
            )
        
        # Clear FSM state
        await context.clear()
        
        # Get manager name, position and response time message
        manager_name = "Менеджер"
        manager_position = "Менеджер"
        if has_manager and assigned_staff_id:
            from database.models import Staff_Member
            from sqlalchemy import select
            
            stmt = select(Staff_Member).where(Staff_Member.id == assigned_staff_id)
            result = await session.execute(stmt)
            staff_member = result.scalar_one_or_none()
            
            if staff_member:
                manager_name = staff_member.full_name or "Менеджер"
                manager_position = staff_member.position or "Менеджер"
        
        # Determine response time message based on working hours
        from services.calendar_service import get_current_work_mode
        from database.models import WorkMode
        from datetime import datetime
        
        work_mode = await get_current_work_mode(session)
        is_working = work_mode != WorkMode.NON_WORKING
        
        # Send success message to user
        # In NON_WORKING mode, show queue message instead of manager info
        if not is_working:
            # Non-working hours: show queue message
            from bots.max_bot.texts import get_invoice_non_working_hours_message
            message_text = get_invoice_non_working_hours_message()
        elif has_manager:
            # Working hours with assigned manager
            response_time_message = INVOICE_RESPONSE_TIME_WORKING
            message_text = INVOICE_CREATED.format(
                ticket_id=ticket.id,
                manager_name=manager_name,
                manager_position=manager_position,
                response_time_message=response_time_message
            )
        else:
            # Working hours without assigned manager
            response_time_message = INVOICE_RESPONSE_TIME_WORKING
            message_text = INVOICE_CREATED_NO_MANAGER.format(
                ticket_id=ticket.id,
                response_time_message=response_time_message
            )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode="HTML"
        )
        
        # Show main menu after successful ticket creation
        from services.ticket_service import get_user_active_tickets_count
        from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
        
        active_tickets_count = await get_user_active_tickets_count(session, user.id)
        keyboard = await get_main_menu_inline_keyboard(active_tickets_count, show_done_button=True)
        
        main_menu_text = (
            "У Вас остались вопросы?\n\n"
            "Выберите нужное действие:"
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=main_menu_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        # Send notifications
        from services.ticket_service import send_staff_notification, route_ticket
        from services.escalation_service import get_active_admins
        from loaders import max_bot
        
        # Get routing info for staff notification
        routing_info = await route_ticket(session, ticket, work_mode)
        
        if assigned_staff_id:
            # If user had no assigned manager, send special notification to admin
            if not has_manager:
                await _notify_admin_about_unassigned_user(
                    session=session,
                    ticket=ticket,
                    user=user,
                    assigned_admin_id=assigned_staff_id
                )
            else:
                # Send standard notification to assigned manager (only in working hours)
                # In NON_WORKING mode, notifications will be sent by queue task at 9 AM
                if work_mode != WorkMode.NON_WORKING:
                    notification_sent = await send_staff_notification(
                        bot=max_bot,
                        staff_id=assigned_staff_id,
                        ticket=ticket,
                        routing_info=routing_info,
                        session=session
                    )
                    
                    if notification_sent:
                        logger.info(
                            f"Manager notification sent immediately: ticket_id={ticket.id}, "
                            f"staff_id={assigned_staff_id}, work_mode={work_mode.value}"
                        )
                        
                        # Set queue_notification_sent_at to prevent queue processing
                        from utils.timezone_utils import get_moscow_now_naive
                        ticket.queue_notification_sent_at = get_moscow_now_naive()
                        await session.commit()
                        
                        logger.info(
                            f"Set queue_notification_sent_at for invoice ticket: ticket_id={ticket.id}"
                        )
                        
                        # Forward attachments to manager if any
                        if attachments:
                            try:
                                await _forward_attachments_to_staff(
                                    messenger_adapter=messenger_adapter,
                                    session=session,
                                    ticket_id=ticket.id,
                                    staff_id=assigned_staff_id,
                                    attachments=attachments,
                                    user_name=user.full_name or "Клиент"
                                )
                            except Exception as e:
                                logger.error(
                                    f"Failed to forward attachments for invoice ticket: "
                                    f"ticket_id={ticket.id}, error={e}",
                                    exc_info=True
                                )
                    else:
                        logger.warning(
                            f"Failed to send staff notification: ticket_id={ticket.id}, "
                            f"staff_id={assigned_staff_id}"
                        )
                else:
                    logger.info(
                        f"Invoice ticket queued for next working period: ticket_id={ticket.id}, "
                        f"manager_id={assigned_staff_id}, work_mode={work_mode.value}"
                    )
        else:
            # No manager or admin available - log error
            logger.error(
                f"No staff available for ticket assignment: ticket_id={ticket.id}, "
                f"user_id={user_id}"
            )
    
    except Exception as e:
        logger.error(
            f"Error creating invoice ticket: user_id={user_id}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


# ========== Cancellation Handler ==========


async def cancel_invoice_flow(
    event: MessageCreated | MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle cancellation at any step in invoice flow.
    
    Clears FSM state completely.
    Deletes old message (if callback) and shows main menu.
    
    Args:
        event: Message or callback event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 2.16
    """
    chat_id = event.message.recipient.chat_id
    
    # Get user_id based on event type
    from maxapi.types import MessageCallback as MCType
    if isinstance(event, MCType):
        max_user_id = event.callback.user.user_id
        message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    else:
        max_user_id = event.message.sender.user_id
        message_id = None
    
    logger.info(f"Cancelling invoice flow: chat_id={chat_id}, max_user_id={max_user_id}, message_id={message_id}")
    
    try:
        # Delete old message with buttons (if callback)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Clear FSM state
        await context.clear()
        
        # Get user from database to show appropriate menu
        from services.user_service import get_user_by_max_id
        from services.ticket_service import get_user_active_tickets_count
        from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
        
        user = await get_user_by_max_id(session, max_user_id)
        
        if user and user.registration_status == RegistrationStatus.ACTIVE:
            # Get active tickets count for menu
            active_tickets_count = await get_user_active_tickets_count(session, user.id)
            
            # Show main menu with inline keyboard
            keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
            
            from bots.max_bot.texts import MAIN_MENU_WELCOME_TEXT
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=MAIN_MENU_WELCOME_TEXT,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            # User not found or not active - show cancellation message
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=FLOW_CANCELLED,
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(
            f"Error cancelling invoice flow: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )







async def _notify_admin_about_unassigned_user(
    session: AsyncSession,
    ticket: Ticket,
    user: User,
    assigned_admin_id: int
) -> None:
    """
    Notify admin that user had no assigned manager and ticket was redirected.
    
    Args:
        session: Database session
        ticket: Created ticket
        user: User who created the ticket
        assigned_admin_id: ID of admin who was assigned the ticket
    """
    try:
        from loaders import max_bot
        from database.models import Staff_Member
        from sqlalchemy import select
        
        # Get admin details
        stmt = select(Staff_Member).where(Staff_Member.id == assigned_admin_id)
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()
        
        if not admin:
            logger.warning(f"Admin {assigned_admin_id} not found")
            return
        
        # Get chat_id: first from Staff_Member, then fallback to MAX_Messenger_Data
        chat_id = admin.max_chat_id
        
        # If not found in Staff_Member, try MAX_Messenger_Data table
        if not chat_id and admin.max_user_id:
            from database.models import MAX_Messenger_Data
            stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                MAX_Messenger_Data.max_user_id == admin.max_user_id
            )
            result_chat = await session.execute(stmt_chat)
            chat_id = result_chat.scalar_one_or_none()
            
            if chat_id:
                logger.info(
                    f"Found chat_id in MAX_Messenger_Data for admin {admin.id} "
                    f"(max_user_id={admin.max_user_id}): chat_id={chat_id}"
                )
        
        if not chat_id:
            logger.warning(
                f"Cannot notify admin {assigned_admin_id} - no MAX chat_id found "
                f"in Staff_Member or MAX_Messenger_Data tables (max_user_id={admin.max_user_id})"
            )
            return
        
        # Build notification message
        ticket_type_names = {
            TicketType.INVOICE: "💰 Счёт",
            TicketType.TECHNICAL_SUPPORT: "🛠 Техподдержка",
            TicketType.CONSULTATION: "💬 Консультация",
            TicketType.RENEWAL: "🔄 Продление"
        }
        
        ticket_type = ticket_type_names.get(ticket.ticket_type, str(ticket.ticket_type))
        user_name = user.full_name or f"{user.first_name} {user.last_name}".strip() or "Неизвестно"
        user_phone = user.phone_number or "Не указано"
        
        notification_text = (
            f"⚠️ <b>Заявка перенаправлена администратору</b>\n\n"
            f"У пользователя не был назначен менеджер, поэтому заявка #{ticket.id} "
            f"была автоматически перенаправлена вам.\n\n"
            f"<b>Тип заявки:</b> {ticket_type}\n"
            f"<b>Клиент:</b> {user_name}\n"
            f"<b>Телефон:</b> {user_phone}\n"
        )
        
        if ticket.organization:
            if ticket.organization.organization_name:
                org_text = f"{ticket.organization.organization_name} ({ticket.organization.inn})"
            else:
                org_text = ticket.organization.inn
            notification_text += f"<b>Организация:</b> {org_text}\n"
        
        if ticket.description:
            desc_preview = ticket.description[:150]
            if len(ticket.description) > 150:
                desc_preview += "..."
            notification_text += f"\n<b>Описание:</b>\n{desc_preview}\n"
        
        notification_text += (
            f"\n💡 <b>Рекомендация:</b> Назначьте пользователю менеджера "
            f"в CRM для автоматической маршрутизации будущих заявок."
        )
        
        # Create keyboard with "К заявке" button
        from bots.max_bot.payloads import ManagerTicketSelectPayload
        from maxapi.types.attachments.buttons import CallbackButton
        from maxapi.types.attachments.attachment import ButtonsPayload
        
        buttons = [[
            CallbackButton(
                text="📋 К заявке",
                payload=ManagerTicketSelectPayload(ticket_id=ticket.id).pack()
            )
        ]]
        keyboard_payload = ButtonsPayload(buttons=buttons).pack()
        
        # Send notification
        from maxapi import Bot as MAXBot
        from maxapi.enums.parse_mode import ParseMode
        from constants import MAX_BOT_TOKEN
        
        max_bot_instance = MAXBot(token=MAX_BOT_TOKEN, parse_mode=ParseMode.HTML)
        
        try:
            await max_bot_instance.send_message(
                chat_id=chat_id,
                text=notification_text,
                attachments=[keyboard_payload]
            )
            
            logger.info(
                f"Admin notified about unassigned user: ticket_id={ticket.id}, "
                f"admin_id={assigned_admin_id}, user_id={user.id}"
            )
        
        except Exception as e:
            logger.error(
                f"Failed to notify admin about unassigned user: "
                f"ticket_id={ticket.id}, admin_id={assigned_admin_id}, error={e}"
            )
        
        finally:
            if max_bot_instance.session:
                await max_bot_instance.session.close()
    
    except Exception as e:
        logger.error(
            f"Error in _notify_admin_about_unassigned_user: "
            f"ticket_id={ticket.id}, error={e}",
            exc_info=True
        )