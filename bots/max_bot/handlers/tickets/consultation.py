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
    ConsultationDescriptionNextPayload,
)
from bots.max_bot.states import ConsultationStates
from bots.max_bot.texts import (
    CONSULTATION_ADD_NEW_INN,
    CONSULTATION_ADD_NEW_KEY,
    CONSULTATION_ENTER_DESCRIPTION,
    CONSULTATION_INN_ADDED,
    CONSULTATION_INN_DUPLICATE,
    CONSULTATION_KEY_ADDED,
    CONSULTATION_KEY_CONFLICT,
    CONSULTATION_NO_SUBSCRIPTION,
    CONSULTATION_RENEWAL_ALREADY_EXISTS_EXPIRED,
    CONSULTATION_RENEWAL_ALREADY_EXISTS_NO_SUBSCRIPTION,
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
from database.models import (
    KeyConflictStatus,
    SubscriptionStatus,
    TicketType,
    User,
    WorkMode,
)
from services.calendar_service import get_current_work_mode
from services.ticket_service import create_ticket, route_ticket
from services.user_service import (
    KeyAlreadyOwnedByUserError,
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
        # For RENEWAL tickets, only REGULAR mode is working hours —
        # EXTENDED has no manager available, so the ticket must be queued.
        is_working = work_mode == WorkMode.REGULAR

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
                    Ticket.ticket_status.in_([
                        TicketStatus.NEW,
                        TicketStatus.IN_PROGRESS,
                        TicketStatus.WAITING_CLIENT,
                    ]),
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
            
            # Set queue_notification_sent_at immediately for working hours tickets
            # to prevent queue processing task from picking them up
            if is_working:
                from utils.timezone_helpers import get_moscow_now_naive
                ticket.queue_notification_sent_at = get_moscow_now_naive()
                logger.info(
                    f"Set queue_notification_sent_at immediately for working hours auto-renewal ticket: ticket_id={ticket.id}"
                )
            
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
                    notification_sent = await send_staff_notification(
                        bot=max_bot,
                        staff_id=assigned_staff_id,
                        ticket=ticket,
                        session=session,
                    )
                    
                    if notification_sent:
                        # No need to set queue_notification_sent_at here - already set at ticket creation
                        pass
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

            # Notify manager that user is trying to get consultation again
            # while renewal ticket is already open
            try:
                from bots.max_bot.handlers.tickets.support import notify_manager_about_duplicate_renewal
                await notify_manager_about_duplicate_renewal(session, existing_ticket, user.id)
            except Exception as e:
                logger.error(
                    f"Failed to notify manager about duplicate renewal attempt from consultation: "
                    f"ticket_id={existing_ticket.id}, error={e}",
                    exc_info=True,
                )

        # Show blocking message to user — different text if ticket already existed
        if existing_ticket:
            text = (
                CONSULTATION_RENEWAL_ALREADY_EXISTS_EXPIRED.format(ticket_id=existing_ticket.id)
                if subscription_status == SubscriptionStatus.EXPIRED
                else CONSULTATION_RENEWAL_ALREADY_EXISTS_NO_SUBSCRIPTION.format(ticket_id=existing_ticket.id)
            )
        else:
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
            if existing_ticket:
                # Duplicate case: compact menu prompt (same as handle_renewal_callback)
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="Выберите нужное действие:",
                    keyboard=keyboard,
                    parse_mode="HTML",
                )
            else:
                # New ticket case: full welcome text with menu
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


async def process_consultation_org_text_action(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle text replies on the consultation organization selection step."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    text = (event.message.body.text or "").strip()

    user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
    if not user_id:
        return

    from services.yandex_gpt_service import classify_organization_step_action
    ai_action = await classify_organization_step_action(
        user_text=text,
        scenario="сметная консультация",
    )

    if ai_action.action == "add_new_organization":
        await context.set_state(ConsultationStates.adding_new_inn)
        from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_ADD_NEW_INN,
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    if ai_action.action == "skip":
        await context.update_data(selected_inn=None)
        await context.set_state(ConsultationStates.selecting_keys)
        await _show_key_selection(chat_id, user_id, set(), 0, session, messenger_adapter)
        return

    if ai_action.action == "cancel":
        await _cancel_flow(event, context, session, messenger_adapter)
        return

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=(
            "Выберите организацию кнопкой, напишите «Новая организация», "
            "«Пропустить» или «Отмена»."
        ),
        parse_mode="HTML",
    )


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
        from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_VALIDATION_INN.format(error_details=error_msg),
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    user_id = await _get_user_id(
        context, event.message.sender.user_id, session, chat_id, messenger_adapter
    )
    if not user_id:
        return

    # Check for duplicate INN before adding
    existing_organizations = await get_user_organizations(session, user_id)
    existing_inns = [org.inn for org in existing_organizations]
    if inn in existing_inns:
        logger.info(f"Duplicate INN detected locally: user_id={user_id}, inn={inn}")
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_INN_DUPLICATE,
            parse_mode="HTML",
        )
        # Treat as if INN was just added — proceed to key selection
        await context.update_data(selected_inn=inn)
        await context.set_state(ConsultationStates.selecting_keys)
        await _show_key_selection(chat_id, user_id, set(), 0, session, messenger_adapter)
        return

    # Check INN with i-TAT API and get organization name
    from services.i_tat_service import get_itat_client
    from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
    organization_name: str | None = None
    try:
        user = await get_user_by_max_id(session, event.message.sender.user_id)
        itat_client = get_itat_client()
        api_response = await itat_client.check_inn(
            messenger="max",
            user_id=user.max_user_id if user else None,
            inn=inn,
        )
        logger.info(f"i-TAT API INN check successful: {api_response}")

        exists = api_response.get("exists")
        organization_name = api_response.get("name")

        if exists is False:
            logger.info(f"INN not found in 1C, requesting org name: inn={inn}")
            from bots.max_bot.texts import ENTER_ORG_NAME
            from bots.max_bot.keyboards.user.registration_kb import get_skip_keyboard
            await context.update_data(pending_inn=inn)
            await context.set_state(ConsultationStates.adding_org_name)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ENTER_ORG_NAME.format(inn=inn),
                keyboard=get_skip_keyboard(),
                parse_mode="HTML",
            )
            return

        # Legacy fallback
        if exists is None and not api_response.get("is_valid", True):
            error_details = api_response.get("error_message", "ИНН не найден в базе данных")
            logger.warning(f"INN rejected by i-TAT API: inn={inn}, reason={error_details}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Ошибка проверки ИНН</b>\n\n{error_details}\n\nПроверьте правильность введённого ИНН и попробуйте снова.",
                keyboard=get_cancel_keyboard(),
                parse_mode="HTML",
            )
            return

    except Exception as api_error:
        logger.error(f"i-TAT API INN check error: {api_error}", exc_info=True)
        # Continue with local validation if API fails

    try:
        await add_user_organization(session, user_id, inn, organization_name=organization_name)
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


async def process_consultation_org_name(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Process optional org name input after INN not found in 1C (consultation flow).
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
            parse_mode="HTML",
        )
        return

    data = await context.get_data()
    inn = data.get("pending_inn")
    user_id = await _get_user_id(
        context, event.message.sender.user_id, session, chat_id, messenger_adapter
    )
    if not inn or not user_id:
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
        await context.clear()
        return

    await _finalize_consultation_inn(chat_id, user_id, inn, org_name, context, session, messenger_adapter)


async def skip_consultation_org_name(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Handle skip button during org name step in consultation flow.
    Saves INN without a name and proceeds to key selection.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete old message: {e}")

    data = await context.get_data()
    inn = data.get("pending_inn")
    user_id = await _get_user_id(
        context, max_user_id, session, chat_id, messenger_adapter
    )
    if not inn or not user_id:
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
        await context.clear()
        return

    await _finalize_consultation_inn(chat_id, user_id, inn, None, context, session, messenger_adapter)


async def _finalize_consultation_inn(
    chat_id: int,
    user_id: int,
    inn: str,
    organization_name: str | None,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Save INN (with optional name) and proceed to key selection."""
    try:
        await add_user_organization(session, user_id, inn, organization_name=organization_name)
        await context.update_data(selected_inn=inn)
        await context.set_state(ConsultationStates.selecting_keys)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_INN_ADDED,
            parse_mode="HTML",
        )
        await _show_key_selection(chat_id, user_id, set(), 0, session, messenger_adapter)

    except Exception as e:
        logger.error(f"Error in _finalize_consultation_inn: inn={inn}, error={e}", exc_info=True)
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

    keys = await get_user_keys(session, user_id)
    key = next((item for item in keys if item.id == payload.key_id), None)
    if not key:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ERROR_GENERAL,
            parse_mode="HTML",
        )
        return
    if key.conflict_status == KeyConflictStatus.PENDING_REVIEW:
        logger.warning(
            "Attempted to select PENDING_REVIEW consultation key: key_id=%s",
            payload.key_id,
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ Ключ <code>{key.key_number}</code> находится на проверке "
                "конфликта и пока не может быть выбран."
            ),
            parse_mode="HTML",
        )
        await _show_key_selection(
            chat_id,
            user_id,
            selected_keys,
            data.get("key_page", 0),
            session,
            messenger_adapter,
        )
        return

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
        # Check if user already has content from a previous visit to this step
        ctx_data = await context.get_data()
        has_content = bool(ctx_data.get("description")) or bool(ctx_data.get("attachments"))
        keyboard = get_consultation_description_keyboard(has_content=has_content)
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

            # Determine assigned staff BEFORE creating the ticket (same pattern as TECHNICAL_SUPPORT)
            assigned_staff_id = None
            if work_mode == WorkMode.REGULAR:
                from services.round_robin_service import get_next_consultation_specialist
                assigned_rr = await get_next_consultation_specialist(session)
                if assigned_rr:
                    assigned_staff_id = assigned_rr.id
                    logger.info(f"Consultation REGULAR (skip): round-robin assigned staff_id={assigned_staff_id}")
                else:
                    from services.escalation_service import get_active_admins
                    admins = await get_active_admins(session)
                    if admins:
                        assigned_staff_id = admins[0].id
                        logger.warning(f"No consultation specialists (skip), falling back to admin: admin_id={assigned_staff_id}")
            elif work_mode == WorkMode.EXTENDED:
                from services.ticket_service import _get_duty_estimate_specialist
                duty_specialist = await _get_duty_estimate_specialist(session)
                if duty_specialist:
                    assigned_staff_id = duty_specialist.id
                    logger.info(f"Consultation EXTENDED (skip): duty specialist assigned staff_id={assigned_staff_id}")
                else:
                    from services.escalation_service import get_active_admins
                    admins = await get_active_admins(session)
                    if admins:
                        assigned_staff_id = admins[0].id
                        logger.warning(f"No duty estimate specialist (skip), falling back to admin: admin_id={assigned_staff_id}")

            ticket_data = {
                "ticket_type": TicketType.CONSULTATION,
                "user_id": user_id,
                "organization_inn": selected_inn,
                "description": None,
                "selected_key_ids": selected_keys_list,
                "assigned_staff_id": assigned_staff_id,
            }
            ticket = await create_ticket(session, ticket_data)
            
            # Set queue_notification_sent_at immediately for working hours tickets
            # to prevent queue processing task from picking them up
            if is_working:
                from utils.timezone_helpers import get_moscow_now_naive
                ticket.queue_notification_sent_at = get_moscow_now_naive()
                logger.info(
                    f"Set queue_notification_sent_at immediately for working hours consultation ticket: ticket_id={ticket.id}"
                )
            
            await session.commit()
            try:
                from bots.max_bot.utils.itat_logging import log_ticket_creation_to_itat
                await log_ticket_creation_to_itat(session, ticket)
            except Exception as e:
                logger.error(f"Failed to log consultation ticket to i-TAT: {e}", exc_info=True)
            confirmation_text = (
                CONSULTATION_TICKET_CREATED.format(ticket_id=ticket.id)
                if is_working
                else get_consultation_non_working_hours_message(ticket.id)
            )
            await messenger_adapter.send_message(chat_id=chat_id, text=confirmation_text, parse_mode="HTML")
            if is_working and ticket.assigned_staff_id:
                from services.ticket_service import send_staff_notification, route_ticket
                from loaders import max_bot
                routing_info = await route_ticket(session, ticket, work_mode)
                notification_sent = await send_staff_notification(
                    bot=max_bot,
                    staff_id=ticket.assigned_staff_id,
                    ticket=ticket,
                    routing_info=routing_info,
                    session=session,
                )
                if notification_sent:
                    logger.info(f"Consultation notification sent: ticket_id={ticket.id}, staff_id={ticket.assigned_staff_id}")
                else:
                    logger.warning(f"Failed to send consultation notification: ticket_id={ticket.id}, staff_id={ticket.assigned_staff_id}")
                
                # Schedule escalation AFTER assignment is committed
                try:
                    from celery_app.escalation_tasks import schedule_technical_support_monitoring
                    await schedule_technical_support_monitoring(ticket_id=ticket.id)
                except Exception as e:
                    logger.error(f"Failed to schedule escalation for consultation {ticket.id}: {e}", exc_info=True)
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
        from services.key_conflict_service import add_key_with_conflict_handling

        user = await session.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        key_result = await add_key_with_conflict_handling(
            session=session,
            user=user,
            key_number=key_number,
        )

        if key_result.has_conflict:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=CONSULTATION_KEY_CONFLICT,
                parse_mode="HTML",
            )
            return

        data = await context.get_data()
        selected_keys: set[int] = set(data.get("selected_keys", []))
        selected_keys.add(key_result.key.id)
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
    during the consultation description step.

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
    Process description input (text, photo, voice, document).

    Accumulates description and attachments in FSM context across multiple messages.
    Shows updated keyboard with "Далее" button after first message received.
    User must click "Далее" to proceed to ticket creation.
    """
    chat_id = event.message.recipient.chat_id

    try:
        # Get existing attachments from context
        data = await context.get_data()
        attachments = data.get("attachments") or []
        has_description = bool(data.get("description"))

        # Handle text message
        if event.message.body and event.message.body.text:
            description = event.message.body.text.strip()

            if len(description) > 4000:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=ERROR_TEXT_TOO_LONG.format(max_length=4000, actual_length=len(description)),
                    keyboard=get_consultation_description_keyboard(has_content=has_description or bool(attachments)),
                    parse_mode="HTML",
                )
                return

            # Append to existing description (user may send multiple messages)
            existing_description = data.get("description") or ""
            combined = (existing_description + "\n" + description).strip() if existing_description else description
            await context.update_data(description=combined)
            has_description = True
            logger.info(f"Consultation description stored: chat_id={chat_id}, length={len(combined)}")

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

        # Check if we received any content
        has_content = has_description or bool(attachments)

        if has_content:
            # Show confirmation with updated keyboard (now with "Далее" button)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="✅ Принято. Можете добавить ещё сообщения или нажмите «Далее» для продолжения.",
                keyboard=get_consultation_description_keyboard(has_content=True),
                parse_mode="HTML",
            )
        else:
            # Nothing received yet — wait for more input
            logger.info(f"No content received yet: chat_id={chat_id}")

    except Exception as e:
        logger.error(f"Error processing consultation description: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML"
        )


async def handle_consultation_description_next(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Handle "Далее" button click in consultation description step.

    Creates consultation ticket after user confirms they are done
    entering description and attachments.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    logger.info(f"Consultation description next: chat_id={chat_id}")

    try:
        data = await context.get_data()
        attachments = data.get("attachments") or []
        description = data.get("description")

        if not description and not attachments:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="⚠️ Пожалуйста, введите описание или прикрепите файл перед тем как продолжить.",
                keyboard=get_consultation_description_keyboard(has_content=False),
                parse_mode="HTML",
            )
            return

        selected_inn = data.get("selected_inn")
        selected_keys = data.get("selected_keys", [])

        user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
        if not user_id:
            return

        # Delete old message with buttons
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete consultation description message: {e}")

        # Clear FSM state before DB operations so it's not left dirty on error
        await context.clear()

        # Determine work mode before ticket creation
        work_mode = await get_current_work_mode(session)
        is_working = work_mode != WorkMode.NON_WORKING

        # Determine assigned staff BEFORE creating the ticket (same pattern as TECHNICAL_SUPPORT).
        # REGULAR  → round-robin among active consultation specialists; fallback to admins
        # EXTENDED → duty estimate specialist; fallback to admins
        # NON_WORKING → no assignment (queued)
        assigned_staff_id = None
        if work_mode == WorkMode.REGULAR:
            from services.round_robin_service import get_next_consultation_specialist
            assigned_rr = await get_next_consultation_specialist(session)
            if assigned_rr:
                assigned_staff_id = assigned_rr.id
                logger.info(
                    f"Consultation REGULAR: round-robin assigned staff_id={assigned_staff_id}"
                )
            else:
                from services.escalation_service import get_active_admins
                admins = await get_active_admins(session)
                if admins:
                    assigned_staff_id = admins[0].id
                    logger.warning(
                        f"No consultation specialists, falling back to admin: "
                        f"admin_id={assigned_staff_id}"
                    )
                else:
                    logger.error("No consultation specialists and no admins available")

        elif work_mode == WorkMode.EXTENDED:
            from services.ticket_service import _get_duty_estimate_specialist
            duty_specialist = await _get_duty_estimate_specialist(session)
            if duty_specialist:
                assigned_staff_id = duty_specialist.id
                logger.info(
                    f"Consultation EXTENDED: duty specialist assigned staff_id={assigned_staff_id}"
                )
            else:
                from services.escalation_service import get_active_admins
                admins = await get_active_admins(session)
                if admins:
                    assigned_staff_id = admins[0].id
                    logger.warning(
                        f"No duty estimate specialist configured, falling back to admin: "
                        f"admin_id={assigned_staff_id}"
                    )
                else:
                    logger.error("No duty estimate specialist and no admins available")

        else:  # NON_WORKING
            assigned_staff_id = None
            logger.info("Consultation NON_WORKING: ticket queued, no assignment")

        # Create ticket
        ticket_data = {
            "ticket_type": TicketType.CONSULTATION,
            "user_id": user_id,
            "organization_inn": selected_inn,
            "description": description or None,
            "selected_key_ids": selected_keys,
            "assigned_staff_id": assigned_staff_id,
        }

        ticket = await create_ticket(session, ticket_data)
        
        # Set queue_notification_sent_at immediately for working hours tickets
        # to prevent queue processing task from picking them up
        if is_working:
            from utils.timezone_helpers import get_moscow_now_naive
            ticket.queue_notification_sent_at = get_moscow_now_naive()
            logger.info(
                f"Set queue_notification_sent_at immediately for working hours consultation ticket: ticket_id={ticket.id}"
            )
        
        await session.commit()

        logger.info(
            f"Consultation ticket created: ticket_id={ticket.id}, user_id={user_id}, "
            f"work_mode={work_mode.value}"
        )

        # Save description and attachments to DB so they appear in ticket history
        # and Celery queue task can forward attachments in non-working hours
        if description or attachments:
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
                logger.info(
                    f"Saved ticket data for consultation ticket {ticket.id}: "
                    f"attachments={len(attachments)}, has_description={bool(description)}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to save ticket data for consultation ticket {ticket.id}: {e}",
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
        confirmation_text = (
            CONSULTATION_TICKET_CREATED.format(ticket_id=ticket.id)
            if is_working
            else get_consultation_non_working_hours_message(ticket.id)
        )
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

        # Send notifications to assigned staff (only in working hours)
        if is_working:
            from services.ticket_service import send_staff_notification
            from loaders import max_bot

            if ticket.assigned_staff_id:
                routing_info = await route_ticket(session, ticket, work_mode)
                notification_sent = await send_staff_notification(
                    bot=max_bot,
                    staff_id=ticket.assigned_staff_id,
                    ticket=ticket,
                    routing_info=routing_info,
                    session=session,
                )
                if notification_sent:
                    logger.info(
                        f"Consultation notification sent: ticket_id={ticket.id}, "
                        f"staff_id={ticket.assigned_staff_id}, work_mode={work_mode.value}"
                    )
                    # Forward attachments to recipient
                    if attachments:
                        try:
                            await _forward_attachments_to_staff(
                                messenger_adapter=messenger_adapter,
                                session=session,
                                ticket_id=ticket.id,
                                staff_id=ticket.assigned_staff_id,
                                attachments=attachments,
                                user_name=user.full_name if user else "Клиент",
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to forward attachments for consultation ticket "
                                f"{ticket.id}: {e}",
                                exc_info=True,
                            )
                else:
                    logger.warning(
                        f"Failed to send consultation notification: "
                        f"ticket_id={ticket.id}, staff_id={ticket.assigned_staff_id}"
                    )
            else:
                logger.error(
                    f"Consultation ticket {ticket.id} is_working but no assigned_staff_id — "
                    f"no notification sent"
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
