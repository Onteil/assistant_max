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


async def notify_admins_webhook_error(
    session: AsyncSession,
    webhook_name: str,
    error_type: str,
    error_details: str,
    payload_summary: str | None = None
) -> None:
    """
    Send webhook error notification to all MAX administrators.
    
    Called when a webhook endpoint encounters an error during processing.
    Notifies admins about the error with details for debugging.
    
    Uses fallback mechanism: Staff_Member.max_chat_id → MAX_Messenger_Data.max_chat_id
    
    Args:
        session: Database session
        webhook_name: Name of the webhook endpoint (e.g., "user_update", "registration_status")
        error_type: Type of error (e.g., "ValidationError", "DatabaseError")
        error_details: Detailed error message
        payload_summary: Optional summary of the webhook payload
    """
    try:
        from database.models import MAX_Messenger_Data
        
        # Query all active administrators (removed max_chat_id filter for fallback support)
        stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        admins = result.scalars().all()
        
        if not admins:
            logger.warning("No active administrators found to send webhook error notification")
            return
        
        # Format error date in Moscow timezone
        moscow_tz = timezone(timedelta(hours=3))
        error_date_moscow = datetime.now(moscow_tz)
        error_date = error_date_moscow.strftime("%d.%m.%Y %H:%M:%S")
        
        # Format notification message
        message_text = (
            f"❌ Ошибка в вебхуке\n\n"
            f"🔗 Вебхук: {webhook_name}\n"
            f"⚠️ Тип ошибки: {error_type}\n"
            f"📝 Детали: {error_details[:500]}\n"  # Limit to 500 chars
        )
        
        if payload_summary:
            message_text += f"\n📦 Данные запроса: {payload_summary[:200]}\n"
        
        message_text += f"\n📅 Время: {error_date}\n"
        
        # Send notification to all administrators with fallback mechanism
        bot = MaxBot(token=MAX_BOT_TOKEN)
        
        sent_count = 0
        for admin in admins:
            # Resolve chat_id with fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
            chat_id = admin.max_chat_id
            
            if not chat_id and admin.max_user_id:
                # Fallback: lookup in MAX_Messenger_Data by max_user_id
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == admin.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                chat_id = result_chat.scalar_one_or_none()
                
                if chat_id:
                    logger.debug(
                        f"Found chat_id in MAX_Messenger_Data (fallback): "
                        f"admin_id={admin.id}, max_user_id={admin.max_user_id}, chat_id={chat_id}"
                    )
            
            if not chat_id:
                logger.warning(
                    f"No MAX chat_id found for admin {admin.id}, "
                    f"checked both Staff_Member and MAX_Messenger_Data"
                )
                continue
            
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text
                )
                sent_count += 1
                logger.info(f"Sent webhook error notification to admin {admin.id} (chat_id: {chat_id})")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send webhook error notification to admin {admin.id} "
                    f"(chat_id: {chat_id}): {send_error}",
                    exc_info=True
                )
        
        # Close bot session
        try:
            if hasattr(bot, 'session') and bot.session:
                await bot.session.close()
        except Exception as e:
            logger.warning(f"Error closing MAX bot session: {e}")
        
        logger.info(
            f"Webhook error notification sent: webhook={webhook_name}, "
            f"error_type={error_type}, admins_notified={sent_count}/{len(admins)}"
        )
        
    except Exception as e:
        logger.error(
            f"Error sending webhook error notification: webhook={webhook_name}, "
            f"error={e}",
            exc_info=True
        )


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
        # Note: conflict_status may already be PENDING_REVIEW at this point,
        # so we do NOT filter by conflict_status here
        stmt = select(User).join(User.gs_keys).where(
            GS_Key.key_number == key_number,
            User.id != new_user_id,
        ).options(selectinload(User.gs_keys))
        result = await session.execute(stmt)
        current_owner = result.scalar_one_or_none()
        
        # Query all active administrators (removed max_chat_id filter for fallback support)
        stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        admins = result.scalars().all()
        
        if not admins:
            logger.warning("No active administrators found to send key conflict notification")
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
        
        # Send notification to all administrators with fallback mechanism
        bot = MaxBot(token=MAX_BOT_TOKEN)
        
        sent_count = 0
        for admin in admins:
            # Resolve chat_id with fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
            chat_id = admin.max_chat_id
            
            if not chat_id and admin.max_user_id:
                # Fallback: lookup in MAX_Messenger_Data by max_user_id
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == admin.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                chat_id = result_chat.scalar_one_or_none()
                
                if chat_id:
                    logger.debug(
                        f"Found chat_id in MAX_Messenger_Data (fallback): "
                        f"admin_id={admin.id}, max_user_id={admin.max_user_id}, chat_id={chat_id}"
                    )
            
            if not chat_id:
                logger.warning(
                    f"No MAX chat_id found for admin {admin.id}, "
                    f"checked both Staff_Member and MAX_Messenger_Data"
                )
                continue
            
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text
                )
                sent_count += 1
                logger.info(f"Sent key conflict notification to admin {admin.id} (chat_id: {chat_id})")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send key conflict notification to admin {admin.id} "
                    f"(chat_id: {chat_id}): {send_error}",
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


async def notify_admins_new_registration(
    session: AsyncSession,
    user_id: int,
    inn: str | None = None,
    key_number: str | None = None
) -> None:
    """
    Send new user registration notification to all MAX administrators.

    Called when a user completes registration and status is set to PENDING.
    Notifies admins with all data entered by the user during registration.

    Uses fallback mechanism: Staff_Member.max_chat_id → MAX_Messenger_Data.max_chat_id

    Args:
        session: Database session
        user_id: Internal ID of the newly registered user
        inn: INN entered during registration (from FSM context)
        key_number: GS Key entered during registration (from FSM context)
    """
    try:
        from database.models import MAX_Messenger_Data
        
        # Get user details
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            logger.error(f"User {user_id} not found for new registration notification")
            return

        # Query all active administrators (removed max_chat_id filter for fallback support)
        stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        admins = result.scalars().all()

        if not admins:
            logger.warning("No active administrators found to send new registration notification")
            return

        # Format registration date in Moscow timezone
        moscow_tz = timezone(timedelta(hours=3))
        reg_date_moscow = datetime.now(moscow_tz)
        reg_date = reg_date_moscow.strftime("%d.%m.%Y %H:%M:%S")

        # Build full name with middle name if available
        name_parts = [
            user.last_name or "",
            user.first_name or "",
            user.middle_name or "",
        ]
        full_name = " ".join(p for p in name_parts if p).strip() or "Не указано"

        # Format notification message
        message_text = (
            f"🆕 Новая регистрация пользователя\n\n"
            f"👤 Данные пользователя:\n"
            f"🪪 ФИО: {full_name}\n"
            f"📞 Телефон: {user.phone_number or 'Не указан'}\n"
            f"📧 Email: {user.email or 'Не указан'}\n"
            f"🏢 ИНН: {inn or 'Не указан'}\n"
            f"🔑 Ключ Гранд-сметы: {key_number or 'Не указан'}\n"
            f"🆔 MAX ID: {user.max_user_id or 'Не указан'}\n\n"
            f"📅 Дата и время оформления: {reg_date}\n\n"
            f"⏳ Статус: Ожидает подтверждения"
        )

        # Send notification to all administrators with fallback mechanism
        bot = MaxBot(token=MAX_BOT_TOKEN)

        sent_count = 0
        for admin in admins:
            # Resolve chat_id with fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
            chat_id = admin.max_chat_id
            
            if not chat_id and admin.max_user_id:
                # Fallback: lookup in MAX_Messenger_Data by max_user_id
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == admin.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                chat_id = result_chat.scalar_one_or_none()
                
                if chat_id:
                    logger.debug(
                        f"Found chat_id in MAX_Messenger_Data (fallback): "
                        f"admin_id={admin.id}, max_user_id={admin.max_user_id}, chat_id={chat_id}"
                    )
            
            if not chat_id:
                logger.warning(
                    f"No MAX chat_id found for admin {admin.id}, "
                    f"checked both Staff_Member and MAX_Messenger_Data"
                )
                continue
            
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text
                )
                sent_count += 1
                logger.info(
                    f"Sent new registration notification to admin {admin.id} "
                    f"(chat_id: {chat_id})"
                )

            except Exception as send_error:
                logger.error(
                    f"Failed to send new registration notification to admin {admin.id} "
                    f"(chat_id: {chat_id}): {send_error}",
                    exc_info=True
                )

        # Close bot session
        try:
            if hasattr(bot, 'session') and bot.session:
                await bot.session.close()
        except Exception as e:
            logger.warning(f"Error closing MAX bot session: {e}")

        logger.info(
            f"New registration notification sent: user_id={user_id}, "
            f"admins_notified={sent_count}/{len(admins)}"
        )

    except Exception as e:
        logger.error(
            f"Error sending new registration notification: user_id={user_id}, "
            f"error={e}",
            exc_info=True
        )


async def notify_admins_api_retry_queued(
    session: AsyncSession,
    operation: str,
    payload: dict,
    error_message: str,
    retry_id: int,
    user_id: int | None = None,
) -> None:
    """
    Notify admins when a failed i-TAT API call is queued for retry.

    TEMPORARY: Used during testing phase to monitor retry queue activity.
    Remove this call once the system is stable in production.
    
    Uses fallback mechanism: Staff_Member.max_chat_id → MAX_Messenger_Data.max_chat_id

    Args:
        session: Database session
        operation: ITatAPIClient method name (e.g. "update_user_assets")
        payload: Request payload that failed
        error_message: Error that triggered the retry
        retry_id: ID of the created retry record
        user_id: Internal user DB id (optional)
    """
    try:
        from database.models import MAX_Messenger_Data
        
        stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        admins = result.scalars().all()

        if not admins:
            logger.warning("No active admins for retry_queued notification")
            return

        moscow_tz = timezone(timedelta(hours=3))
        now_moscow = datetime.now(moscow_tz).strftime("%d.%m.%Y %H:%M:%S")

        # Truncate payload for display
        payload_str = str(payload)
        if len(payload_str) > 300:
            payload_str = payload_str[:300] + "..."

        message_text = (
            f"🔄 Запрос к i-TAT поставлен в очередь повтора\n\n"
            f"🆔 ID записи: {retry_id}\n"
            f"⚙️ Метод: {operation}\n"
            f"❌ Ошибка: {error_message[:300]}\n"
            f"📦 Данные: {payload_str}\n"
        )
        if user_id:
            message_text += f"👤 User ID: {user_id}\n"
        message_text += (
            f"\n📅 Время: {now_moscow}\n"
            f"⏱ Следующая попытка через 5 минут\n\n"
            f"ℹ️ Это уведомление временное (тестовый режим)"
        )

        bot = MaxBot(token=MAX_BOT_TOKEN)
        sent_count = 0
        for admin in admins:
            # Resolve chat_id with fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
            chat_id = admin.max_chat_id
            
            if not chat_id and admin.max_user_id:
                # Fallback: lookup in MAX_Messenger_Data by max_user_id
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == admin.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                chat_id = result_chat.scalar_one_or_none()
                
                if chat_id:
                    logger.debug(
                        f"Found chat_id in MAX_Messenger_Data (fallback): "
                        f"admin_id={admin.id}, max_user_id={admin.max_user_id}, chat_id={chat_id}"
                    )
            
            if not chat_id:
                logger.warning(
                    f"No MAX chat_id found for admin {admin.id}, "
                    f"checked both Staff_Member and MAX_Messenger_Data"
                )
                continue
            
            try:
                await bot.send_message(chat_id=chat_id, text=message_text)
                sent_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to send retry_queued notification to admin {admin.id}: {e}"
                )

        try:
            if hasattr(bot, "session") and bot.session:
                await bot.session.close()
        except Exception:
            pass

        logger.info(
            f"retry_queued notification sent: retry_id={retry_id}, "
            f"operation={operation}, admins_notified={sent_count}/{len(admins)}"
        )

    except Exception as e:
        logger.error(
            f"Error sending retry_queued notification: operation={operation}, error={e}",
            exc_info=True,
        )


async def notify_admins_api_retry_exhausted(
    session: AsyncSession,
    retry_id: int,
    operation: str,
    payload: dict,
    attempt_count: int,
    last_error: str,
    user_id: int | None = None,
) -> None:
    """
    Notify admins when all retry attempts for an i-TAT API call are exhausted.

    This requires manual intervention — the operation was never successfully
    delivered to i-TAT after all retry attempts.
    
    Uses fallback mechanism: Staff_Member.max_chat_id → MAX_Messenger_Data.max_chat_id

    Args:
        session: Database session
        retry_id: ID of the exhausted retry record
        operation: ITatAPIClient method name
        payload: Request payload that was being retried
        attempt_count: Total number of attempts made
        last_error: Last error message
        user_id: Internal user DB id (optional)
    """
    try:
        from database.models import MAX_Messenger_Data
        
        stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        admins = result.scalars().all()

        if not admins:
            logger.warning("No active admins for retry_exhausted notification")
            return

        moscow_tz = timezone(timedelta(hours=3))
        now_moscow = datetime.now(moscow_tz).strftime("%d.%m.%Y %H:%M:%S")

        payload_str = str(payload)
        if len(payload_str) > 300:
            payload_str = payload_str[:300] + "..."

        message_text = (
            f"🚨 Запрос к i-TAT НЕ ДОСТАВЛЕН — все попытки исчерпаны\n\n"
            f"🆔 ID записи: {retry_id}\n"
            f"⚙️ Метод: {operation}\n"
            f"🔁 Попыток: {attempt_count}\n"
            f"❌ Последняя ошибка: {last_error[:400]}\n"
            f"📦 Данные: {payload_str}\n"
        )
        if user_id:
            message_text += f"👤 User ID: {user_id}\n"
        message_text += (
            f"\n📅 Время: {now_moscow}\n\n"
            f"⚠️ Требуется ручное вмешательство!\n"
            f"Данные не были синхронизированы с 1С/CRM."
        )

        bot = MaxBot(token=MAX_BOT_TOKEN)
        sent_count = 0
        for admin in admins:
            # Resolve chat_id with fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
            chat_id = admin.max_chat_id
            
            if not chat_id and admin.max_user_id:
                # Fallback: lookup in MAX_Messenger_Data by max_user_id
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == admin.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                chat_id = result_chat.scalar_one_or_none()
                
                if chat_id:
                    logger.debug(
                        f"Found chat_id in MAX_Messenger_Data (fallback): "
                        f"admin_id={admin.id}, max_user_id={admin.max_user_id}, chat_id={chat_id}"
                    )
            
            if not chat_id:
                logger.warning(
                    f"No MAX chat_id found for admin {admin.id}, "
                    f"checked both Staff_Member and MAX_Messenger_Data"
                )
                continue
            
            try:
                await bot.send_message(chat_id=chat_id, text=message_text)
                sent_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to send retry_exhausted notification to admin {admin.id}: {e}"
                )

        try:
            if hasattr(bot, "session") and bot.session:
                await bot.session.close()
        except Exception:
            pass

        logger.info(
            f"retry_exhausted notification sent: retry_id={retry_id}, "
            f"operation={operation}, admins_notified={sent_count}/{len(admins)}"
        )

    except Exception as e:
        logger.error(
            f"Error sending retry_exhausted notification: retry_id={retry_id}, error={e}",
            exc_info=True,
        )


async def notify_admins_phone_change_request(
    session: AsyncSession,
    source_user_id: int,
    target_user_id: int,
    old_phone: str,
    new_phone: str,
    ticket_id: int,
) -> None:
    """
    Send phone change request notification to all MAX administrators.

    Called when a user confirms a phone change request (ticket created).
    Notifies admins with details of both accounts and a direct link to the
    ticket management screen (approve/reject).
    
    Uses fallback mechanism: Staff_Member.max_chat_id → MAX_Messenger_Data.max_chat_id

    Args:
        session: Database session
        source_user_id: Internal ID of the user who filed the request (old phone)
        target_user_id: Internal ID of the target account (new phone)
        old_phone: Current phone number (source account)
        new_phone: New phone number (target account)
        ticket_id: ID of the created PHONE_CHANGE ticket
    """
    try:
        from database.models import MAX_Messenger_Data
        
        # Load both users
        source_stmt = select(User).where(User.id == source_user_id)
        target_stmt = select(User).where(User.id == target_user_id)
        source_user = (await session.execute(source_stmt)).scalar_one_or_none()
        target_user = (await session.execute(target_stmt)).scalar_one_or_none()

        if not source_user or not target_user:
            logger.error(
                f"Users not found for phone change notification: "
                f"source={source_user_id}, target={target_user_id}"
            )
            return

        # Query all active administrators (removed max_chat_id filter for fallback support)
        admins_stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
            Staff_Member.is_active == True
        )
        admins = (await session.execute(admins_stmt)).scalars().all()

        if not admins:
            logger.warning("No active administrators for phone change notification")
            return

        moscow_tz = timezone(timedelta(hours=3))
        req_date = datetime.now(moscow_tz).strftime("%d.%m.%Y %H:%M:%S")

        def _fmt_name(u: User) -> str:
            return (
                u.full_name
                or f"{u.last_name or ''} {u.first_name or ''} {u.middle_name or ''}".strip()
                or "Не указано"
            )

        message_text = (
            f"📱 Запрос на смену номера телефона\n\n"
            f"👤 Заявитель (старый номер):\n"
            f"🪪 ФИО: {_fmt_name(source_user)}\n"
            f"📞 Телефон: {old_phone}\n"
            f"🆔 MAX ID: {source_user.max_user_id or 'Не указан'}\n\n"
            f"👤 Целевой аккаунт (новый номер):\n"
            f"🪪 ФИО: {_fmt_name(target_user)}\n"
            f"📞 Телефон: {new_phone}\n"
            f"🆔 MAX ID: {target_user.max_user_id or 'Не указан'}\n\n"
            f"🎫 Заявка: #{ticket_id}\n"
            f"📅 Дата запроса: {req_date}\n\n"
            f"⚠️ После одобрения все данные заявителя будут перенесены "
            f"на целевой аккаунт, старый аккаунт будет удалён."
        )

        from bots.max_bot.payloads import PhoneChangePayload
        from maxapi.types.attachments.buttons import CallbackButton
        from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

        builder = InlineKeyboardBuilder()
        builder.row(
            CallbackButton(
                text="🔍 Детали операции",
                payload=PhoneChangePayload(action="view", ticket_id=ticket_id).pack(),
            )
        )
        attachments = [builder.as_markup()]

        bot = MaxBot(token=MAX_BOT_TOKEN)
        sent_count = 0

        for admin in admins:
            # Resolve chat_id with fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
            chat_id = admin.max_chat_id
            
            if not chat_id and admin.max_user_id:
                # Fallback: lookup in MAX_Messenger_Data by max_user_id
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == admin.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                chat_id = result_chat.scalar_one_or_none()
                
                if chat_id:
                    logger.debug(
                        f"Found chat_id in MAX_Messenger_Data (fallback): "
                        f"admin_id={admin.id}, max_user_id={admin.max_user_id}, chat_id={chat_id}"
                    )
            
            if not chat_id:
                logger.warning(
                    f"No MAX chat_id found for admin {admin.id}, "
                    f"checked both Staff_Member and MAX_Messenger_Data"
                )
                continue
            
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    attachments=attachments,
                )
                sent_count += 1
                logger.info(
                    f"Sent phone change notification to admin {admin.id} "
                    f"(chat_id={chat_id})"
                )
            except Exception as send_error:
                logger.error(
                    f"Failed to send phone change notification to admin {admin.id} "
                    f"(chat_id={chat_id}): {send_error}",
                    exc_info=True,
                )

        try:
            if hasattr(bot, "session") and bot.session:
                await bot.session.close()
        except Exception as e:
            logger.warning(f"Error closing MAX bot session: {e}")

        logger.info(
            f"Phone change notification sent: ticket_id={ticket_id}, "
            f"source={source_user_id}, target={target_user_id}, "
            f"admins_notified={sent_count}/{len(admins)}"
        )

    except Exception as e:
        logger.error(
            f"Error sending phone change notification: ticket_id={ticket_id}, error={e}",
            exc_info=True,
        )
