"""
Consultation Request Handler for MAX Bot

Handles consultation request flow:
- /consultation command to initiate flow
- Organization selection with pagination
- Key selection with multi-select toggle
- Description collection
- Consultation ticket creation and specialist notification

Flow is analogous to invoice flow but without delivery method selection.
Tickets are routed to TECHNICAL_SUPPORT staff with is_estimate_tech_specialist flag.
"""

import logging
from typing import Optional

from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.keyboards.tickets.consultation_kb import (
    get_consultation_description_keyboard,
    get_consultation_key_selection_keyboard,
    get_consultation_organization_keyboard,
)
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.payloads import (
    ConsultationKeyActionPayload,
    ConsultationKeyPagePayload,
    ConsultationKeyTogglePayload,
    ConsultationOrgActionPayload,
    ConsultationOrgPagePayload,
    ConsultationOrgSelectPayload,
)
from bots.max_bot.states import ConsultationStates
from bots.max_bot.texts import (
    CONSULTATION_ADD_NEW_INN,
    CONSULTATION_ADD_NEW_KEY,
    CONSULTATION_ENTER_DESCRIPTION,
    CONSULTATION_INN_ADDED,
    CONSULTATION_KEY_ADDED,
    CONSULTATION_KEY_CONFLICT,
    CONSULTATION_NO_SUBSCRIPTION,
    CONSULTATION_SELECT_KEYS,
    CONSULTATION_SELECT_ORGANIZATION,
    CONSULTATION_SUBSCRIPTION_EXPIRED,
    CONSULTATION_TICKET_CREATED,
    get_consultation_non_working_hours_message,
    ERROR_GENERAL,
    ERROR_TEXT_TOO_LONG,
    ERROR_VALIDATION_INN,
    ERROR_VALIDATION_KEY,
    FLOW_CANCELLED,
)
from database.models import KeyConflictStatus, SubscriptionStatus, TicketType, WorkMode
from services.calendar_service import get_current_work_mode
from services.ticket_service import create_ticket, route_ticket
from services.user_service import (
    KeyAlreadyOwnedByUserError,
    KeyConflictError,
    add_user_key,
    add_user_organization,
    get_user_by_max_id,
    get_user_keys,
    get_user_organizations,
)
from services.validation_service import validate_gs_key, validate_inn

logger = logging.getLogger(__name__)


# ========== Helper Functions ==========


async def _get_user_id(
    context: MemoryContext,
    max_user_id: int,
    session: AsyncSession,
    chat_id: int,
    messenger_adapter: MAXMessengerAdapter,
) -> Optional[int]:
    """Get user_id from FSM context with database fallback."""
    data = await context.get_data()
    user_id = data.get("user_id")
    if user_id:
        return user_id

    logger.warning(f"No user_id in context, falling back to DB: max_user_id={max_user_id}")
    user = await get_user_by_max_id(session, max_user_id)
    if not user:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Пользователь не найден. Пожалуйста, пройдите регистрацию командой /start",
            parse_mode="HTML",
        )
        await context.clear()
        return None

    await context.update_data(
        user_id=user.id,
        selected_inn=None,
        selected_keys=[],
        description=None,
    )
    await context.set_state(ConsultationStates.selecting_organization)
    return user.id


async def _show_main_menu(
    chat_id: int,
    max_user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Show main menu after flow completion or cancellation."""
    from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard
    from bots.max_bot.texts import MAX_MAIN_MENU_TEXT
    from services.ticket_service import get_user_active_tickets_count

    user = await get_user_by_max_id(session, max_user_id)
    if user:
        active_tickets_count = await get_user_active_tickets_count(session, user.id)
        keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=MAX_MAIN_MENU_TEXT,
            keyboard=keyboard,
            parse_mode="HTML",
        )


# ========== Entry Point ==========


async def cmd_consultation(
    event: MessageCreated | MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Handle /consultation command or callback — check subscription and initiate consultation flow.

    Subscription check:
    - ACTIVE: Proceed to organization selection
    - EXPIRED/NONE: Auto-create RENEWAL ticket to assigned manager, block consultation

    commands_info: Задать вопрос сметному специалисту
    """
    chat_id = event.message.recipient.chat_id
    from maxapi.types import MessageCallback as MCType
    max_user_id = event.callback.user.user_id if isinstance(event, MCType) else event.message.sender.user_id

    logger.info(f"User initiated consultation: max_user_id={max_user_id}, chat_id={chat_id}")

    try:
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден. Пожалуйста, пройдите регистрацию командой /start",
                parse_mode="HTML",
            )
            return

        subscription_status = user.subscription_status
        logger.info(f"Consultation subscription check: user_id={user.id}, status={subscription_status.value}")

        if subscription_status != SubscriptionStatus.ACTIVE:
            # Block consultation and auto-create RENEWAL ticket to assigned manager
            logger.info(
                f"Consultation blocked (no active subscription): user_id={user.id}, "
                f"status={subscription_status.value}"
            )
            await _create_renewal_ticket_for_consultation(
                session=session,
                messenger_adapter=messenger_adapter,
                chat_id=chat_id,
                user=user,
                subscription_status=subscription_status,
            )
            return

        # Active subscription — proceed to consultation flow
        await context.update_data(
            user_id=user.id,
            selected_inn=None,
            selected_keys=[],
            description=None,
        )
        await context.set_state(ConsultationStates.selecting_organization)

        await _show_organization_selection(
            chat_id=chat_id,
            user_id=user.id,
            page=0,
            session=session,
            messenger_adapter=messenger_adapter,
        )

    except SQLAlchemyError as e:
        logger.error(f"DB error in cmd_consultation: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Unexpected error in cmd_consultation: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


async def _create_renewal_ticket_for_consultation(
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    chat_id: int,
    user,
    subscription_status: SubscriptionStatus,
) -> None:
    """
    Create RENEWAL ticket when user without active subscription requests consultation.

    Creates a RENEWAL ticket routed to the assigned manager and notifies them.
    Shows appropriate message to the user based on subscription status.
    """
    from services.ticket_service import determine_assigned_manager, send_staff_notification
    from services.calendar_service import get_current_work_mode
    from bots.max_bot.utils.itat_logging import log_ticket_creation_to_itat
    from loaders import max_bot

    logger.info(f"Creating auto-renewal ticket for consultation block: user_id={user.id}")

    try:
        work_mode = await get_current_work_mode(session)
        is_working = work_mode != WorkMode.NON_WORKING

        assigned_staff_id, has_manager = await determine_assigned_manager(
            session=session,
            user_id=user.id,
            assign_admin_if_no_manager=True,
        )

        if not assigned_staff_id:
            logger.error(f"No staff available for auto-renewal ticket: user_id={user.id}")
            # Still show the blocking message even if ticket creation fails
            text = (
                CONSULTATION_SUBSCRIPTION_EXPIRED
                if subscription_status == SubscriptionStatus.EXPIRED
                else CONSULTATION_NO_SUBSCRIPTION
            )
            await messenger_adapter.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            return

        # Check for existing active RENEWAL ticket to avoid duplicates
        from sqlalchemy import and_, select
        from database.models import Ticket, TicketStatus

        result = await session.execute(
            select(Ticket).where(
                and_(
                    Ticket.user_id == user.id,
                    Ticket.ticket_type == TicketType.RENEWAL,
                    Ticket.ticket_status.in_([TicketStatus.NEW, TicketStatus.IN_PROGRESS]),
                )
            )
        )
        existing_ticket = result.scalar_one_or_none()

        if not existing_ticket:
            ticket_data = {
                "ticket_type": TicketType.RENEWAL,
                "user_id": user.id,
                "assigned_staff_id": assigned_staff_id,
                "description": "Запрос на продление подписки (автоматически при попытке получить консультацию)",
            }
            ticket = await create_ticket(session, ticket_data)
            await session.commit()

            logger.info(
                f"Auto-renewal ticket created: ticket_id={ticket.id}, user_id={user.id}, "
                f"assigned_staff={assigned_staff_id}"
            )

            try:
                await log_ticket_creation_to_itat(session, ticket)
            except Exception as e:
                logger.error(
                    f"Failed to log auto-renewal ticket to i-TAT: ticket_id={ticket.id}, error={e}",
                    exc_info=True,
                )

            # Notify manager during working hours
            if assigned_staff_id and is_working:
                try:
                    await send_staff_notification(
                        bot=max_bot,
                        staff_id=assigned_staff_id,
                        ticket=ticket,
                        session=session,
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to notify manager about auto-renewal ticket: "
                        f"ticket_id={ticket.id}, error={e}",
                        exc_info=True,
                    )
        else:
            logger.info(
                f"Active RENEWAL ticket already exists, skipping creation: "
                f"user_id={user.id}, ticket_id={existing_ticket.id}"
            )

        # Show blocking message to user
        text = (
            CONSULTATION_SUBSCRIPTION_EXPIRED
            if subscription_status == SubscriptionStatus.EXPIRED
            else CONSULTATION_NO_SUBSCRIPTION
        )
        await messenger_adapter.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

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
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(
            f"Error in _create_renewal_ticket_for_consultation: user_id={user.id}, error={e}",
            exc_info=True,
        )
        await session.rollback()
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


# ========== Organization Step ==========


async def _show_organization_selection(
    chat_id: int,
    user_id: int,
    page: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Display organization selection keyboard."""
    organizations = await get_user_organizations(session, user_id)
    keyboard = get_consultation_organization_keyboard(organizations, page)
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=CONSULTATION_SELECT_ORGANIZATION,
        keyboard=keyboard,
        parse_mode="HTML",
    )


async def handle_consultation_org_select(
    event: MessageCallback,
    payload: ConsultationOrgSelectPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle organization selection by INN."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")

    user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
    if not user_id:
        return

    await context.update_data(selected_inn=payload.inn)
    await context.set_state(ConsultationStates.selecting_keys)
    await _show_key_selection(chat_id, user_id, set(), 0, session, messenger_adapter)


async def handle_consultation_org_page(
    event: MessageCallback,
    payload: ConsultationOrgPagePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle organization list pagination."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")

    user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
    if not user_id:
        return

    await _show_organization_selection(chat_id, user_id, payload.page, session, messenger_adapter)


async def handle_consultation_org_action(
    event: MessageCallback,
    payload: ConsultationOrgActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle organization actions: add_new, skip, cancel."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")

    user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
    if not user_id:
        return

    if payload.action == "add_new":
        await context.set_state(ConsultationStates.adding_new_inn)
        from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_ADD_NEW_INN,
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML",
        )

    elif payload.action == "skip":
        await context.update_data(selected_inn=None)
        await context.set_state(ConsultationStates.selecting_keys)
        await _show_key_selection(chat_id, user_id, set(), 0, session, messenger_adapter)

    elif payload.action == "cancel":
        await _cancel_flow(event, context, session, messenger_adapter)


async def process_consultation_new_inn(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Process new INN input in consultation flow."""
    chat_id = event.message.recipient.chat_id
    inn = event.message.body.text.strip()

    is_valid, error_msg = validate_inn(inn)
    if not is_valid:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_INN.format(error_details=error_msg),
            parse_mode="HTML",
        )
        return

    user_id = await _get_user_id(
        context, event.message.sender.user_id, session, chat_id, messenger_adapter
    )
    if not user_id:
        return

    try:
        await add_user_organization(session, user_id, inn)
        await context.update_data(selected_inn=inn)
        await context.set_state(ConsultationStates.selecting_keys)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_INN_ADDED,
            parse_mode="HTML",
        )
        await _show_key_selection(chat_id, user_id, set(), 0, session, messenger_adapter)

    except Exception as e:
        logger.error(f"Error adding INN in consultation: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


# ========== Key Selection Step ==========


async def _show_key_selection(
    chat_id: int,
    user_id: int,
    selected_keys: set[int],
    page: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Display key selection keyboard."""
    keys = await get_user_keys(session, user_id)
    keyboard = get_consultation_key_selection_keyboard(keys, selected_keys, page)
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=CONSULTATION_SELECT_KEYS,
        keyboard=keyboard,
        parse_mode="HTML",
    )


async def handle_consultation_key_toggle(
    event: MessageCallback,
    payload: ConsultationKeyTogglePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Toggle key selection."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")

    user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
    if not user_id:
        return

    data = await context.get_data()
    selected_keys: set[int] = set(data.get("selected_keys", []))

    if payload.key_id in selected_keys:
        selected_keys.discard(payload.key_id)
    else:
        selected_keys.add(payload.key_id)

    await context.update_data(selected_keys=list(selected_keys))

    page = data.get("key_page", 0)
    await _show_key_selection(chat_id, user_id, selected_keys, page, session, messenger_adapter)


async def handle_consultation_key_page(
    event: MessageCallback,
    payload: ConsultationKeyPagePayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle key list pagination."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")

    user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
    if not user_id:
        return

    await context.update_data(key_page=payload.page)
    data = await context.get_data()
    selected_keys: set[int] = set(data.get("selected_keys", []))
    await _show_key_selection(chat_id, user_id, selected_keys, payload.page, session, messenger_adapter)


async def handle_consultation_key_action(
    event: MessageCallback,
    payload: ConsultationKeyActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle key actions: add_new, done, skip, back, back_to_keys, cancel."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")

    user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
    if not user_id:
        return

    data = await context.get_data()

    if payload.action == "add_new":
        await context.set_state(ConsultationStates.adding_new_key)
        from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_ADD_NEW_KEY,
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML",
        )

    elif payload.action in ("done", "skip"):
        await context.set_state(ConsultationStates.entering_description)
        keyboard = get_consultation_description_keyboard()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_ENTER_DESCRIPTION,
            keyboard=keyboard,
            parse_mode="HTML",
        )

    elif payload.action == "back":
        await context.set_state(ConsultationStates.selecting_organization)
        await _show_organization_selection(chat_id, user_id, 0, session, messenger_adapter)

    elif payload.action == "back_to_keys":
        await context.set_state(ConsultationStates.selecting_keys)
        selected_keys: set[int] = set(data.get("selected_keys", []))
        await _show_key_selection(chat_id, user_id, selected_keys, 0, session, messenger_adapter)

    elif payload.action == "skip_description":
        # Skip description — create ticket with empty description
        from maxapi.types import MessageCreated as MCCreated
        # Reuse process_consultation_description logic by calling it with empty text
        # We need to create ticket directly here
        await context.set_state(ConsultationStates.entering_description)
        selected_inn = data.get("selected_inn")
        selected_keys_list = data.get("selected_keys", [])
        await context.clear()
        try:
            from database.models import WorkMode
            work_mode = await get_current_work_mode(session)
            is_working = work_mode != WorkMode.NON_WORKING
            ticket_data = {
                "ticket_type": TicketType.CONSULTATION,
                "user_id": user_id,
                "organization_inn": selected_inn,
                "description": None,
                "selected_key_ids": selected_keys_list,
            }
            ticket = await create_ticket(session, ticket_data)
            await session.commit()
            try:
                from bots.max_bot.utils.itat_logging import log_ticket_creation_to_itat
                await log_ticket_creation_to_itat(session, ticket)
            except Exception as e:
                logger.error(f"Failed to log consultation ticket to i-TAT: {e}", exc_info=True)
            if is_working:
                try:
                    from celery_app.escalation_tasks import schedule_technical_support_monitoring
                    await schedule_technical_support_monitoring(ticket_id=ticket.id)
                except Exception as e:
                    logger.error(f"Failed to schedule escalation for consultation {ticket.id}: {e}", exc_info=True)
            confirmation_text = CONSULTATION_TICKET_CREATED if is_working else get_consultation_non_working_hours_message()
            await messenger_adapter.send_message(chat_id=chat_id, text=confirmation_text, parse_mode="HTML")
            if is_working:
                from services.employee_service import get_estimate_tech_specialists
                from services.ticket_service import send_staff_notification, route_ticket
                from loaders import max_bot
                routing_info = await route_ticket(session, ticket, work_mode)
                specialists = await get_estimate_tech_specialists(session)
                if specialists:
                    for specialist in specialists:
                        try:
                            await send_staff_notification(bot=max_bot, staff_id=specialist.id, ticket=ticket, routing_info=routing_info, session=session)
                        except Exception as e:
                            logger.error(f"Failed to notify specialist {specialist.id}: {e}", exc_info=True)
                else:
                    from services.escalation_service import get_active_admins
                    admins = await get_active_admins(session)
                    for admin in admins:
                        try:
                            await send_staff_notification(bot=max_bot, staff_id=admin.id, ticket=ticket, routing_info=routing_info, session=session)
                        except Exception as e:
                            logger.error(f"Failed to notify admin {admin.id}: {e}", exc_info=True)
            await _show_main_menu(chat_id, max_user_id, session, messenger_adapter)
        except Exception as e:
            logger.error(f"Error creating consultation ticket (skip_description): {e}", exc_info=True)
            await session.rollback()
            await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")

    elif payload.action == "cancel":
        await _cancel_flow(event, context, session, messenger_adapter)


async def process_consultation_new_key(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Process new key input in consultation flow."""
    chat_id = event.message.recipient.chat_id
    key_number = event.message.body.text.strip()

    is_valid, error_msg = validate_gs_key(key_number)
    if not is_valid:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_KEY.format(error_details=error_msg),
            parse_mode="HTML",
        )
        return

    user_id = await _get_user_id(
        context, event.message.sender.user_id, session, chat_id, messenger_adapter
    )
    if not user_id:
        return

    try:
        result = await add_user_key(session, user_id, key_number)

        if result and hasattr(result, "conflict_status") and result.conflict_status == KeyConflictStatus.PENDING_REVIEW:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=CONSULTATION_KEY_CONFLICT,
                parse_mode="HTML",
            )
            return

        data = await context.get_data()
        selected_keys: set[int] = set(data.get("selected_keys", []))
        if result:
            selected_keys.add(result.id)
            await context.update_data(selected_keys=list(selected_keys))

        await context.set_state(ConsultationStates.selecting_keys)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_KEY_ADDED,
            parse_mode="HTML",
        )
        await _show_key_selection(chat_id, user_id, selected_keys, 0, session, messenger_adapter)

    except KeyAlreadyOwnedByUserError:
        logger.info(f"User tried to add their own key again: key={key_number}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="ℹ️ Этот ключ уже добавлен в ваш профиль. Вы не можете добавить свой же ключ повторно.",
            parse_mode="HTML"
        )
    except KeyConflictError as e:
        logger.warning(
            f"Key conflict (DB fallback) in consultation: key={key_number}, "
            f"owner_user_id={e.existing_user_id}"
        )
        await session.commit()
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_key_conflict
            await notify_admins_key_conflict(session, user_id, key_number)
        except Exception as notify_error:
            logger.error(f"Failed to send key conflict notification: {notify_error}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_KEY_CONFLICT,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error adding key in consultation: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


# ========== Description Step ==========


async def _forward_attachments_to_staff(
    messenger_adapter: MAXMessengerAdapter,
    session: AsyncSession,
    ticket_id: int,
    staff_id: int,
    attachments: list,
    user_name: str,
) -> None:
    """
    Forward FSM attachments (photo/voice/document) to a staff member's chat.

    Called after send_staff_notification to deliver files attached by the client
    during the consultation description step. Mirrors invoice._forward_attachments_to_staff.
    """
    import uuid
    from pathlib import Path
    from database.models import Staff_Member, MAX_Messenger_Data
    from sqlalchemy import select as sa_select

    if not attachments:
        return

    stmt_staff = sa_select(Staff_Member).where(Staff_Member.id == staff_id)
    res_staff = await session.execute(stmt_staff)
    staff_member = res_staff.scalar_one_or_none()

    if not staff_member or not staff_member.max_user_id:
        logger.warning(f"Staff member not found or no MAX ID: staff_id={staff_id}")
        return

    stmt_chat = sa_select(MAX_Messenger_Data.max_chat_id).where(
        MAX_Messenger_Data.max_user_id == staff_member.max_user_id
    )
    res_chat = await session.execute(stmt_chat)
    staff_chat_id = res_chat.scalar_one_or_none()

    if not staff_chat_id:
        logger.warning(f"No MAX chat_id for staff: staff_id={staff_id}")
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
                unique_name = f"consultation_{ticket_id}_{uuid.uuid4()}.jpg"
                try:
                    local_path = await messenger_adapter.download_file(
                        file_url=file_url,
                        destination=f"media/temp/{unique_name}",
                    )
                    await messenger_adapter.send_photo(
                        chat_id=staff_chat_id,
                        photo_path=local_path,
                        caption=caption,
                        parse_mode="HTML",
                    )
                    try:
                        Path(local_path).unlink()
                    except Exception:
                        pass
                except Exception as img_error:
                    logger.error(f"Failed to send image: {img_error}")
                    await messenger_adapter.send_message(
                        chat_id=staff_chat_id,
                        text=f"{caption}\n\n📷 <a href=\"{file_url}\">Скачать изображение</a>",
                        parse_mode="HTML",
                    )

            elif att_type == "voice":
                unique_name = f"consultation_{ticket_id}_{uuid.uuid4()}.ogg"
                try:
                    local_path = await messenger_adapter.download_file(
                        file_url=file_url,
                        destination=f"media/temp/{unique_name}",
                    )
                    await messenger_adapter.send_document(
                        chat_id=staff_chat_id,
                        document_path=local_path,
                        caption=caption,
                        parse_mode="HTML",
                    )
                    try:
                        Path(local_path).unlink()
                    except Exception:
                        pass
                except Exception as voice_error:
                    logger.error(f"Failed to send voice: {voice_error}")
                    await messenger_adapter.send_message(
                        chat_id=staff_chat_id,
                        text=f"{caption}\n\n🎤 <a href=\"{file_url}\">Голосовое сообщение</a>",
                        parse_mode="HTML",
                    )

            else:
                # Documents/files — send link to avoid .bin filename issues
                await messenger_adapter.send_message(
                    chat_id=staff_chat_id,
                    text=f"{caption}\n\n📎 <a href=\"{file_url}\">Скачать файл</a>",
                    parse_mode="HTML",
                )

            logger.info(
                f"Consultation attachment forwarded to staff: ticket_id={ticket_id}, "
                f"staff_chat_id={staff_chat_id}, type={att_type}"
            )

        except Exception as e:
            logger.error(
                f"Failed to forward consultation attachment to staff: ticket_id={ticket_id}, "
                f"type={att_type}, error={e}",
                exc_info=True,
            )


async def process_consultation_description(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Process description input (text, photo, voice, document) and create consultation ticket.

    Handles attachments the same way as invoice flow:
    - Accumulates attachments in FSM context across multiple messages
    - Saves attachments to DB via save_initial_ticket_attachments
    - Forwards attachments to notified specialists after ticket creation
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id

    try:
        # Get existing attachments from context
        data = await context.get_data()
        attachments = data.get("attachments") or []

        # Handle text message
        if event.message.body and event.message.body.text:
            description = event.message.body.text.strip()

            if len(description) > 4000:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=ERROR_TEXT_TOO_LONG,
                    keyboard=get_consultation_description_keyboard(),
                    parse_mode="HTML",
                )
                return

            await context.update_data(description=description)
            logger.info(f"Consultation description stored: chat_id={chat_id}, length={len(description)}")

        # Handle attachments (photo, voice, document)
        if event.message.body and event.message.body.attachments:
            for attachment in event.message.body.attachments:
                logger.info(
                    f"Consultation description attachment: chat_id={chat_id}, "
                    f"type={attachment.type!r}, payload={attachment.payload!r}"
                )
                if attachment.type == "image":
                    photo_url = attachment.payload.url
                    caption = event.message.body.text if event.message.body else None
                    attachments.append({"type": "image", "url": photo_url, "caption": caption})
                    logger.info(f"Consultation photo attachment added: chat_id={chat_id}")

                elif attachment.type in ("voice", "audio_video_note"):
                    voice_url = attachment.payload.url if hasattr(attachment.payload, "url") else None
                    attachments.append({"type": "voice", "url": voice_url})
                    logger.info(f"Consultation voice attachment added: chat_id={chat_id}, url={voice_url}")

                elif attachment.type == "audio":
                    audio_url = attachment.payload.url if hasattr(attachment.payload, "url") else None
                    attachments.append({"type": "voice", "url": audio_url})
                    logger.info(f"Consultation audio attachment added: chat_id={chat_id}, url={audio_url}")

                elif attachment.type == "file":
                    file_url = attachment.payload.url
                    file_name = attachment.payload.name if hasattr(attachment.payload, "name") else "document"
                    from services.validation_service import classify_file_type
                    file_type = classify_file_type(file_name)
                    attachments.append({
                        "type": "document",
                        "url": file_url,
                        "file_name": file_name,
                        "file_type": file_type.value,
                    })
                    logger.info(f"Consultation document attachment added: chat_id={chat_id}, file={file_name}")

            await context.update_data(attachments=attachments)

        # Check if we have description or attachments to proceed
        updated_data = await context.get_data()
        description = updated_data.get("description")
        if not description and not attachments:
            # Nothing received yet — wait for more input
            return

        selected_inn = updated_data.get("selected_inn")
        selected_keys = updated_data.get("selected_keys", [])

        user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
        if not user_id:
            return

        # Clear FSM state before DB operations so it's not left dirty on error
        await context.clear()

        # Determine work mode before ticket creation
        work_mode = await get_current_work_mode(session)
        is_working = work_mode != WorkMode.NON_WORKING

        # Create ticket
        ticket_data = {
            "ticket_type": TicketType.CONSULTATION,
            "user_id": user_id,
            "organization_inn": selected_inn,
            "description": description or None,
            "selected_key_ids": selected_keys,
        }

        ticket = await create_ticket(session, ticket_data)
        await session.commit()

        logger.info(
            f"Consultation ticket created: ticket_id={ticket.id}, user_id={user_id}, "
            f"work_mode={work_mode.value}"
        )

        # Save attachments to DB so Celery queue task can forward them in non-working hours
        if attachments:
            try:
                from services.ticket_service import save_initial_ticket_attachments
                await save_initial_ticket_attachments(
                    session=session,
                    ticket_id=ticket.id,
                    user_id=user_id,
                    attachments=attachments,
                )
                await session.commit()
                logger.info(f"Saved {len(attachments)} attachments for consultation ticket {ticket.id}")
            except Exception as e:
                logger.error(
                    f"Failed to save attachments for consultation ticket {ticket.id}: {e}",
                    exc_info=True,
                )

        # Log ticket creation to i-TAT API
        try:
            from bots.max_bot.utils.itat_logging import log_ticket_creation_to_itat
            await log_ticket_creation_to_itat(session, ticket)
        except Exception as e:
            logger.error(
                f"Failed to log consultation ticket to i-TAT API: ticket_id={ticket.id}, error={e}",
                exc_info=True,
            )

        # Schedule escalation monitoring (same as TECHNICAL_SUPPORT)
        # Only in REGULAR/EXTENDED modes — NON_WORKING tickets wait without escalation
        if is_working:
            try:
                from celery_app.escalation_tasks import schedule_technical_support_monitoring
                task_id = await schedule_technical_support_monitoring(ticket_id=ticket.id)
                logger.info(
                    f"Consultation escalation monitoring scheduled: "
                    f"ticket_id={ticket.id}, task_id={task_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to schedule escalation monitoring for consultation ticket "
                    f"{ticket.id}: {e}",
                    exc_info=True,
                )

        # Send confirmation to user
        confirmation_text = CONSULTATION_TICKET_CREATED if is_working else get_consultation_non_working_hours_message()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=confirmation_text,
            parse_mode="HTML",
        )

        # Show main menu with "Done" button
        from services.ticket_service import get_user_active_tickets_count
        from bots.max_bot.keyboards.user.main_menu_kb import get_main_menu_inline_keyboard

        user = await get_user_by_max_id(session, max_user_id)
        if user:
            active_tickets_count = await get_user_active_tickets_count(session, user.id)
            keyboard = await get_main_menu_inline_keyboard(
                active_tickets_count, show_done_button=True
            )
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="У Вас остались вопросы?\n\nВыберите нужное действие:",
                keyboard=keyboard,
                parse_mode="HTML",
            )

        # Send notifications to estimate tech specialists (only in working hours)
        if is_working:
            from services.employee_service import get_estimate_tech_specialists
            from services.ticket_service import send_staff_notification
            from loaders import max_bot

            routing_info = await route_ticket(session, ticket, work_mode)
            specialists = await get_estimate_tech_specialists(session)

            if specialists:
                for specialist in specialists:
                    try:
                        notification_sent = await send_staff_notification(
                            bot=max_bot,
                            staff_id=specialist.id,
                            ticket=ticket,
                            routing_info=routing_info,
                            session=session,
                        )
                        if notification_sent:
                            logger.info(
                                f"Specialist notification sent: ticket_id={ticket.id}, "
                                f"staff_id={specialist.id}"
                            )
                            # Forward attachments to specialist
                            if attachments:
                                try:
                                    await _forward_attachments_to_staff(
                                        messenger_adapter=messenger_adapter,
                                        session=session,
                                        ticket_id=ticket.id,
                                        staff_id=specialist.id,
                                        attachments=attachments,
                                        user_name=user.full_name if user else "Клиент",
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to forward attachments to specialist {specialist.id}: {e}",
                                        exc_info=True,
                                    )
                        else:
                            logger.warning(
                                f"Failed to send specialist notification: "
                                f"ticket_id={ticket.id}, staff_id={specialist.id}"
                            )
                    except Exception as notify_err:
                        logger.error(
                            f"Error notifying specialist {specialist.id}: {notify_err}",
                            exc_info=True,
                        )
            else:
                # No specialists configured — fall back to admins with reason
                logger.warning(
                    f"No estimate tech specialists found for consultation ticket {ticket.id}, "
                    f"falling back to admins"
                )
                from services.escalation_service import get_active_admins
                from loaders import max_bot  # noqa: F811

                admins = await get_active_admins(session)
                for admin in admins:
                    try:
                        admin_routing_info = dict(routing_info) if routing_info else {}
                        admin_routing_info["no_specialist_reason"] = (
                            "⚠️ <b>Причина уведомления администратора:</b> "
                            "В системе не настроен ни один сметный тех. специалист. "
                            "Заявка требует ручного назначения."
                        )
                        notification_sent = await send_staff_notification(
                            bot=max_bot,
                            staff_id=admin.id,
                            ticket=ticket,
                            routing_info=admin_routing_info,
                            session=session,
                        )
                        if notification_sent and attachments:
                            try:
                                await _forward_attachments_to_staff(
                                    messenger_adapter=messenger_adapter,
                                    session=session,
                                    ticket_id=ticket.id,
                                    staff_id=admin.id,
                                    attachments=attachments,
                                    user_name=user.full_name if user else "Клиент",
                                )
                            except Exception as e:
                                logger.error(
                                    f"Failed to forward attachments to admin {admin.id}: {e}",
                                    exc_info=True,
                                )
                    except Exception as e:
                        logger.error(
                            f"Failed to notify admin {admin.id}: {e}", exc_info=True
                        )
        else:
            logger.info(
                f"Consultation ticket {ticket.id} queued — notifications deferred to working hours."
            )

    except Exception as e:
        logger.error(f"Error creating consultation ticket: {e}", exc_info=True)
        await session.rollback()
        await messenger_adapter.send_message(
            chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML"
        )


# ========== Cancel Flow ==========


async def cancel_consultation_add_inn(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle cancel button when user is adding a new INN — return to org selection."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")

    user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
    if not user_id:
        return

    await context.set_state(ConsultationStates.selecting_organization)
    await _show_organization_selection(chat_id, user_id, 0, session, messenger_adapter)


async def cancel_consultation_add_key(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle cancel button when user is adding a new key — return to key selection."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")

    user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
    if not user_id:
        return

    data = await context.get_data()
    selected_keys: set[int] = set(data.get("selected_keys", []))
    await context.set_state(ConsultationStates.selecting_keys)
    await _show_key_selection(chat_id, user_id, selected_keys, 0, session, messenger_adapter)


async def _cancel_flow(
    event: MessageCreated | MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Cancel consultation flow and show main menu."""
    chat_id = event.message.recipient.chat_id
    from maxapi.types import MessageCallback as MCType
    max_user_id = event.callback.user.user_id if isinstance(event, MCType) else event.message.sender.user_id

    await context.clear()

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=FLOW_CANCELLED,
        parse_mode="HTML",
    )
    await _show_main_menu(chat_id, max_user_id, session, messenger_adapter)
