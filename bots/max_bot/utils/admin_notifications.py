"""
Admin Notification Utilities for MAX Bot

Centralized functions for sending notifications to administrators.
Handles proper chat_id resolution for MAX messenger.

IMPORTANT: MAX API requires chat_id for sending messages, not user_id.
For staff members, use max_chat_id from staff_members table.
"""

import logging
from datetime import datetime, timezone, timedelta

from maxapi import Bot as MaxBot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from constants import MAX_BOT_TOKEN
from database.models import (
    GS_Key,
    KeyConflictStatus,
    Staff_Member,
    StaffRole,
    User,
)

logger = logging.getLogger(__name__)


async def notify_admins_key_conflict(
    session: AsyncSession,
    new_user_id: int,
    key_number: str
) -> None:
    """
    Send key conflict notification to all MAX administrators.
    
    Called when a key conflict is detected during registration or key addition.
    Notifies admins about the conflict with details of both users.
    
    IMPORTANT: Uses max_chat_id from staff_members table for sending messages.
    
    Args:
        session: Database session
        new_user_id: ID of new user with conflicting key
        key_number: The conflicting GS_Key number
    """
    try:
        # Get new user details
        stmt = select(User).where(User.id == new_user_id).options(
            selectinload(User.gs_keys)
        )
        result = await session.execute(stmt)
        new_user = result.scalar_one_or_none()
        
        if not new_user:
            logger.error(f"New user {new_user_id} not found for key conflict notification")
            return
        
        # Find the current owner of the key (if exists in our DB)
        stmt = select(User).join(User.gs_keys).where(
            GS_Key.key_number == key_number,
            User.id != new_user_id,
            GS_Key.conflict_status == KeyConflictStatus.NONE
        ).options(selectinload(User.gs_keys))
        result = await session.execute(stmt)
        current_owner = result.scalar_one_or_none()
        
        # Query all administrators with MAX chat_id
        stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
            Staff_Member.is_active == True,
            Staff_Member.max_chat_id.isnot(None)
        )
        result = await session.execute(stmt)
        admins = result.scalars().all()
        
        if not admins:
            logger.warning("No active administrators with MAX chat_id found to send key conflict notification")
            return
        
        # Format conflict date in Moscow timezone
        moscow_tz = timezone(timedelta(hours=3))
        conflict_date_moscow = datetime.now(moscow_tz)
        conflict_date = conflict_date_moscow.strftime("%d.%m.%Y %H:%M")
        
        # Format notification message (no HTML tags for MAX)
        message_text = (
            f"⚠️ При добавлении ключа возник конфликт\n\n"
            f"👤 Данные нового пользователя:\n"
            f"🪪 ФИО: {new_user.full_name or 'Не указано'}\n"
            f"📞 Телефон: {new_user.phone_number}\n"
            f"🆔 MAX ID: {new_user.max_user_id or 'Не указан'}\n\n"
            f"🔑 Конфликтный ключ: {key_number}\n\n"
            f"👤 Текущий владелец ключа:\n"
            f"🪪 ФИО: {current_owner.full_name if current_owner else 'Не найден в системе'}\n"
            f"📞 Телефон: {current_owner.phone_number if current_owner else 'Не указан'}\n"
            f"🆔 MAX ID: {current_owner.max_user_id if current_owner else 'Не указан'}\n\n"
            f"📅 Дата обнаружения: {conflict_date}\n\n"
            f"🔧 Для разрешения конфликта перейдите в раздел 'Операции' → 'Конфликты ключей'"
        )
        
        # Send notification to all administrators using max_chat_id
        bot = MaxBot(token=MAX_BOT_TOKEN)
        
        sent_count = 0
        for admin in admins:
            try:
                await bot.send_message(
                    chat_id=admin.max_chat_id,
                    text=message_text
                )
                sent_count += 1
                logger.info(f"Sent key conflict notification to admin {admin.id} (chat_id: {admin.max_chat_id})")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send key conflict notification to admin {admin.id} "
                    f"(chat_id: {admin.max_chat_id}): {send_error}",
                    exc_info=True
                )
        
        # Close bot session
        try:
            if hasattr(bot, 'session') and bot.session:
                await bot.session.close()
        except Exception as e:
            logger.warning(f"Error closing MAX bot session: {e}")
        
        logger.info(
            f"Key conflict notification sent: new_user_id={new_user_id}, "
            f"key={key_number}, admins_notified={sent_count}/{len(admins)}"
        )
        
    except Exception as e:
        logger.error(
            f"Error sending key conflict notification: new_user_id={new_user_id}, "
            f"key={key_number}, error={e}",
            exc_info=True
        )
