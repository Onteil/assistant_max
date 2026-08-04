"""
Technical Support Handler for MAX Bot

Handles technical support flow including:
- /support command to initiate flow
- Organization (INN) selection with pagination
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
    get_support_organization_keyboard,
)
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.payloads import (
    RenewalActionPayload,
    SupportDescriptionNextPayload,
    SupportOrgSelectPayload,
    SupportOrgPagePayload,
    SupportOrgActionPayload,
)
from bots.max_bot.states import SupportStates
from bots.max_bot.utils.callback_utils import answer_max_callback
from bots.max_bot.texts import (
    ERROR_GENERAL,
    ERROR_TEXT_TOO_LONG,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    FLOW_CANCELLED,
    RENEWAL_STATUS_ACTIVE,
    RENEWAL_STATUS_EXPIRED,
    RENEWAL_STATUS_NONE,
    RENEWAL_TICKET_CREATED,
    SUPPORT_CREATE_TICKET,
    SUPPORT_NO_SUBSCRIPTION,
    SUPPORT_SELECT_KEY_CONTEXT,
    SUPPORT_SELECT_ORGANIZATION,
    SUPPORT_SUBSCRIPTION_EXPIRED,
    SUPPORT_TICKET_CREATED,
    SUPPORT_ROUTING_REGULAR,
    SUPPORT_ROUTING_EXTENDED,
    SUPPORT_ROUTING_NON_WORKING,
    SUPPORT_RESPONSE_TIME_REGULAR,
    SUPPORT_RESPONSE_TIME_EXTENDED,
    SUPPORT_RESPONSE_TIME_NON_WORKING,
    get_support_non_working_hours_message,
    get_renewal_non_working_hours_message,
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
from services.itat_retry_helper import call_itat_with_retry
from services.ticket_service import create_ticket, route_ticket
from services.user_service import (
    KeyAlreadyOwnedByUserError,
    add_user_organization,
    get_user_by_id,
    get_user_by_max_id,
    get_user_keys,
    get_user_organizations,
)
from services.validation_service import validate_gs_key, validate_inn

logger = logging.getLogger(__name__)


# ========== /support Command Handler ==========


async def cmd_support(
    event: MessageCreated | MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /support command or callback and validate the support subscription.

    Users without an active subscription are offered the existing renewal flow,
    which creates both RENEWAL and TECHNICAL_SUPPORT tickets.

    Args:
        event: Message or callback event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages

    commands_info: Запросить техническую поддержку

    Requirements: 3.1, 3.2, 3.3
    """
    chat_id = event.message.recipient.chat_id
    from maxapi.types import MessageCallback as MCType
    if isinstance(event, MCType):
        max_user_id = event.callback.user.user_id
    else:
        max_user_id = event.message.sender.user_id

    logger.info(f"User initiated support request: max_user_id={max_user_id}, chat_id={chat_id}")

    try:
        user = await get_user_by_max_id(session, max_user_id)

        if not user:
            logger.error(f"User not found for support request: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден. Пожалуйста, пройдите регистрацию командой /start",
                parse_mode="HTML"
            )
            return

        if user.subscription_status != SubscriptionStatus.ACTIVE:
            await context.clear()

            if user.subscription_status == SubscriptionStatus.EXPIRED:
                expiry_date = (
                    user.subscription_end_date.strftime("%d.%m.%Y")
                    if user.subscription_end_date
                    else "неизвестно"
                )
                message_text = SUPPORT_SUBSCRIPTION_EXPIRED.format(
                    expiry_date=expiry_date
                )
            else:
                message_text = SUPPORT_NO_SUBSCRIPTION

            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=message_text,
                keyboard=get_renewal_keyboard(),
                parse_mode="HTML",
            )
            logger.info(
                "Support request redirected to renewal: user_id=%s, status=%s",
                user.id,
                user.subscription_status.value,
            )
            return

        logger.info(f"Proceeding to organization selection: user_id={user.id}")

        await context.update_data(
            user_id=user.id,
            selected_inn=None,
            problem_description=None,
            attachments=[],
            selected_keys=[]
        )
        await context.set_state(SupportStates.selecting_organization)

        await show_support_organization_selection(
            chat_id=chat_id,
            user_id=user.id,
            page=0,
            session=session,
            messenger_adapter=messenger_adapter
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


# ========== Organization Selection Handlers ==========


async def show_support_organization_selection(
    chat_id: int,
    user_id: int,
    page: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    message_id: Optional[int] = None
) -> None:
    """
    Display organization selection with pagination for support flow.

    Shows user's existing organizations. Includes pagination (7 per page),
    add new INN, skip, and cancel buttons.

    Args:
        chat_id: Chat ID for sending messages
        user_id: Internal user ID (primary key)
        page: Current page number (0-indexed)
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        message_id: Optional message ID to delete before sending new one
    """
    logger.info(f"Showing support organization selection: user_id={user_id}, page={page}")

    try:
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message in show_support_organization_selection: {e}")

        organizations = await get_user_organizations(session, user_id)
        keyboard = get_support_organization_keyboard(organizations, page)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=SUPPORT_SELECT_ORGANIZATION,
            keyboard=keyboard,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(
            f"Error showing support organization selection: user_id={user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_support_org_select_callback(
    event: MessageCallback,
    payload: SupportOrgSelectPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle organization selection by INN in support flow.

    Stores the selected INN and proceeds to problem description step.

    Args:
        event: Callback event from MAX
        payload: Parsed organization selection payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    logger.info(f"Support org selected: chat_id={chat_id}, inn={payload.inn}")

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")

    try:
        await context.update_data(selected_inn=payload.inn)
        await context.set_state(SupportStates.entering_problem)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=SUPPORT_CREATE_TICKET,
            keyboard=get_problem_description_keyboard(),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(
            f"Error handling support org select: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML"
        )


async def handle_support_org_page_callback(
    event: MessageCallback,
    payload: SupportOrgPagePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle organization list pagination in support flow.

    Args:
        event: Callback event from MAX
        payload: Parsed page payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    logger.info(f"Support org page: chat_id={chat_id}, page={payload.page}")

    try:
        data = await context.get_data()
        user_id = data.get("user_id")

        if not user_id:
            logger.error(f"No user_id in context for org page: chat_id={chat_id}")
            await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
            await context.clear()
            return

        await show_support_organization_selection(
            chat_id=chat_id,
            user_id=user_id,
            page=payload.page,
            session=session,
            messenger_adapter=messenger_adapter,
            message_id=message_id
        )

    except Exception as e:
        logger.error(
            f"Error handling support org page: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


async def handle_support_org_action_callback(
    event: MessageCallback,
    payload: SupportOrgActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle organization action callbacks in support flow.

    Actions:
    - "add_new": Prompt user to enter a new INN
    - "skip": Skip organization selection, proceed to problem description
    - "cancel": Cancel the support flow and return to main menu

    Args:
        event: Callback event from MAX
        payload: Parsed action payload
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    logger.info(f"Support org action: chat_id={chat_id}, action={payload.action}")

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")

    try:
        if payload.action == "cancel":
            await cancel_support_flow(event, context, session, messenger_adapter)
            return

        if payload.action == "skip":
            logger.info(f"User skipped organization selection: chat_id={chat_id}")
            await context.update_data(selected_inn=None)
            await context.set_state(SupportStates.entering_problem)

            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=SUPPORT_CREATE_TICKET,
                keyboard=get_problem_description_keyboard(),
                parse_mode="HTML"
            )
            return

        if payload.action == "add_new":
            await context.set_state(SupportStates.adding_new_inn)

            from bots.max_bot.texts import INVOICE_ADD_NEW_INN
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_ADD_NEW_INN,
                keyboard=_get_support_add_inn_keyboard(),
                parse_mode="HTML"
            )
            return

        if payload.action == "back_to_orgs":
            # Return from adding_new_inn to organization selection
            data = await context.get_data()
            user_id = data.get("user_id")
            await context.set_state(SupportStates.selecting_organization)
            await show_support_organization_selection(
                chat_id=chat_id,
                user_id=user_id,
                page=0,
                session=session,
                messenger_adapter=messenger_adapter
            )
            return

        if payload.action == "back_from_description":
            # Return from entering_problem to organization selection
            data = await context.get_data()
            user_id = data.get("user_id")
            # Clear accumulated description so user starts fresh if they go back
            await context.update_data(problem_description=None, attachments=[])
            await context.set_state(SupportStates.selecting_organization)
            await show_support_organization_selection(
                chat_id=chat_id,
                user_id=user_id,
                page=0,
                session=session,
                messenger_adapter=messenger_adapter
            )
            return

    except Exception as e:
        logger.error(
            f"Error handling support org action: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


async def process_support_org_text_action(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle text replies on the support organization selection step."""
    chat_id = event.message.recipient.chat_id
    text = (event.message.body.text or "").strip()

    from services.yandex_gpt_service import classify_organization_step_action
    ai_action = await classify_organization_step_action(
        user_text=text,
        scenario="заявка в техническую поддержку",
    )

    if ai_action.action == "add_new_organization":
        await context.set_state(SupportStates.adding_new_inn)
        from bots.max_bot.texts import INVOICE_ADD_NEW_INN
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_ADD_NEW_INN,
            keyboard=_get_support_add_inn_keyboard(),
            parse_mode="HTML",
        )
        return

    if ai_action.action == "skip":
        await context.update_data(selected_inn=None)
        await context.set_state(SupportStates.entering_problem)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=SUPPORT_CREATE_TICKET,
            keyboard=get_problem_description_keyboard(),
            parse_mode="HTML",
        )
        return

    if ai_action.action == "cancel":
        await cancel_support_flow(event, context, session, messenger_adapter)
        return

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=(
            "Выберите организацию кнопкой, напишите «Новая организация», "
            "«Пропустить» или «Отмена»."
        ),
        parse_mode="HTML",
    )


def _get_support_add_inn_keyboard() -> "Keyboard":
    """Return a simple back/cancel keyboard for the add-INN step."""
    from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
    buttons = [[
        KeyboardButton(
            text="⬅️ Назад",
            payload=SupportOrgActionPayload(action="back_to_orgs").pack()
        ),
        KeyboardButton(
            text="❌ Отмена",
            payload=SupportOrgActionPayload(action="cancel").pack()
        )
    ]]
    return Keyboard(buttons=buttons, inline=True)


async def process_new_inn_for_support(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process new INN text input in support flow (SupportStates.adding_new_inn).

    Validates the INN, checks i-TAT API for organization name.
    If found — saves and proceeds to problem description.
    If not found — transitions to adding_org_name to ask for a short name.

    Args:
        event: Message event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    text = (event.message.body.text or "").strip() if event.message.body else ""

    logger.info(f"Processing new INN for support: chat_id={chat_id}")

    try:
        data = await context.get_data()
        user_id = data.get("user_id")

        if not user_id:
            logger.error(f"No user_id in context for new INN: chat_id={chat_id}")
            await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
            await context.clear()
            return

        # Validate INN format
        if not validate_inn(text):
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_VALIDATION_INN,
                keyboard=_get_support_add_inn_keyboard(),
                parse_mode="HTML"
            )
            return

        inn = text

        # Try to look up organization name via i-TAT API
        organization_name = None
        try:
            user = await get_user_by_id(session, user_id)
            itat_client = get_itat_client()
            org_info = await itat_client.check_inn(
                messenger="max",
                user_id=user.max_user_id if user else None,
                inn=inn,
            )
            if org_info.get("status") == "ok":
                organization_name = org_info.get("name") or org_info.get("short_name")
        except Exception as e:
            logger.warning(f"i-TAT lookup failed for INN {inn}: {e}")

        if organization_name is None:
            # INN not found in 1C — ask user for a short name
            await context.update_data(pending_inn=inn)
            await context.set_state(SupportStates.adding_org_name)

            from bots.max_bot.texts import ENTER_ORG_NAME
            from bots.max_bot.payloads import KeyContextActionPayload
            skip_kb = _get_support_org_name_keyboard()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ENTER_ORG_NAME.format(inn=inn),
                keyboard=skip_kb,
                parse_mode="HTML"
            )
            return

        # INN found — save organization and proceed
        await _save_support_inn_and_proceed(
            chat_id=chat_id,
            user_id=user_id,
            inn=inn,
            organization_name=organization_name,
            context=context,
            session=session,
            messenger_adapter=messenger_adapter
        )

    except Exception as e:
        logger.error(
            f"Error processing new INN for support: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


def _get_support_org_name_keyboard() -> "Keyboard":
    """Return keyboard for the org-name input step (skip + cancel)."""
    from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
    buttons = [
        [KeyboardButton(
            text="⏭️ Пропустить",
            payload=SupportOrgActionPayload(action="skip_org_name").pack()
        )],
        [KeyboardButton(
            text="❌ Отмена",
            payload=SupportOrgActionPayload(action="cancel").pack()
        )]
    ]
    return Keyboard(buttons=buttons, inline=True)


async def process_org_name_for_support(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process organization name text input in support flow (SupportStates.adding_org_name).

    Saves the INN with the provided short name and proceeds to problem description.

    Args:
        event: Message event from MAX
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    org_name = (event.message.body.text or "").strip() if event.message.body else ""

    logger.info(f"Processing org name for support: chat_id={chat_id}")

    try:
        data = await context.get_data()
        user_id = data.get("user_id")
        inn = data.get("pending_inn")

        if not user_id or not inn:
            logger.error(f"Missing user_id or pending_inn in context: chat_id={chat_id}")
            await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
            await context.clear()
            return

        await _save_support_inn_and_proceed(
            chat_id=chat_id,
            user_id=user_id,
            inn=inn,
            organization_name=org_name or None,
            context=context,
            session=session,
            messenger_adapter=messenger_adapter
        )

    except Exception as e:
        logger.error(
            f"Error processing org name for support: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


async def handle_support_org_name_action_callback(
    event: MessageCallback,
    payload: SupportOrgActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle action callbacks during the org-name input step.

    Actions:
    - "skip_org_name": Save INN without a name and proceed
    - "back_to_orgs": Return to organization selection
    - "cancel": Cancel the support flow
    """
    chat_id = event.message.recipient.chat_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")

    try:
        if payload.action == "cancel":
            await cancel_support_flow(event, context, session, messenger_adapter)
            return

        if payload.action == "back_to_orgs":
            data = await context.get_data()
            user_id = data.get("user_id")
            await context.set_state(SupportStates.selecting_organization)
            await show_support_organization_selection(
                chat_id=chat_id,
                user_id=user_id,
                page=0,
                session=session,
                messenger_adapter=messenger_adapter
            )
            return

        if payload.action == "skip_org_name":
            data = await context.get_data()
            user_id = data.get("user_id")
            inn = data.get("pending_inn")

            if not user_id or not inn:
                await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
                await context.clear()
                return

            await _save_support_inn_and_proceed(
                chat_id=chat_id,
                user_id=user_id,
                inn=inn,
                organization_name=None,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )

    except Exception as e:
        logger.error(
            f"Error handling support org name action: chat_id={chat_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


async def _save_support_inn_and_proceed(
    chat_id: int,
    user_id: int,
    inn: str,
    organization_name: Optional[str],
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Save INN to user's organizations and transition to problem description.

    Helper used by both process_new_inn_for_support and process_org_name_for_support.
    """
    try:
        await add_user_organization(session, user_id, inn, organization_name=organization_name)
        await session.commit()
        logger.info(f"Organization added (support): user_id={user_id}, inn={inn}, name={organization_name}")
    except IntegrityError:
        await session.rollback()
        logger.info(f"Organization already exists (support): user_id={user_id}, inn={inn}")
    except Exception as e:
        await session.rollback()
        logger.error(f"Error saving organization (support): user_id={user_id}, inn={inn}, error={e}")
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
        return

    await context.update_data(selected_inn=inn, pending_inn=None)
    await context.set_state(SupportStates.entering_problem)

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=SUPPORT_CREATE_TICKET,
        keyboard=get_problem_description_keyboard(),
        parse_mode="HTML"
    )


# ========== Subscription Renewal Handlers ==========


async def handle_renewal_callback(
    event: MessageCallback,
    payload: RenewalActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle renewal callback - create RENEWAL ticket or cancel.
    
    Actions:
    - "renew": Create RENEWAL ticket if no active ticket exists
    - "cancel": Cancel and return to main menu
    
    Checks for existing active RENEWAL tickets to prevent duplicates.
    Creates RENEWAL ticket and notifies assigned manager.
    
    Args:
        event: Callback event from MAX
        payload: RenewalActionPayload with action type
        context: FSM context for state management
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
    
    Requirements: 3.4, 3.5, 3.6
    """
    chat_id = event.message.recipient.chat_id
    # In callback events, user_id comes from event.callback.user, not event.message.sender
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Renewal callback: max_user_id={max_user_id}, chat_id={chat_id}, action={payload.action}, message_id={message_id}")
    
    try:
        # Answer callback
        if not await answer_max_callback(event):
            return
        
        # Delete old message with buttons (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Handle cancel action
        if payload.action == "cancel":
            logger.info(f"User cancelled renewal offer: max_user_id={max_user_id}")
            
            # Get user from database to show main menu
            user = await get_user_by_max_id(session, max_user_id)
            
            if not user:
                logger.error(f"User not found for renewal cancel: max_user_id={max_user_id}")
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=ERROR_GENERAL,
                    parse_mode="HTML"
                )
                return
            
            # Show main menu
            from services.ticket_service import get_user_active_tickets_count
            from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
            from database.models import RegistrationStatus
            
            if user.registration_status == RegistrationStatus.ACTIVE:
                active_tickets_count = await get_user_active_tickets_count(session, user.id)
                keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
                
                from bots.max_bot.texts import MAIN_MENU_WELCOME_TEXT
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=MAIN_MENU_WELCOME_TEXT,
                    keyboard=keyboard,
                    parse_mode="HTML"
                )
            else:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=FLOW_CANCELLED,
                    parse_mode="HTML"
                )
            return
        
        # Handle renew action
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
                    Ticket.ticket_status.in_(
                        [
                            TicketStatus.NEW,
                            TicketStatus.IN_PROGRESS,
                            TicketStatus.WAITING_CLIENT,
                        ]
                    )
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
            
            # Notify manager about duplicate attempt
            await notify_manager_about_duplicate_renewal(session, existing_ticket, user.id)
            
            # Show message with "В меню" button
            from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
            from services.ticket_service import get_user_active_tickets_count
            
            active_tickets_count = await get_user_active_tickets_count(session, user.id)
            keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"📋 У вас уже есть активная заявка на продление (#{existing_ticket.id}).\n\n"
                     f"Ожидайте ответа от менеджера.",
                parse_mode="HTML"
            )
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="Выберите нужное действие:",
                keyboard=keyboard,
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
        
        # Check current work mode for response time message
        from services.calendar_service import get_current_work_mode
        from database.models import WorkMode
        
        work_mode = await get_current_work_mode(session)
        # For RENEWAL tickets, only REGULAR mode is working hours —
        # EXTENDED has no manager available, so the ticket must be queued.
        is_working = work_mode == WorkMode.REGULAR
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
        
        # Set queue_notification_sent_at immediately for working hours tickets
        # to prevent queue processing task from picking them up.
        # For RENEWAL tickets, only REGULAR mode is working hours.
        if is_working:
            from utils.timezone_helpers import get_moscow_now_naive
            ticket.queue_notification_sent_at = get_moscow_now_naive()
            logger.info(
                f"Set queue_notification_sent_at immediately for working hours renewal ticket: ticket_id={ticket.id}"
            )
        
        await session.commit()
        
        logger.info(
            f"Renewal ticket created: ticket_id={ticket.id}, user_id={user_id}, "
            f"assigned_staff={assigned_staff_id}, has_manager={has_manager}"
        )
        
        # Log ticket creation to I-TAT API
        try:
            from bots.max_bot.utils.itat_logging import log_ticket_creation_to_itat
            await log_ticket_creation_to_itat(session, ticket)
        except Exception as e:
            # Log error but don't fail ticket creation
            logger.error(
                f"Failed to log renewal ticket to I-TAT API: ticket_id={ticket.id}, error={e}",
                exc_info=True
            )
        
        # Also create a TECHNICAL_SUPPORT ticket so the tech specialist is notified
        # alongside the renewal request to the manager (restored behaviour per tester request)
        support_ticket = None
        try:
            from services.ticket_service import check_support_staff_availability
            has_support_staff = await check_support_staff_availability(session)
            
            support_assigned_staff_id = None
            if work_mode == WorkMode.REGULAR:
                if not has_support_staff:
                    from services.escalation_service import get_active_admins
                    admins = await get_active_admins(session)
                    if admins:
                        support_assigned_staff_id = admins[0].id
            elif work_mode == WorkMode.EXTENDED:
                from services.ticket_service import _get_duty_engineer
                duty_engineer = await _get_duty_engineer(session)
                if duty_engineer:
                    support_assigned_staff_id = duty_engineer.id
                else:
                    from services.escalation_service import get_active_admins
                    admins = await get_active_admins(session)
                    if admins:
                        support_assigned_staff_id = admins[0].id
            # NON_WORKING: support_assigned_staff_id stays None (queued)
            
            support_ticket_data = {
                "ticket_type": TicketType.TECHNICAL_SUPPORT,
                "user_id": user_id,
                "assigned_staff_id": support_assigned_staff_id,
                "description": "Запрос техподдержки (создан вместе с заявкой на продление подписки)"
            }
            support_ticket = await create_ticket(session, support_ticket_data)
            
            # Set queue_notification_sent_at immediately for working hours tickets
            # to prevent queue processing task from picking them up
            if work_mode != WorkMode.NON_WORKING:
                from utils.timezone_helpers import get_moscow_now_naive
                support_ticket.queue_notification_sent_at = get_moscow_now_naive()
                logger.info(
                    f"Set queue_notification_sent_at immediately for working hours support ticket: ticket_id={support_ticket.id}"
                )
            
            await session.commit()
            
            logger.info(
                f"Support ticket created alongside renewal: support_ticket_id={support_ticket.id}, "
                f"renewal_ticket_id={ticket.id}, user_id={user_id}"
            )
            
            try:
                await log_ticket_creation_to_itat(session, support_ticket)
            except Exception as e:
                logger.error(
                    f"Failed to log support ticket to I-TAT API: ticket_id={support_ticket.id}, error={e}",
                    exc_info=True
                )
            
            if work_mode != WorkMode.NON_WORKING:
                try:
                    from celery_app.escalation_tasks import schedule_technical_support_monitoring
                    await schedule_technical_support_monitoring(ticket_id=support_ticket.id)
                except Exception as e:
                    logger.error(
                        f"Failed to schedule monitoring for support ticket {support_ticket.id}: {e}",
                        exc_info=True
                    )
        except Exception as e:
            logger.error(
                f"Failed to create support ticket alongside renewal: user_id={user_id}, error={e}",
                exc_info=True
            )
            # Don't fail the whole flow — renewal ticket was already created
        
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
        
        # Send success message to user based on working hours
        if is_working:
            # Working hours - standard message
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=RENEWAL_TICKET_CREATED.format(
                    ticket_id=ticket.id,
                    manager_name=manager_name,
                    manager_position=manager_position
                ),
                parse_mode="HTML"
            )
        else:
            # Non-working hours - friendly message
            from bots.max_bot.texts import get_renewal_non_working_hours_message
            
            # Show ticket creation confirmation first
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"✅ <b>Заявка на продление создана!</b>\n\nНомер заявки: #{ticket.id}",
                parse_mode="HTML"
            )
            
            # Then show non-working hours message
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=get_renewal_non_working_hours_message(),
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
        
        # Send notifications based on working hours
        from services.ticket_service import send_staff_notification
        from loaders import max_bot
        
        if assigned_staff_id and is_working:
            # Send notification only during working hours
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
        elif assigned_staff_id and not is_working:
            # Non-working hours - ticket queued, notifications will be sent at 9 AM
            logger.info(
                f"Renewal ticket queued for next working period: ticket_id={ticket.id}, "
                f"staff_id={assigned_staff_id}, work_mode={work_mode.value}"
            )
        
        # Notify support staff about the TECHNICAL_SUPPORT ticket (if created)
        if support_ticket and is_working:
            try:
                # Round-robin: assign to the next support staff member in rotation
                from services.round_robin_service import get_next_support_staff

                assigned_rr_staff = await get_next_support_staff(session)

                if assigned_rr_staff:
                    # Persist the assignment on the support ticket
                    support_ticket.assigned_staff_id = assigned_rr_staff.id
                    await session.commit()

                    try:
                        await send_staff_notification(
                            bot=max_bot,
                            staff_id=assigned_rr_staff.id,
                            ticket=support_ticket,
                            routing_info={"expected_response_time": "в течение рабочего дня"},
                            session=session
                        )
                        logger.info(
                            f"Support staff notified for renewal support ticket (round-robin): "
                            f"ticket_id={support_ticket.id}, staff_id={assigned_rr_staff.id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to notify support staff about renewal support ticket: "
                            f"ticket_id={support_ticket.id}, staff_id={assigned_rr_staff.id}, error={e}",
                            exc_info=True
                        )
                else:
                    # No support staff — notify admins
                    from services.escalation_service import get_active_admins
                    admins = await get_active_admins(session)
                    for admin in admins:
                        try:
                            await send_staff_notification(
                                bot=max_bot,
                                staff_id=admin.id,
                                ticket=support_ticket,
                                routing_info={"expected_response_time": "в течение рабочего дня"},
                                session=session
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to notify admin about renewal support ticket: "
                                f"ticket_id={support_ticket.id}, admin_id={admin.id}, error={e}",
                                exc_info=True
                            )
            except Exception as e:
                logger.error(
                    f"Failed to send support staff notifications for renewal support ticket: "
                    f"ticket_id={support_ticket.id}, error={e}",
                    exc_info=True
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

    Accumulates description and attachments in FSM context across multiple messages.
    Shows updated keyboard with "Далее" button after first message received.
    User must click "Далее" to proceed to key context selection.

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
        has_description = bool(data.get("problem_description"))

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
                    text=ERROR_TEXT_TOO_LONG.format(max_length=4000, actual_length=len(text)),
                    keyboard=get_problem_description_keyboard(has_content=has_description or bool(attachments)),
                    parse_mode="HTML"
                )
                return

            # Append to existing description (user may send multiple messages)
            existing_description = data.get("problem_description") or ""
            combined = (existing_description + "\n" + text).strip() if existing_description else text
            await context.update_data(problem_description=combined)
            has_description = True

            logger.info(f"Problem description stored: user_id={user_id}, length={len(combined)}")

        # Handle photo attachment
        if event.message.body and event.message.body.attachments:
            for attachment in event.message.body.attachments:
                logger.info(
                    f"Support description attachment: chat_id={chat_id}, "
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

                    logger.info(f"Photo attachment added: user_id={user_id}, url={photo_url}")

                elif attachment.type in ("voice", "audio_video_note"):
                    voice_url = attachment.payload.url if hasattr(attachment.payload, 'url') else None

                    attachments.append({
                        "type": "voice",
                        "url": voice_url
                    })

                    logger.info(f"Voice attachment added: user_id={user_id}, url={voice_url}")

                elif attachment.type == "audio":
                    audio_url = attachment.payload.url if hasattr(attachment.payload, 'url') else None

                    attachments.append({
                        "type": "voice",
                        "url": audio_url
                    })

                    logger.info(f"Audio attachment added: user_id={user_id}, url={audio_url}")

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

                    logger.info(
                        f"Document attachment added: user_id={user_id}, "
                        f"file_name={file_name}, file_type={file_type.value}"
                    )

            # Update attachments in context
            await context.update_data(attachments=attachments)

        # Check if we received any content in this message
        has_content = has_description or bool(attachments)

        if has_content:
            # Show confirmation with updated keyboard (now with "Далее" button)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="✅ Принято. Можете добавить ещё сообщения или нажмите «Далее» для продолжения.",
                keyboard=get_problem_description_keyboard(has_content=True),
                parse_mode="HTML"
            )
        else:
            # Still waiting for description
            logger.info(f"No content received yet: chat_id={chat_id}")

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


async def handle_support_description_next(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Далее" button click in support description step.

    Transitions to key context selection after user confirms
    they are done entering problem description and attachments.

    Requirements: 3.7, 3.8
    """
    chat_id = event.message.recipient.chat_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    logger.info(f"Support description next: chat_id={chat_id}")

    try:
        data = await context.get_data()
        user_id = data.get("user_id")
        problem_description = data.get("problem_description")
        attachments = data.get("attachments") or []

        if not user_id:
            logger.error(f"No user_id in context for description next: chat_id={chat_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_GENERAL,
                parse_mode="HTML"
            )
            await context.clear()
            return

        if not problem_description and not attachments:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="⚠️ Пожалуйста, введите описание или прикрепите файл перед тем как продолжить.",
                keyboard=get_problem_description_keyboard(has_content=False),
                parse_mode="HTML"
            )
            return

        # Delete old message with buttons
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete support description message: {e}")

        # Proceed to key context selection
        await context.set_state(SupportStates.selecting_key_context)

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
            f"Error handling support description next: chat_id={chat_id}, error={e}",
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
            
            from bots.max_bot.texts import MAIN_MENU_WELCOME_TEXT
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=MAIN_MENU_WELCOME_TEXT,
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
        if not await answer_max_callback(event):
            return
        
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
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⚠️ Ключ <code>{key.key_number}</code> находится на проверке "
                        "конфликта и пока не может быть выбран."
                    ),
                    parse_mode="HTML",
                )
                await show_key_context_selection(
                    chat_id=chat_id,
                    user_id=user_id,
                    selected_keys=selected_keys,
                    page=data.get("key_page", 0),
                    session=session,
                    messenger_adapter=messenger_adapter,
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
            
            # Check if user already has content from a previous visit to this step
            ctx_data = await context.get_data()
            has_content = bool(ctx_data.get("problem_description")) or bool(ctx_data.get("attachments"))
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=SUPPORT_CREATE_TICKET,
                keyboard=get_problem_description_keyboard(has_content=has_content),
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
            text=ERROR_VALIDATION_KEY.format(error_details=result),
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
        
        from services.key_conflict_service import add_key_with_conflict_handling

        key_result = await add_key_with_conflict_handling(
            session=session,
            user=user,
            key_number=normalized_key,
        )
        conflict_status = (
            KeyConflictStatus.PENDING_REVIEW
            if key_result.has_conflict
            else KeyConflictStatus.NONE
        )

        if not key_result.has_conflict:
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
            if assets_response is None:
                logger.warning(
                    "update_user_assets queued for retry: user_id=%s, key=%s",
                    user.id,
                    normalized_key,
                )

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
    
    except KeyAlreadyOwnedByUserError:
        logger.info(f"User tried to add their own key again: key={key_number}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="ℹ️ Этот ключ уже добавлен в ваш профиль. Вы не можете добавить свой же ключ повторно.",
            parse_mode="HTML"
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

    Called after send_staff_notification to deliver files that were attached
    by the client during the support flow description step.

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
                unique_name = f"support_{ticket_id}_{uuid.uuid4()}.jpg"
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
                unique_name = f"support_{ticket_id}_{uuid.uuid4()}.ogg"
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
                f"Attachment forwarded to staff: ticket_id={ticket_id}, "
                f"staff_chat_id={staff_chat_id}, type={att_type}"
            )

        except Exception as e:
            logger.error(
                f"Failed to forward attachment to staff: ticket_id={ticket_id}, "
                f"type={att_type}, error={e}",
                exc_info=True
            )


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
        problem_description = data.get("problem_description") or ""
        attachments = data.get("attachments") or []
        selected_keys = data.get("selected_keys") or []
        selected_inn = data.get("selected_inn")
        
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
            "organization_inn": selected_inn,
            "description": full_description,
            "selected_key_ids": selected_keys
        }
        
        ticket = await create_ticket(session, ticket_data)
        
        # Set queue_notification_sent_at immediately for working hours tickets
        # to prevent queue processing task from picking them up
        if work_mode != WorkMode.NON_WORKING:
            from utils.timezone_helpers import get_moscow_now_naive
            ticket.queue_notification_sent_at = get_moscow_now_naive()
            logger.info(
                f"Set queue_notification_sent_at immediately for working hours support ticket: ticket_id={ticket.id}"
            )
        
        # Store attachments in ticket (if needed, extend ticket model)
        # For now, attachments are included in description
        
        await session.commit()
        
        logger.info(
            f"Support ticket created: ticket_id={ticket.id}, user_id={user_id}, "
            f"work_mode={work_mode.value}, assigned_staff={assigned_staff_id}, "
            f"has_support_staff={has_support_staff}"
        )
        
        # Save description and attachments to DB so they appear in ticket history
        # and Celery queue task can forward attachments in non-working hours
        if problem_description or attachments:
            logger.info(
                f"Calling save_initial_ticket_attachments: ticket_id={ticket.id}, "
                f"user_id={user_id}, attachments_count={len(attachments)}, has_description={bool(problem_description)}"
            )
            try:
                from services.ticket_service import save_initial_ticket_attachments
                await save_initial_ticket_attachments(
                    session=session,
                    ticket_id=ticket.id,
                    user_id=user_id,
                    attachments=attachments,
                    description=problem_description,
                )
                await session.commit()
                logger.info(f"Successfully saved and committed ticket data for ticket_id={ticket.id}")
            except Exception as e:
                logger.error(
                    f"Failed to save initial ticket data for support ticket: "
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
                f"Failed to log support ticket to I-TAT API: ticket_id={ticket.id}, error={e}",
                exc_info=True
            )
        
        # Schedule 10-minute escalation check for technical support tickets
        # Only in REGULAR/EXTENDED modes - NON_WORKING tickets wait without escalation
        # NOTE: scheduling is deferred to AFTER the notification block so that
        # ticket.assigned_staff_id is committed before the escalation task fires.
        _schedule_escalation = work_mode != WorkMode.NON_WORKING
        
        # Clear FSM state
        await context.clear()
        
        # Prepare routing and response time messages based on work mode
        routing_messages = {
            WorkMode.REGULAR: SUPPORT_ROUTING_REGULAR,
            WorkMode.EXTENDED: SUPPORT_ROUTING_EXTENDED,
            WorkMode.NON_WORKING: ""  # NON_WORKING info is fully covered by response_time_message
        }
        
        response_time_messages = {
            WorkMode.REGULAR: SUPPORT_RESPONSE_TIME_REGULAR,
            WorkMode.EXTENDED: SUPPORT_RESPONSE_TIME_EXTENDED,
            WorkMode.NON_WORKING: None  # Will be handled separately
        }
        
        # Get response time message based on work mode
        if work_mode == WorkMode.NON_WORKING:
            # Non-working hours: show queue message instead of standard template
            from bots.max_bot.texts import get_support_non_working_hours_message
            message_text = get_support_non_working_hours_message(ticket.id)
        else:
            # Working hours: use standard template
            response_time_message = response_time_messages[work_mode]
            message_text = SUPPORT_TICKET_CREATED.format(
                ticket_id=ticket.id,
                routing_message=routing_messages[work_mode],
                response_time_message=response_time_message
            )
        
        # Send success message to user
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
        
        # Send notifications based on work mode and staff availability
        from services.ticket_service import send_staff_notification
        from loaders import max_bot
        
        if work_mode == WorkMode.REGULAR:
            if has_support_staff:
                # Round-robin: assign to the next support staff member in rotation
                from services.round_robin_service import get_next_support_staff

                assigned_rr_staff = await get_next_support_staff(session)

                if assigned_rr_staff:
                    # Persist the assignment on the ticket
                    ticket.assigned_staff_id = assigned_rr_staff.id
                    await session.commit()

                    try:
                        notification_sent = await send_staff_notification(
                            bot=max_bot,
                            staff_id=assigned_rr_staff.id,
                            ticket=ticket,
                            routing_info={
                                "work_mode": work_mode.value,
                                "expected_response_time": "в течение рабочего дня"
                            },
                            session=session
                        )

                        if notification_sent:
                            logger.info(
                                f"Support staff notification sent (round-robin): "
                                f"ticket_id={ticket.id}, staff_id={assigned_rr_staff.id}"
                            )
                            
                            # Mark as notified to prevent queue processing
                            from utils.timezone_helpers import get_moscow_now_naive
                            ticket.queue_notification_sent_at = get_moscow_now_naive()
                            await session.commit()
                            
                        else:
                            logger.warning(
                                f"Failed to send support staff notification (round-robin): "
                                f"ticket_id={ticket.id}, staff_id={assigned_rr_staff.id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to send support staff notification: "
                            f"ticket_id={ticket.id}, staff_id={assigned_rr_staff.id}, error={e}",
                            exc_info=True
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
                    
                    # Mark as notified to prevent queue processing
                    from utils.timezone_helpers import get_moscow_now_naive
                    ticket.queue_notification_sent_at = get_moscow_now_naive()
                    await session.commit()
                    
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
                    
                    # Mark as notified to prevent queue processing
                    from utils.timezone_helpers import get_moscow_now_naive
                    ticket.queue_notification_sent_at = get_moscow_now_naive()
                    await session.commit()
                    
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
                    
                    # Mark as notified to prevent queue processing
                    from utils.timezone_helpers import get_moscow_now_naive
                    ticket.queue_notification_sent_at = get_moscow_now_naive()
                    await session.commit()
                    
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
        
        # Forward attachments to all notified staff (if any)
        if attachments and work_mode != WorkMode.NON_WORKING:
            # Collect staff IDs that were notified
            # After round-robin, ticket.assigned_staff_id holds the chosen staff member.
            notified_staff_ids: list[int] = []

            if work_mode == WorkMode.REGULAR:
                # Round-robin assigns exactly one staff member; use that ID.
                if ticket.assigned_staff_id:
                    notified_staff_ids = [ticket.assigned_staff_id]
                elif assigned_staff_id:
                    notified_staff_ids = [assigned_staff_id]
            elif work_mode == WorkMode.EXTENDED:
                if assigned_staff_id:
                    notified_staff_ids = [assigned_staff_id]

            user_name = user.full_name or user.phone_number or "Клиент"

            for sid in notified_staff_ids:
                try:
                    await _forward_attachments_to_staff(
                        messenger_adapter=messenger_adapter,
                        session=session,
                        ticket_id=ticket.id,
                        staff_id=sid,
                        attachments=attachments,
                        user_name=user_name
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to forward attachments to staff {sid}: {e}",
                        exc_info=True
                    )

        # Schedule escalation monitoring AFTER round-robin assignment is committed
        # so the escalation task sees the correct assigned_staff_id.
        if _schedule_escalation:
            try:
                from celery_app.escalation_tasks import schedule_technical_support_monitoring
                task_id = await schedule_technical_support_monitoring(ticket_id=ticket.id)
                logger.info(
                    f"Technical support monitoring scheduled: ticket_id={ticket.id}, "
                    f"task_id={task_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to schedule technical support monitoring for ticket {ticket.id}: {e}",
                    exc_info=True
                )
                logger.warning(
                    f"Ticket {ticket.id} created without escalation monitoring. "
                    f"Manual intervention may be required."
                )
        else:
            logger.info(
                f"Technical support ticket {ticket.id} created in NON_WORKING mode - "
                f"escalation not scheduled (will be processed in next working period)"
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
                chat_id=chat_id,
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
                chat_id=chat_id,
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


async def notify_manager_about_duplicate_renewal(
    session: AsyncSession,
    existing_ticket: Ticket,
    user_id: int
) -> None:
    """
    Notify manager about user's attempt to create duplicate renewal ticket.
    
    Sends notification to the manager assigned to the existing renewal ticket
    with a button to open the ticket card.
    
    Args:
        session: Database session
        existing_ticket: The existing active renewal ticket
        user_id: User ID who attempted to create duplicate ticket
    
    Requirements: Manager notification for duplicate renewal attempts
    """
    try:
        from loaders import max_bot
        from bots.max_bot.handlers.staff.manager import format_ticket_card_detailed, get_ticket_action_keyboard
        from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
        from bots.max_bot.payloads import ManagerTicketActionPayload
        from database.models import Staff_Member
        from sqlalchemy import select
        
        # Load ticket relationships for proper formatting
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == existing_ticket.id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys),
            selectinload(Ticket.assigned_staff)
        )
        result = await session.execute(stmt)
        ticket_with_relations = result.scalar_one_or_none()
        
        if not ticket_with_relations:
            logger.warning(f"Ticket not found: {existing_ticket.id}")
            return
        
        # Try assigned staff first, fallback to any admin with max_chat_id
        staff_member = None
        staff_chat_id = None
        if existing_ticket.assigned_staff_id:
            stmt = select(Staff_Member).where(Staff_Member.id == existing_ticket.assigned_staff_id)
            result = await session.execute(stmt)
            candidate = result.scalar_one_or_none()
            if candidate:
                # Try direct max_chat_id first
                if candidate.max_chat_id:
                    staff_member = candidate
                    staff_chat_id = candidate.max_chat_id
                elif candidate.max_user_id:
                    # Fallback: look up chat_id from MAX_Messenger_Data by max_user_id
                    from database.models import MAX_Messenger_Data
                    stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                        MAX_Messenger_Data.max_user_id == candidate.max_user_id
                    )
                    result_chat = await session.execute(stmt_chat)
                    resolved_chat_id = result_chat.scalar_one_or_none()
                    if resolved_chat_id:
                        staff_member = candidate
                        staff_chat_id = resolved_chat_id
                    else:
                        logger.warning(
                            f"Assigned staff has no MAX chat ID in staff_members or max_messenger_data: "
                            f"staff_id={existing_ticket.assigned_staff_id}, "
                            f"max_user_id={candidate.max_user_id}, falling back to admin"
                        )
                else:
                    logger.warning(
                        f"Assigned staff not found or no MAX chat ID: "
                        f"staff_id={existing_ticket.assigned_staff_id}, falling back to admin"
                    )
        
        if not staff_member:
            # Fallback: find any admin with max_chat_id or resolvable via MAX_Messenger_Data
            from database.models import StaffRole, MAX_Messenger_Data
            stmt = select(Staff_Member).where(
                Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
                Staff_Member.is_active == True  # noqa: E712
            ).limit(5)
            result = await session.execute(stmt)
            admin_candidates = result.scalars().all()
            for admin_candidate in admin_candidates:
                if admin_candidate.max_chat_id:
                    staff_member = admin_candidate
                    staff_chat_id = admin_candidate.max_chat_id
                    break
                elif admin_candidate.max_user_id:
                    stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                        MAX_Messenger_Data.max_user_id == admin_candidate.max_user_id
                    )
                    result_chat = await session.execute(stmt_chat)
                    resolved_chat_id = result_chat.scalar_one_or_none()
                    if resolved_chat_id:
                        staff_member = admin_candidate
                        staff_chat_id = resolved_chat_id
                        break
        
        if not staff_member or not staff_chat_id:
            logger.error(
                f"No staff available to notify about duplicate renewal: "
                f"ticket_id={existing_ticket.id}"
            )
            return
        
        # Format ticket card
        ticket_card = format_ticket_card_detailed(ticket_with_relations)
        
        # Create notification message
        notification_text = (
            f"🔔 <b>Повторная попытка создания заявки на продление</b>\n\n"
            f"Пользователь повторно нажал кнопку \"Продлить\", но у него уже есть активная заявка:\n\n"
            f"{ticket_card}"
        )
        
        # Create keyboard with "Go to ticket" button (using history action to show ticket details)
        keyboard = Keyboard(
            buttons=[[
                KeyboardButton(
                    text="📋 Перейти к заявке",
                    payload=ManagerTicketActionPayload(
                        action="history", 
                        ticket_id=existing_ticket.id
                    ).pack()
                )
            ]],
            inline=True
        )
        
        # Send notification to manager
        messenger_adapter = MAXMessengerAdapter(max_bot)
        await messenger_adapter.send_message(
            chat_id=staff_chat_id,
            text=notification_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Duplicate renewal notification sent: "
            f"ticket_id={existing_ticket.id}, staff_id={existing_ticket.assigned_staff_id}, "
            f"user_id={user_id}"
        )
    
    except Exception as e:
        logger.error(
            f"Error sending duplicate renewal notification: "
            f"ticket_id={existing_ticket.id}, user_id={user_id}, error={e}",
            exc_info=True
        )
