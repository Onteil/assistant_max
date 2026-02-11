"""
Employee Focus Mode Message Handlers

Handles message routing when employee is in focus mode on a ticket.
Implements bidirectional messaging between employees and clients.

Requirements: 4.2, 4.3, 4.4
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.states import EmployeeStates
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


@router.message(EmployeeStates.in_focus, F.text)
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
    
    Requirements: 4.2, 4.4, 5.1
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
                "Используйте /employee для возврата в меню."
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
            message_text=message_text
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


@router.message(EmployeeStates.in_focus, F.photo | F.document)
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
                "Используйте /employee для возврата в меню."
            )
            return
        
        # Determine file type and get file_id
        file_id = None
        file_type = None
        file_name = None
        
        if message.photo:
            # Get the largest photo
            file_id = message.photo[-1].file_id
            file_type = FileType.IMAGE
            file_name = "photo.jpg"
        elif message.document:
            file_id = message.document.file_id
            file_name = message.document.file_name or "document"
            
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
            file_type=file_type
        )
        
        # Confirm to employee
        await message.answer(
            f"✅ Файл '{file_name}' отправлен клиенту."
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


# ========== Message Without Focus Handler ==========


@router.message(F.text | F.photo | F.document)
async def handle_message_without_focus(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle messages sent by employee when not in focus mode.
    
    Requires explicit ticket selection before sending messages.
    Prompts employee to select a ticket or enter focus mode.
    
    Requirements: 4.5, 13.3
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is staff member
        employee = await is_staff_member(session, user_id)
        if not employee:
            # Not a staff member, ignore (let other handlers handle it)
            return
        
        # Check current state
        current_state = await state.get_state()
        
        # If in any other employee state (closing, transferring, searching), ignore
        # Those states have their own handlers
        if current_state in [
            EmployeeStates.closing_ticket,
            EmployeeStates.transferring_ticket,
            EmployeeStates.searching_archive
        ]:
            return
        
        # Employee is trying to send a message without being in focus mode
        await message.answer(
            "❌ Вы не в режиме фокуса.\n\n"
            "Для отправки сообщений клиенту:\n"
            "1. Используйте /employee для просмотра активных тикетов\n"
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
