"""
Employee Focus Mode Message Handlers for MAX Bot

Handles message routing when employee is in focus mode on a ticket.
Implements bidirectional messaging between employees and clients.

Requirements: 4.2, 4.3, 4.4
"""

import logging

from maxapi.types import MessageCreated
from maxapi.context import MemoryContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.states import EmployeeStates
from database.models import Staff_Member, FileType
from services.ticket_service import send_message_to_client_max
from services.validation_service import classify_file_type

logger = logging.getLogger(__name__)


# ========== Helper Functions ==========


async def is_staff_member(session: AsyncSession, max_user_id: int) -> Staff_Member | None:
    """
    Check if user is a staff member and return their record.
    
    Args:
        session: Database session
        max_user_id: MAX user ID
    
    Returns:
        Staff_Member object if user is staff, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == max_user_id,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking staff member status for MAX user {max_user_id}: {e}", exc_info=True)
        return None


# ========== Focus Mode Message Handlers ==========


async def handle_focus_message(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle messages (text, files, images) in focus mode.
    
    - Retrieves focused_ticket_id from FSM
    - Sends message/file to client with signature
    - Stores message in database
    - Logs action
    
    Supports: text, photo, document, voice, video, audio
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Checks event.message.body.attachments for files
    - Uses MemoryContext for FSM state management
    
    Requirements: 4.2, 4.3, 4.4, 15.1, 15.2
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    logger.info(
        f"handle_focus_message called: max_user_id={max_user_id}, "
        f"chat_id={chat_id}, has_text={bool(event.message.body.text)}"
    )
    
    try:
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Get focused ticket from FSM data
        data = await context.get_data()
        focused_ticket_id = data.get("focused_ticket_id")
        
        if not focused_ticket_id:
            logger.error(f"Employee {max_user_id} in focus mode but no focused_ticket_id in FSM")
            await context.clear()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка состояния. Пожалуйста, выберите заявку заново.\nИспользуйте /manager для возврата в меню.",
                parse_mode="HTML"
            )
            return
        
        # Check if message has attachments
        has_attachments = (
            event.message.body.attachments and 
            len(event.message.body.attachments) > 0
        )
        
        if has_attachments:
            # Handle file attachments
            await handle_focus_file_message(
                event, context, session, messenger_adapter, 
                employee, focused_ticket_id
            )
        else:
            # Handle text message
            await handle_focus_text_message(
                event, context, session, messenger_adapter,
                employee, focused_ticket_id
            )
    
    except Exception as e:
        logger.error(
            f"Error handling focus message: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при отправке сообщения.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )


async def handle_focus_text_message(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    employee: Staff_Member,
    focused_ticket_id: int
) -> None:
    """
    Handle text message in focus mode.
    
    Args:
        event: MessageCreated event
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
        employee: Staff member object
        focused_ticket_id: ID of focused ticket
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    # Get message text
    message_text = event.message.body.text.strip() if event.message.body.text else None
    
    if not message_text:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Сообщение не может быть пустым.",
            parse_mode="HTML"
        )
        return
    
    try:
        # Send message to client (signature will be appended by service)
        await send_message_to_client_max(
            messenger_adapter=messenger_adapter,
            session=session,
            ticket_id=focused_ticket_id,
            employee_id=employee.id,  # Use internal staff ID
            message_text=message_text,
            messenger="max"
        )
        
        # Confirm to employee
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="✅ Сообщение отправлено клиенту.",
            parse_mode="HTML"
        )
        
        logger.info(
            f"Employee {max_user_id} sent text message to ticket {focused_ticket_id}"
        )
    
    except ValueError as e:
        # Handle case when client doesn't have MAX messenger data
        if "Client has no MAX messenger data" in str(e):
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "❌ Не удалось отправить сообщение.\n\n"
                    "Клиент использует только Telegram бота.\n"
                    "Для общения с этим клиентом используйте Telegram."
                ),
                parse_mode="HTML"
            )
            logger.warning(
                f"Employee {max_user_id} tried to send message to Telegram-only client "
                f"(ticket {focused_ticket_id})"
            )
        else:
            # Re-raise other ValueError exceptions
            raise


async def handle_focus_file_message(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    employee: Staff_Member,
    focused_ticket_id: int
) -> None:
    """
    Handle file attachment in focus mode.
    
    Args:
        event: MessageCreated event
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
        employee: Staff member object
        focused_ticket_id: ID of focused ticket
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    # Process each attachment
    for attachment in event.message.body.attachments:
        try:
            file_id = None
            file_type = None
            file_name = None
            max_media_type = attachment.type
            
            # Determine file type based on attachment type
            if attachment.type == "image":
                file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                file_type = FileType.IMAGE
                file_name = "image.jpg"
            
            elif attachment.type == "file":
                file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                file_name = attachment.payload.name if hasattr(attachment.payload, 'name') else "document"
                # Classify file type based on extension
                file_type = classify_file_type(file_name)
            
            elif attachment.type == "voice":
                file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                file_type = FileType.OTHER
                file_name = "voice.ogg"
            
            elif attachment.type == "video":
                file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                file_type = FileType.OTHER
                file_name = attachment.payload.name if hasattr(attachment.payload, 'name') else "video.mp4"
            
            elif attachment.type == "audio":
                file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                file_type = FileType.OTHER
                file_name = attachment.payload.name if hasattr(attachment.payload, 'name') else "audio.mp3"
            
            else:
                logger.warning(f"Unknown attachment type: {attachment.type}")
                continue
            
            if not file_id:
                logger.warning(f"No file URL found for attachment type: {attachment.type}")
                continue
            
            # Get caption if provided (from message text)
            caption = event.message.body.text.strip() if event.message.body.text else None
            
            # Use file name as message text if no caption
            message_text = caption if caption else f"📎 {file_name}"
            
            # Send file to client
            await send_message_to_client_max(
                messenger_adapter=messenger_adapter,
                session=session,
                ticket_id=focused_ticket_id,
                employee_id=employee.id,  # Use internal staff ID
                message_text=message_text,
                file_id=file_id,
                file_type=file_type,
                max_media_type=max_media_type,
                messenger="max"
            )
            
            # Confirm to employee
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"✅ Файл '{file_name}' отправлен клиенту.",
                parse_mode="HTML"
            )
            
            logger.info(
                f"Employee {max_user_id} sent file to ticket {focused_ticket_id}: {file_name}"
            )
        
        except ValueError as e:
            # Handle case when client doesn't have MAX messenger data
            if "Client has no MAX messenger data" in str(e):
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=(
                        "❌ Не удалось отправить файл.\n\n"
                        "Клиент использует только Telegram бота.\n"
                        "Для общения с этим клиентом используйте Telegram."
                    ),
                    parse_mode="HTML"
                )
                logger.warning(
                    f"Employee {max_user_id} tried to send file to Telegram-only client "
                    f"(ticket {focused_ticket_id})"
                )
            else:
                # Re-raise other ValueError exceptions
                raise
        
        except Exception as e:
            logger.error(
                f"Error processing attachment: type={attachment.type}, error={e}",
                exc_info=True
            )
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка при отправке файла.",
                parse_mode="HTML"
            )


async def handle_message_without_focus(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle messages sent by employee when not in focus mode.
    
    Requires explicit ticket selection before sending messages.
    Prompts employee to select a ticket or enter focus mode.
    
    CRITICAL: Checks if user is staff member and returns early if not,
    allowing client handlers to process non-staff messages.
    
    Requirements: 4.5, 13.3
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    try:
        # CRITICAL: Check if user is staff member
        # If not staff, return immediately to let client handlers process
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            # Not a staff member, let client handlers process this message
            return
        
        # Employee is trying to send a message without being in focus mode
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "❌ Вы не в режиме фокуса.\n\n"
                "Для отправки сообщений клиенту:\n"
                "1. Используйте /manager для просмотра активных заявок\n"
                "2. Выберите заявку и нажмите 'Взять в работу'\n"
                "3. После этого ваши сообщения будут автоматически отправляться клиенту"
            ),
            parse_mode="HTML"
        )
        
        logger.info(
            f"Employee {max_user_id} attempted to send message without focus mode"
        )
    
    except Exception as e:
        logger.error(
            f"Error handling message without focus: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
