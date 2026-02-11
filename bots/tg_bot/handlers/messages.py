"""
Message Handlers

Паттерн: Обработка текстовых сообщений и медиа
- Используйте F (Magic Filter) для фильтрации по типу контента
- Используйте StateFilter для обработки в конкретных состояниях
- Обрабатывайте ошибки gracefully
"""

import logging

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.states import (
    EmployeeStates,
    FormStates,
    InvoiceStates,
    ProfileStates,
    RegistrationStates,
    SupportStates,
)
from database.models import Ticket, TicketStatus
from services.ticket_service import handle_client_message_to_ticket

logger = logging.getLogger(__name__)

router = Router(name="messages")


@router.message(StateFilter(RegistrationStates.waiting_for_name), F.text)
async def process_name_input(message: Message, state: FSMContext):
    """
    Обработчик ввода имени в состоянии регистрации.

    Паттерн:
    - Проверка на StateFilter
    - Валидация входных данных
    - Сохранение в FSMContext
    - Переход к следующему состоянию
    """
    name = message.text.strip()

    if len(name) < 2:
        await message.answer("❌ Имя слишком короткое. Попробуйте еще раз:")
        return

    await state.update_data(name=name)
    await state.set_state(RegistrationStates.waiting_for_email)

    await message.answer(f"✅ Отлично, {name}!\n\nТеперь введите ваш email:")


@router.message(StateFilter(FormStates.waiting_for_file), F.document)
async def process_document_upload(message: Message, state: FSMContext):
    """
    Обработчик загрузки документа.

    Паттерн:
    - Фильтр по типу контента (F.document)
    - Получение информации о файле
    - Сохранение file_id для дальнейшей работы
    """
    document = message.document

    # Проверка размера файла (например, макс 10 МБ)
    max_size = 10 * 1024 * 1024
    if document.file_size > max_size:
        await message.answer("❌ Файл слишком большой. Максимальный размер: 10 МБ")
        return

    await state.update_data(file_id=document.file_id, file_name=document.file_name)

    await message.answer(f"✅ Файл '{document.file_name}' получен!\n\nПодтвердите отправку?")
    await state.set_state(FormStates.waiting_for_confirmation)


@router.message(F.photo)
async def process_photo(message: Message):
    """
    Обработчик фотографий (без привязки к состоянию).

    Паттерн:
    - Получение фото в лучшем качестве ([-1])
    - Сохранение file_id
    """
    photo = message.photo[-1]  # Берем фото в лучшем качестве

    await message.answer(
        f"📸 Фото получено!\nРазмер: {photo.file_size} байт\nID: <code>{photo.file_id}</code>", parse_mode="HTML"
    )


# ========== Client Ticket Message Routing ==========


async def get_client_active_ticket(session: AsyncSession, tg_user_id: int) -> Ticket | None:
    """
    Get client's active ticket if one exists.
    
    Returns the most recent ticket with status NEW, IN_PROGRESS, or WAITING_CLIENT.
    
    Args:
        session: Database session
        tg_user_id: Client's Telegram user ID
    
    Returns:
        Ticket object if found, None otherwise
    """
    result = await session.execute(
        select(Ticket)
        .where(
            Ticket.tg_user_id == tg_user_id,
            Ticket.ticket_status.in_([
                TicketStatus.NEW,
                TicketStatus.IN_PROGRESS,
                TicketStatus.WAITING_CLIENT
            ])
        )
        .order_by(Ticket.created_at.desc())
        .limit(1)
    )
    
    return result.scalar_one_or_none()


@router.message(F.text & ~StateFilter(
    RegistrationStates,
    InvoiceStates,
    SupportStates,
    ProfileStates,
    FormStates,
    EmployeeStates
))
async def route_client_text_message(
    message: Message,
    session: AsyncSession,
    bot: Bot
):
    """
    Route client text messages to assigned employee if active ticket exists.
    
    This handler intercepts client messages when they're not in any specific
    conversation flow and routes them to the employee assigned to their active ticket.
    
    Requirements: 6.1, 6.7
    """
    tg_user_id = message.from_user.id
    
    try:
        # Check if client has an active ticket
        ticket = await get_client_active_ticket(session, tg_user_id)
        
        if ticket and ticket.assigned_staff_id:
            # Route message to assigned employee
            await handle_client_message_to_ticket(bot, session, ticket.id, message)
            await session.commit()
            
            # Acknowledge receipt to client
            await message.answer(
                f"✅ Ваше сообщение отправлено сотруднику (Тикет #{ticket.id})"
            )
            
            logger.info(
                f"Client message routed to employee: client_id={tg_user_id}, "
                f"ticket_id={ticket.id}, employee_id={ticket.assigned_staff_id}"
            )
        else:
            # No active ticket - use default echo handler
            await message.answer(
                f"Вы написали: {message.text}\n\n"
                f"Используйте /help для списка команд."
            )
    
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Error routing client message: client_id={tg_user_id}, error={e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при отправке сообщения.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.message((F.photo | F.document) & ~StateFilter(
    RegistrationStates,
    InvoiceStates,
    SupportStates,
    ProfileStates,
    FormStates,
    EmployeeStates
))
async def route_client_file_message(
    message: Message,
    session: AsyncSession,
    bot: Bot
):
    """
    Route client file attachments to assigned employee if active ticket exists.
    
    This handler intercepts client file messages when they're not in any specific
    conversation flow and routes them to the employee assigned to their active ticket.
    
    Requirements: 6.3, 6.7
    """
    tg_user_id = message.from_user.id
    
    try:
        # Check if client has an active ticket
        ticket = await get_client_active_ticket(session, tg_user_id)
        
        if ticket and ticket.assigned_staff_id:
            # Route file to assigned employee
            await handle_client_message_to_ticket(bot, session, ticket.id, message)
            await session.commit()
            
            # Acknowledge receipt to client
            file_name = ""
            if message.document:
                file_name = message.document.file_name or "документ"
            elif message.photo:
                file_name = "фото"
            
            await message.answer(
                f"✅ Ваш файл ({file_name}) отправлен сотруднику (Тикет #{ticket.id})"
            )
            
            logger.info(
                f"Client file routed to employee: client_id={tg_user_id}, "
                f"ticket_id={ticket.id}, employee_id={ticket.assigned_staff_id}, "
                f"file_type={'document' if message.document else 'photo'}"
            )
        else:
            # No active ticket - inform client
            await message.answer(
                "📎 Файл получен, но у вас нет активных обращений.\n\n"
                "Используйте /help для списка команд."
            )
    
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Error routing client file: client_id={tg_user_id}, error={e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при отправке файла.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.message(F.text)
async def echo_handler(message: Message):
    """
    Эхо-обработчик для необработанных текстовых сообщений.

    Паттерн:
    - Ловит все текстовые сообщения, не обработанные выше
    - Полезен для отладки и fallback
    """
    await message.answer(f"Вы написали: {message.text}\n\nИспользуйте /help для списка команд.")
