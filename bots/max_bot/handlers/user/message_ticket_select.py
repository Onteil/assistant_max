"""
Handlers for ticket selection when routing a free-text message.

When a user sends a message without an active FSM state and has multiple
active tickets, the message metadata (text/file URL/attachment type) is
stored in FSM and a selection menu is shown. After the user picks a ticket,
the pending message is forwarded using the same full logic as the live handler
(download → re-upload for voice/audio/image, link for file/video).
"""

import logging

from maxapi.types import MessageCallback
from maxapi.context import MemoryContext
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.payloads import (
    MessageTicketSelectPayload,
    MessageTicketPaginationPayload,
    MessageTicketCancelPayload,
)
from bots.max_bot.keyboards.user.message_ticket_select_kb import get_message_ticket_select_keyboard
from database.models import TicketStatus
from services.ticket_service import (
    get_ticket_by_id,
    get_user_active_tickets,
    forward_client_message_to_manager,
)
from services.user_service import get_user_by_max_id

logger = logging.getLogger(__name__)

# FSM keys for pending message metadata
_KEY_TEXT = "pending_message_text"
_KEY_TYPE = "pending_message_type"
_KEY_FILE_URL = "pending_file_url"
_KEY_ATTACH_TYPE = "pending_attachment_type"
_KEY_FILE_NAME = "pending_file_name"
_KEY_FILE_SIZE = "pending_file_size"


def build_pending_data(meta: dict) -> dict:
    """Build FSM update dict from extract_attachment_metadata() result."""
    return {
        _KEY_TEXT: meta["message_text"],
        _KEY_TYPE: meta["message_type"],
        _KEY_FILE_URL: meta["file_url"],
        _KEY_ATTACH_TYPE: meta["attachment_type"],
        _KEY_FILE_NAME: meta["file_name"],
        _KEY_FILE_SIZE: meta["file_size"],
    }


def clear_pending_data() -> dict:
    """Build FSM update dict that clears all pending message keys."""
    return {
        _KEY_TEXT: None,
        _KEY_TYPE: None,
        _KEY_FILE_URL: None,
        _KEY_ATTACH_TYPE: None,
        _KEY_FILE_NAME: None,
        _KEY_FILE_SIZE: None,
    }


async def handle_message_ticket_select(
    event: MessageCallback,
    payload: MessageTicketSelectPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Handle ticket selection from the message routing menu.

    Retrieves pending message metadata from FSM and forwards the message
    (including files) to the selected ticket's manager using the full
    forwarding logic (download/re-upload for voice/audio/image).
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    ticket_id = payload.ticket_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    # Delete selection menu
    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete ticket select menu: {e}")

    try:
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователь не найден.",
                parse_mode="HTML"
            )
            return

        ticket = await get_ticket_by_id(session, ticket_id)
        if not ticket or ticket.user_id != user.id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return

        if ticket.ticket_status not in [
            TicketStatus.NEW,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_CLIENT,
        ]:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ Заявка #{ticket_id} уже закрыта.",
                parse_mode="HTML"
            )
            await context.update_data(**clear_pending_data())
            return

        # Retrieve pending message metadata from FSM
        data = await context.get_data()
        message_text = data.get(_KEY_TEXT) or ""
        message_type_val = data.get(_KEY_TYPE) or "text"
        file_url = data.get(_KEY_FILE_URL)
        attachment_type = data.get(_KEY_ATTACH_TYPE)
        file_name = data.get(_KEY_FILE_NAME)
        file_size = data.get(_KEY_FILE_SIZE)

        # Clear pending data (do NOT set active_ticket_id — each new message
        # should go through the auto-routing logic again so the correct ticket
        # is picked based on the current number of active tickets)
        await context.update_data(**clear_pending_data())

        # Forward the pending message using the full forwarding logic
        # Check if manager is already in focus for this ticket (no buttons needed)
        manager_in_focus = False
        try:
            from loaders import max_dp
            from bots.max_bot.states import EmployeeStates
            from database.models import Staff_Member, MAX_Messenger_Data
            from sqlalchemy import select as sa_select

            if max_dp and ticket.assigned_staff_id:
                staff_result = await session.execute(
                    sa_select(Staff_Member).where(Staff_Member.id == ticket.assigned_staff_id)
                )
                staff_member = staff_result.scalar_one_or_none()
                if staff_member and staff_member.max_user_id:
                    max_data_result = await session.execute(
                        sa_select(MAX_Messenger_Data).where(
                            MAX_Messenger_Data.max_user_id == staff_member.max_user_id
                        )
                    )
                    max_data = max_data_result.scalar_one_or_none()
                    if max_data:
                        ctx = max_dp.contexts.get((max_data.max_chat_id, None))
                        if ctx is not None:
                            state = await ctx.get_state()
                            if state == EmployeeStates.in_focus:
                                data_ctx = await ctx.get_data()
                                if data_ctx.get("focused_ticket_id") == ticket.id:
                                    manager_in_focus = True
        except Exception as e:
            logger.warning(f"Could not check manager focus state: {e}")

        await forward_client_message_to_manager(
            session=session,
            messenger_adapter=messenger_adapter,
            ticket=ticket,
            user=user,
            message_text=message_text,
            message_type_val=message_type_val,
            file_url=file_url,
            attachment_type=attachment_type,
            file_name=file_name,
            file_size=file_size,
            manager_in_focus=manager_in_focus,
        )

        # Determine display name for confirmation
        type_display = {
            "text": "текст",
            "photo": "фото",
            "document": "документ",
            "voice": "голосовое сообщение",
            "video": "видео",
        }.get(message_type_val, "сообщение")

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ Ваше сообщение ({type_display}) отправлено менеджеру "
                f"(Заявка #{ticket_id})"
            ),
            parse_mode="HTML"
        )

        logger.info(
            f"Pending message forwarded after ticket selection: "
            f"max_user_id={max_user_id}, ticket_id={ticket_id}, "
            f"message_type={message_type_val}, has_file={file_url is not None}"
        )

    except Exception as e:
        logger.error(
            f"Error in handle_message_ticket_select: max_user_id={max_user_id}, "
            f"ticket_id={ticket_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


async def handle_message_ticket_pagination(
    event: MessageCallback,
    payload: MessageTicketPaginationPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle pagination in the message ticket selection menu."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete ticket select menu: {e}")

    try:
        user = await get_user_by_max_id(session, max_user_id)
        if not user:
            return

        tickets = await get_user_active_tickets(session, user.id)
        keyboard = await get_message_ticket_select_keyboard(tickets, page=payload.page)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="📋 <b>По какой заявке отправить сообщение?</b>",
            keyboard=keyboard,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(
            f"Error in handle_message_ticket_pagination: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )


async def handle_message_ticket_cancel(
    event: MessageCallback,
    payload: MessageTicketCancelPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle cancellation of ticket selection for message routing."""
    chat_id = event.message.recipient.chat_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    if message_id:
        try:
            await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete ticket select menu: {e}")

    await context.update_data(**clear_pending_data())

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="❌ Отправка сообщения отменена.",
        parse_mode="HTML"
    )
