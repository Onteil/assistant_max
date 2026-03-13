"""
Technical Support Handler for MAX Bot

Handles technical support flow including:
- /support command to initiate flow
- Subscription status check and renewal option
- Problem description collection (text, photo, voice, document)
- Key context selection with multi-select toggle
- Support ticket creation and manager notification

Requirements: 3.1-3.18
"""

import logging
from typing import Optional

from maxapi import F
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.callback_datas import KeyCallback
from bots.max_bot.keyboards.tickets.support_kb import (
    get_add_key_keyboard,
    get_key_context_keyboard,
    get_problem_description_keyboard,
    get_renewal_keyboard,
)
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.states import SupportStates
from bots.max_bot.texts import (
    ERROR_GENERAL,
    ERROR_TEXT_TOO_LONG,
    ERROR_VALIDATION_KEY,
    FLOW_CANCELLED,
    RENEWAL_STATUS_ACTIVE,
    RENEWAL_STATUS_EXPIRED,
    RENEWAL_STATUS_NONE,
    RENEWAL_TICKET_CREATED,
    SUPPORT_CREATE_TICKET,
    SUPPORT_NO_SUBSCRIPTION,
    SUPPORT_SELECT_KEY_CONTEXT,
    SUPPORT_SUBSCRIPTION_EXPIRED,
    SUPPORT_TICKET_CREATED,
    SUPPORT_ROUTING_REGULAR,
    SUPPORT_ROUTING_EXTENDED,
    SUPPORT_ROUTING_NON_WORKING,
    SUPPORT_RESPONSE_TIME_REGULAR,
    SUPPORT_RESPONSE_TIME_EXTENDED,
    SUPPORT_RESPONSE_TIME_NON_WORKING,
)
from database.models import (
    KeyConflictStatus,
    SubscriptionStatus,
    Ticket,
    TicketStatus,
    TicketType,
    User,
    WorkMode,
)
from services.calendar_service import get_current_work_mode
from services.i_tat_service import get_itat_client
from services.ticket_service import create_ticket, route_ticket
from services.user_service import (
    add_user_key,
    get_user_by_id,
    get_user_by_max_id,
    get_user_keys,
)
from services.validation_service import validate_gs_key

logger = logging.getLogger(__name__)


# ========== /support Command Handler ==========


async def cmd_support(
    event: MessageCreated | MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /support command or callback - check subscription status and initiate flow.
    
    Checks user subscription status:
    - ACTIVE: Proceed to problem description
    - EXPIRED/NONE: Offer renewal option
    
    Args:
        event: Message or callback event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    commands_info: Запросить техническую поддержку
    
    Requirements: 3.1, 3.2, 3.3
    """
    chat_id = event.message.recipient.chat_id
    # Get user_id based on event type (MessageCreated uses sender, MessageCallback uses callback.user)
    from maxapi.types import MessageCallback as MCType
    if isinstance(event, MCType):
        max_user_id = event.callback.user.user_id
    else:
        max_user_id = event.message.sender.user_id
    
    logger.info(f"User initiated support request: max_user_id={max_user_id}, chat_id={chat_id}")
    
    try:
        # Get user from database
        user = await get_user_by_max_id(session, max_user_id)
        
        if not user:
            logger.error(f"User not found for support request: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден. Пожалуйста, пройдите регистрацию командой /start",
                parse_mode="HTML"
            )
            return
        
        # Check subscription status
        subscription_status = user.subscription_status
        
        logger.info(
            f"User subscription status: user_id={user.id}, status={subscription_status.value}"
        )
        
        if subscription_status == SubscriptionStatus.ACTIVE:
            # Proceed to problem description
            logger.info(f"Active subscription - proceeding to problem description: user_id={user.id}")
            
            # Initialize FSM context
            await context.update_data(
                user_id=user.id,
                problem_description=None,
                attachments=[],
                selected_keys=[]
            )
            
            # Set FSM state
            await context.set_state(SupportStates.entering_problem)
            
            # Prompt for problem description
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=SUPPORT_CREATE_TICKET,
                keyboard=get_problem_description_keyboard(),
                parse_mode="HTML"
            )
        
        elif subscription_status == SubscriptionStatus.EXPIRED:
            # Offer renewal option
            logger.info(f"Expired subscription - offering renewal: user_id={user.id}")
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=SUPPORT_SUBSCRIPTION_EXPIRED,
                keyboard=get_renewal_keyboard(),
                parse_mode="HTML"
            )
        
        else:  # SubscriptionStatus.NONE
            # Offer renewal option
            logger.info(f"No subscription - offering renewal: user_id={user.id}")
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=SUPPORT_NO_SUBSCRIPTION,
                keyboard=get_renewal_keyboard(),
                parse_mode="HTML"
            )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in cmd_support: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(
            f"Unexpected error in cmd_support: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


# ========== Subscription Renewal Handlers ==========


async def handle_renewal_callback(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle renewal callback - create RENEWAL ticket if no active ticket exists.
    
    Checks for existing active RENEWAL tickets to prevent duplicates.
    Creates RENEWAL ticket and notifies assigned manager.
    
    Note: payload parameter removed because maxapi doesn't inject it for this handler.
    We parse the payload manually if needed.
    
    Args:
        event: Callback event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 3.4, 3.5, 3.6
    """
    chat_id = event.message.recipient.chat_id
    # In callback events, user_id comes from event.callback.user, not event.message.sender
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Renewal callback: max_user_id={max_user_id}, chat_id={chat_id}, message_id={message_id}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Delete old message with buttons (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get user from database
        user = await get_user_by_max_id(session, max_user_id)
        
        if not user:
            logger.error(f"User not found for renewal: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            return
        
        # Check for existing active RENEWAL tickets
        from sqlalchemy import and_, select
        from database.models import Ticket
        
        result = await session.execute(
            select(Ticket).where(
                and_(
                    Ticket.user_id == user.id,
                    Ticket.ticket_type == TicketType.RENEWAL,
                    Ticket.ticket_status.in_([TicketStatus.NEW, TicketStatus.IN_PROGRESS])
                )
            )
        )
        existing_ticket = result.scalar_one_or_none()
        
        if existing_ticket:
            # Prevent duplicate ticket creation
            logger.warning(
                f"Active RENEWAL ticket already exists: user_id={user.id}, "
                f"ticket_id={existing_ticket.id}"
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"📋 У вас уже есть активная заявка на продление (#{existing_ticket.id}).\n\n"
                     f"Ожидайте ответа от менеджера.",
                parse_mode="HTML"
            )
            return
        
        # Create RENEWAL ticket
        await create_renewal_ticket(session, messenger_adapter, chat_id, user.id)
    
    except Exception as e:
        logger.error(
            f"Error handling renewal callback: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def create_renewal_ticket(
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    chat_id: int,
    user_id: int
) -> None:
    """
    Create RENEWAL ticket for subscription renewal.
    
    Creates ticket with RENEWAL type.
    Routes ticket to assigned manager or admin if no manager assigned.
    Sends notification to assigned staff.
    Displays success message to user.
    
    Args:
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        chat_id: Chat ID for sending messages
        user_id: Internal user ID (primary key)
    
    Requirements: 3.4, 3.5, 3.6
    """
    logger.info(f"Creating renewal ticket: user_id={user_id}")
    
    try:
        # Get user to determine assigned manager
        user = await get_user_by_id(session, user_id)
        if not user:
            logger.error(f"User not found for renewal ticket creation: user_id={user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            return
        
        # Determine assigned manager (with admin fallback if no manager)
        from services.ticket_service import determine_assigned_manager
        
        assigned_staff_id, has_manager = await determine_assigned_manager(
            session=session,
            user_id=user_id,
            assign_admin_if_no_manager=True  # Auto-assign admin if no manager
        )
        
        if not assigned_staff_id:
            logger.error(f"No staff available for renewal ticket: user_id={user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ В данный момент нет доступных сотрудников для обработки заявки. Попробуйте позже.",
                parse_mode="HTML"
            )
            return
        
        # Create ticket
        ticket_data = {
            "ticket_type": TicketType.RENEWAL,
            "user_id": user_id,
            "assigned_staff_id": assigned_staff_id,
            "description": "Запрос на продление подписки на техническую поддержку"
        }
        
        ticket = await create_ticket(session, ticket_data)
        await session.commit()
        
        logger.info(
            f"Renewal ticket created: ticket_id={ticket.id}, user_id={user_id}, "
            f"assigned_staff={assigned_staff_id}, has_manager={has_manager}"
        )
        
        # Get manager name and position for user message
        manager_name = "Менеджер"
        manager_position = "Менеджер"
        if assigned_staff_id:
            from database.models import Staff_Member
            from sqlalchemy import select
            
            stmt = select(Staff_Member).where(Staff_Member.id == assigned_staff_id)
            result = await session.execute(stmt)
            staff_member = result.scalar_one_or_none()
            
            if staff_member:
                manager_name = staff_member.full_name or "Менеджер"
                manager_position = staff_member.position or "Менеджер"
        
        # Send success message to user
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=RENEWAL_TICKET_CREATED.format(
                ticket_id=ticket.id,
                manager_name=manager_name,
                manager_position=manager_position
            ),
            parse_mode="HTML"
        )
        
        # Show main menu after successful ticket creation
        from services.ticket_service import get_user_active_tickets_count
        from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
        
        active_tickets_count = await get_user_active_tickets_count(session, user.id)
        keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
        
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
        from services.ticket_service import send_staff_notification
        from loaders import max_bot
        
        if assigned_staff_id:
            # Send notification to assigned manager or admin
            notification_sent = await send_staff_notification(
                bot=max_bot,
                staff_id=assigned_staff_id,
                ticket=ticket,
                session=session
            )
            
            if notification_sent:
                logger.info(
                    f"Staff notification sent: ticket_id={ticket.id}, "
                    f"staff_id={assigned_staff_id}"
                )
            else:
                logger.warning(
                    f"Failed to send staff notification: ticket_id={ticket.id}, "
                    f"staff_id={assigned_staff_id}"
                )
            
            # If user had no assigned manager, notify admin about this
            if not has_manager:
                await _notify_admin_about_unassigned_user_renewal(
                    session=session,
                    ticket=ticket,
                    user=user,
                    assigned_admin_id=assigned_staff_id
                )
    
    except Exception as e:
        logger.error(
            f"Error creating renewal ticket: user_id={user_id}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


# ========== Problem Description Handlers ==========


async def process_problem_description(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process problem description (text, photo, voice, document).
    
    Validates text length (max 4000 characters).
    Handles photo attachments with optional caption.
    Handles voice message attachments.
    Handles document attachments with file type classification.
    Stores all attachments in FSM context data.
    
    Args:
        event: Message event from MAX
        context: FSM context for state management
        session: Database session (injected by middleware)
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 3.7, 3.8, 3.9, 3.10, 8.3, 8.4, 8.5
    """
    chat_id = event.message.recipient.chat_id
    
    logger.info(f"Processing problem description: chat_id={chat_id}")
    
    try:
        # Get data from context
        data = await context.get_data()
        user_id = data.get("user_id")
        attachments = data.get("attachments", [])
        
        if not user_id:
            logger.error(f"No user_id in context: chat_id={chat_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Handle text message
        if event.message.body and event.message.body.text:
            text = event.message.body.text.strip()
            
            # Validate text length
            if len(text) > 4000:
                logger.warning(f"Problem description too long: length={len(text)}")
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=f"{ERROR_TEXT_TOO_LONG}\n\nМаксимальная длина описания: 4000 символов. Ваше описание: {len(text)} символов.",
                    keyboard=get_problem_description_keyboard(),
                    parse_mode="HTML"
                )
                return
            
            # Store description
            await context.update_data(problem_description=text)
            
            logger.info(f"Problem description stored: user_id={user_id}, length={len(text)}")
        
        # Handle photo attachment
        if hasattr(event.message, 'attachments') and event.message.attachments:
            for attachment in event.message.attachments:
                if attachment.type == "photo":
                    # Upload photo to MAX API
                    photo_url = attachment.payload.url
                    caption = event.message.body.text if event.message.body else None
                    
                    attachments.append({
                        "type": "photo",
                        "url": photo_url,
                        "caption": caption
                    })
                    
                    logger.info(f"Photo attachment added: user_id={user_id}, url={photo_url}")
                
                elif attachment.type == "voice":
                    # Handle voice message
                    voice_url = attachment.payload.url
                    
                    attachments.append({
                        "type": "voice",
                        "url": voice_url
                    })
                    
                    logger.info(f"Voice attachment added: user_id={user_id}, url={voice_url}")
                
                elif attachment.type == "file":
                    # Handle document attachment
                    file_url = attachment.payload.url
                    file_name = attachment.payload.name if hasattr(attachment.payload, 'name') else "document"
                    
                    # Classify file type
                    from services.validation_service import classify_file_type
                    file_type = classify_file_type(file_name)
                    
                    attachments.append({
                        "type": "document",
                        "url": file_url,
                        "file_name": file_name,
                        "file_type": file_type.value
                    })
                    
                    logger.info(
                        f"Document attachment added: user_id={user_id}, "
                        f"file_name={file_name}, file_type={file_type.value}"
                    )
            
            # Update attachments in context
            await context.update_data(attachments=attachments)
        
        # Check if we have description or attachments
        problem_description = data.get("problem_description")
        if not problem_description and not attachments:
            # Still waiting for description
            return
        
        # Proceed to key context selection
        await context.set_state(SupportStates.selecting_key_context)
        
        # Show key context selection with keyboard
        await show_key_context_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=set(),
            page=0,
            session=session,
            messenger_adapter=messenger_adapter
        )
    
    except Exception as e:
        logger.error(
            f"Error processing problem description: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


# ========== Cancellation Handler ==========


async def cancel_support_flow(
    event: MessageCreated | MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle cancellation at any step in support flow.
    
    Clears FSM state completely.
    Deletes old message (if callback) and shows main menu.
    
    Args:
        event: Message or callback event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 3.18
    """
    chat_id = event.message.recipient.chat_id
    
    # Get user_id and message_id based on event type
    from maxapi.types import MessageCallback as MCType
    if isinstance(event, MCType):
        max_user_id = event.callback.user.user_id
        message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    else:
        max_user_id = event.message.sender.user_id
        message_id = None
    
    logger.info(f"Cancelling support flow: chat_id={chat_id}, max_user_id={max_user_id}, message_id={message_id}")
    
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
        from services.ticket_service import get_user_active_tickets_count
        from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
        
        user = await get_user_by_max_id(session, max_user_id)
        from database.models import RegistrationStatus
        if user and user.registration_status == RegistrationStatus.ACTIVE:
            # Get active tickets count for menu
            active_tickets_count = await get_user_active_tickets_count(session, user.id)
            
            # Show main menu with inline keyboard
            keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
            
            welcome_text = (
                "🎉 <b>Добро пожаловать в меню сметчика АЙТАТ!</b>\n\n"
                "Здесь вы можете:\n\n"
                "💰 <b>Получить счёт</b> — запросить счет на обновление базы\n"
                "🆘 <b>Техподдержка</b> — получить помощь по работе с программой ГРАНД-Смета\n"
                "🔄 <b>Продление</b> — продлить подписку на информационно-техническое сопровождение\n"
                "🗄 <b>Архив обращений</b> — просмотреть историю ваших обращений\n"
                "👤 <b>Мой профиль</b> — управление вашими данными и настройками\n\n"
                "Выберите нужное действие:"
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=welcome_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            # Fallback if user not found or not active
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=FLOW_CANCELLED,
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(
            f"Error cancelling support flow: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )



# ========== Key Context Selection Handlers ==========


async def show_key_context_selection(
    chat_id: int,
    user_id: int,
    selected_keys: set[int],
    page: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    message_id: Optional[int] = None
) -> None:
    """
    Display key context selection with multi-select toggle.
    
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
    
    Requirements: 3.11, 3.12
    """
    logger.info(f"Showing key context selection: user_id={user_id}, page={page}, selected={len(selected_keys)}")
    
    try:
        # Get user keys
        keys = await get_user_keys(session, user_id)
        
        # Build keyboard
        keyboard = get_key_context_keyboard(keys, selected_keys, page)
        
        # Send or edit message
        if message_id:
            await messenger_adapter.edit_message(
                chat_id=chat_id,
                message_id=message_id,
                text=SUPPORT_SELECT_KEY_CONTEXT,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=SUPPORT_SELECT_KEY_CONTEXT,
                keyboard=keyboard,
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(
            f"Error showing key context selection: user_id={user_id}, page={page}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_key_context_callback(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle key context callbacks (toggle, add_new, done, skip, page, skip_description).
    
    This handler is registered for multiple payload types:
    - KeyContextTogglePayload: Toggle key selection
    - KeyContextPagePayload: Navigate between pages
    - KeyContextActionPayload: Actions (add_new, done, skip, back, cancel, etc.)
    
    Args:
        event: Callback event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 3.11, 3.12, 3.13, 3.14
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    # Parse callback data from payload
    # maxapi sends payload in pipe-separated format (e.g., "key_ctx_action|skip")
    # We need to unpack it to get the action and other fields
    from bots.max_bot.payloads import (
        KeyContextTogglePayload,
        KeyContextPagePayload,
        KeyContextActionPayload,
    )
    
    raw_payload = event.callback.payload
    action = None
    key_id = None
    page = None
    
    # Try to unpack as different payload types
    try:
        if isinstance(raw_payload, str):
            # Try KeyContextActionPayload first (most common)
            if raw_payload.startswith('key_ctx_action|'):
                payload_obj = KeyContextActionPayload.unpack(raw_payload)
                action = payload_obj.action
            # Try KeyContextTogglePayload
            elif raw_payload.startswith('key_ctx_toggle|'):
                payload_obj = KeyContextTogglePayload.unpack(raw_payload)
                action = "toggle"
                key_id = payload_obj.key_id
            # Try KeyContextPagePayload
            elif raw_payload.startswith('key_ctx_page|'):
                payload_obj = KeyContextPagePayload.unpack(raw_payload)
                action = "page"
                page = payload_obj.page
            else:
                logger.error(f"Unknown payload format: {raw_payload}")
                return
        elif isinstance(raw_payload, dict):
            # Fallback for dict format
            action = raw_payload.get("action")
            key_id = raw_payload.get("key_id")
            page = raw_payload.get("page")
        else:
            logger.error(f"Unexpected payload type: {type(raw_payload)}")
            return
    except Exception as e:
        logger.error(f"Failed to parse callback payload: {raw_payload}, error={e}")
        return
    
    logger.info(f"Key context callback: chat_id={chat_id}, action={action}, key_id={key_id}, page={page}, message_id={message_id}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Delete old message with buttons (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get data from context
        data = await context.get_data()
        user_id = data.get("user_id")
        selected_keys = set(data.get("selected_keys", []))
        
        if not user_id:
            logger.error(f"No user_id in context: chat_id={chat_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        if action == "toggle":
            # Toggle key selection
            if key_id is None:
                logger.error(f"Missing key_id in toggle action")
                return
            
            # Get key to check conflict status
            keys = await get_user_keys(session, user_id)
            key = next((k for k in keys if k.id == key_id), None)
            
            if not key:
                logger.error(f"Key not found: key_id={key_id}")
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=ERROR_GENERAL,
                    parse_mode="HTML"
                )
                return
            
            # Prevent selection of PENDING_REVIEW keys
            if key.conflict_status == KeyConflictStatus.PENDING_REVIEW:
                logger.warning(f"Attempted to select PENDING_REVIEW key: key_id={key_id}")
                await event.answer(
                    text="⚠️ Этот ключ находится на проверке и не может быть выбран",
                    show_alert=True
                )
                return
            
            # Toggle selection
            if key_id in selected_keys:
                selected_keys.remove(key_id)
                logger.info(f"Key deselected: key_id={key_id}")
            else:
                selected_keys.add(key_id)
                logger.info(f"Key selected: key_id={key_id}")
            
            # Update context
            await context.update_data(selected_keys=list(selected_keys))
            
            # Show key context selection (send new message)
            await show_key_context_selection(
                chat_id=chat_id,
                user_id=user_id,
                selected_keys=selected_keys,
                page=0,
                session=session,
                messenger_adapter=messenger_adapter
            )
        
        elif action == "add_new":
            # Prompt for new key input
            logger.info(f"User adding new key: user_id={user_id}")
            
            # Set state for adding new key
            await context.set_state(SupportStates.adding_new_key)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="🔑 Введите новый ключ Гранд-сметы (формат: 00001_00011):",
                keyboard=get_add_key_keyboard(),
                parse_mode="HTML"
            )
        
        elif action == "done":
            # Proceed to ticket creation with selected keys
            logger.info(f"User completed key context selection: user_id={user_id}, keys={len(selected_keys)}")
            
            await create_support_ticket(context, session, messenger_adapter, chat_id, user_id)
        
        elif action == "skip":
            # Proceed to ticket creation without keys
            logger.info(f"User skipped key context selection: user_id={user_id}")
            
            await context.update_data(selected_keys=[])
            await create_support_ticket(context, session, messenger_adapter, chat_id, user_id)
        
        elif action == "skip_description":
            # Skip problem description and proceed to key selection
            logger.info(f"User skipped problem description: user_id={user_id}")
            
            # Set empty description
            await context.update_data(problem_description="")
            
            # Proceed to key context selection
            await context.set_state(SupportStates.selecting_key_context)
            
            # Show key context selection with keyboard
            await show_key_context_selection(
                chat_id=chat_id,
                user_id=user_id,
                selected_keys=selected_keys,
                page=0,
                session=session,
                messenger_adapter=messenger_adapter
            )
        
        elif action == "page":
            # Navigate to different page
            if page is None:
                logger.error(f"Missing page in page action")
                return
            
            logger.info(f"Key context pagination: user_id={user_id}, page={page}")
            
            await show_key_context_selection(
                chat_id=chat_id,
                user_id=user_id,
                selected_keys=selected_keys,
                page=page,
                session=session,
                messenger_adapter=messenger_adapter
            )
        
        elif action == "back":
            # Return to problem description
            logger.info(f"User returned to problem description: user_id={user_id}")
            
            await context.set_state(SupportStates.entering_problem)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=SUPPORT_CREATE_TICKET,
                keyboard=get_problem_description_keyboard(),
                parse_mode="HTML"
            )
        
        elif action == "back_to_keys":
            # Return to key context selection (from add_new state)
            logger.info(f"User returned to key context selection: user_id={user_id}")
            
            await context.set_state(SupportStates.selecting_key_context)
            
            await show_key_context_selection(
                chat_id=chat_id,
                user_id=user_id,
                selected_keys=selected_keys,
                page=0,
                session=session,
                messenger_adapter=messenger_adapter
            )
        
        elif action == "cancel":
            # Cancel support flow
            logger.info(f"User cancelled support flow: user_id={user_id}")
            await cancel_support_flow(event, context, session, messenger_adapter)
    
    except Exception as e:
        logger.error(
            f"Error handling key context callback: action={action}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def process_new_key_for_support(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process new key input for support flow, validate format, check conflicts.
    
    Validates GS_Key format (XXXXX_XXXXX).
    Checks for key conflicts via i-TAT API.
    Adds key to user profile.
    Returns to key context selection.
    
    Args:
        event: Message event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 3.14
    """
    chat_id = event.message.recipient.chat_id
    key_number = event.message.body.text.strip()
    
    logger.info(f"Processing new key for support: chat_id={chat_id}, key={key_number}")
    
    # Validate GS_Key format
    is_valid, result = validate_gs_key(key_number)
    
    if not is_valid:
        logger.warning(f"Invalid GS_Key: key={key_number}, error={result}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"{ERROR_VALIDATION_KEY}\n\n{result}",
            keyboard=get_add_key_keyboard(),
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
        
        # Check for key conflicts via i-TAT API
        itat_client = get_itat_client()
        conflict_response = await itat_client.check_key_conflict(
            grand_key=normalized_key,
            user_id=user_id
        )
        
        logger.info(f"Key conflict check result: {conflict_response}")
        
        conflict_status = KeyConflictStatus.NONE
        if conflict_response.get("status") == "conflict":
            conflict_status = KeyConflictStatus.PENDING_REVIEW
            owner_info = conflict_response.get("owner", "Неизвестный владелец")
            logger.warning(f"Key conflict detected: key={normalized_key}, owner={owner_info}")
        
        # Add key to user profile
        await add_user_key(session, user_id, normalized_key, conflict_status)
        await session.commit()
        
        logger.info(f"GS_Key added: user_id={user_id}, key={normalized_key}, conflict={conflict_status.value}")
        
        # Return to key context selection state
        await context.set_state(SupportStates.selecting_key_context)
        
        # Show confirmation
        if conflict_status == KeyConflictStatus.PENDING_REVIEW:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="⚠️ Ключ добавлен, но обнаружен конфликт. Ключ отправлен на проверку и не может быть выбран.",
                parse_mode="HTML"
            )
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="✅ Ключ успешно добавлен!",
                parse_mode="HTML"
            )
        
        # Show key context selection again
        selected_keys = set(data.get("selected_keys", []))
        await show_key_context_selection(
            chat_id=chat_id,
            user_id=user_id,
            selected_keys=selected_keys,
            page=0,
            session=session,
            messenger_adapter=messenger_adapter
        )
    
    except Exception as e:
        logger.error(
            f"Error processing new key for support: key={key_number}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


# ========== Support Ticket Creation ==========


async def create_support_ticket(
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    chat_id: int,
    user_id: int
) -> None:
    """
    Create SUPPORT ticket with all collected data.
    
    Determines work mode based on business logic.
    Routes ticket to appropriate manager.
    Sends notification to assigned manager.
    Displays success message to user.
    
    Args:
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        chat_id: Chat ID for sending messages
        user_id: Internal user ID (primary key)
    
    Requirements: 3.15, 3.16, 3.17
    """
    logger.info(f"Creating support ticket: user_id={user_id}")
    
    try:
        # Get data from context
        data = await context.get_data()
        problem_description = data.get("problem_description", "")
        attachments = data.get("attachments", [])
        selected_keys = data.get("selected_keys", [])
        
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
        
        # Determine current work mode
        work_mode = await get_current_work_mode(session)
        logger.info(f"Current work mode: {work_mode.value}")
        
        # Check if support staff is available
        from services.ticket_service import check_support_staff_availability
        has_support_staff = await check_support_staff_availability(session)
        
        # If no support staff available, notify admin immediately
        if not has_support_staff:
            logger.warning(
                f"No support staff available when creating ticket for user {user_id}"
            )
            # Will notify admin after ticket creation
        
        # Determine assigned staff based on work mode
        assigned_staff_id = None
        
        if work_mode == WorkMode.REGULAR:
            if has_support_staff:
                # Route to any available support staff (no specific assignment)
                # Support team will pick up the ticket
                assigned_staff_id = None
                logger.info(f"Routing to support team: work_mode={work_mode.value}")
            else:
                # No support staff available - route to admin
                from services.escalation_service import get_active_admins
                admins = await get_active_admins(session)
                if admins:
                    assigned_staff_id = admins[0].id
                    logger.warning(
                        f"No support staff available, routing to admin: "
                        f"admin_id={assigned_staff_id}"
                    )
                else:
                    logger.error("No support staff and no admins available")
                    await messenger_adapter.send_message(
                        chat_id=chat_id,
                        text="❌ В данный момент нет доступных сотрудников для обработки заявки техподдержки. Попробуйте позже.",
                        parse_mode="HTML"
                    )
                    return
        
        elif work_mode == WorkMode.EXTENDED:
            # Route to duty engineer
            from services.ticket_service import _get_duty_engineer
            duty_engineer = await _get_duty_engineer(session)
            if duty_engineer:
                assigned_staff_id = duty_engineer.id
                logger.info(
                    f"Routing to duty engineer: work_mode={work_mode.value}, "
                    f"engineer_id={assigned_staff_id}"
                )
            else:
                # No duty engineer configured - route to admin
                from services.escalation_service import get_active_admins
                admins = await get_active_admins(session)
                if admins:
                    assigned_staff_id = admins[0].id
                    logger.warning(
                        f"No duty engineer configured, routing to admin: "
                        f"admin_id={assigned_staff_id}"
                    )
                else:
                    logger.error("No duty engineer and no admins available")
                    await messenger_adapter.send_message(
                        chat_id=chat_id,
                        text="❌ В данный момент нет доступных сотрудников для обработки заявки техподдержки. Попробуйте позже.",
                        parse_mode="HTML"
                    )
                    return
        
        else:  # NON_WORKING
            # Queue for next working period (no assignment)
            assigned_staff_id = None
            logger.info(f"Queuing for next working period: work_mode={work_mode.value}")
        
        # Build description with attachments info
        full_description = problem_description
        if attachments:
            full_description += f"\n\n📎 Вложения: {len(attachments)}"
        
        # Create ticket
        ticket_data = {
            "ticket_type": TicketType.TECHNICAL_SUPPORT,
            "user_id": user_id,
            "assigned_staff_id": assigned_staff_id,
            "description": full_description,
            "selected_key_ids": selected_keys
        }
        
        ticket = await create_ticket(session, ticket_data)
        
        # Store attachments in ticket (if needed, extend ticket model)
        # For now, attachments are included in description
        
        await session.commit()
        
        logger.info(
            f"Support ticket created: ticket_id={ticket.id}, user_id={user_id}, "
            f"work_mode={work_mode.value}, assigned_staff={assigned_staff_id}, "
            f"has_support_staff={has_support_staff}"
        )
        
        # Schedule 10-minute escalation check for technical support tickets
        # This will notify admins if ticket is not taken by support staff
        try:
            from celery_app.escalation_tasks import schedule_technical_support_monitoring
            
            task_id = await schedule_technical_support_monitoring(ticket_id=ticket.id)
            
            logger.info(
                f"Technical support monitoring scheduled: ticket_id={ticket.id}, "
                f"task_id={task_id}"
            )
        
        except Exception as e:
            # Don't fail ticket creation if escalation scheduling fails
            logger.error(
                f"Failed to schedule technical support monitoring for ticket {ticket.id}: {e}",
                exc_info=True
            )
            logger.warning(
                f"Ticket {ticket.id} created without escalation monitoring. "
                f"Manual intervention may be required."
            )
        
        # Clear FSM state
        await context.clear()
        
        # Prepare routing and response time messages based on work mode
        routing_messages = {
            WorkMode.REGULAR: SUPPORT_ROUTING_REGULAR,
            WorkMode.EXTENDED: SUPPORT_ROUTING_EXTENDED,
            WorkMode.NON_WORKING: SUPPORT_ROUTING_NON_WORKING
        }
        
        response_time_messages = {
            WorkMode.REGULAR: SUPPORT_RESPONSE_TIME_REGULAR,
            WorkMode.EXTENDED: SUPPORT_RESPONSE_TIME_EXTENDED,
            WorkMode.NON_WORKING: SUPPORT_RESPONSE_TIME_NON_WORKING
        }
        
        # Send success message to user
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=SUPPORT_TICKET_CREATED.format(
                ticket_id=ticket.id,
                routing_message=routing_messages[work_mode],
                response_time_message=response_time_messages[work_mode]
            ),
            parse_mode="HTML"
        )
        
        # Show main menu after successful ticket creation
        from services.ticket_service import get_user_active_tickets_count
        from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
        
        active_tickets_count = await get_user_active_tickets_count(session, user.id)
        keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
        
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
        
        # Send notifications based on work mode and staff availability
        from services.ticket_service import send_staff_notification
        from loaders import max_bot
        
        if work_mode == WorkMode.REGULAR:
            if has_support_staff:
                # Send notification to all active support staff
                from database.models import Staff_Member, StaffRole
                from sqlalchemy import select, and_
                
                stmt = select(Staff_Member).where(
                    and_(
                        Staff_Member.staff_role == StaffRole.TECHNICAL_SUPPORT,
                        Staff_Member.is_active == True,
                        Staff_Member.max_user_id.isnot(None)
                    )
                )
                result = await session.execute(stmt)
                support_staff = result.scalars().all()
                
                if support_staff:
                    for staff in support_staff:
                        try:
                            notification_sent = await send_staff_notification(
                                bot=max_bot,
                                staff_id=staff.id,
                                ticket=ticket,
                                routing_info={
                                    "work_mode": work_mode.value,
                                    "expected_response_time": "в течение рабочего дня"
                                },
                                session=session
                            )
                            
                            if notification_sent:
                                logger.info(
                                    f"Support staff notification sent: ticket_id={ticket.id}, "
                                    f"staff_id={staff.id}"
                                )
                        except Exception as e:
                            logger.error(
                                f"Failed to send support staff notification: "
                                f"ticket_id={ticket.id}, staff_id={staff.id}, error={e}",
                                exc_info=True
                            )
                    
                    logger.info(
                        f"Support team notifications sent: ticket_id={ticket.id}, "
                        f"staff_count={len(support_staff)}"
                    )
                else:
                    logger.warning(
                        f"No active support staff with MAX ID found: ticket_id={ticket.id}"
                    )
            else:
                # No support staff available - notify ALL admins
                from services.escalation_service import get_active_admins
                admins = await get_active_admins(session)
                
                if admins:
                    for admin in admins:
                        try:
                            notification_sent = await send_staff_notification(
                                bot=max_bot,
                                staff_id=admin.id,
                                ticket=ticket,
                                routing_info={
                                    "work_mode": work_mode.value,
                                    "expected_response_time": "в течение рабочего дня"
                                },
                                session=session
                            )
                            
                            if notification_sent:
                                logger.info(
                                    f"Admin notification sent (no support staff): ticket_id={ticket.id}, "
                                    f"admin_id={admin.id}"
                                )
                                
                                # Notify admin about missing support staff
                                await _notify_admin_about_no_support_staff(
                                    session=session,
                                    ticket=ticket,
                                    user=user,
                                    assigned_admin_id=admin.id
                                )
                            else:
                                logger.warning(
                                    f"Failed to send admin notification: ticket_id={ticket.id}, "
                                    f"admin_id={admin.id}"
                                )
                        except Exception as e:
                            logger.error(
                                f"Failed to send admin notification: "
                                f"ticket_id={ticket.id}, admin_id={admin.id}, error={e}",
                                exc_info=True
                            )
                    
                    logger.info(
                        f"Admin notifications sent (no support staff): ticket_id={ticket.id}, "
                        f"admin_count={len(admins)}"
                    )
                else:
                    logger.error(
                        f"No support staff and no admins available: ticket_id={ticket.id}"
                    )
        
        elif work_mode == WorkMode.EXTENDED:
            # Check if duty engineer is configured
            from services.ticket_service import _get_duty_engineer
            duty_engineer = await _get_duty_engineer(session)
            
            if duty_engineer:
                # Send notification to duty engineer
                notification_sent = await send_staff_notification(
                    bot=max_bot,
                    staff_id=duty_engineer.id,
                    ticket=ticket,
                    routing_info={
                        "work_mode": work_mode.value,
                        "expected_response_time": "в продленное рабочее время"
                    },
                    session=session
                )
                
                if notification_sent:
                    logger.info(
                        f"Duty engineer notification sent: ticket_id={ticket.id}, "
                        f"staff_id={duty_engineer.id}"
                    )
                else:
                    logger.warning(
                        f"Failed to send duty engineer notification: "
                        f"ticket_id={ticket.id}, staff_id={duty_engineer.id}"
                    )
            else:
                # No duty engineer - notify ALL admins
                from services.escalation_service import get_active_admins
                admins = await get_active_admins(session)
                
                if admins:
                    for admin in admins:
                        try:
                            notification_sent = await send_staff_notification(
                                bot=max_bot,
                                staff_id=admin.id,
                                ticket=ticket,
                                routing_info={
                                    "work_mode": work_mode.value,
                                    "expected_response_time": "в продленное рабочее время"
                                },
                                session=session
                            )
                            
                            if notification_sent:
                                logger.info(
                                    f"Admin notification sent (no duty engineer): ticket_id={ticket.id}, "
                                    f"admin_id={admin.id}"
                                )
                                
                                # Notify admin about missing duty engineer
                                await _notify_admin_about_no_support_staff(
                                    session=session,
                                    ticket=ticket,
                                    user=user,
                                    assigned_admin_id=admin.id
                                )
                            else:
                                logger.warning(
                                    f"Failed to send admin notification: "
                                    f"ticket_id={ticket.id}, admin_id={admin.id}"
                                )
                        except Exception as e:
                            logger.error(
                                f"Failed to send admin notification: "
                                f"ticket_id={ticket.id}, admin_id={admin.id}, error={e}",
                                exc_info=True
                            )
                    
                    logger.info(
                        f"Admin notifications sent (no duty engineer): ticket_id={ticket.id}, "
                        f"admin_count={len(admins)}"
                    )
                else:
                    logger.error(
                        f"No duty engineer and no admins available: ticket_id={ticket.id}"
                    )
        
        else:  # NON_WORKING
            # No notifications during non-working hours
            logger.info(
                f"Ticket queued for next working period: ticket_id={ticket.id}, "
                f"work_mode={work_mode.value}"
            )
    
    except Exception as e:
        logger.error(
            f"Error creating support ticket: user_id={user_id}, error={e}",
            exc_info=True
        )
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )





async def _notify_admin_about_unassigned_user_renewal(
    session: AsyncSession,
    ticket: Ticket,
    user: User,
    assigned_admin_id: int
) -> None:
    """
    Notify admin that user had no assigned manager for renewal ticket.
    
    Args:
        session: Database session
        ticket: Created renewal ticket
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
        
        if not admin or not admin.max_chat_id:
            logger.warning(f"Cannot notify admin {assigned_admin_id} - no MAX chat_id")
            return
        
        user_name = user.full_name or f"{user.first_name} {user.last_name}".strip() or "Неизвестно"
        user_phone = user.phone_number or "Не указано"
        
        notification_text = (
            f"⚠️ <b>Заявка на продление перенаправлена администратору</b>\n\n"
            f"У пользователя не был назначен менеджер, поэтому заявка на продление #{ticket.id} "
            f"была автоматически перенаправлена вам.\n\n"
            f"<b>Тип заявки:</b> 🔄 Продление\n"
            f"<b>Клиент:</b> {user_name}\n"
            f"<b>Телефон:</b> {user_phone}\n"
            f"\n💡 <b>Рекомендация:</b> Назначьте пользователю менеджера"
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
                chat_id=admin.max_chat_id,
                text=notification_text,
                attachments=[keyboard_payload]
            )
            
            logger.info(
                f"Admin notified about unassigned user (renewal): ticket_id={ticket.id}, "
                f"admin_id={assigned_admin_id}, user_id={user.id}"
            )
        
        except Exception as e:
            logger.error(
                f"Failed to notify admin about unassigned user (renewal): "
                f"ticket_id={ticket.id}, admin_id={assigned_admin_id}, error={e}"
            )
        
        finally:
            if max_bot_instance.session:
                await max_bot_instance.session.close()
    
    except Exception as e:
        logger.error(
            f"Error in _notify_admin_about_unassigned_user_renewal: "
            f"ticket_id={ticket.id}, error={e}",
            exc_info=True
        )

async def _notify_admin_about_no_support_staff(
    session: AsyncSession,
    ticket: Ticket,
    user: User,
    assigned_admin_id: int
) -> None:
    """
    Notify admin that support ticket was redirected due to no support staff available.
    
    Args:
        session: Database session
        ticket: Created support ticket
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
        
        if not admin or not admin.max_chat_id:
            logger.warning(f"Cannot notify admin {assigned_admin_id} - no MAX chat_id")
            return
        
        user_name = user.full_name or f"{user.first_name} {user.last_name}".strip() or "Неизвестно"
        user_phone = user.phone_number or "Не указано"
        
        notification_text = (
            f"⚠️ <b>Заявка техподдержки перенаправлена администратору</b>\n\n"
            f"📋 <b>Причина:</b> В системе нет активных сотрудников техподдержки\n\n"
            f"Заявка #{ticket.id} была автоматически перенаправлена вам.\n\n"
            f"<b>Тип заявки:</b> 🛠 Техподдержка\n"
            f"<b>Клиент:</b> {user_name}\n"
            f"<b>Телефон:</b> {user_phone}\n"
        )
        
        if ticket.description:
            desc_preview = ticket.description[:150]
            if len(ticket.description) > 150:
                desc_preview += "..."
            notification_text += f"\n<b>Описание проблемы:</b>\n{desc_preview}\n"
        
        notification_text += (
            f"\n💡 <b>Рекомендация:</b> Добавьте активных сотрудников с ролью "
            f"'Техподдержка' для автоматической маршрутизации заявок техподдержки."
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
                chat_id=admin.max_chat_id,
                text=notification_text,
                attachments=[keyboard_payload]
            )
            
            logger.info(
                f"Admin notified about no support staff: ticket_id={ticket.id}, "
                f"admin_id={assigned_admin_id}, user_id={user.id}"
            )
        
        except Exception as e:
            logger.error(
                f"Failed to notify admin about no support staff: "
                f"ticket_id={ticket.id}, admin_id={assigned_admin_id}, error={e}"
            )
        
        finally:
            if max_bot_instance.session:
                await max_bot_instance.session.close()
    
    except Exception as e:
        logger.error(
            f"Error in _notify_admin_about_no_support_staff: "
            f"ticket_id={ticket.id}, error={e}",
            exc_info=True
        )