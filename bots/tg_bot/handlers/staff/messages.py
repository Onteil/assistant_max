"""
Employee Focus Mode Message Handlers

Handles message routing when employee is in focus mode on a ticket.
Implements bidirectional messaging between employees and clients.

Requirements: 4.2, 4.3, 4.4
"""

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.states import EmployeeStates
from bots.tg_bot.texts import (
    BTN_ACTIVE_TICKETS,
    BTN_ARCHIVE_SEARCH,
    BTN_EMPLOYEE_SETTINGS,
    BTN_ADMIN_PANEL,
)
from database.models import FileType, Staff_Member
from services.ticket_service import send_message_to_client
from services.validation_service import classify_file_type

logger = logging.getLogger(__name__)

router = Router(name="employee_messages")


# ========== Helper Functions ==========


async def is_staff_member(session: AsyncSession, user_id: int) -> Staff_Member | None:
    """
    Check if user is a staff member and return their record.
    
    Args:
        session: Database session
        user_id: Telegram user ID
    
    Returns:
        Staff_Member object if user is staff, None otherwise
    """
    try:
        from sqlalchemy import select
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == user_id,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking staff member status for user {user_id}: {e}", exc_info=True)
        return None


# ========== Focus Mode Message Handlers ==========


@router.message(EmployeeStates.in_focus, F.photo | F.document | F.voice | F.video | F.audio | F.video_note)
async def handle_focus_file_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle file attachment in focus mode.
    
    - Retrieves focused_ticket_id from FSM
    - Sends file to client with caption (if provided)
    - Stores file attachment in database
    - Logs action
    
    Supports: photo, document, voice, video, audio, video_note
    
    Requirements: 4.3, 15.1, 15.2
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            await state.clear()
            return
        
        # Get focused ticket from FSM data
        data = await state.get_data()
        focused_ticket_id = data.get("focused_ticket_id")
        
        if not focused_ticket_id:
            logger.error(f"Employee {user_id} in focus mode but no focused_ticket_id in FSM")
            await state.clear()
            await message.answer(
                "❌ Ошибка состояния. Пожалуйста, выберите тикет заново.\n"
                "Используйте /manager для возврата в меню."
            )
            return
        
        # Determine file type and get file_id
        file_id = None
        file_type = None
        file_name = None
        telegram_media_type = None
        
        if message.photo:
            # Get the largest photo
            file_id = message.photo[-1].file_id
            file_type = FileType.IMAGE
            file_name = "photo.jpg"
            telegram_media_type = "photo"
        elif message.voice:
            file_id = message.voice.file_id
            file_type = FileType.OTHER
            file_name = "voice.ogg"
            telegram_media_type = "voice"
        elif message.video:
            file_id = message.video.file_id
            file_type = FileType.OTHER
            file_name = message.video.file_name or "video.mp4"
            telegram_media_type = "video"
        elif message.audio:
            file_id = message.audio.file_id
            file_type = FileType.OTHER
            file_name = message.audio.file_name or "audio.mp3"
            telegram_media_type = "audio"
        elif message.video_note:
            file_id = message.video_note.file_id
            file_type = FileType.OTHER
            file_name = "video_note.mp4"
            telegram_media_type = "video_note"
        elif message.document:
            file_id = message.document.file_id
            file_name = message.document.file_name or "document"
            telegram_media_type = "document"
            
            # Classify file type based on extension
            file_type = classify_file_type(file_name)
        
        if not file_id:
            await message.answer(
                "❌ Не удалось получить файл. Пожалуйста, попробуйте снова."
            )
            return
        
        # Get caption if provided
        caption = message.caption.strip() if message.caption else None
        
        # Send file to client (signature will be appended to caption if provided)
        await send_message_to_client(
            bot=message.bot,
            session=session,
            ticket_id=focused_ticket_id,
            employee_id=user_id,
            message_text=caption or f"📎 {file_name}",
            file_id=file_id,
            file_type=file_type,
            telegram_media_type=telegram_media_type,
            messenger="telegram"
        )
        
        # Confirm to employee
        await message.answer(
            "✅ Файл успешно отправлен клиенту."
        )
        
        logger.info(
            f"Employee {user_id} sent file to ticket {focused_ticket_id}: {file_name}"
        )
        
    except Exception as e:
        logger.error(
            f"Error handling focus file message: user={message.from_user.id}, error={e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при отправке файла.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.message(
    EmployeeStates.in_focus,
    F.text 
    & ~F.text.startswith("❌ Снять фокус с заявки #")
)
async def handle_focus_text_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle text message in focus mode.
    
    - Retrieves focused_ticket_id from FSM
    - Appends employee signature
    - Sends message to client
    - Stores message in database
    - Logs action
    
    NOTE: This handler is registered AFTER handle_focus_file_message,
    so media messages with captions are handled by the file handler first.
    
    Requirements: 4.2, 4.4, 5.1
    """
    try:
        user_id = message.from_user.id
        logger.info(
            f"[MESSAGES ROUTER] handle_focus_text_message called by user {user_id}, "
            f"text='{message.text[:50] if message.text else None}'"
        )
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            await message.answer(
                "❌ У вас нет доступа к интерфейсу сотрудника."
            )
            await state.clear()
            return
        
        # Get focused ticket from FSM data
        data = await state.get_data()
        focused_ticket_id = data.get("focused_ticket_id")
        
        if not focused_ticket_id:
            logger.error(f"Employee {user_id} in focus mode but no focused_ticket_id in FSM")
            await state.clear()
            await message.answer(
                "❌ Ошибка состояния. Пожалуйста, выберите тикет заново.\n"
                "Используйте /manager для возврата в меню."
            )
            return
        
        # Get message text
        message_text = message.text.strip()
        
        if not message_text:
            await message.answer(
                "❌ Сообщение не может быть пустым."
            )
            return
        
        # Send message to client (signature will be appended by service)
        await send_message_to_client(
            bot=message.bot,
            session=session,
            ticket_id=focused_ticket_id,
            employee_id=user_id,
            message_text=message_text,
            messenger="telegram"
        )
        
        # Confirm to employee
        await message.answer(
            "✅ Сообщение отправлено клиенту."
        )
        
        logger.info(
            f"Employee {user_id} sent text message to ticket {focused_ticket_id}"
        )
        
    except Exception as e:
        logger.error(
            f"Error handling focus text message: user={message.from_user.id}, error={e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при отправке сообщения.\n"
            "Пожалуйста, попробуйте позже."
        )


# ========== Message Without Focus Handler ==========


# OLD VERSION - Commented out to fix calendar routing bug
# This handler was too broad and intercepted calendar commands
# @router.message(F.text | F.photo | F.document)
# async def handle_message_without_focus_OLD(
#     message: Message,
#     state: FSMContext,
#     session: AsyncSession
# ) -> None:
#     """
#     Handle messages sent by employee when not in focus mode.
#     
#     Requires explicit ticket selection before sending messages.
#     Prompts employee to select a ticket or enter focus mode.
#     
#     Requirements: 4.5, 13.3
#     """
#     try:
#         user_id = message.from_user.id
#         
#         # Check if user is in CalendarStates - let calendar handlers process it
#         current_state = await state.get_state()
#         from bots.tg_bot.states import CalendarStates
#         if current_state in [s.state for s in CalendarStates.__all_states__]:
#             return
#         
#         # Ignore commands (messages starting with /)
#         if message.text and message.text.startswith('/'):
#             return
#         
#         # Ignore reply keyboard buttons (they have their own handlers)
#         from bots.tg_bot.texts import BTN_ACTIVE_TICKETS, BTN_ARCHIVE_SEARCH, BTN_EMPLOYEE_SETTINGS, BTN_ADMIN_PANEL
#         if message.text and message.text in [BTN_ACTIVE_TICKETS, BTN_ARCHIVE_SEARCH, BTN_EMPLOYEE_SETTINGS, BTN_ADMIN_PANEL]:
#             return
#         
#         # Ignore calendar commands (they have their own handlers)
#         # Check if message contains calendar-related keywords
#         if message.text:
#             text_lower = message.text.lower()
#             calendar_keywords = ["января", "февраля", "марта", "апреля", "мая", "июня",
#                                "июля", "августа", "сентября", "октября", "ноября", "декабря",
#                                "рабочее время", "продленное", "нерабочее", "удалить правило"]
#             if any(keyword in text_lower for keyword in calendar_keywords):
#                 return
#         
#         # Verify user is staff member
#         employee = await is_staff_member(session, user_id)
#         if not employee:
#             # Not a staff member, ignore (let other handlers handle it)
#             return
#         
#         # Check current state
#         current_state = await state.get_state()
#         
#         # If in any other employee state (closing, transferring, searching), ignore
#         # Those states have their own handlers
#         if current_state in [
#             EmployeeStates.closing_ticket,
#             EmployeeStates.transferring_ticket,
#             EmployeeStates.searching_archive
#         ]:
#             return
#         
#         # Employee is trying to send a message without being in focus mode
#         await message.answer(
#             "❌ Вы не в режиме фокуса.\n\n"
#             "Для отправки сообщений клиенту:\n"
#             "1. Используйте /manager для просмотра активных заявок\n"
#             "2. Выберите тикет и нажмите 'Взять в работу'\n"
#             "3. После этого ваши сообщения будут автоматически отправляться клиенту"
#         )
#         
#         logger.info(
#             f"Employee {user_id} attempted to send message without focus mode"
#         )
#         
#     except Exception as e:
#         logger.error(
#             f"Error handling message without focus: user={message.from_user.id}, error={e}",
#             exc_info=True


# NEW VERSION - Only handles messages when state is None
# This prevents interference with calendar and other FSM-based handlers

@router.message(
    StateFilter(None),
    F.text 
    & ~F.text.in_([BTN_ACTIVE_TICKETS, BTN_ARCHIVE_SEARCH, BTN_EMPLOYEE_SETTINGS, BTN_ADMIN_PANEL])
    & ~F.text.startswith("❌ Снять фокус с заявки #")
    & ~F.text.startswith("/")
    | F.photo
    | F.document
)
async def handle_message_without_focus(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle messages sent by employee when not in focus mode (state is None).
    
    Requires explicit ticket selection before sending messages.
    Prompts employee to select a ticket or enter focus mode.
    
    Excludes Reply keyboard buttons which are handled by common.py handlers.
    
    CRITICAL: Checks if user is staff member and returns early if not,
    allowing client handlers to process non-staff messages.
    
    Requirements: 4.5, 13.3
    
    NOTE: This handler only triggers when FSM state is None, allowing
    other handlers with specific states to process messages first.
    """
    try:
        user_id = message.from_user.id
        
        # CRITICAL: Check if user is staff member
        # If not staff, return immediately to let client handlers process
        employee = await is_staff_member(session, user_id)
        if not employee:
            # Not a staff member, let client handlers process this message
            return
        
        # Employee is trying to send a message without being in focus mode
        await message.answer(
            "❌ Вы не в режиме фокуса.\n\n"
            "Для отправки сообщений клиенту:\n"
            "1. Используйте /manager для просмотра активных заявок\n"
            "2. Выберите тикет и нажмите 'Взять в работу'\n"
            "3. После этого ваши сообщения будут автоматически отправляться клиенту"
        )
        
        logger.info(
            f"Employee {user_id} attempted to send message without focus mode"
        )
        
    except Exception as e:
        logger.error(
            f"Error handling message without focus: user={message.from_user.id}, error={e}",
            exc_info=True
        )

