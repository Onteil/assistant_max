"""
Client Message Handlers for MAX Bot

Handles client messages in communication mode with active ticket.
Routes messages (text, photos, documents, voice, video) to assigned manager.

File Forwarding:
- Downloads files from MAX URLs to temporary storage
- Re-uploads files to manager's chat
- Cleans up temporary files after sending
- Falls back to URL links if file forwarding fails

Requirements: 6.1, 6.3, 6.7, 13.4
"""

import logging
from pathlib import Path
from typing import Any

from maxapi.context import MemoryContext
from maxapi.types import MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from database.models import TicketStatus
from services.ticket_service import get_ticket_by_id

logger = logging.getLogger(__name__)


def extract_attachment_metadata(event: MessageCreated) -> dict[str, Any]:
    """
    Extract attachment metadata from a MessageCreated event.

    Returns a dict with keys:
        message_text: str  — display text (e.g. "📷 Фото")
        message_type: str  — MessageType value ("text", "photo", etc.)
        file_url: str | None
        attachment_type: str | None  — raw MAX type ("image", "file", "voice", …)
        file_name: str | None
        file_size: int | None

    Used to persist attachment info in FSM when ticket selection is deferred.
    """
    from database.models import MessageType, FileType

    message_text = ""
    message_type_val = MessageType.TEXT.value
    file_url = None
    attachment_type = None
    file_name = None
    file_size = None

    if event.message.body.text:
        message_text = event.message.body.text
        message_type_val = MessageType.TEXT.value

    if event.message.body.attachments:
        for att in event.message.body.attachments:
            attachment_type = att.type

            if attachment_type == "image":
                message_text = "📷 Фото"
                message_type_val = MessageType.PHOTO.value
                file_url = att.payload.url if hasattr(att.payload, 'url') else None
                file_name = "photo.jpg"

            elif attachment_type == "file":
                file_name = att.payload.name if hasattr(att.payload, 'name') else "Документ"
                message_text = "📎 Файл"
                message_type_val = MessageType.DOCUMENT.value
                file_url = att.payload.url if hasattr(att.payload, 'url') else None
                file_size = att.payload.size if hasattr(att.payload, 'size') else None

            elif attachment_type in ("voice", "audio_video_note"):
                message_text = "🎤 Голосовое сообщение"
                message_type_val = MessageType.VOICE.value
                file_url = att.payload.url if hasattr(att.payload, 'url') else None
                file_name = "voice.ogg"

            elif attachment_type == "audio":
                message_text = "🎤 Голосовое сообщение"
                message_type_val = MessageType.VOICE.value
                file_url = att.payload.url if hasattr(att.payload, 'url') else None
                file_name = "audio.mp3"

            elif attachment_type == "video":
                file_name = att.payload.name if hasattr(att.payload, 'name') else "Видео"
                message_text = "🎥 Видео"
                message_type_val = MessageType.VIDEO.value
                file_url = att.payload.url if hasattr(att.payload, 'url') else None
                file_size = att.payload.size if hasattr(att.payload, 'size') else None

            break  # only first attachment

    return {
        "message_text": message_text,
        "message_type": message_type_val,
        "file_url": file_url,
        "attachment_type": attachment_type,
        "file_name": file_name,
        "file_size": file_size,
    }


async def route_client_message_to_ticket(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> bool:
    """
    Route client message to assigned manager if active ticket exists.
    
    Checks FSM context for active_ticket_id and forwards message to manager.
    Handles text, photos, documents, voice messages, and videos.
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Checks FSM context for active_ticket_id
    - Returns True if message was routed, False otherwise
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Returns:
        True if message was routed to ticket, False otherwise
    
    Requirements: 6.1, 6.3, 6.7, 13.4
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    try:
        # Check FSM data for active_ticket_id
        data = await context.get_data()
        active_ticket_id = data.get("active_ticket_id")
        
        if not active_ticket_id:
            # No active ticket - don't route
            return False
        
        logger.debug(f"Client {max_user_id} has active_ticket_id={active_ticket_id}")
        
        # Verify ticket exists and is active
        ticket = await get_ticket_by_id(session, active_ticket_id)
        
        if not ticket:
            logger.warning(f"Ticket {active_ticket_id} not found for client {max_user_id}")
            # Clear invalid ticket from context
            await context.update_data(active_ticket_id=None)
            return False
        
        # Verify ticket is still active
        if ticket.ticket_status not in [
            TicketStatus.NEW,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_CLIENT
        ]:
            logger.info(
                f"Ticket {active_ticket_id} is no longer active "
                f"(status: {ticket.ticket_status})"
            )
            # Clear closed ticket from context and fall through to auto-routing logic
            await context.update_data(active_ticket_id=None)
            return False
        
        # Route message to manager
        await handle_client_message_to_ticket_max(
            event=event,
            session=session,
            ticket=ticket,
            messenger_adapter=messenger_adapter
        )
        
        # Acknowledge receipt to client
        message_type_name = get_message_type_name(event)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"✅ Ваше сообщение ({message_type_name}) отправлено менеджеру (Заявка #{ticket.id})",
            parse_mode="HTML"
        )
        
        logger.info(
            f"Client message routed to manager: client_id={max_user_id}, "
            f"ticket_id={ticket.id}, manager_id={ticket.assigned_staff_id}"
        )
        
        return True  # Message was routed
    
    except Exception as e:
        logger.error(
            f"Error routing client message: client_id={max_user_id}, error={e}",
            exc_info=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при отправке сообщения.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )
        
        return True  # Message was handled (with error)


async def handle_client_message_to_ticket_max(
    event: MessageCreated,
    session: AsyncSession,
    ticket,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle incoming client message to ticket (MAX version).
    
    Stores message in database, changes ticket status if needed,
    and forwards message to assigned manager.
    
    Args:
        event: MessageCreated event from maxapi
        session: Database session
        ticket: Ticket object
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: 6.1, 6.3, 6.7, 13.4
    """
    from services.ticket_service import forward_client_message_to_manager
    from services.user_service import get_user_by_max_id

    user = await get_user_by_max_id(session, event.message.sender.user_id)
    if not user:
        logger.error(f"User not found: max_user_id={event.message.sender.user_id}")
        return

    meta = extract_attachment_metadata(event)

    # Check if the assigned manager is already in focus mode for this ticket.
    # If so, skip action buttons — the manager is already in the conversation.
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
                            data = await ctx.get_data()
                            if data.get("focused_ticket_id") == ticket.id:
                                manager_in_focus = True
    except Exception as e:
        logger.warning(f"Could not check manager focus state: {e}")

    await forward_client_message_to_manager(
        session=session,
        messenger_adapter=messenger_adapter,
        ticket=ticket,
        user=user,
        message_text=meta["message_text"],
        message_type_val=meta["message_type"],
        file_url=meta["file_url"],
        attachment_type=meta["attachment_type"],
        file_name=meta["file_name"],
        file_size=meta["file_size"],
        manager_in_focus=manager_in_focus,
    )


def get_message_type_name(event: MessageCreated) -> str:
    """
    Get human-readable message type name.
    
    Args:
        event: MessageCreated event
    
    Returns:
        Message type name in Russian
    """
    if event.message.body.text:
        return "текст"
    
    if event.message.body.attachments:
        for attachment in event.message.body.attachments:
            attachment_type = attachment.type
            
            if attachment_type == "image":
                return "фото"
            elif attachment_type == "file":
                return "документ"
            elif attachment_type in ("voice", "audio_video_note"):
                return "голосовое сообщение"
            elif attachment_type == "video":
                return "видео"
    
    return "сообщение"
