"""
Обработчики для смены номера телефона пользователя.

Флоу:
1. Пользователь нажимает "Изменить телефон" в профиле → start_phone_change()
2. Вводит новый номер → process_phone_change() проверяет номер и целевой аккаунт
3. Показывается карточка с данными целевого аккаунта + кнопки "Подтвердить" / "Отмена"
4. При подтверждении → создаётся тикет на одобрение администратором
5. Администратор одобряет → approve_phone_change() выполняет слияние аккаунтов

При одобрении:
- "Старый" аккаунт (старый номер, подавший заявку) — источник
- "Новый" аккаунт (новый номер, уже зарегистрированный) — цель
- Все данные переносятся на целевой аккаунт, старый удаляется
- Бот продолжает работу через max_user_id/max_chat_id целевого аккаунта
"""

import logging
from datetime import datetime

from maxapi.context import MemoryContext
from maxapi.types import MessageCreated, MessageCallback
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import PhoneChangeConfirmPayload
from bots.max_bot.states import ProfileStates
from database.models import (
    Action_Log,
    ActionType,
    API_Retry_Queue,
    Broadcast_Delivery,
    GS_Key,
    Manager_Assignment,
    MAX_Messenger_Data,
    Notification_Event,
    NPS_Response,
    Ticket,
    TicketStatus,
    TicketType,
    User,
    user_organizations,
)
from services.user_service import get_user_by_max_id, get_user_by_phone
from services.ticket_service import create_ticket
from services.validation_service import validate_phone_number
from services.itat_retry_helper import call_itat_with_retry
from bots.max_bot.texts import (
    ERROR_GENERAL,
    ERROR_VALIDATION_PHONE,
    PROFILE_PHONE_CHANGE_SUBMITTED,
    PROFILE_PHONE_CHANGE_PROMPT,
    PROFILE_PHONE_CHANGE_CONFIRM,
)

logger = logging.getLogger(__name__)


async def start_phone_change(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Start phone number change process.

    Shows instructions and prompt for new phone number, sets FSM state.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None

    logger.info(f"Starting phone change process: max_user_id={max_user_id}")

    try:
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")

        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            logger.error(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
            return

        await context.set_state(ProfileStates.changing_phone)

        from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
        keyboard = get_cancel_keyboard()

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=PROFILE_PHONE_CHANGE_PROMPT.format(current_phone=user.phone_number),
            keyboard=keyboard,
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Error starting phone change: max_user_id={max_user_id}, error={e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


async def process_phone_change(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Process phone number input — validate format, check target account exists
    and has max_user_id + max_chat_id, then show confirmation screen.

    maxapi Pattern Notes:
    - Registered with FSM state filter: ProfileStates.changing_phone
    - Uses event.message.sender.user_id for user identification
    - Accesses message text via event.message.body.text
    - Does NOT clear FSM state — waits for confirm/cancel callback
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    new_phone = event.message.body.text.strip()

    logger.info(f"Processing phone change input: max_user_id={max_user_id}, new_phone={new_phone}")

    try:
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            logger.error(f"User not found: max_user_id={max_user_id}")
            await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
            await context.clear()
            return

        # Validate phone format
        is_valid, result = validate_phone_number(new_phone)
        if not is_valid:
            logger.warning(f"Invalid phone format: phone={new_phone}, error={result}")
            from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
            keyboard = get_cancel_keyboard()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ERROR_VALIDATION_PHONE.format(error_details=result),
                keyboard=keyboard,
                parse_mode="HTML",
            )
            return

        normalized_phone = result

        # Same number check
        if normalized_phone == user.phone_number:
            await context.clear()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Новый номер совпадает с текущим. Смена не требуется.",
                parse_mode="HTML",
            )
            return

        # Target account must already be registered in the bot
        target_user = await get_user_by_phone(session, normalized_phone)
        if not target_user:
            from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
            keyboard = get_cancel_keyboard()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "❌ <b>Номер не найден в системе</b>\n\n"
                    f"Номер <code>{normalized_phone}</code> не зарегистрирован в боте.\n\n"
                    "Для смены номера необходимо сначала зарегистрироваться в боте "
                    "с нового номера телефона, а затем подать заявку на смену."
                ),
                keyboard=keyboard,
                parse_mode="HTML",
            )
            return

        # Target account must have max_user_id and max_chat_id
        target_max_data_stmt = select(MAX_Messenger_Data).where(
            MAX_Messenger_Data.user_id == target_user.id
        )
        target_max_data_result = await session.execute(target_max_data_stmt)
        target_max_data = target_max_data_result.scalar_one_or_none()

        if not target_max_data or not target_max_data.max_user_id or not target_max_data.max_chat_id:
            from bots.max_bot.keyboards.user.profile_kb import get_cancel_keyboard
            keyboard = get_cancel_keyboard()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "❌ <b>Аккаунт не привязан к MAX</b>\n\n"
                    f"Аккаунт с номером <code>{normalized_phone}</code> найден, "
                    "но не имеет привязки к MAX мессенджеру.\n\n"
                    "Войдите в бот с нового номера через MAX, а затем повторите запрос."
                ),
                keyboard=keyboard,
                parse_mode="HTML",
            )
            return

        # All checks passed — show confirmation screen
        target_name = (
            target_user.full_name
            or f"{target_user.first_name or ''} {target_user.last_name or ''}".strip()
            or "Не указано"
        )

        confirm_keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="✅ Подтвердить",
                        payload=PhoneChangeConfirmPayload(action="confirm", new_phone=normalized_phone).pack(),
                    ),
                    KeyboardButton(
                        text="❌ Отмена",
                        payload=PhoneChangeConfirmPayload(action="cancel", new_phone=normalized_phone).pack(),
                    ),
                ]
            ],
            inline=True,
        )

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=PROFILE_PHONE_CHANGE_CONFIRM.format(
                old_phone=user.phone_number,
                new_phone=normalized_phone,
                target_name=target_name,
            ),
            keyboard=confirm_keyboard,
            parse_mode="HTML",
        )

        # Keep FSM state — waiting for confirm/cancel callback

    except SQLAlchemyError as e:
        logger.error(f"DB error processing phone change: max_user_id={max_user_id}, error={e}", exc_info=True)
        await context.clear()
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error processing phone change: max_user_id={max_user_id}, error={e}", exc_info=True)
        await context.clear()
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


async def confirm_phone_change(
    event: MessageCallback,
    payload: PhoneChangeConfirmPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Handle confirm/cancel callback after user reviewed the phone change info.

    On confirm: creates a PHONE_CHANGE ticket for admin approval.
    On cancel: clears state and returns to profile.

    maxapi Pattern Notes:
    - Registered with PhoneChangeConfirmPayload.filter()
    - Uses event.callback.user.user_id for user identification
    - Uses replace_message pattern
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None

    # Delete confirmation message
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete confirmation message: {e}")

    await context.clear()

    if payload.action == "cancel":
        from bots.max_bot.handlers.user.profile import show_profile
        user = await get_user_by_max_id(session, max_user_id)
        if user:
            await show_profile(chat_id, user.id, session, messenger_adapter)
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Смена номера отменена.",
                parse_mode="HTML",
            )
        return

    # action == "confirm"
    try:
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")
            return

        normalized_phone = payload.new_phone

        # Re-verify target still exists (race condition guard)
        target_user = await get_user_by_phone(session, normalized_phone)
        if not target_user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "❌ <b>Ошибка</b>\n\n"
                    "Целевой аккаунт больше не найден. Попробуйте снова."
                ),
                parse_mode="HTML",
            )
            return

        ticket_data = {
            "ticket_type": TicketType.PHONE_CHANGE,
            "user_id": user.id,
            "description": (
                f"Запрос на смену номера телефона с {user.phone_number} на {normalized_phone}. "
                f"Целевой аккаунт: user_id={target_user.id}, max_user_id={target_user.max_user_id}"
            ),
            "old_phone": user.phone_number,
            "new_phone": normalized_phone,
        }

        ticket = await create_ticket(session, ticket_data)
        logger.info(f"Phone change ticket created: ticket_id={ticket.id}, user_id={user.id}")

        from bots.max_bot.utils.audit_logger import log_phone_change_requested
        await log_phone_change_requested(
            user_id=user.id,
            max_user_id=max_user_id,
            old_phone=user.phone_number,
            new_phone=normalized_phone,
            ticket_id=f"TKT_{ticket.id}",
        )

        try:
            from bots.max_bot.utils.itat_logging import log_ticket_creation_to_itat
            await log_ticket_creation_to_itat(session, ticket)
        except Exception as e:
            logger.error(f"Failed to log phone change ticket to I-TAT: ticket_id={ticket.id}, error={e}", exc_info=True)

        # Notify administrators with "Детали операции" button
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_phone_change_request
            await notify_admins_phone_change_request(
                session=session,
                source_user_id=user.id,
                target_user_id=target_user.id,
                old_phone=user.phone_number,
                new_phone=normalized_phone,
                ticket_id=ticket.id,
            )
        except Exception as e:
            logger.error(f"Failed to notify admins about phone change: ticket_id={ticket.id}, error={e}", exc_info=True)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=PROFILE_PHONE_CHANGE_SUBMITTED.format(
                old_phone=user.phone_number,
                new_phone=normalized_phone,
                ticket_id=ticket.id,
            ),
            parse_mode="HTML",
        )

        from bots.max_bot.handlers.user.profile import show_profile
        await show_profile(chat_id, user.id, session, messenger_adapter)

    except SQLAlchemyError as e:
        logger.error(f"DB error confirming phone change: max_user_id={max_user_id}, error={e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error confirming phone change: max_user_id={max_user_id}, error={e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text=ERROR_GENERAL, parse_mode="HTML")


async def _merge_accounts(
    session: AsyncSession,
    source_user: User,
    target_user: User,
) -> None:
    """
    Merge source_user data into target_user, then delete source_user.

    "Source" = old account (old phone, filed the request).
    "Target" = new account (new phone, already registered).

    All FK references to source_user.id are re-pointed to target_user.id.
    Tables with unique constraints are handled to avoid conflicts.
    """
    src = source_user.id
    tgt = target_user.id

    logger.info(f"Merging accounts: source_user_id={src} → target_user_id={tgt}")

    # tickets — simple FK
    await session.execute(update(Ticket).where(Ticket.user_id == src).values(user_id=tgt))

    # gs_keys — simple FK
    await session.execute(update(GS_Key).where(GS_Key.user_id == src).values(user_id=tgt))

    # user_organizations — unique(user_id, organization_inn): skip duplicates
    existing_orgs = {
        row[0] for row in (
            await session.execute(
                select(user_organizations.c.organization_inn).where(user_organizations.c.user_id == tgt)
            )
        ).fetchall()
    }
    for row in (await session.execute(select(user_organizations).where(user_organizations.c.user_id == src))).fetchall():
        if row.organization_inn not in existing_orgs:
            await session.execute(
                user_organizations.update()
                .where(user_organizations.c.user_id == src, user_organizations.c.organization_inn == row.organization_inn)
                .values(user_id=tgt)
            )
        else:
            await session.execute(
                delete(user_organizations).where(
                    user_organizations.c.user_id == src,
                    user_organizations.c.organization_inn == row.organization_inn,
                )
            )

    # manager_assignments — unique(user_id, organization_inn): skip duplicates
    existing_ma_inns = {
        row[0] for row in (
            await session.execute(select(Manager_Assignment.organization_inn).where(Manager_Assignment.user_id == tgt))
        ).fetchall()
    }
    for ma in (await session.execute(select(Manager_Assignment).where(Manager_Assignment.user_id == src))).scalars().all():
        if ma.organization_inn not in existing_ma_inns:
            await session.execute(update(Manager_Assignment).where(Manager_Assignment.id == ma.id).values(user_id=tgt))
        else:
            await session.delete(ma)

    # notification_events — simple FK
    await session.execute(update(Notification_Event).where(Notification_Event.user_id == src).values(user_id=tgt))

    # broadcast_deliveries — unique(broadcast_id, user_id): skip duplicates
    existing_broadcast_ids = {
        row[0] for row in (
            await session.execute(select(Broadcast_Delivery.broadcast_id).where(Broadcast_Delivery.user_id == tgt))
        ).fetchall()
    }
    for bd in (await session.execute(select(Broadcast_Delivery).where(Broadcast_Delivery.user_id == src))).scalars().all():
        if bd.broadcast_id not in existing_broadcast_ids:
            await session.execute(update(Broadcast_Delivery).where(Broadcast_Delivery.id == bd.id).values(user_id=tgt))
        else:
            await session.delete(bd)

    # action_logs — simple FK (nullable)
    await session.execute(update(Action_Log).where(Action_Log.user_id == src).values(user_id=tgt))

    # api_retry_queue — simple FK (nullable)
    await session.execute(update(API_Retry_Queue).where(API_Retry_Queue.user_id == src).values(user_id=tgt))

    # nps_responses — simple FK
    await session.execute(update(NPS_Response).where(NPS_Response.user_id == src).values(user_id=tgt))

    # max_messenger_data — source's entry is deleted (target keeps its own)
    source_max_data = (
        await session.execute(select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == src))
    ).scalar_one_or_none()
    if source_max_data:
        await session.delete(source_max_data)

    # default_manager_id — inherit from source if target has none
    if target_user.default_manager_id is None and source_user.default_manager_id is not None:
        target_user.default_manager_id = source_user.default_manager_id

    await session.flush()
    await session.delete(source_user)
    logger.info(f"Account merge complete: source_user_id={src} deleted, target_user_id={tgt} retained")


async def approve_phone_change(
    session: AsyncSession,
    ticket_id: int,
    staff_id: int,
    messenger_adapter: MAXMessengerAdapter,
) -> bool | str:
    """
    Approve phone number change request.

    Performs full account merge:
    - source = old account (filed the request, old phone)
    - target = new account (already registered on new phone)

    All data from source is transferred to target, source is deleted.
    The bot continues to communicate via target's max_user_id/max_chat_id.
    """
    try:
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.user))
        ticket = (await session.execute(stmt)).scalar_one_or_none()

        if not ticket or ticket.ticket_type != TicketType.PHONE_CHANGE:
            logger.error(f"Phone change ticket not found: ticket_id={ticket_id}")
            return False

        if ticket.ticket_status == TicketStatus.CLOSED:
            logger.warning(f"Phone change ticket already closed: ticket_id={ticket_id}")
            return "already_closed"

        source_user = ticket.user
        old_phone = ticket.old_phone
        new_phone = ticket.new_phone

        # Fallback for legacy tickets created before old_phone/new_phone columns were populated
        if (not old_phone or not new_phone) and ticket.description:
            import re
            phones = re.findall(r'\+7\d{10}', ticket.description)
            if len(phones) >= 2:
                old_phone = old_phone or phones[0]
                new_phone = new_phone or phones[1]
                logger.info(
                    f"Recovered phone data from description: "
                    f"ticket_id={ticket_id}, old={old_phone}, new={new_phone}"
                )

        if not old_phone or not new_phone:
            logger.error(f"Missing phone data in ticket: ticket_id={ticket_id}")
            return False

        target_user = await get_user_by_phone(session, new_phone)
        if not target_user:
            logger.error(f"Target account not found for new_phone={new_phone}")
            return "target_not_found"

        if target_user.id == source_user.id:
            logger.error(f"Source and target are the same user: user_id={source_user.id}")
            return False

        logger.info(
            f"Approving phone change: ticket_id={ticket_id}, "
            f"source={source_user.id} ({old_phone}) → target={target_user.id} ({new_phone})"
        )

        # Get target chat_id before merge for notification
        target_max_data = (
            await session.execute(select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == target_user.id))
        ).scalar_one_or_none()
        target_chat_id = target_max_data.max_chat_id if target_max_data else None

        # Call i-TAT API
        api_response = await call_itat_with_retry(
            session=session,
            operation="change_phone",
            payload=dict(
                messenger="max",
                user_id=target_user.max_user_id,
                old_phone=old_phone,
                new_phone=new_phone,
                staff_id=staff_id,
            ),
            user_id=source_user.id,
        )
        if api_response is not None:
            logger.info(f"i-TAT API phone change successful: {api_response}")
        else:
            logger.warning(f"change_phone queued for retry: old={old_phone}, new={new_phone}")

        # Close ticket before merge (merge will re-point ticket.user_id to target)
        ticket.ticket_status = TicketStatus.CLOSED
        ticket.resolution_comment = (
            f"Номер изменён с {old_phone} на {new_phone}. "
            f"Аккаунты объединены: source={source_user.id} → target={target_user.id}"
        )
        ticket.closed_at = datetime.now()
        await session.flush()

        # Full account merge
        await _merge_accounts(session, source_user=source_user, target_user=target_user)
        await session.commit()

        # Notify user via target account
        if target_chat_id:
            try:
                await messenger_adapter.send_message(
                    chat_id=target_chat_id,
                    text=(
                        f"✅ <b>Смена номера телефона одобрена</b>\n\n"
                        f"Ваш номер телефона изменён с <code>{old_phone}</code> на <code>{new_phone}</code>.\n\n"
                        f"Все ваши данные (заявки, ключи, организации) перенесены на текущий аккаунт.\n\n"
                        f"Заявка #{ticket_id} закрыта."
                    ),
                    parse_mode="HTML",
                )
            except Exception as send_error:
                logger.error(f"Failed to send approval notification: {send_error}")

        logger.info(f"Phone change approved: ticket_id={ticket_id}, merged {source_user.id} → {target_user.id}")
        return True

    except Exception as e:
        await session.rollback()
        logger.error(f"Error approving phone change: ticket_id={ticket_id}, error={e}", exc_info=True)
        return False


async def reject_phone_change(
    session: AsyncSession,
    ticket_id: int,
    staff_id: int,
    reason: str,
    messenger_adapter: MAXMessengerAdapter,
) -> bool | str:
    """
    Reject phone number change request.

    Updates ticket status and notifies user via their current (old) account.
    """
    try:
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.user))
        ticket = (await session.execute(stmt)).scalar_one_or_none()

        if not ticket or ticket.ticket_type != TicketType.PHONE_CHANGE:
            logger.error(f"Phone change ticket not found: ticket_id={ticket_id}")
            return False

        if ticket.ticket_status == TicketStatus.CLOSED:
            logger.warning(f"Phone change ticket already closed: ticket_id={ticket_id}")
            return "already_closed"

        user = ticket.user
        old_phone = ticket.old_phone
        new_phone = ticket.new_phone

        # Fallback for legacy tickets created before old_phone/new_phone columns were populated
        if (not old_phone or not new_phone) and ticket.description:
            import re
            phones = re.findall(r'\+7\d{10}', ticket.description)
            if len(phones) >= 2:
                old_phone = old_phone or phones[0]
                new_phone = new_phone or phones[1]
                logger.info(
                    f"Recovered phone data from description: "
                    f"ticket_id={ticket_id}, old={old_phone}, new={new_phone}"
                )

        ticket.ticket_status = TicketStatus.CLOSED
        ticket.resolution_comment = f"Запрос на смену номера отклонён. Причина: {reason}"
        ticket.closed_at = datetime.now()
        await session.commit()

        # Notify via source user's account (still alive after rejection)
        source_max_data = (
            await session.execute(select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == user.id))
        ).scalar_one_or_none()

        if source_max_data:
            try:
                await messenger_adapter.send_message(
                    chat_id=source_max_data.max_chat_id,
                    text=(
                        f"❌ <b>Запрос отклонён</b>\n\n"
                        f"Ваш запрос на смену номера с <code>{old_phone}</code> "
                        f"на <code>{new_phone}</code> отклонён.\n\n"
                        f"<b>Причина:</b> {reason}\n\n"
                        f"Заявка #{ticket.id} закрыта."
                    ),
                    parse_mode="HTML",
                )
            except Exception as send_error:
                logger.error(f"Failed to send rejection notification: {send_error}")

        logger.info(f"Phone change rejected: ticket_id={ticket_id}, user_id={user.id}")
        return True

    except Exception as e:
        await session.rollback()
        logger.error(f"Error rejecting phone change: ticket_id={ticket_id}, error={e}", exc_info=True)
        return False
