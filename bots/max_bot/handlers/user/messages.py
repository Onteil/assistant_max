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
import uuid
from pathlib import Path

from maxapi.context import MemoryContext
from maxapi.types import MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from database.models import TicketStatus
from services.ticket_service import get_ticket_by_id

logger = logging.getLogger(__name__)


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
            # Clear closed ticket from context
            await context.update_data(active_ticket_id=None)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ Заявка #{active_ticket_id} уже закрыта.\n"
                     f"Используйте /start для возврата в главное меню.",
                parse_mode="HTML"
            )
            return True  # Message was handled (with error)
        
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
    from datetime import datetime
    from database.models import (
        MessageType,
        SenderType,
        ActionType,
        Staff_Member,
        User,
        File_Attachment,
        FileType,
        UploaderType
    )
    from services.ticket_service import add_ticket_message, _log_action
    from sqlalchemy import select
    
    try:
        # Determine message type and text
        message_text = ""
        message_type = MessageType.TEXT
        file_id = None
        file_type = None
        file_name = None
        file_size = None
        
        # Check for text
        if event.message.body.text:
            message_text = event.message.body.text
            message_type = MessageType.TEXT
        
        # Check for attachments
        if event.message.body.attachments:
            for attachment in event.message.body.attachments:
                attachment_type = attachment.type
                
                if attachment_type == "image":
                    message_text = "📷 Фото"
                    message_type = MessageType.PHOTO
                    file_type = FileType.IMAGE
                    # MAX API stores image URL in payload.url
                    file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                    file_name = "photo.jpg"
                
                elif attachment_type == "file":
                    # Access payload attributes directly (not .get())
                    file_name = attachment.payload.name if hasattr(attachment.payload, 'name') else "Документ"
                    message_text = f"📎 {file_name}"
                    message_type = MessageType.DOCUMENT
                    file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                    file_size = attachment.payload.size if hasattr(attachment.payload, 'size') else None
                    
                    # Classify file type based on extension
                    from services.validation_service import classify_file_type
                    file_type = classify_file_type(file_name)
                
                elif attachment_type == "voice":
                    message_text = "🎤 Голосовое сообщение"
                    message_type = MessageType.VOICE
                    file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                    file_type = FileType.OTHER
                    file_name = "voice.ogg"
                
                elif attachment_type == "video":
                    file_name = attachment.payload.name if hasattr(attachment.payload, 'name') else "Видео"
                    message_text = f"🎥 {file_name}"
                    message_type = MessageType.VIDEO
                    file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                    file_size = attachment.payload.size if hasattr(attachment.payload, 'size') else None
                    file_type = FileType.OTHER
                
                # Only process first attachment
                break
        
        # Get user from database
        from services.user_service import get_user_by_max_id
        user = await get_user_by_max_id(session, event.message.sender.user_id)
        
        if not user:
            logger.error(f"User not found: max_user_id={event.message.sender.user_id}")
            return
        
        # Store message in database
        message = await add_ticket_message(
            session=session,
            ticket_id=ticket.id,
            sender_type=SenderType.USER,
            sender_id=user.id,  # Use internal user ID
            message_text=message_text,
            message_type=message_type
        )
        
        # Store file attachment if present
        if file_id:
            file_attachment = File_Attachment(
                ticket_id=ticket.id,
                message_id=message.id,
                file_type=file_type,
                telegram_file_id=file_id,  # Store MAX file URL in telegram_file_id field
                file_name=file_name,
                file_size=file_size,
                uploader_id=user.id,
                uploader_type=UploaderType.USER,
                uploaded_at=datetime.utcnow()  # Use naive datetime for PostgreSQL
            )
            
            session.add(file_attachment)
            await session.flush()
            
            logger.debug(
                f"Client file attachment stored: ticket_id={ticket.id}, "
                f"message_id={message.id}, file_type={file_type}"
            )
        
        # If ticket status is WAITING_CLIENT, change to IN_PROGRESS
        if ticket.ticket_status == TicketStatus.WAITING_CLIENT:
            old_status = ticket.ticket_status
            ticket.ticket_status = TicketStatus.IN_PROGRESS
            ticket.updated_at = datetime.utcnow()  # Use naive datetime for PostgreSQL
            
            # Cancel escalation monitoring tasks
            try:
                from celery_app.escalation_tasks import cancel_escalation_monitoring
                await cancel_escalation_monitoring(ticket.id)
                logger.info(f"Escalation monitoring cancelled: ticket_id={ticket.id}")
            except Exception as e:
                logger.warning(
                    f"Failed to cancel escalation monitoring: ticket_id={ticket.id}, error={e}"
                )
            
            await _log_action(
                session=session,
                action_type=ActionType.STATUS_CHANGED,
                ticket_id=ticket.id,
                user_id=user.id,
                action_details={
                    "old_status": old_status.value,
                    "new_status": TicketStatus.IN_PROGRESS.value,
                    "reason": "client_response"
                }
            )
            
            logger.info(
                f"Ticket status changed from WAITING_CLIENT to IN_PROGRESS: "
                f"ticket_id={ticket.id}"
            )
        
        # Forward message to assigned manager (if MAX user)
        if ticket.assigned_staff_id:
            try:
                # Get manager's MAX user ID
                staff_result = await session.execute(
                    select(Staff_Member).where(
                        Staff_Member.id == ticket.assigned_staff_id
                    )
                )
                staff_member = staff_result.scalar_one_or_none()
                
                if not staff_member or not staff_member.max_user_id:
                    logger.warning(
                        f"Manager does not have MAX account: staff_id={ticket.assigned_staff_id}"
                    )
                else:
                    # Get manager's MAX chat ID from max_messenger_data table
                    from database.models import MAX_Messenger_Data
                    
                    max_data_result = await session.execute(
                        select(MAX_Messenger_Data).where(
                            MAX_Messenger_Data.max_user_id == staff_member.max_user_id
                        )
                    )
                    max_data = max_data_result.scalar_one_or_none()
                    
                    if not max_data:
                        logger.warning(
                            f"Manager MAX chat_id not found in max_messenger_data: "
                            f"staff_id={ticket.assigned_staff_id}, max_user_id={staff_member.max_user_id}"
                        )
                    else:
                        # Format client info
                        client_info_lines = []
                        client_name = user.full_name or user.first_name or "Не указано"
                        client_info_lines.append(f"👤 Клиент: {client_name}")
                        
                        if user.phone_number:
                            client_info_lines.append(f"📱 Телефон: {user.phone_number}")
                        
                        if user.email:
                            client_info_lines.append(f"📧 Email: {user.email}")
                        
                        client_info = "\n".join(client_info_lines)
                        
                        # Build context message for manager
                        context_text = (
                            f"💬 <b>Новое сообщение от клиента (Заявка #{ticket.id})</b>\n\n"
                            f"{client_info}\n\n"
                            f"💬 Сообщение:\n{message_text}"
                        )
                        
                        # Send message to manager using max_chat_id
                        # If there's a file attachment, download and forward it
                        if file_id and message_type in [MessageType.PHOTO, MessageType.DOCUMENT, MessageType.VIDEO]:
                            try:
                                # Ensure temp directory exists
                                temp_dir = Path("media/temp")
                                temp_dir.mkdir(parents=True, exist_ok=True)
                                
                                # Generate unique filename
                                file_extension = Path(file_name).suffix if file_name else ""
                                unique_filename = f"ticket_{ticket.id}_{uuid.uuid4()}{file_extension}"
                                download_path = f"media/temp/{unique_filename}"
                                
                                # Download file from MAX URL
                                local_path = await messenger_adapter.download_file(
                                    file_url=file_id,
                                    destination=download_path
                                )
                                
                                # Send file to manager based on type
                                if message_type == MessageType.PHOTO:
                                    await messenger_adapter.send_photo(
                                        chat_id=max_data.max_chat_id,
                                        photo_path=local_path,
                                        caption=context_text,
                                        parse_mode="HTML"
                                    )
                                elif message_type in [MessageType.DOCUMENT, MessageType.VIDEO]:
                                    await messenger_adapter.send_document(
                                        chat_id=max_data.max_chat_id,
                                        document_path=local_path,
                                        caption=context_text,
                                        parse_mode="HTML"
                                    )
                                
                                # Clean up temporary file
                                try:
                                    Path(local_path).unlink()
                                except Exception as cleanup_error:
                                    logger.warning(f"Failed to delete temp file {local_path}: {cleanup_error}")
                                
                                logger.info(
                                    f"File forwarded to manager: ticket_id={ticket.id}, "
                                    f"file_type={message_type.value}, file_name={file_name}"
                                )
                            except Exception as file_error:
                                logger.error(
                                    f"Failed to forward file to manager: ticket_id={ticket.id}, "
                                    f"error={file_error}",
                                    exc_info=True
                                )
                                # Fallback: send text message with file URL
                                fallback_text = (
                                    f"{context_text}\n\n"
                                    f"⚠️ Не удалось переслать файл автоматически.\n"
                                    f"📎 Ссылка для скачивания файла:\n{file_id}"
                                )
                                await messenger_adapter.send_message(
                                    chat_id=max_data.max_chat_id,
                                    text=fallback_text,
                                    parse_mode="HTML"
                                )
                        else:
                            # Text message or voice - send as text
                            # For voice messages, include the URL in the message
                            if message_type == MessageType.VOICE and file_id:
                                context_text += f"\n\n🔗 Ссылка для скачивания голосового сообщения:\n{file_id}"
                            
                            await messenger_adapter.send_message(
                                chat_id=max_data.max_chat_id,
                                text=context_text,
                                parse_mode="HTML"
                            )
                        
                        logger.info(
                            f"Client message forwarded to manager: ticket_id={ticket.id}, "
                            f"staff_id={ticket.assigned_staff_id}, max_user_id={staff_member.max_user_id}, "
                            f"max_chat_id={max_data.max_chat_id}"
                        )
            
            except Exception as e:
                logger.error(
                    f"Error forwarding client message to manager: ticket_id={ticket.id}, "
                    f"staff_id={ticket.assigned_staff_id}, error={e}",
                    exc_info=True
                )
        
        # Log action
        await _log_action(
            session=session,
            action_type=ActionType.MESSAGE_SENT,
            ticket_id=ticket.id,
            user_id=user.id,
            action_details={
                "message_type": message_type.value,
                "has_file": file_id is not None
            }
        )
        
        # Note: session.commit() is handled by middleware
        # Don't commit here to avoid greenlet_spawn error
        
        logger.info(
            f"Client message handled: ticket_id={ticket.id}, "
            f"client_id={user.id}, message_type={message_type.value}"
        )
    
    except Exception as e:
        # Note: session.rollback() is handled by middleware
        logger.error(
            f"Error handling client message to ticket: ticket_id={ticket.id}, error={e}",
            exc_info=True
        )
        raise


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
            elif attachment_type == "voice":
                return "голосовое сообщение"
            elif attachment_type == "video":
                return "видео"
    
    return "сообщение"
