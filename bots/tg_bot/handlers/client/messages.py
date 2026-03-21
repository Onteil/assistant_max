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
    AdminStates,
    CalendarStates,
    EmployeeStates,
    FormStates,
    InvoiceStates,
    ProfileStates,
    RegistrationStates,
    SettingsStates,
    SupportStates,
)
from database.models import Ticket, TicketStatus, User
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
        .join(User, Ticket.user_id == User.id)
        .where(
            User.tg_user_id == tg_user_id,
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


# Handler for client messages when they have active ticket
@router.message(
    ~StateFilter(
        # Exclude all staff states so staff messages are not caught by client handler
        EmployeeStates.in_focus,
        EmployeeStates.closing_ticket,
        EmployeeStates.transferring_ticket,
        EmployeeStates.searching_archive,
        # Exclude all admin states
        AdminStates.adding_employee_id,
        AdminStates.adding_employee_role,
        AdminStates.adding_employee_signature,
        AdminStates.editing_employee_signature,
        AdminStates.editing_employee_name,
        AdminStates.selecting_backup_manager,
        AdminStates.reviewing_registration,
        AdminStates.entering_rejection_reason,
        AdminStates.WAITING_REJECTION_REASON,
        AdminStates.creating_broadcast_content,
        AdminStates.selecting_broadcast_target,
        AdminStates.confirming_broadcast,
        AdminStates.resolving_key_conflict,
        AdminStates.waiting_for_reassign_staff,
        AdminStates.entering_calendar_rule,
        AdminStates.selecting_period_to_clear,
        # Exclude all calendar states
        CalendarStates.managing_calendar,
        CalendarStates.confirming_add_rule,
        CalendarStates.confirming_delete_rule,
        CalendarStates.waiting_for_clear_period_input,
        CalendarStates.waiting_for_clear_period_confirmation,
        # Exclude all settings states
        SettingsStates.entering_timeout_value,
        SettingsStates.entering_escalation_chat_id,
        SettingsStates.testing_escalation_channel,
        SettingsStates.entering_duty_account_id,
        SettingsStates.entering_nps_frequency,
        SettingsStates.entering_nps_trigger_timing,
        SettingsStates.entering_renewal_reminder_days,
    ),
    F.text 
    & ~F.text.startswith('/') 
    & ~F.text.startswith('📥 Активные обращения')  # Exclude active tickets button with counter
    & ~F.text.in_([
        # Client buttons
        "📥 Активные заявки", 
        "🗃️ Архив обращений", 
        "⚙️ Настройки",
        # Staff buttons (to prevent interception by client handler)
        "🔐 Админ-панель",
        "📥 Активные заявки",  # Staff also has this
        "🗃️ Архив обращений",  # Staff also has this
        "⚙️ Настройки"  # Staff also has this
    ])
)
async def route_client_text_message(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext
):
    """
    Route client text messages to assigned employee if active ticket exists.
    
    This handler intercepts client messages and routes them to the employee 
    assigned to their active ticket if one exists.
    
    Excludes staff button texts and staff states (via StateFilter) so they 
    can be handled by staff handlers.
    
    Requirements: 6.1, 6.7
    """
    
    tg_user_id = message.from_user.id
    
    # Check current state - if in specific flow, don't intercept
    current_state = await state.get_state()
    
    # List of CLIENT, EMPLOYEE and ADMIN states where we should NOT intercept messages
    excluded_states = [
        # Client states
        "InvoiceStates:selecting_organization",
        "InvoiceStates:adding_new_inn",
        "InvoiceStates:selecting_keys",
        "InvoiceStates:adding_new_key",
        "InvoiceStates:entering_description",
        "InvoiceStates:entering_email",
        "SupportStates:selecting_key_context",
        "SupportStates:adding_new_key",
        "ProfileStates:adding_inn",
        "ProfileStates:adding_key",
        "ProfileStates:changing_phone",
        "RegistrationStates:waiting_for_phone",
        "RegistrationStates:waiting_for_name",
        "RegistrationStates:waiting_for_email",
        "RegistrationStates:waiting_for_inn",
        "RegistrationStates:waiting_for_key",
        # Employee states
        "EmployeeStates:in_focus",
        "EmployeeStates:closing_ticket",
        "EmployeeStates:transferring_ticket",
        "EmployeeStates:searching_archive",
        # Admin states
        "AdminStates:adding_employee_id",
        "AdminStates:adding_employee_role",
        "AdminStates:adding_employee_signature",
        "AdminStates:editing_employee_signature",
        "AdminStates:editing_employee_name",
        "AdminStates:selecting_backup_manager",
        "AdminStates:reviewing_registration",
        "AdminStates:entering_rejection_reason",
        "AdminStates:WAITING_REJECTION_REASON",
        "AdminStates:creating_broadcast_content",
        "AdminStates:selecting_broadcast_target",
        "AdminStates:confirming_broadcast",
        "AdminStates:resolving_key_conflict",
        "AdminStates:waiting_for_reassign_staff",
        "AdminStates:entering_calendar_rule",
        "AdminStates:selecting_period_to_clear",
        # Calendar states
        "CalendarStates:managing_calendar",
        "CalendarStates:confirming_add_rule",
        "CalendarStates:confirming_delete_rule",
        "CalendarStates:waiting_for_clear_period_input",
        "CalendarStates:waiting_for_clear_period_confirmation",
        # Settings states
        "SettingsStates:entering_timeout_value",
        "SettingsStates:entering_escalation_chat_id",
        "SettingsStates:testing_escalation_channel",
        "SettingsStates:entering_duty_account_id",
        "SettingsStates:entering_nps_frequency",
        "SettingsStates:entering_nps_trigger_timing",
        "SettingsStates:entering_renewal_reminder_days",
    ]
    
    if current_state and current_state in excluded_states:
        # Don't intercept - let specific handler process it
        return
    
    try:
        # Check FSM data for active_ticket_id
        data = await state.get_data()
        active_ticket_id = data.get("active_ticket_id")
        
        if active_ticket_id:
            # Verify ticket exists and is active
            from database.models import Ticket
            stmt = select(Ticket).where(Ticket.id == active_ticket_id)
            result = await session.execute(stmt)
            ticket = result.scalar_one_or_none()
            
            if ticket and ticket.ticket_status in [TicketStatus.NEW, TicketStatus.IN_PROGRESS, TicketStatus.WAITING_CLIENT]:
                # Route message to assigned employee
                await handle_client_message_to_ticket(bot, session, ticket.id, message)
                await session.commit()
                
                # Acknowledge receipt to client
                await message.answer(
                    f"✅ Ваше сообщение отправлено сотруднику (Заявка #{ticket.id})"
                )
                
                logger.info(
                    f"Client message routed to employee: client_id={tg_user_id}, "
                    f"ticket_id={ticket.id}, employee_id={ticket.assigned_staff_id}"
                )
                return
        
        # No active ticket in FSM - check database
        ticket = await get_client_active_ticket(session, tg_user_id)
        
        if ticket and ticket.assigned_staff_id:
            # Route message to assigned employee
            await handle_client_message_to_ticket(bot, session, ticket.id, message)
            await session.commit()
            
            # Acknowledge receipt to client
            await message.answer(
                f"✅ Ваше сообщение отправлено сотруднику (Заявка #{ticket.id})"
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


# Handler for client file messages when they have active ticket
@router.message(
    ~StateFilter(
        # Exclude all staff states so staff file messages are not caught by client handler
        EmployeeStates.in_focus,
        EmployeeStates.closing_ticket,
        EmployeeStates.transferring_ticket,
        EmployeeStates.searching_archive,
        # Exclude all admin states
        AdminStates.adding_employee_id,
        AdminStates.adding_employee_role,
        AdminStates.adding_employee_signature,
        AdminStates.editing_employee_signature,
        AdminStates.editing_employee_name,
        AdminStates.selecting_backup_manager,
        AdminStates.reviewing_registration,
        AdminStates.entering_rejection_reason,
        AdminStates.WAITING_REJECTION_REASON,
        AdminStates.creating_broadcast_content,
        AdminStates.selecting_broadcast_target,
        AdminStates.confirming_broadcast,
        AdminStates.resolving_key_conflict,
        AdminStates.waiting_for_reassign_staff,
        AdminStates.entering_calendar_rule,
        AdminStates.selecting_period_to_clear,
        # Exclude all calendar states
        CalendarStates.managing_calendar,
        CalendarStates.confirming_add_rule,
        CalendarStates.confirming_delete_rule,
        CalendarStates.waiting_for_clear_period_input,
        CalendarStates.waiting_for_clear_period_confirmation,
        # Exclude all settings states
        SettingsStates.entering_timeout_value,
        SettingsStates.entering_escalation_chat_id,
        SettingsStates.testing_escalation_channel,
        SettingsStates.entering_duty_account_id,
        SettingsStates.entering_nps_frequency,
        SettingsStates.entering_nps_trigger_timing,
        SettingsStates.entering_renewal_reminder_days,
    ),
    F.photo | F.document | F.voice | F.video | F.audio | F.video_note
)
async def route_client_file_message(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext
):
    """
    Route client file attachments to assigned employee if active ticket exists.
    
    This handler intercepts client file messages and routes them to the employee 
    assigned to their active ticket if one exists.
    
    Excludes staff states (via StateFilter) so staff file messages in focus mode
    can be handled by staff handlers.
    
    Requirements: 6.3, 6.7
    """
    
    tg_user_id = message.from_user.id
    
    # Check current state - if in specific flow, don't intercept
    current_state = await state.get_state()
    
    # List of CLIENT states where we should NOT intercept file messages
    excluded_states = [
        "InvoiceStates:entering_description",  # May upload files with invoice
        "SupportStates:entering_problem",  # May upload files with support request
    ]
    
    if current_state and current_state in excluded_states:
        # Don't intercept - let specific handler process it
        return
    
    # Additional safety check: if user is a staff member (even with state=None),
    # don't route their files as client messages
    # This prevents edge cases where staff member has no active state
    from database.models import Staff_Member
    stmt = select(Staff_Member).where(
        Staff_Member.tg_user_id == tg_user_id,
        Staff_Member.is_active == True
    )
    result = await session.execute(stmt)
    staff_member = result.scalar_one_or_none()
    
    # If user is staff, don't route their files
    # Let staff handlers process them
    if staff_member:
        # Don't intercept - let staff handlers process it
        logger.debug(f"User {tg_user_id} is staff member, skipping client file routing")
        return
    
    logger.debug(f"User {tg_user_id} is NOT staff member, proceeding with client file routing")
    
    try:
        # Check FSM data for active_ticket_id
        data = await state.get_data()
        active_ticket_id = data.get("active_ticket_id")
        
        logger.debug(f"Client {tg_user_id} FSM data: active_ticket_id={active_ticket_id}")
        
        if active_ticket_id:
            # Verify ticket exists and is active
            from database.models import Ticket
            stmt = select(Ticket).where(Ticket.id == active_ticket_id)
            result = await session.execute(stmt)
            ticket = result.scalar_one_or_none()
            
            if ticket and ticket.ticket_status in [TicketStatus.NEW, TicketStatus.IN_PROGRESS, TicketStatus.WAITING_CLIENT]:
                # Route file to assigned employee
                await handle_client_message_to_ticket(bot, session, ticket.id, message)
                await session.commit()
                
                # Acknowledge receipt to client
                file_name = ""
                file_type_name = ""
                if message.document:
                    file_name = message.document.file_name or "документ"
                    file_type_name = "document"
                elif message.photo:
                    file_name = "фото"
                    file_type_name = "photo"
                elif message.voice:
                    file_name = "голосовое сообщение"
                    file_type_name = "voice"
                elif message.video:
                    file_name = message.video.file_name or "видео"
                    file_type_name = "video"
                elif message.audio:
                    file_name = message.audio.file_name or "аудио"
                    file_type_name = "audio"
                elif message.video_note:
                    file_name = "видео-сообщение"
                    file_type_name = "video_note"
                
                await message.answer(
                    f"✅ Ваш файл ({file_name}) отправлен сотруднику (Заявка #{ticket.id})"
                )
                
                logger.info(
                    f"Client file routed to employee: client_id={tg_user_id}, "
                    f"ticket_id={ticket.id}, employee_id={ticket.assigned_staff_id}, "
                    f"file_type={file_type_name}"
                )
                return
        
        # No active ticket in FSM - check database
        ticket = await get_client_active_ticket(session, tg_user_id)
        
        if ticket and ticket.assigned_staff_id:
            # Route file to assigned employee
            await handle_client_message_to_ticket(bot, session, ticket.id, message)
            await session.commit()
            
            # Acknowledge receipt to client
            file_name = ""
            file_type_name = ""
            if message.document:
                file_name = message.document.file_name or "документ"
                file_type_name = "document"
            elif message.photo:
                file_name = "фото"
                file_type_name = "photo"
            elif message.voice:
                file_name = "голосовое сообщение"
                file_type_name = "voice"
            elif message.video:
                file_name = message.video.file_name or "видео"
                file_type_name = "video"
            elif message.audio:
                file_name = message.audio.file_name or "аудио"
                file_type_name = "audio"
            elif message.video_note:
                file_name = "видео-сообщение"
                file_type_name = "video_note"
            
            await message.answer(
                f"✅ Ваш файл ({file_name}) отправлен сотруднику (Заявка #{ticket.id})"
            )
            
            logger.info(
                f"Client file routed to employee: client_id={tg_user_id}, "
                f"ticket_id={ticket.id}, employee_id={ticket.assigned_staff_id}, "
                f"file_type={file_type_name}"
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