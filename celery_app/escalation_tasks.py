"""
Celery tasks for ticket escalation monitoring.

This module implements background tasks for automatic ticket escalation:
- Reminder task (10 minutes): Sends reminder to assigned staff
- Escalation task (20 minutes): Creates escalation and notifies admins
- Scheduling and cancellation utilities

Requirements: 1.1, 1.2, 1.3, 2.1
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from typing import Any

# Add project root to Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from celery_app.celery_config import app as celery_app
from constants import (
    TG_BOT_TOKEN,
    AsyncSessionLocal,
    ESCALATION_REMINDER_TIMEOUT,
)
from database.models import (
    Action_Log,
    ActionType,
    Escalation,
    EscalationType,
    Staff_Member,
    StaffRole,
    Ticket,
    TicketStatus,
)
from services.escalation_service import create_escalation, get_active_admins

# Use Celery-specific logger
logger = get_task_logger(__name__)


# ========== Helper Functions ==========


async def get_backup_escalation_timeout() -> int:
    """
    Get backup escalation timeout from system settings.
    
    Returns the configured timeout in seconds for backup manager escalation.
    Falls back to default 600 seconds (10 minutes) if setting not found.
    
    Returns:
        Timeout in seconds
    """
    try:
        from services.settings_service import get_setting
        
        async with AsyncSessionLocal() as session:
            timeout_minutes = await get_setting(session, "backup_escalation_timeout")
            
            if timeout_minutes is None:
                logger.warning("backup_escalation_timeout setting not found, using default 10 minutes")
                return 600  # 10 minutes default
            
            timeout_seconds = int(timeout_minutes) * 60
            logger.debug(f"Using backup escalation timeout: {timeout_minutes} minutes ({timeout_seconds} seconds)")
            return timeout_seconds
    
    except Exception as e:
        logger.error(f"Error getting backup escalation timeout: {e}", exc_info=True)
        return 600  # 10 minutes fallback


def get_backup_escalation_timeout_sync() -> int:
    """
    Synchronous wrapper for get_backup_escalation_timeout.
    
    Used in synchronous Celery task scheduling context.
    
    Returns:
        Timeout in seconds
    """
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(get_backup_escalation_timeout())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error in sync timeout getter: {e}", exc_info=True)
        return 600  # 10 minutes fallback


# ========== Celery Tasks ==========


@shared_task(
    name="celery_app.escalation_tasks.check_ticket_reminder",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="escalations"
)
def check_ticket_reminder(self, ticket_id: int) -> dict[str, Any]:
    """
    Check ticket status after 10 minutes and escalate to backup manager if still NEW.
    
    This task is scheduled when a ticket is created with status NEW.
    If the ticket is still NEW after 10 minutes:
    - escalation_level=0: Reassign to backup_manager_1 and schedule next check
    - escalation_level=1: Reassign to backup_manager_2 and schedule next check
    - escalation_level=2: Create escalation and notify admins
    
    Preconditions:
    - ticket_id exists in database
    - Task scheduled at ticket creation or previous escalation
    
    Postconditions:
    - If status=NEW: ticket reassigned to backup manager OR escalation created
    - If status!=NEW: task completes without action
    - Returns dict with execution result
    
    Args:
        ticket_id: ID of the ticket to check
    
    Returns:
        Dict with status, message, and additional data:
        - status: "success", "skipped", or "error"
        - message: Description of what happened
        - Additional fields depending on outcome
    
    Requirements: 1.1, 1.3, Backup Manager Escalation Flow
    """
    logger.info(f"Starting check_ticket_reminder for ticket_id={ticket_id}")
    
    loop = None
    try:
        # Create and set new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_check_ticket_reminder_async(ticket_id))
        
        logger.info(
            f"check_ticket_reminder completed: ticket_id={ticket_id}, "
            f"status={result['status']}"
        )
        
        return result
    
    except Exception as exc:
        logger.error(
            f"check_ticket_reminder failed: ticket_id={ticket_id}, error={exc}",
            exc_info=True
        )
        
        # Retry with exponential backoff
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(
                f"Max retries exceeded for check_ticket_reminder: ticket_id={ticket_id}"
            )
            return {
                "status": "error",
                "message": "Max retries exceeded",
                "ticket_id": ticket_id
            }
    
    finally:
        if loop is not None:
            try:
                # Dispose engine connections before closing loop (Windows asyncpg fix)
                from constants import engine
                loop.run_until_complete(engine.dispose())
                loop.close()
            except Exception as e:
                logger.warning(f"Error closing event loop: {e}")


@shared_task(
    name="celery_app.escalation_tasks.check_ticket_escalation",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="escalations"
)
def check_ticket_escalation(self, ticket_id: int) -> dict[str, Any]:
    """
    Check ticket status after 20 minutes and create escalation if still NEW.
    
    This task is scheduled when a ticket is created with status NEW.
    If the ticket is still NEW after 20 minutes, creates an escalation record
    and notifies all active administrators.
    
    Preconditions:
    - ticket_id exists in database
    - Task scheduled at ticket creation
    - 20 minutes have passed since ticket creation
    
    Postconditions:
    - If status=NEW: escalation created, admins notified
    - If status!=NEW: task completes without action
    - ticket.is_escalated set to True if escalation created
    - Returns dict with execution result
    
    Args:
        ticket_id: ID of the ticket to check
    
    Returns:
        Dict with status, message, and additional data:
        - status: "success", "skipped", or "error"
        - message: Description of what happened
        - escalation_id: ID of created escalation (if created)
        - admins_notified: Number of admins successfully notified
    
    Requirements: 1.1, 1.3
    """
    logger.info(f"Starting check_ticket_escalation for ticket_id={ticket_id}")
    
    loop = None
    try:
        # Create and set new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(_check_ticket_escalation_async(ticket_id))
        
        logger.info(
            f"check_ticket_escalation completed: ticket_id={ticket_id}, "
            f"status={result['status']}"
        )
        
        return result
    
    except Exception as exc:
        logger.error(
            f"check_ticket_escalation failed: ticket_id={ticket_id}, error={exc}",
            exc_info=True
        )
        
        # Retry with exponential backoff
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(
                f"Max retries exceeded for check_ticket_escalation: ticket_id={ticket_id}"
            )
            return {
                "status": "error",
                "message": "Max retries exceeded",
                "ticket_id": ticket_id
            }
    
    finally:
        if loop is not None:
            try:
                # Dispose engine connections before closing loop (Windows asyncpg fix)
                from constants import engine
                loop.run_until_complete(engine.dispose())
                loop.close()
            except Exception as e:
                logger.warning(f"Error closing event loop: {e}")


# ========== Async Implementation Functions ==========


async def _check_ticket_reminder_async(ticket_id: int) -> dict[str, Any]:
    """
    Async implementation of backup manager escalation check.
    
    Implements 3-level escalation:
    - Level 0 (10 min): Reassign to backup_manager_1, send notification
    - Level 1 (20 min): Reassign to backup_manager_2, send notification
    - Level 2 (30 min): Create escalation, notify admins and group chat
    
    Uses MAX messenger only. Sends notifications with "take over" buttons.
    
    Args:
        ticket_id: ID of the ticket to check
    
    Returns:
        Dict with execution result
    
    Requirements: FR-1.3.1, FR-1.10.2, Backup Manager Escalation Flow
    """
    from database.models import MAX_Messenger_Data
    from maxapi import Bot as MAXBot
    from maxapi.enums.parse_mode import ParseMode
    from maxapi.exceptions import MaxApiError
    from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
    from maxapi.types import CallbackButton
    
    async with AsyncSessionLocal() as session:
        # Get ticket with relationships
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.assigned_staff).selectinload(Staff_Member.backup_manager_1),
                selectinload(Ticket.assigned_staff).selectinload(Staff_Member.backup_manager_2),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.organization)
            )
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            logger.warning(f"Ticket not found: ticket_id={ticket_id}")
            return {
                "status": "error",
                "message": "Ticket not found",
                "ticket_id": ticket_id
            }
        
        # Check if ticket is still NEW
        if ticket.ticket_status != TicketStatus.NEW:
            logger.info(
                f"Ticket already processed: ticket_id={ticket_id}, "
                f"status={ticket.ticket_status.value}"
            )
            return {
                "status": "skipped",
                "message": "Ticket already processed",
                "ticket_id": ticket_id,
                "ticket_status": ticket.ticket_status.value
            }
        
        current_level = ticket.escalation_level
        logger.info(
            f"Processing escalation: ticket_id={ticket_id}, "
            f"current_level={current_level}"
        )
        
        # Level 0: Escalate to backup_manager_1
        if current_level == 0:
            return await _escalate_to_backup_manager_1(ticket, session)
        
        # Level 1: Escalate to backup_manager_2
        elif current_level == 1:
            return await _escalate_to_backup_manager_2(ticket, session)
        
        # Level 2: Create escalation and notify admins
        elif current_level == 2:
            return await _escalate_to_admins(ticket, session)
        
        else:
            logger.error(f"Invalid escalation level: ticket_id={ticket_id}, level={current_level}")
            return {
                "status": "error",
                "message": f"Invalid escalation level: {current_level}",
                "ticket_id": ticket_id
            }


async def _escalate_to_backup_manager_1(ticket: Ticket, session: AsyncSession) -> dict[str, Any]:
    """
    Escalate ticket to backup_manager_1 (Level 0 → Level 1).
    
    Reassigns ticket to backup_manager_1, sends notification with "take over" button,
    and schedules next escalation check in 10 minutes.
    
    Args:
        ticket: Ticket object with loaded relationships
        session: Database session
    
    Returns:
        Dict with execution result
    """
    from maxapi import Bot as MAXBot
    from maxapi.enums.parse_mode import ParseMode
    from maxapi.exceptions import MaxApiError
    from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
    from maxapi.types import CallbackButton
    from constants import MAX_BOT_TOKEN
    
    if not ticket.assigned_staff:
        logger.warning(f"No assigned staff for ticket {ticket.id}, cannot escalate to backup")
        return {
            "status": "skipped",
            "message": "No assigned staff",
            "ticket_id": ticket.id
        }
    
    # Optimization: If no backup managers are configured at all, escalate directly to admins
    if not ticket.assigned_staff.backup_manager_1_id and not ticket.assigned_staff.backup_manager_2_id:
        logger.warning(
            f"No backup managers configured for staff {ticket.assigned_staff.id}, "
            f"escalating directly to admins"
        )
        return await _escalate_to_admins(ticket, session)
    
    backup_manager = ticket.assigned_staff.backup_manager_1
    
    if not backup_manager:
        logger.warning(
            f"No backup_manager_1 configured for staff {ticket.assigned_staff.id}, "
            f"escalating directly to admins"
        )
        # Skip directly to admin escalation since no backup manager available
        return await _escalate_to_admins(ticket, session)
    
    # Check if backup manager has MAX messenger
    if not backup_manager.max_chat_id:
        logger.error(
            f"Backup manager {backup_manager.id} has no MAX chat_id, "
            f"cannot send notification, escalating directly to admins"
        )
        # Skip directly to admin escalation since backup manager can't be notified
        return await _escalate_to_admins(ticket, session)
    
    # Reassign ticket to backup_manager_1
    old_staff_id = ticket.assigned_staff_id
    ticket.assigned_staff_id = backup_manager.id
    ticket.escalation_level = 1
    
    # Build notification message
    ticket_type_names = {
        TicketType.INVOICE: "💰 Счёт",
        TicketType.TECHNICAL_SUPPORT: "🛠 ТП",
        TicketType.RENEWAL: "🔄 Продление"
    }
    
    ticket_type = ticket_type_names.get(ticket.ticket_type, str(ticket.ticket_type))
    user_name = ticket.user.full_name if ticket.user else "Неизвестно"
    user_phone = ticket.user.phone_number if ticket.user else "Не указано"
    
    # Calculate time elapsed
    from datetime import datetime, timezone
    elapsed = datetime.now(timezone.utc) - ticket.created_at.replace(tzinfo=timezone.utc)
    minutes = int(elapsed.total_seconds() // 60)
    
    notification_text = (
        f"⚠️ <b>Эскалация заявки #{ticket.id}</b>\n\n"
        f"Заявка не была взята в работу основным менеджером в течение 10 минут.\n"
        f"Вы назначены резервным менеджером (Резерв 1).\n\n"
        f"<b>Тип:</b> {ticket_type}\n"
        f"<b>Клиент:</b> {user_name}\n"
        f"<b>Телефон:</b> {user_phone}\n"
    )
    
    if ticket.organization:
        org_text = ticket.organization.inn
        if ticket.organization.organization_name:
            org_text += f" ({ticket.organization.organization_name})"
        notification_text += f"<b>Организация:</b> {org_text}\n"
    
    if ticket.gs_keys:
        keys_text = ", ".join([key.key_number for key in ticket.gs_keys])
        notification_text += f"<b>Ключи ГС:</b> {keys_text}\n"
    
    if ticket.description:
        desc_preview = ticket.description[:150]
        if len(ticket.description) > 150:
            desc_preview += "..."
        notification_text += f"\n<b>Описание:</b>\n{desc_preview}\n"
    
    notification_text += (
        f"\n⏱ <b>Время с создания:</b> {minutes} мин\n"
        f"⚠️ <b>Если не возьмете в работу в течение 10 минут, заявка будет передана следующему резервному менеджеру.</b>"
    )
    
    # Build keyboard with "Take Over" button
    # Import payload class
    import json
    take_over_payload = json.dumps({
        "prefix": "backup_esc",
        "action": "take_over",
        "ticket_id": ticket.id,
        "escalation_level": 1
    })
    
    builder = InlineKeyboardBuilder()
    builder.row(
        CallbackButton(
            text="✋ Взять в работу",
            payload=take_over_payload
        )
    )
    keyboard = builder.as_markup()
    
    # Send notification via MAX
    max_bot = None
    try:
        max_bot = MAXBot(token=MAX_BOT_TOKEN, parse_mode=ParseMode.HTML)
        
        await max_bot.send_message(
            chat_id=backup_manager.max_chat_id,
            text=notification_text,
            attachments=[keyboard]
        )
        
        logger.info(
            f"Escalation notification sent to backup_manager_1: "
            f"ticket_id={ticket.id}, backup_id={backup_manager.id}, "
            f"chat_id={backup_manager.max_chat_id}"
        )
    
    except MaxApiError as e:
        error_str = str(e).lower()
        if "blocked" in error_str or "forbidden" in error_str or "chat.not.found" in error_str:
            logger.warning(
                f"MAX bot blocked by backup manager: "
                f"backup_id={backup_manager.id}, chat_id={backup_manager.max_chat_id}"
            )
        else:
            logger.error(f"Failed to send escalation notification: {e}", exc_info=True)
    
    except Exception as e:
        logger.error(f"Failed to send escalation notification: {e}", exc_info=True)
    
    finally:
        if max_bot and max_bot.session:
            await max_bot.session.close()
    
    # Log action
    action_log = Action_Log(
        ticket_id=ticket.id,
        staff_id=backup_manager.id,
        action_type=ActionType.TICKET_ASSIGNED,
        action_details={
            "escalation_level": 1,
            "old_staff_id": old_staff_id,
            "new_staff_id": backup_manager.id,
            "backup_type": "backup_manager_1",
            "time_elapsed_minutes": minutes
        }
    )
    session.add(action_log)
    
    # Schedule next escalation check in configured timeout
    timeout_seconds = get_backup_escalation_timeout_sync()
    reminder_task = check_ticket_reminder.apply_async(
        args=[ticket.id],
        countdown=timeout_seconds
    )
    ticket.escalation_task_reminder_id = reminder_task.id
    
    await session.commit()
    
    return {
        "status": "success",
        "message": "Escalated to backup_manager_1",
        "ticket_id": ticket.id,
        "old_staff_id": old_staff_id,
        "new_staff_id": backup_manager.id,
        "escalation_level": 1,
        "time_elapsed_minutes": minutes
    }


async def _escalate_to_backup_manager_2(ticket: Ticket, session: AsyncSession) -> dict[str, Any]:
    """
    Escalate ticket to backup_manager_2 (Level 1 → Level 2).
    
    Reassigns ticket to backup_manager_2, sends notification with "take over" button,
    and schedules final escalation check in 10 minutes.
    
    Args:
        ticket: Ticket object with loaded relationships
        session: Database session
    
    Returns:
        Dict with execution result
    """
    from maxapi import Bot as MAXBot
    from maxapi.enums.parse_mode import ParseMode
    from maxapi.exceptions import MaxApiError
    from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
    from maxapi.types import CallbackButton
    from constants import MAX_BOT_TOKEN
    
    # Get original staff to access backup_manager_2
    stmt = (
        select(Staff_Member)
        .where(Staff_Member.id == ticket.assigned_staff_id)
        .options(
            selectinload(Staff_Member.backup_manager_1),
            selectinload(Staff_Member.backup_manager_2)
        )
    )
    result = await session.execute(stmt)
    current_staff = result.scalar_one_or_none()
    
    if not current_staff:
        logger.error(f"Current staff not found for ticket {ticket.id}")
        # Escalate directly to admins
        ticket.escalation_level = 2
        await session.commit()
        
        reminder_task = check_ticket_reminder.apply_async(
            args=[ticket.id],
            countdown=get_backup_escalation_timeout_sync()
        )
        ticket.escalation_task_reminder_id = reminder_task.id
        await session.commit()
        
        return {
            "status": "skipped_to_admins",
            "message": "Current staff not found",
            "ticket_id": ticket.id
        }
    
    # Get backup_manager_2 from the ORIGINAL assigned staff (not current backup_manager_1)
    # We need to go back to the original staff who has the backup managers configured
    stmt_original = (
        select(Staff_Member)
        .options(
            selectinload(Staff_Member.backup_manager_1),
            selectinload(Staff_Member.backup_manager_2)
        )
    )
    result_all = await session.execute(stmt_original)
    all_staff = result_all.scalars().all()
    
    # Find the original staff (the one who has current_staff as backup_manager_1)
    original_staff = None
    for staff in all_staff:
        if staff.backup_manager_1 and staff.backup_manager_1.id == current_staff.id:
            original_staff = staff
            break
    
    if not original_staff:
        # Current staff might be the original staff
        original_staff = current_staff
    
    backup_manager = original_staff.backup_manager_2
    
    if not backup_manager:
        logger.warning(
            f"No backup_manager_2 configured for original staff {original_staff.id}, "
            f"escalating directly to admins"
        )
        # Skip directly to admin escalation since no backup manager available
        return await _escalate_to_admins(ticket, session)
    
    # Check if backup manager has MAX messenger
    if not backup_manager.max_chat_id:
        logger.error(
            f"Backup manager {backup_manager.id} has no MAX chat_id, "
            f"cannot send notification, escalating directly to admins"
        )
        # Skip directly to admin escalation since backup manager can't be notified
        return await _escalate_to_admins(ticket, session)
        
        return {
            "status": "skipped_to_admins",
            "message": "Backup manager has no MAX chat_id",
            "ticket_id": ticket.id
        }
    
    # Reassign ticket to backup_manager_2
    old_staff_id = ticket.assigned_staff_id
    ticket.assigned_staff_id = backup_manager.id
    ticket.escalation_level = 2
    
    # Build notification message
    ticket_type_names = {
        TicketType.INVOICE: "💰 Счёт",
        TicketType.TECHNICAL_SUPPORT: "🛠 ТП",
        TicketType.RENEWAL: "🔄 Продление"
    }
    
    ticket_type = ticket_type_names.get(ticket.ticket_type, str(ticket.ticket_type))
    user_name = ticket.user.full_name if ticket.user else "Неизвестно"
    user_phone = ticket.user.phone_number if ticket.user else "Не указано"
    
    # Calculate time elapsed
    from datetime import datetime, timezone
    elapsed = datetime.now(timezone.utc) - ticket.created_at.replace(tzinfo=timezone.utc)
    minutes = int(elapsed.total_seconds() // 60)
    
    notification_text = (
        f"⚠️⚠️ <b>Эскалация заявки #{ticket.id}</b>\n\n"
        f"Заявка не была взята в работу основным и первым резервным менеджером.\n"
        f"Вы назначены вторым резервным менеджером (Резерв 2).\n\n"
        f"<b>Тип:</b> {ticket_type}\n"
        f"<b>Клиент:</b> {user_name}\n"
        f"<b>Телефон:</b> {user_phone}\n"
    )
    
    if ticket.organization:
        org_text = ticket.organization.inn
        if ticket.organization.organization_name:
            org_text += f" ({ticket.organization.organization_name})"
        notification_text += f"<b>Организация:</b> {org_text}\n"
    
    if ticket.gs_keys:
        keys_text = ", ".join([key.key_number for key in ticket.gs_keys])
        notification_text += f"<b>Ключи ГС:</b> {keys_text}\n"
    
    if ticket.description:
        desc_preview = ticket.description[:150]
        if len(ticket.description) > 150:
            desc_preview += "..."
        notification_text += f"\n<b>Описание:</b>\n{desc_preview}\n"
    
    notification_text += (
        f"\n⏱ <b>Время с создания:</b> {minutes} мин\n"
        f"🚨 <b>КРИТИЧНО: Если не возьмете в работу в течение 10 минут, заявка будет эскалирована администраторам!</b>"
    )
    
    # Build keyboard with "Take Over" button
    import json
    take_over_payload = json.dumps({
        "prefix": "backup_esc",
        "action": "take_over",
        "ticket_id": ticket.id,
        "escalation_level": 2
    })
    
    builder = InlineKeyboardBuilder()
    builder.row(
        CallbackButton(
            text="✋ Взять в работу",
            payload=take_over_payload
        )
    )
    keyboard = builder.as_markup()
    
    # Send notification via MAX
    max_bot = None
    try:
        max_bot = MAXBot(token=MAX_BOT_TOKEN, parse_mode=ParseMode.HTML)
        
        await max_bot.send_message(
            chat_id=backup_manager.max_chat_id,
            text=notification_text,
            attachments=[keyboard]
        )
        
        logger.info(
            f"Escalation notification sent to backup_manager_2: "
            f"ticket_id={ticket.id}, backup_id={backup_manager.id}, "
            f"chat_id={backup_manager.max_chat_id}"
        )
    
    except MaxApiError as e:
        error_str = str(e).lower()
        if "blocked" in error_str or "forbidden" in error_str or "chat.not.found" in error_str:
            logger.warning(
                f"MAX bot blocked by backup manager: "
                f"backup_id={backup_manager.id}, chat_id={backup_manager.max_chat_id}"
            )
        else:
            logger.error(f"Failed to send escalation notification: {e}", exc_info=True)
    
    except Exception as e:
        logger.error(f"Failed to send escalation notification: {e}", exc_info=True)
    
    finally:
        if max_bot and max_bot.session:
            await max_bot.session.close()
    
    # Log action
    action_log = Action_Log(
        ticket_id=ticket.id,
        staff_id=backup_manager.id,
        action_type=ActionType.TICKET_ASSIGNED,
        action_details={
            "escalation_level": 2,
            "old_staff_id": old_staff_id,
            "new_staff_id": backup_manager.id,
            "backup_type": "backup_manager_2",
            "time_elapsed_minutes": minutes
        }
    )
    session.add(action_log)
    
    # Schedule final escalation check in configured timeout
    timeout_seconds = get_backup_escalation_timeout_sync()
    reminder_task = check_ticket_reminder.apply_async(
        args=[ticket.id],
        countdown=timeout_seconds
    )
    ticket.escalation_task_reminder_id = reminder_task.id
    
    await session.commit()
    
    return {
        "status": "success",
        "message": "Escalated to backup_manager_2",
        "ticket_id": ticket.id,
        "old_staff_id": old_staff_id,
        "new_staff_id": backup_manager.id,
        "escalation_level": 2,
        "time_elapsed_minutes": minutes
    }


async def _escalate_to_admins(ticket: Ticket, session: AsyncSession) -> dict[str, Any]:
    """
    Final escalation to administrators (Level 2 → Escalation record).
    
    Creates escalation record, notifies all admins with action buttons,
    and sends notification to group chat.
    
    This is called when backup_manager_2 also fails to take the ticket.
    
    Args:
        ticket: Ticket object with loaded relationships
        session: Database session
    
    Returns:
        Dict with execution result
    """
    # This function is essentially the same as the original _check_ticket_escalation_async
    # but called from the backup manager flow
    return await _check_ticket_escalation_async(ticket.id)


async def _check_ticket_escalation_async(ticket_id: int) -> dict[str, Any]:
    """
    Async implementation of escalation check.
    
    Checks ticket status and creates escalation if still NEW.
    Notifies all active administrators with quick action buttons.
    Uses centralized notification templates from escalation_notifications.
    Supports both Telegram and MAX messengers.
    
    Implements FR-1.3.4: Error sending to one admin does NOT block others.
    
    Args:
        ticket_id: ID of the ticket to check
    
    Returns:
        Dict with execution result including:
        - status: "success", "skipped", or "error"
        - admins_notified: Number of successfully notified admins
        - admins_failed: Number of failed notifications
        - failed_admins: List of admin IDs that failed (if any)
    
    Requirements: FR-1.3.2, FR-1.3.3, FR-1.3.4, FR-1.10.2
    """
    from database.models import MAX_Messenger_Data
    from maxapi import Bot as MAXBot
    from maxapi.enums.parse_mode import ParseMode
    from maxapi.exceptions import MaxApiError
    
    async with AsyncSessionLocal() as session:
        # Get ticket with relationships
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.assigned_staff),
                selectinload(Ticket.organization)
            )
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            logger.warning(f"Ticket not found: ticket_id={ticket_id}")
            return {
                "status": "error",
                "message": "Ticket not found",
                "ticket_id": ticket_id
            }
        
        # Check if ticket is still NEW
        if ticket.ticket_status != TicketStatus.NEW:
            logger.info(
                f"Ticket already processed: ticket_id={ticket_id}, "
                f"status={ticket.ticket_status.value}"
            )
            return {
                "status": "skipped",
                "message": "Ticket already processed",
                "ticket_id": ticket_id,
                "ticket_status": ticket.ticket_status.value
            }
        
        # Create escalation
        try:
            escalation = await create_escalation(
                session=session,
                ticket_id=ticket.id,
                escalation_type=EscalationType.ESCALATION_20MIN
            )
            
            # Set escalation flag on ticket
            ticket.is_escalated = True
            ticket.escalated_at = datetime.utcnow()
            
            await session.flush()
            
            logger.info(
                f"Escalation created: escalation_id={escalation.id}, "
                f"ticket_id={ticket_id}"
            )
        
        except Exception as e:
            logger.error(
                f"Failed to create escalation: ticket_id={ticket_id}, error={e}",
                exc_info=True
            )
            await session.rollback()
            return {
                "status": "error",
                "message": f"Failed to create escalation: {str(e)}",
                "ticket_id": ticket_id
            }
        
        # Get active administrators
        try:
            admins = await get_active_admins(session)
            
            if not admins:
                logger.error(f"No active admins found for escalation: ticket_id={ticket_id}")
                await session.commit()
                return {
                    "status": "error",
                    "message": "No active admins found",
                    "ticket_id": ticket_id,
                    "escalation_id": escalation.id
                }
        
        except Exception as e:
            logger.error(
                f"Failed to get active admins: ticket_id={ticket_id}, error={e}",
                exc_info=True
            )
            await session.commit()
            return {
                "status": "error",
                "message": f"Failed to get admins: {str(e)}",
                "ticket_id": ticket_id,
                "escalation_id": escalation.id
            }
        
        # Calculate time elapsed
        # Import here to avoid circular dependency
        from bots.tg_bot.utils.escalation_notifications import (
            calculate_time_elapsed,
            get_escalation_notification_keyboard,
            get_escalation_notification_text,
        )
        
        time_elapsed = calculate_time_elapsed(ticket.created_at)
        
        # Generate notification text and keyboard using centralized templates
        notification_text = get_escalation_notification_text(ticket, time_elapsed)
        notification_keyboard = get_escalation_notification_keyboard(
            escalation_id=escalation.id,
            ticket_id=ticket.id
        )
        
        # Send notifications to all admins (FR-1.3.4: continue on individual failures)
        notified_count = 0
        failed_count = 0
        failed_admins = []
        
        # Initialize MAX bot only
        max_bot = None
        
        try:
            from constants import MAX_BOT_TOKEN
            max_bot = MAXBot(
                token=MAX_BOT_TOKEN,
                parse_mode=ParseMode.HTML
            )
            
            for admin in admins:
                try:
                    # Send via MAX only
                    if admin.max_user_id:
                        # Get MAX chat_id from staff member
                        chat_id = admin.max_chat_id
                        
                        if chat_id is None:
                            logger.error(
                                f"No MAX chat_id found for admin: admin_id={admin.id}, "
                                f"max_user_id={admin.max_user_id}"
                            )
                            failed_count += 1
                            failed_admins.append(admin.id)
                            continue
                        
                        # Send via MAX
                        try:
                            await max_bot.send_message(
                                chat_id=chat_id,
                                text=notification_text
                            )
                            # Note: MAX doesn't support inline keyboards in the same way
                            # Buttons would need to be sent separately or as attachment
                            
                            notified_count += 1
                            logger.info(
                                f"Admin notified via MAX: admin_id={admin.id}, "
                                f"max_user_id={admin.max_user_id}, chat_id={chat_id}, "
                                f"ticket_id={ticket_id}"
                            )
                        
                        except MaxApiError as e:
                            error_str = str(e).lower()
                            if "blocked" in error_str or "forbidden" in error_str or "chat.not.found" in error_str:
                                logger.warning(
                                    f"MAX bot blocked by admin: admin_id={admin.id}, "
                                    f"max_user_id={admin.max_user_id}, chat_id={chat_id}"
                                )
                            else:
                                logger.error(
                                    f"MAX API error notifying admin: admin_id={admin.id}, "
                                    f"error={e}"
                                )
                            failed_count += 1
                            failed_admins.append(admin.id)
                    
                    else:
                        logger.warning(
                            f"Admin has no MAX messenger ID: admin_id={admin.id}"
                        )
                        failed_count += 1
                        failed_admins.append(admin.id)
                
                except Exception as e:
                    failed_count += 1
                    failed_admins.append(admin.id)
                    logger.error(
                        f"Failed to notify admin: admin_id={admin.id}, "
                        f"ticket_id={ticket_id}, error={str(e)}"
                    )
                    # Continue notifying other admins (FR-1.3.4)
        
        finally:
            # Close bot session
            if max_bot and max_bot.session:
                await max_bot.session.close()
        
        # Send to escalation channels based on ticket type (MAX only)
        channels_notified = []
        
        # Helper function to determine messenger type
        def is_max_chat_id(chat_id: str) -> bool:
            """Determine if chat_id is for MAX messenger."""
            try:
                chat_id_int = int(chat_id)
                # MAX chat IDs are typically very long negative numbers (> 10^13 in absolute value)
                return abs(chat_id_int) > 10000000000000
            except (ValueError, TypeError):
                return False
        
        # Initialize MAX bot for channel notifications
        max_bot = None
        
        try:
            from constants import MAX_BOT_TOKEN
            if MAX_BOT_TOKEN:
                try:
                    max_bot = MAXBot(
                        token=MAX_BOT_TOKEN,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Failed to initialize MAX bot for channels: {e}")
            
            # Get escalation channel settings
            from services.settings_service import get_setting
            
            if ticket.ticket_type.value in ["invoice", "renewal"]:
                # For invoice/renewal tickets, send to manager escalation channel
                manager_channel = await get_setting(session, "escalation_manager_channel")
                if manager_channel:
                    is_max = is_max_chat_id(manager_channel)
                    
                    if is_max and max_bot:
                        try:
                            await max_bot.send_message(
                                chat_id=int(manager_channel),
                                text=notification_text
                            )
                            channels_notified.append("escalation_manager_channel (MAX)")
                            logger.info(
                                f"Escalation notification sent to MAX manager channel: {manager_channel}, "
                                f"ticket_id={ticket_id}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to send escalation to MAX manager channel {manager_channel}: {e}",
                                exc_info=True
                            )
                    else:
                        logger.warning(
                            f"Cannot send to manager channel {manager_channel}: "
                            f"{'Not a MAX chat ID' if not is_max else 'MAX bot not available'}"
                        )
            
            elif ticket.ticket_type.value == "technical_support":
                # For technical support tickets, send to duty escalation channel
                duty_channel = await get_setting(session, "escalation_duty_channel")
                if duty_channel:
                    is_max = is_max_chat_id(duty_channel)
                    
                    if is_max and max_bot:
                        try:
                            await max_bot.send_message(
                                chat_id=int(duty_channel),
                                text=notification_text
                            )
                            channels_notified.append("escalation_duty_channel (MAX)")
                            logger.info(
                                f"Escalation notification sent to MAX duty channel: {duty_channel}, "
                                f"ticket_id={ticket_id}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to send escalation to MAX duty channel {duty_channel}: {e}",
                                exc_info=True
                            )
                    else:
                        logger.warning(
                            f"Cannot send to duty channel {duty_channel}: "
                            f"{'Not a MAX chat ID' if not is_max else 'MAX bot not available'}"
                        )
        
        finally:
            # Close bot session
            if max_bot and max_bot.session:
                await max_bot.session.close()
        
        # Log escalation action with detailed results
        try:
            action_details_data = {
                "escalation_id": escalation.id,
                "escalation_type": EscalationType.ESCALATION_20MIN.value,
                "time_elapsed": time_elapsed,
                "admins_notified": notified_count,
                "admins_failed": failed_count,
                "total_admins": len(admins),
                "channels_notified": channels_notified
            }
            
            if failed_admins:
                action_details_data["failed_admins"] = failed_admins
            
            action_log = Action_Log(
                ticket_id=ticket.id,
                action_type=ActionType.TICKET_ESCALATED,
                action_details=action_details_data
            )
            session.add(action_log)
            await session.commit()
        except Exception as e:
            logger.error(
                f"Failed to log escalation action: ticket_id={ticket_id}, error={e}"
            )
            # Don't fail the task if logging fails
        
        # Determine overall status
        if notified_count == 0 and not channels_notified:
            status = "error"
            message = "Escalation created but failed to notify any admins or channels"
        elif notified_count == 0:
            status = "partial"
            message = f"Escalation created, notified {len(channels_notified)} channel(s) but no admins"
        elif failed_count > 0:
            status = "success"
            message = f"Escalation created, {notified_count}/{len(admins)} admins and {len(channels_notified)} channel(s) notified"
        else:
            status = "success"
            message = f"Escalation created, all admins and {len(channels_notified)} channel(s) notified"
        
        logger.info(
            f"Escalation notification completed: ticket_id={ticket_id}, "
            f"escalation_id={escalation.id}, notified={notified_count}, "
            f"failed={failed_count}, channels={len(channels_notified)}"
        )
        
        return {
            "status": status,
            "message": message,
            "ticket_id": ticket_id,
            "escalation_id": escalation.id,
            "admins_notified": notified_count,
            "admins_failed": failed_count,
            "failed_admins": failed_admins if failed_admins else None,
            "channels_notified": channels_notified,
            "time_elapsed": time_elapsed
        }



# ========== Scheduling and Cancellation Utilities ==========


async def schedule_escalation_monitoring(ticket_id: int) -> tuple[str, str]:
    """
    Schedule backup manager escalation monitoring for a new ticket.
    
    New backup manager escalation flow:
    - 10 min: Escalate to backup_manager_1 (Level 0 → 1)
    - 20 min: Escalate to backup_manager_2 (Level 1 → 2)  
    - 30 min: Create escalation record and notify admins (Level 2 → Escalation)
    
    Only schedules the first reminder task. Subsequent tasks are scheduled
    by each escalation step to create a chain.
    
    Preconditions:
    - ticket_id exists in database
    - Ticket has status NEW and escalation_level = 0
    - Celery worker is running and accessible
    
    Postconditions:
    - First reminder task scheduled in Celery (10 minutes)
    - task_id saved to ticket record in database
    - Returns tuple (reminder_task_id, None) for compatibility
    
    Args:
        ticket_id: ID of the ticket to monitor
    
    Returns:
        Tuple of (reminder_task_id, None) - escalation_task_id is None since
        escalation tasks are now chained through reminder tasks
    
    Raises:
        Exception: If Celery is unavailable or task scheduling fails
    
    Requirements: 1.1, Backup Manager Escalation Flow
    """
    try:
        # Schedule first reminder task (configured timeout) - will escalate to backup_manager_1
        timeout_seconds = get_backup_escalation_timeout_sync()
        reminder_task = check_ticket_reminder.apply_async(
            args=[ticket_id],
            countdown=timeout_seconds
        )
        
        logger.info(
            f"Backup manager escalation monitoring scheduled: ticket_id={ticket_id}, "
            f"reminder_task_id={reminder_task.id}"
        )
        
        # Save task ID to ticket
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Ticket).where(Ticket.id == ticket_id)
            )
            ticket = result.scalar_one_or_none()
            
            if ticket:
                ticket.escalation_task_reminder_id = reminder_task.id
                # escalation_task_escalation_id is not used in new flow
                ticket.escalation_task_escalation_id = None
                await session.commit()
                
                logger.info(
                    f"Task ID saved to ticket: ticket_id={ticket_id}"
                )
        
        # Return tuple for compatibility (escalation_task_id is None)
        return (reminder_task.id, None)
    
    except Exception as e:
        logger.error(
            f"Failed to schedule backup manager escalation monitoring: ticket_id={ticket_id}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def cancel_escalation_monitoring(ticket_id: int) -> bool:
    """
    Cancel scheduled backup manager escalation monitoring for a ticket.
    
    Cancels the current reminder task if it is still pending.
    In the new backup manager flow, only one task is active at a time.
    
    This function is idempotent - calling it multiple times has no adverse effects.
    
    Preconditions:
    - ticket_id exists in database
    - Ticket has task_id saved (or None if already cancelled)
    - Task has not yet executed
    
    Postconditions:
    - Task revoked in Celery (if still pending)
    - task_id cleared in ticket record
    - Returns True if successful, False if ticket not found
    
    Args:
        ticket_id: ID of the ticket to cancel monitoring for
    
    Returns:
        True if cancellation successful, False if ticket not found
    
    Requirements: 1.2, Backup Manager Escalation Flow
    """
    try:
        async with AsyncSessionLocal() as session:
            # Get ticket with task IDs
            result = await session.execute(
                select(Ticket).where(Ticket.id == ticket_id)
            )
            ticket = result.scalar_one_or_none()
            
            if not ticket:
                logger.warning(
                    f"Cannot cancel monitoring - ticket not found: ticket_id={ticket_id}"
                )
                return False
            
            # Revoke current reminder task (only one active task in new flow)
            if ticket.escalation_task_reminder_id:
                try:
                    celery_app.control.revoke(
                        ticket.escalation_task_reminder_id,
                        terminate=True
                    )
                    logger.info(
                        f"Backup escalation task revoked: task_id={ticket.escalation_task_reminder_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to revoke backup escalation task: "
                        f"task_id={ticket.escalation_task_reminder_id}, error={e}"
                    )
            
            # Clear task IDs in database
            ticket.escalation_task_reminder_id = None
            ticket.escalation_task_escalation_id = None
            await session.commit()
            
            logger.info(
                f"Backup manager escalation monitoring cancelled: ticket_id={ticket_id}"
            )
            
            return True
    
    except Exception as e:
        logger.error(
            f"Failed to cancel backup manager escalation monitoring: ticket_id={ticket_id}, "
            f"error={e}",
            exc_info=True
        )
        return False

