"""
Admin Panel - Operations Handlers

Handles administrative operational activities:
- Registration approval/rejection
- Broadcast creation and delivery
- Key conflict resolution

Requirements: 9.x, 10.x, 11.x

Note: Key conflict handlers are registered in admin_panel.py
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import BroadcastCallback
from bots.tg_bot.keyboards.admin_kb import (
    get_broadcast_preview_keyboard,
    get_broadcast_targeting_keyboard,
    get_cancel_keyboard,
)
from bots.tg_bot.states import AdminStates
from database.models import Action_Log, ActionType, Staff_Member, StaffRole, TicketStatus
from services.broadcast_service import (
    create_broadcast,
    create_delivery_records,
    get_target_users,
    send_broadcast,
)
from services.logging_service import log_ticket_action

logger = logging.getLogger(__name__)

router = Router(name="admin_operations")


# ========== Helper Functions ==========


async def is_admin(session: AsyncSession, user_id: int) -> Staff_Member | None:
    """
    Check if user is an administrator and return their record.
    
    Args:
        session: Database session
        user_id: Telegram user ID
    
    Returns:
        Staff_Member object if user is admin, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == user_id,
            Staff_Member.is_active == True,
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}", exc_info=True)
        return None


# ========== Broadcast System ==========


@router.callback_query(BroadcastCallback.filter(F.action == "create"))
async def handle_broadcast_create(
    callback: CallbackQuery,
    callback_data: BroadcastCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Broadcast" menu button - start broadcast creation flow.
    
    Prompts administrator to enter broadcast message content.
    
    Requirements: 10.1
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.message.answer("❌ У вас нет доступа к этой функции.")
            return
        
        # Set state to wait for broadcast content
        await state.set_state(AdminStates.creating_broadcast_content)
        
        # Get cancel keyboard
        keyboard = await get_cancel_keyboard(action="operations")
        
        # Prompt for broadcast message
        await callback.message.answer(
            "📢 <b>Создание рассылки</b>\n\n"
            "Введите текст сообщения для рассылки.\n"
            "Вы сможете выбрать целевую аудиторию на следующем шаге.",
            reply_markup=keyboard
        )
        
        logger.info(f"Admin {admin.id} started broadcast creation")
        
    except Exception as e:
        logger.error(f"Error starting broadcast creation: {e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при создании рассылки. Попробуйте позже."
        )


@router.message(AdminStates.creating_broadcast_content, F.text)
async def handle_broadcast_content_input(
    message: Message,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle broadcast content input from administrator.
    
    Creates broadcast record and prompts for targeting selection.
    
    Requirements: 10.1, 10.2
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await message.answer("❌ У вас нет доступа к этой функции.")
            await state.clear()
            return
        
        message_text = message.text
        
        # Create broadcast in DRAFT status
        broadcast = await create_broadcast(
            session=session,
            created_by_staff_id=admin.id,
            message_text=message_text
        )
        
        # Store broadcast ID in state
        await state.update_data(broadcast_id=broadcast.id)
        
        # Set state to wait for targeting selection
        await state.set_state(AdminStates.selecting_broadcast_target)
        
        # Get targeting keyboard
        keyboard = await get_broadcast_targeting_keyboard()
        
        # Show targeting options
        await message.answer(
            "📊 <b>Выбор целевой аудитории</b>\n\n"
            "Выберите, кому отправить рассылку:",
            reply_markup=keyboard
        )
        
        logger.info(f"Admin {admin.id} entered broadcast content, broadcast {broadcast.id} created")
        
    except Exception as e:
        logger.error(f"Error handling broadcast content: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при создании рассылки. Попробуйте позже."
        )
        await state.clear()


@router.callback_query(
    AdminStates.selecting_broadcast_target,
    BroadcastCallback.filter(F.action == "target")
)
async def handle_broadcast_targeting(
    callback: CallbackQuery,
    callback_data: BroadcastCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle targeting selection for broadcast.
    
    Gets target users, creates delivery records, and shows preview.
    
    Requirements: 10.2, 10.3, 10.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.message.answer("❌ У вас нет доступа к этой функции.")
            await state.clear()
            return
        
        # Get broadcast ID from state
        state_data = await state.get_data()
        broadcast_id = state_data.get("broadcast_id")
        
        if not broadcast_id:
            await callback.message.answer("❌ Ошибка: рассылка не найдена.")
            await state.clear()
            return
        
        target = callback_data.target
        
        # Get target users
        target_users = await get_target_users(session, target)
        
        if not target_users:
            await callback.message.answer(
                "⚠️ Не найдено пользователей для выбранной целевой аудитории.\n"
                "Выберите другую аудиторию или отмените рассылку."
            )
            return
        
        # Create delivery records
        user_ids = [user.id for user in target_users]
        await create_delivery_records(session, broadcast_id, user_ids)
        
        # Update broadcast target count
        from database.models import Broadcast
        result = await session.execute(
            select(Broadcast).where(Broadcast.id == broadcast_id)
        )
        broadcast = result.scalar_one()
        broadcast.target_user_count = len(user_ids)
        await session.commit()
        
        # Store target info in state
        await state.update_data(target=target, target_count=len(user_ids))
        
        # Set state to confirming
        await state.set_state(AdminStates.confirming_broadcast)
        
        # Get preview keyboard
        keyboard = await get_broadcast_preview_keyboard(broadcast_id)
        
        # Target display names
        target_display = {
            "all": "Всем пользователям",
            "active_subscription": "Пользователям с активной подпиской",
            "marketing_consent": "Пользователям, согласившимся на маркетинг"
        }
        
        target_text = target_display.get(target, target)
        
        # Show preview
        await callback.message.answer(
            f"📋 <b>Превью рассылки</b>\n\n"
            f"<b>Целевая аудитория:</b> {target_text}\n"
            f"<b>Количество получателей:</b> {len(user_ids)}\n\n"
            f"<b>Текст сообщения:</b>\n"
            f"{broadcast.message_text}\n\n"
            f"Подтвердите запуск рассылки:",
            reply_markup=keyboard
        )
        
        logger.info(
            f"Admin {admin.id} selected target '{target}' for broadcast {broadcast_id}, "
            f"{len(user_ids)} recipients"
        )
        
    except Exception as e:
        logger.error(f"Error handling broadcast targeting: {e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при подготовке рассылки. Попробуйте позже."
        )
        await state.clear()


@router.callback_query(
    AdminStates.confirming_broadcast,
    BroadcastCallback.filter(F.action == "send")
)
async def handle_broadcast_send(
    callback: CallbackQuery,
    callback_data: BroadcastCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Launch" button - send broadcast to all target users.
    
    Sends messages to all users and provides delivery report.
    
    Requirements: 10.5, 10.6, 10.7
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.message.answer("❌ У вас нет доступа к этой функции.")
            await state.clear()
            return
        
        broadcast_id = callback_data.broadcast_id
        
        # Show "sending" message
        await callback.message.answer(
            "🚀 <b>Запуск рассылки...</b>\n\n"
            "Отправка сообщений пользователям. Это может занять некоторое время."
        )
        
        # Get bot instance from callback
        bot = callback.bot
        
        # Send broadcast
        delivered_count, error_count = await send_broadcast(
            session=session,
            broadcast_id=broadcast_id,
            bot=bot
        )
        
        # Log action
        await log_ticket_action(
            session=session,
            action_type=ActionType.BROADCAST_SENT,
            ticket_id=None,
            staff_id=admin.id,
            action_details={
                "broadcast_id": broadcast_id,
                "delivered_count": delivered_count,
                "error_count": error_count
            }
        )
        
        # Show delivery report
        total_count = delivered_count + error_count
        success_rate = (delivered_count / total_count * 100) if total_count > 0 else 0
        
        await callback.message.answer(
            f"✅ <b>Рассылка завершена</b>\n\n"
            f"<b>Всего получателей:</b> {total_count}\n"
            f"<b>Доставлено:</b> {delivered_count}\n"
            f"<b>Ошибок:</b> {error_count}\n"
            f"<b>Успешность:</b> {success_rate:.1f}%"
        )
        
        # Clear state
        await state.clear()
        
        logger.info(
            f"Admin {admin.id} completed broadcast {broadcast_id}: "
            f"{delivered_count} delivered, {error_count} errors"
        )
        
    except Exception as e:
        logger.error(f"Error sending broadcast: {e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при отправке рассылки. Попробуйте позже."
        )
        await state.clear()


@router.callback_query(BroadcastCallback.filter(F.action == "cancel"))
async def handle_broadcast_cancel(
    callback: CallbackQuery,
    callback_data: BroadcastCallback,
    state: FSMContext
) -> None:
    """
    Handle broadcast cancellation.
    
    Clears state and returns to operations menu.
    
    Requirements: 10.1
    """
    await callback.answer()
    
    try:
        # Clear state
        await state.clear()
        
        await callback.message.answer(
            "❌ Создание рассылки отменено."
        )
        
        logger.info(f"User {callback.from_user.id} cancelled broadcast creation")
        
    except Exception as e:
        logger.error(f"Error cancelling broadcast: {e}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка. Попробуйте позже."
        )

