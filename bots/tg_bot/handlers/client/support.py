"""
Technical Support Handler

Manages the technical support conversation flow.
Checks subscription status, collects problem description (text/photo/voice/document),
routes based on working hours, and creates support tickets.

Requirements: 12.1-12.5, 13.1-13.7, 14.1-14.5, 15.1-15.6
"""

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bots.tg_bot.callback_datas import KeyCallback, RenewalCallback
from bots.tg_bot.keyboards.support_kb import (
    get_add_key_keyboard,
    get_key_context_keyboard,
    get_problem_description_keyboard,
    get_renewal_offer_keyboard,
)
from bots.tg_bot.states import SupportStates
from bots.tg_bot.texts import (
    BTN_CANCEL,
    ERROR_TEXT_TOO_LONG,
    SUPPORT_CREATE_TICKET,
    SUPPORT_NO_SUBSCRIPTION,
    SUPPORT_RESPONSE_TIME_EXTENDED,
    SUPPORT_RESPONSE_TIME_NON_WORKING,
    SUPPORT_RESPONSE_TIME_REGULAR,
    SUPPORT_ROUTING_EXTENDED,
    SUPPORT_ROUTING_NON_WORKING,
    SUPPORT_ROUTING_REGULAR,
    SUPPORT_SELECT_KEY_CONTEXT,
    SUPPORT_SUBSCRIPTION_EXPIRED,
    SUPPORT_TICKET_CREATED,
)
from database.models import (
    FileType,
    GS_Key,
    MessageType,
    SubscriptionStatus,
    TicketType,
    UploaderType,
    WorkMode,
)
from services.ticket_service import (
    create_ticket,
    get_current_work_mode,
    route_ticket,
    send_staff_notification,
)
from services.user_service import get_user_by_tg_id, get_user_keys
from services.validation_service import classify_file_type

logger = logging.getLogger(__name__)

router = Router(name="support")


# ========== Helper Functions ==========


async def has_active_renewal_ticket(session: AsyncSession, user_id: int) -> bool:
    """
    Check if user has an active RENEWAL ticket.
    
    Args:
        session: Database session
        user_id: User ID from database
    
    Returns:
        True if user has active RENEWAL ticket, False otherwise
    """
    from database.models import Ticket, TicketStatus
    
    stmt = select(Ticket).where(
        Ticket.user_id == user_id,
        Ticket.ticket_type == TicketType.RENEWAL,
        Ticket.ticket_status.in_([
            TicketStatus.NEW,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_CLIENT
        ])
    )
    
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


# ========== Entry Point ==========


@router.message(Command("support"))
async def start_support_request(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Entry point for technical support request.
    
    Checks user subscription status before proceeding:
    - ACTIVE: Proceed to problem description
    - EXPIRED/NONE: Offer renewal option
    
    Requirements: 12.1, 12.2, 12.4
    """
    tg_user_id = message.from_user.id
    
    try:
        # Clear any existing state
        await state.clear()
        
        # Get user and check subscription status
        user = await get_user_by_tg_id(session, tg_user_id)
        
        if not user:
            await message.answer(
                "❌ Пользователь не найден.\n"
                "Пожалуйста, пройдите регистрацию с помощью /start",
                reply_markup=ReplyKeyboardRemove()
            )
            logger.warning(f"Support request from unregistered user: {tg_user_id}")
            return
        
        # Check subscription status
        if user.subscription_status == SubscriptionStatus.ACTIVE:
            # Subscription active - proceed to problem description
            await state.set_state(SupportStates.entering_problem)
            await state.update_data(problem_media=[])
            
            keyboard = await get_problem_description_keyboard()
            await message.answer(
                SUPPORT_CREATE_TICKET,
                reply_markup=keyboard
            )
            
            logger.info(f"User {tg_user_id} started support request with active subscription")
        
        elif user.subscription_status == SubscriptionStatus.EXPIRED:
            # Subscription expired - offer renewal
            expiry_date = user.subscription_end_date.strftime("%d.%m.%Y") if user.subscription_end_date else "неизвестно"
            
            keyboard = await get_renewal_offer_keyboard()
            await message.answer(
                SUPPORT_SUBSCRIPTION_EXPIRED.format(expiry_date=expiry_date),
                reply_markup=keyboard
            )
            
            logger.info(f"User {tg_user_id} attempted support request with expired subscription")
        
        else:  # NONE
            # No subscription - offer renewal
            keyboard = await get_renewal_offer_keyboard()
            await message.answer(
                SUPPORT_NO_SUBSCRIPTION,
                reply_markup=keyboard
            )
            
            logger.info(f"User {tg_user_id} attempted support request with no subscription")
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error starting support request for user {tg_user_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при загрузке данных.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )


# ========== Expired Subscription Handling ==========


@router.callback_query(RenewalCallback.filter(F.action == "contact_manager"))
async def handle_expired_subscription(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot
):
    """
    Handle renewal request when subscription is expired.
    
    Creates RENEWAL ticket and routes to user's manager.
    Checks if user already has active RENEWAL ticket.
    
    Requirements: 4.6, 4.8
    """
    tg_user_id = callback.from_user.id
    
    try:
        # Get user
        user = await get_user_by_tg_id(session, tg_user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Check if user already has active RENEWAL ticket
        if await has_active_renewal_ticket(session, user.id):
            await callback.message.edit_text(
                "ℹ️ У вас уже есть активная заявка на продление подписки.\n\n"
                "Ваш менеджер получил уведомление и свяжется с вами в ближайшее время."
            )
            await callback.answer()
            logger.info(f"User {tg_user_id} already has active RENEWAL ticket")
            return
        
        # Create RENEWAL ticket
        ticket_data = {
            "ticket_type": TicketType.RENEWAL,
            "user_id": user.id,
            "assigned_staff_id": user.default_manager_id,
            "description": "Запрос на продление подписки техподдержки"
        }
        
        ticket = await create_ticket(session, ticket_data)
        
        # Get work mode for routing
        work_mode = await get_current_work_mode(session)
        routing_info = await route_ticket(session, ticket, work_mode)
        
        # Commit transaction
        await session.commit()
        
        # Refresh ticket with user relationship for notification
        from sqlalchemy.orm import selectinload
        await session.refresh(ticket, ["user"])
        
        # Send notification to manager if assigned
        if user.default_manager_id:
            await send_staff_notification(
                bot,
                user.default_manager_id,
                ticket,
                routing_info,
                session
            )
        
        # Inform user
        await callback.message.edit_text(
            f"✅ Запрос на продление создан!\n\n"
            f"Номер заявки: #{ticket.id}\n"
            f"Ваш менеджер получил уведомление и свяжется с вами в ближайшее время."
        )
        await callback.answer()
        
        logger.info(
            f"Renewal ticket created: ticket_id={ticket.id}, user={tg_user_id}, "
            f"manager={user.default_manager_id}"
        )
    
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error creating renewal ticket for user {tg_user_id}: {e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Unexpected error creating renewal ticket for user {tg_user_id}: {e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(RenewalCallback.filter(F.action == "cancel"))
async def handle_renewal_cancel(
    callback: CallbackQuery
):
    """
    Handle cancel action from renewal offer keyboard.
    
    Requirements: 4.4
    """
    await callback.message.edit_text(
        "❌ Действие отменено."
    )
    await callback.answer()
    
    logger.info(f"User {callback.from_user.id} cancelled renewal offer")


# ========== Problem Description Collection ==========


@router.callback_query(
    SupportStates.entering_problem,
    KeyCallback.filter()
)
async def handle_problem_description_callback(
    callback: CallbackQuery,
    callback_data: KeyCallback,
    state: FSMContext
):
    """
    Handle callback buttons on problem description step.
    
    Supports:
    - Cancel operation
    
    Requirements: 13.1
    """
    action = callback_data.action
    tg_user_id = callback.from_user.id
    
    if action == "cancel":
        # Cancel support request
        await state.clear()
        await callback.message.edit_text(
            "❌ Запрос техподдержки отменен."
        )
        await callback.answer()
        logger.info(f"User {tg_user_id} cancelled support request at description step")
    else:
        await callback.answer("❌ Неизвестное действие")


@router.message(SupportStates.entering_problem, F.text)
async def process_problem_description_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handle text problem description.
    
    Validates length (max 4000 characters) and stores in FSM.
    
    Requirements: 13.1, 13.2
    """
    description = message.text.strip()
    tg_user_id = message.from_user.id
    
    # Check for cancel
    if description == BTN_CANCEL:
        await state.clear()
        await message.answer(
            "❌ Запрос техподдержки отменен.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {tg_user_id} cancelled support request at description step")
        return
    
    # Validate length
    max_length = 4000
    if len(description) > max_length:
        await message.answer(
            ERROR_TEXT_TOO_LONG.format(
                max_length=max_length,
                actual_length=len(description)
            )
        )
        logger.warning(
            f"User {tg_user_id} provided too long description: {len(description)} chars"
        )
        return
    
    # Store description
    await state.update_data(problem_description=description)
    
    # Move to key context selection
    await proceed_to_key_context(message, state, session, tg_user_id)


@router.message(SupportStates.entering_problem, F.photo)
async def process_problem_description_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handle photo problem description.
    
    Stores photo file_id and optional caption in FSM.
    
    Requirements: 13.3
    """
    tg_user_id = message.from_user.id
    
    # Get largest photo
    photo = message.photo[-1]
    file_id = photo.file_id
    
    # Get caption if provided
    caption = message.caption.strip() if message.caption else "Фото проблемы"
    
    # Store media info
    data = await state.get_data()
    problem_media = data.get("problem_media", [])
    problem_media.append({
        "type": MessageType.PHOTO.value,
        "file_type": FileType.IMAGE.value,
        "file_id": file_id,
        "file_size": photo.file_size
    })
    
    await state.update_data(
        problem_description=caption,
        problem_media=problem_media
    )
    
    # Move to key context selection
    await proceed_to_key_context(message, state, session, tg_user_id)


@router.message(SupportStates.entering_problem, F.voice)
async def process_problem_description_voice(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handle voice problem description.
    
    Stores voice file_id in FSM.
    
    Requirements: 13.5
    """
    tg_user_id = message.from_user.id
    
    voice = message.voice
    file_id = voice.file_id
    
    # Store media info
    data = await state.get_data()
    problem_media = data.get("problem_media", [])
    problem_media.append({
        "type": MessageType.VOICE.value,
        "file_type": FileType.OTHER.value,
        "file_id": file_id,
        "file_size": voice.file_size,
        "duration": voice.duration
    })
    
    await state.update_data(
        problem_description="Голосовое сообщение с описанием проблемы",
        problem_media=problem_media
    )
    
    # Move to key context selection
    await proceed_to_key_context(message, state, session, tg_user_id)


@router.message(SupportStates.entering_problem, F.document)
async def process_problem_description_document(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handle document problem description.
    
    Stores document file_id and metadata in FSM.
    
    Requirements: 13.6
    """
    tg_user_id = message.from_user.id
    
    document = message.document
    file_id = document.file_id
    file_name = document.file_name or "document"
    
    # Classify file type based on extension
    file_type = classify_file_type(file_name)
    
    # Get caption if provided
    caption = message.caption.strip() if message.caption else f"Документ: {file_name}"
    
    # Store media info
    data = await state.get_data()
    problem_media = data.get("problem_media", [])
    problem_media.append({
        "type": MessageType.DOCUMENT.value,
        "file_type": file_type.value,
        "file_id": file_id,
        "file_name": file_name,
        "file_size": document.file_size
    })
    
    await state.update_data(
        problem_description=caption,
        problem_media=problem_media
    )
    
    # Move to key context selection
    await proceed_to_key_context(message, state, session, tg_user_id)


async def proceed_to_key_context(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    tg_user_id: int
):
    """Helper to move to key context selection step."""
    await state.set_state(SupportStates.selecting_key_context)
    
    # Initialize selected_key_ids as empty set
    await state.update_data(selected_key_ids=set())
    
    # Get user to get internal user.id
    user = await get_user_by_tg_id(session, tg_user_id)
    
    if not user:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "Пожалуйста, пройдите регистрацию с помощью /start",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return
    
    # Get user's keys using internal user.id
    keys = await get_user_keys(session, user.id)
    
    # Display key selection
    keyboard = await get_key_context_keyboard(keys, selected_key_ids=set(), page=0)
    await message.answer(
        SUPPORT_SELECT_KEY_CONTEXT,
        reply_markup=keyboard
    )
    
    logger.info(f"User {tg_user_id} provided problem description, moving to key context with {len(keys)} keys")


# ========== Key Context Selection ==========


@router.callback_query(
    SupportStates.selecting_key_context,
    KeyCallback.filter()
)
async def process_key_context(
    callback: CallbackQuery,
    callback_data: KeyCallback,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
):
    """
    Handle GS_Key selection for problem context with multi-select support.
    
    Supports:
    - Toggling key selection (multi-select)
    - Completing selection with "Done"
    - Skipping key selection
    - Adding a new key
    - Pagination
    - Back/Cancel navigation
    
    Requirements: 14.1, 14.3, 14.4
    """
    tg_user_id = callback.from_user.id
    action = callback_data.action
    
    try:
        # Get user for keys query
        user = await get_user_by_tg_id(session, tg_user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Get current state data
        data = await state.get_data()
        selected_key_ids = data.get("selected_key_ids", set())
        
        if action == "toggle":
            # Toggle key selection
            key_id = callback_data.key_id
            
            # Check if key is under review (PENDING_REVIEW status)
            from database.models import KeyConflictStatus
            key_result = await session.execute(
                select(GS_Key).where(GS_Key.id == key_id)
            )
            key = key_result.scalar_one_or_none()
            
            if key and key.conflict_status == KeyConflictStatus.PENDING_REVIEW:
                await callback.answer(
                    "⚠️ Этот ключ находится на проверке и не может быть выбран. Пожалуйста, выберите другой ключ.",
                    show_alert=True
                )
                return
            
            if key_id in selected_key_ids:
                selected_key_ids.remove(key_id)
            else:
                selected_key_ids.add(key_id)
            
            await state.update_data(selected_key_ids=selected_key_ids)
            
            # Update keyboard with new selection state
            keys = await get_user_keys(session, user.id)
            keyboard = await get_key_context_keyboard(keys, selected_key_ids=selected_key_ids, page=0)
            
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer()
        
        elif action == "done":
            # Complete selection with selected keys
            await state.update_data(key_ids=list(selected_key_ids))
            
            # Create support ticket
            await callback.message.edit_text("⏳ Создаем обращение...")
            await callback.answer()
            
            await create_support_ticket(callback.message, state, session, bot, tg_user_id)
        
        elif action == "skip":
            # Skip key selection
            await state.update_data(key_ids=[])
            
            # Create support ticket
            await callback.message.edit_text("⏳ Создаем обращение...")
            await callback.answer()
            
            await create_support_ticket(callback.message, state, session, bot, tg_user_id)
        
        elif action == "add_new":
            # User wants to add new key
            await state.set_state(SupportStates.adding_new_key)
            
            keyboard = await get_add_key_keyboard()
            await callback.message.edit_text(
                "➕ Введите номер ключа ГрандСметы (например: 00001_00011):\n\n"
                "Формат: 5 цифр + _ + 5 цифр",
                reply_markup=keyboard
            )
            await callback.answer()
        
        elif action == "page":
            # Pagination
            page = callback_data.page
            keys = await get_user_keys(session, user.id)
            keyboard = await get_key_context_keyboard(keys, selected_key_ids=selected_key_ids, page=page)
            
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer()
        
        elif action == "back":
            # Go back to problem description
            await state.set_state(SupportStates.entering_problem)
            await callback.message.edit_text(
                SUPPORT_CREATE_TICKET
            )
            await callback.answer()
        
        elif action == "cancel":
            # Cancel support request
            await state.clear()
            await callback.message.edit_text(
                "❌ Запрос техподдержки отменен."
            )
            await callback.answer()
            logger.info(f"User {tg_user_id} cancelled support request at key selection")
        
        else:
            await callback.answer("❌ Неизвестное действие")
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in key context selection for user {tg_user_id}: {e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(
    SupportStates.adding_new_key,
    KeyCallback.filter()
)
async def handle_add_key_callback(
    callback: CallbackQuery,
    callback_data: KeyCallback,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handle callback buttons on add new key step.
    
    Supports:
    - Back to key selection
    - Cancel operation
    
    Requirements: 14.3
    """
    action = callback_data.action
    tg_user_id = callback.from_user.id
    
    try:
        if action == "back_to_keys":
            # Go back to key selection
            await state.set_state(SupportStates.selecting_key_context)
            
            # Get user first
            user = await get_user_by_tg_id(session, tg_user_id)
            
            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            # Get current selected keys
            data = await state.get_data()
            selected_key_ids = data.get("selected_key_ids", set())
            
            keys = await get_user_keys(session, user.id)
            keyboard = await get_key_context_keyboard(keys, selected_key_ids=selected_key_ids, page=0)
            
            await callback.message.edit_text(
                SUPPORT_SELECT_KEY_CONTEXT,
                reply_markup=keyboard
            )
            await callback.answer()
        
        elif action == "cancel":
            # Cancel support request
            await state.clear()
            await callback.message.edit_text(
                "❌ Запрос техподдержки отменен."
            )
            await callback.answer()
            logger.info(f"User {tg_user_id} cancelled support request at add key step")
        
        else:
            await callback.answer("❌ Неизвестное действие")
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in add key callback for user {tg_user_id}: {e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.message(SupportStates.adding_new_key, F.text)
async def process_new_key_for_support(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """
    Handle new GS_Key input during support request.
    
    Validates format, checks for conflicts via API, and adds key to user's profile.
    Then returns to key selection.
    """
    key_input = message.text.strip()
    tg_user_id = message.from_user.id
    
    # Get user first to get user.id
    user = await get_user_by_tg_id(session, tg_user_id)
    
    if not user:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "Пожалуйста, пройдите регистрацию с помощью /start",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return
    
    # Get current selected keys
    data = await state.get_data()
    selected_key_ids = data.get("selected_key_ids", set())
    
    try:
        # Validate key format
        from services.validation_service import validate_gs_key
        
        is_valid, result = validate_gs_key(key_input)
        
        if not is_valid:
            await message.answer(
                f"❌ {result}\n\n"
                "Попробуйте еще раз:"
            )
            return
        
        # Use normalized key from validation
        normalized_key = result
        
        # Check if key already exists for this user
        from services.user_service import get_user_keys
        existing_keys = await get_user_keys(session, user.id)
        
        if any(k.key_number.upper() == normalized_key for k in existing_keys):
            await message.answer(
                "⚠️ Этот ключ уже добавлен в ваш профиль.\n\n"
                "Выберите его из списка или введите другой ключ:"
            )
            return
        
        # Check key via API
        from services.i_tat_service import get_itat_client
        
        itat_client = get_itat_client()
        check_result = await itat_client.check_key_conflict(normalized_key, user_id=user.id)
        
        if check_result["status"] == "conflict":
            # Key belongs to another user - create admin ticket
            await message.answer(
                "⚠️ Этот ключ уже зарегистрирован на другого пользователя.\n"
                "Создана заявка администратору для проверки конфликта.\n\n"
                "Пожалуйста, выберите другой ключ или пропустите этот шаг."
            )
            
            # Create conflict ticket (admin will handle)
            from database.models import ConflictStatus
            conflict_ticket_data = {
                "ticket_type": TicketType.KEY_CONFLICT,
                "user_id": user.id,
                "description": f"Конфликт ключа {normalized_key} при создании обращения в техподдержку"
            }
            await create_ticket(session, conflict_ticket_data)
            await session.commit()
            
            # Return to key selection
            await state.set_state(SupportStates.selecting_key_context)
            keys = await get_user_keys(session, user.id)
            keyboard = await get_key_context_keyboard(keys, selected_key_ids=selected_key_ids, page=0)
            await message.answer(
                SUPPORT_SELECT_KEY_CONTEXT,
                reply_markup=keyboard
            )
            return
        
        elif check_result["status"] == "available":
            # Add key to user profile
            from database.models import GS_Key, ConflictStatus
            
            new_key = GS_Key(
                user_id=user.id,
                key_number=normalized_key,
                conflict_status=ConflictStatus.NO_CONFLICT
            )
            session.add(new_key)
            await session.flush()
            
            # Return to key selection with new key and success message
            await state.set_state(SupportStates.selecting_key_context)
            keys = await get_user_keys(session, user.id)
            keyboard = await get_key_context_keyboard(keys, selected_key_ids=selected_key_ids, page=0)
            await message.answer(
                f"✅ Ключ {normalized_key} успешно добавлен!\n\n{SUPPORT_SELECT_KEY_CONTEXT}",
                reply_markup=keyboard
            )
            
            await session.commit()
            
            logger.info(
                f"New key added during support request: key={normalized_key}, "
                f"user={tg_user_id}"
            )
        
        else:
            # API error or unknown status
            await message.answer(
                "❌ Не удалось проверить ключ.\n"
                "Пожалуйста, попробуйте позже или выберите существующий ключ."
            )
            
            # Return to key selection
            await state.set_state(SupportStates.selecting_key_context)
            keys = await get_user_keys(session, user.id)
            keyboard = await get_key_context_keyboard(keys, selected_key_ids=selected_key_ids, page=0)
            await message.answer(
                SUPPORT_SELECT_KEY_CONTEXT,
                reply_markup=keyboard
            )
    
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error adding new key for user {tg_user_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при добавлении ключа.\n"
            "Пожалуйста, попробуйте позже."
        )
        await state.clear()
    
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Unexpected error adding new key for user {tg_user_id}: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла непредвиденная ошибка.\n"
            "Пожалуйста, попробуйте позже."
        )
        await state.clear()


# ========== Ticket Creation ==========


async def create_support_ticket(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    tg_user_id: int
):
    """
    Create support ticket with all collected data.
    
    Determines routing based on work mode, creates ticket record with file attachments,
    routes to appropriate support channel, and sends notifications.
    
    Requirements: 13.7, 14.5, 15.1-15.6
    """
    try:
        # Get all data from FSM
        data = await state.get_data()
        problem_description = data.get("problem_description", "")
        problem_media = data.get("problem_media", [])
        key_ids = data.get("key_ids", [])
        
        # Get user to get user.id (internal database ID)
        user = await get_user_by_tg_id(session, tg_user_id)
        
        if not user:
            await message.answer(
                "❌ Пользователь не найден.\n"
                "Пожалуйста, пройдите регистрацию с помощью /start",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()
            return
        
        # Get current work mode
        work_mode = await get_current_work_mode(session)
        
        # Create ticket
        ticket_data = {
            "ticket_type": TicketType.TECHNICAL_SUPPORT,
            "user_id": user.id,  # Use internal user.id, not tg_user_id
            "description": problem_description,
            "selected_key_ids": key_ids
        }
        
        ticket = await create_ticket(session, ticket_data)
        
        # Create file attachments if any
        if problem_media:
            from database.models import File_Attachment
            
            for media in problem_media:
                # Convert string value back to enum
                file_type_str = media["file_type"].upper()
                try:
                    file_type_enum = FileType[file_type_str]
                except KeyError:
                    file_type_enum = FileType.OTHER
                
                file_attachment = File_Attachment(
                    ticket_id=ticket.id,
                    file_type=file_type_enum,
                    telegram_file_id=media["file_id"],
                    file_name=media.get("file_name"),
                    file_size=media.get("file_size"),
                    uploader_id=tg_user_id,
                    uploader_type=UploaderType.USER
                )
                session.add(file_attachment)
            
            await session.flush()
            logger.info(
                f"Created {len(problem_media)} file attachments for ticket {ticket.id}"
            )
        
        # Route ticket based on work mode
        routing_info = await route_ticket(session, ticket, work_mode)
        
        # Commit transaction
        await session.commit()
        
        # Refresh ticket with user relationship for notification
        from sqlalchemy.orm import selectinload
        await session.refresh(ticket, ["user"])
        
        # Send notification to appropriate target
        if routing_info["target_id"]:
            await send_staff_notification(
                bot,
                routing_info["target_id"],
                ticket,
                routing_info,
                session
            )
        
        # Clear FSM state
        await state.clear()
        
        # Determine routing and response time messages
        if work_mode == WorkMode.REGULAR:
            routing_msg = SUPPORT_ROUTING_REGULAR
            response_time_msg = SUPPORT_RESPONSE_TIME_REGULAR
        elif work_mode == WorkMode.EXTENDED:
            routing_msg = SUPPORT_ROUTING_EXTENDED
            response_time_msg = SUPPORT_RESPONSE_TIME_EXTENDED
        else:
            routing_msg = SUPPORT_ROUTING_NON_WORKING
            response_time_msg = SUPPORT_RESPONSE_TIME_NON_WORKING
        
        # Send success message
        await message.answer(
            SUPPORT_TICKET_CREATED.format(
                ticket_id=ticket.id,
                routing_message=routing_msg,
                response_time_message=response_time_msg
            ),
            reply_markup=ReplyKeyboardRemove()
        )
        
        logger.info(
            f"Support ticket created: ticket_id={ticket.id}, user={tg_user_id}, "
            f"work_mode={work_mode.value}, routing={routing_info['target_type']}, "
            f"media_count={len(problem_media)}"
        )
    
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            f"Database error creating support ticket for user {tg_user_id}: {e}",
            exc_info=True
        )
        
        await message.answer(
            "❌ Произошла ошибка при создании обращения.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await state.clear()
    
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Unexpected error creating support ticket for user {tg_user_id}: {e}",
            exc_info=True
        )
        
        await message.answer(
            "❌ Произошла непредвиденная ошибка.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        await state.clear()
