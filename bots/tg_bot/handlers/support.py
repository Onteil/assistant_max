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

from bots.tg_bot.callback_datas import KeyCallback
from bots.tg_bot.keyboards.support_kb import (
    get_key_context_keyboard,
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

logger = logging.getLogger(__name__)

router = Router(name="support")


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
            
            await message.answer(
                SUPPORT_CREATE_TICKET,
                reply_markup=ReplyKeyboardRemove()
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
            # No subscription - deny access
            await message.answer(
                SUPPORT_NO_SUBSCRIPTION,
                reply_markup=ReplyKeyboardRemove()
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


@router.callback_query(KeyCallback.filter(F.action == "contact_manager"))
async def handle_expired_subscription(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot
):
    """
    Handle renewal request when subscription is expired.
    
    Creates RENEWAL ticket and routes to user's manager.
    
    Requirements: 12.3, 12.5
    """
    tg_user_id = callback.from_user.id
    
    try:
        # Get user
        user = await get_user_by_tg_id(session, tg_user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Create RENEWAL ticket
        ticket_data = {
            "ticket_type": TicketType.RENEWAL,
            "tg_user_id": tg_user_id,
            "assigned_staff_id": user.default_manager_id,
            "description": "Запрос на продление подписки техподдержки"
        }
        
        ticket = await create_ticket(session, ticket_data)
        
        # Get work mode for routing
        work_mode = await get_current_work_mode(session)
        routing_info = await route_ticket(session, ticket, work_mode)
        
        # Commit transaction
        await session.commit()
        
        # Send notification to manager if assigned
        if user.default_manager_id:
            await send_staff_notification(
                bot,
                user.default_manager_id,
                ticket,
                routing_info
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


# ========== Problem Description Collection ==========


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
    
    # Determine file type
    file_type = FileType.DOCUMENT
    if file_name.lower().endswith('.pdf'):
        file_type = FileType.PDF
    elif file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
        file_type = FileType.IMAGE
    
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
    
    # Get user's keys
    keys = await get_user_keys(session, tg_user_id)
    
    # Display key selection
    keyboard = await get_key_context_keyboard(keys, page=0)
    await message.answer(
        SUPPORT_SELECT_KEY_CONTEXT,
        reply_markup=keyboard
    )
    
    logger.info(f"User {tg_user_id} provided problem description, moving to key context")


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
    Handle GS_Key selection for problem context.
    
    Supports:
    - Selecting a key
    - Skipping key selection
    - Pagination
    
    Requirements: 14.1, 14.3, 14.4
    """
    tg_user_id = callback.from_user.id
    action = callback_data.action
    
    try:
        if action == "select":
            # Key selected
            key_id = callback_data.key_id
            await state.update_data(key_id=key_id)
            
            # Create support ticket
            await callback.message.edit_text("⏳ Создаем обращение...")
            await callback.answer()
            
            await create_support_ticket(callback.message, state, session, bot, tg_user_id)
        
        elif action == "skip":
            # Skip key selection
            await state.update_data(key_id=None)
            
            # Create support ticket
            await callback.message.edit_text("⏳ Создаем обращение...")
            await callback.answer()
            
            await create_support_ticket(callback.message, state, session, bot, tg_user_id)
        
        elif action == "page":
            # Pagination
            page = callback_data.page
            keys = await get_user_keys(session, tg_user_id)
            keyboard = await get_key_context_keyboard(keys, page=page)
            
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer()
        
        else:
            await callback.answer("❌ Неизвестное действие")
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in key context selection for user {tg_user_id}: {e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка", show_alert=True)


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
        key_id = data.get("key_id")
        
        # Get current work mode
        work_mode = await get_current_work_mode(session)
        
        # Create ticket
        ticket_data = {
            "ticket_type": TicketType.TECHNICAL_SUPPORT,
            "tg_user_id": tg_user_id,
            "description": problem_description,
            "selected_key_ids": [key_id] if key_id else []
        }
        
        ticket = await create_ticket(session, ticket_data)
        
        # Create file attachments if any
        if problem_media:
            from database.models import File_Attachment
            
            for media in problem_media:
                file_attachment = File_Attachment(
                    ticket_id=ticket.id,
                    file_type=FileType[media["file_type"]],
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
        
        # Send notification to appropriate target
        if routing_info["target_id"]:
            await send_staff_notification(
                bot,
                routing_info["target_id"],
                ticket,
                routing_info
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
