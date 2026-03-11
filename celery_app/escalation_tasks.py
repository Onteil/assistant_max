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
from sqlalchemy.orm import selectinload

from celery_app.celery_config import app as celery_app
from constants import (
    ESCALATION_REMINDER_TIMEOUT,
    ESCALATION_TIMEOUT,
    TG_BOT_TOKEN,
    AsyncSessionLocal,
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
    Check ticket status after 10 minutes and send reminder to assigned staff.
    
    This task is scheduled when a ticket is created with status NEW.
    If the ticket is still NEW after 10 minutes, sends a reminder notification
    to the assigned staff member.
    
    Preconditions:
    - ticket_id exists in database
    - Task scheduled at ticket creation
    
    Postconditions:
    - If status=NEW: reminder sent to assigned staff
    - If status!=NEW: task completes without action
    - Returns dict with execution result
    
    Args:
        ticket_id: ID of the ticket to check
    
    Returns:
        Dict with status, message, and additional data:
        - status: "success", "skipped", or "error"
        - message: Description of what happened
        - Additional fields depending on outcome
    
    Requirements: 1.1, 1.3
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
    Async implementation of reminder check.
    
    Checks ticket status and sends reminder if still NEW.
    Uses centralized notification templates from escalation_notifications.
    Supports both Telegram and MAX messengers.
    
    Args:
        ticket_id: ID of the ticket to check
    
    Returns:
        Dict with execution result
    
    Requirements: FR-1.3.1, FR-1.10.2
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
                selectinload(Ticket.assigned_staff)
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
        
        # Check if staff is assigned and has messenger ID
        if not ticket.assigned_staff:
            logger.info(
                f"No assigned staff for reminder: ticket_id={ticket_id}"
            )
            return {
                "status": "skipped",
                "message": "No assigned staff - ticket routed to team or queued",
                "ticket_id": ticket_id,
                "assigned_staff_id": ticket.assigned_staff_id
            }
        
        # Determine messenger type and ID
        messenger_type = None
        messenger_id = None
        
        if ticket.assigned_staff.tg_user_id:
            messenger_type = "telegram"
            messenger_id = ticket.assigned_staff.tg_user_id
        elif ticket.assigned_staff.max_user_id:
            messenger_type = "max"
            messenger_id = ticket.assigned_staff.max_user_id
        else:
            logger.info(
                f"Staff has no messenger ID: ticket_id={ticket_id}, "
                f"staff_id={ticket.assigned_staff.id}"
            )
            return {
                "status": "skipped",
                "message": "Staff has no messenger ID",
                "ticket_id": ticket_id,
                "staff_id": ticket.assigned_staff.id
            }
        
        # Calculate time elapsed
        # Import here to avoid circular dependency
        from bots.tg_bot.utils.escalation_notifications import (
            calculate_time_elapsed,
            get_reminder_notification_text,
        )
        
        time_elapsed = calculate_time_elapsed(ticket.created_at)
        
        # Use centralized notification template
        reminder_text = get_reminder_notification_text(ticket, time_elapsed)
        
        # Send reminder via appropriate messenger
        try:
            if messenger_type == "telegram":
                # Send via Telegram
                async with Bot(
                    token=TG_BOT_TOKEN,
                    default=DefaultBotProperties(parse_mode="HTML")
                ).context(auto_close=True) as bot:
                    await bot.send_message(
                        chat_id=messenger_id,
                        text=reminder_text
                    )
                
                logger.info(
                    f"Telegram reminder sent: ticket_id={ticket_id}, "
                    f"staff_id={ticket.assigned_staff.id}, "
                    f"tg_user_id={messenger_id}, time_elapsed={time_elapsed} min"
                )
            
            elif messenger_type == "max":
                # Get MAX chat_id from staff member
                chat_id = ticket.assigned_staff.max_chat_id
                
                if chat_id is None:
                    logger.error(
                        f"No MAX chat_id found: ticket_id={ticket_id}, "
                        f"staff_id={ticket.assigned_staff.id}, "
                        f"max_user_id={messenger_id}"
                    )
                    return {
                        "status": "error",
                        "message": "No MAX chat_id found for staff",
                        "ticket_id": ticket_id,
                        "staff_id": ticket.assigned_staff.id
                    }
                
                # Send via MAX
                from constants import MAX_BOT_TOKEN
                
                max_bot = MAXBot(
                    token=MAX_BOT_TOKEN,
                    parse_mode=ParseMode.HTML
                )
                
                try:
                    await max_bot.send_message(
                        chat_id=chat_id,
                        text=reminder_text
                    )
                    
                    logger.info(
                        f"MAX reminder sent: ticket_id={ticket_id}, "
                        f"staff_id={ticket.assigned_staff.id}, "
                        f"max_user_id={messenger_id}, chat_id={chat_id}, "
                        f"time_elapsed={time_elapsed} min"
                    )
                
                except MaxApiError as e:
                    error_str = str(e).lower()
                    if "blocked" in error_str or "forbidden" in error_str or "chat.not.found" in error_str:
                        logger.warning(
                            f"MAX bot blocked by staff: ticket_id={ticket_id}, "
                            f"staff_id={ticket.assigned_staff.id}, "
                            f"max_user_id={messenger_id}, chat_id={chat_id}"
                        )
                        return {
                            "status": "bot_blocked",
                            "message": "MAX bot blocked by staff",
                            "ticket_id": ticket_id,
                            "staff_id": ticket.assigned_staff.id
                        }
                    raise
                
                finally:
                    # Close MAX bot session
                    if max_bot and max_bot.session:
                        await max_bot.session.close()
        
        except Exception as e:
            logger.error(
                f"Failed to send reminder: ticket_id={ticket_id}, "
                f"staff_id={ticket.assigned_staff.id}, "
                f"messenger={messenger_type}, messenger_id={messenger_id}, "
                f"error={str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "message": f"Failed to send reminder: {str(e)}",
                "ticket_id": ticket_id,
                "staff_id": ticket.assigned_staff.id
            }
        
        # Log action
        try:
            action_log = Action_Log(
                ticket_id=ticket.id,
                staff_id=ticket.assigned_staff.id,
                action_type=ActionType.REMINDER_SENT,
                action_details={
                    "reminder_type": "10_minute",
                    "time_elapsed": time_elapsed,
                    "messenger": messenger_type
                }
            )
            session.add(action_log)
            await session.commit()
        except Exception as e:
            logger.error(
                f"Failed to log reminder action: ticket_id={ticket_id}, error={e}",
                exc_info=True
            )
            await session.rollback()
            # Don't fail the task if logging fails
        
        return {
            "status": "success",
            "message": "Reminder sent",
            "ticket_id": ticket_id,
            "staff_id": ticket.assigned_staff.id,
            "time_elapsed": time_elapsed,
            "messenger": messenger_type
        }


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
        
        # Initialize bots
        tg_bot = None
        max_bot = None
        
        try:
            tg_bot = Bot(
                token=TG_BOT_TOKEN,
                default=DefaultBotProperties(parse_mode="HTML")
            )
            
            from constants import MAX_BOT_TOKEN
            max_bot = MAXBot(
                token=MAX_BOT_TOKEN,
                parse_mode=ParseMode.HTML
            )
            
            for admin in admins:
                try:
                    # Determine messenger type
                    if admin.tg_user_id:
                        # Send via Telegram
                        await tg_bot.send_message(
                            chat_id=admin.tg_user_id,
                            text=notification_text,
                            reply_markup=notification_keyboard
                        )
                        notified_count += 1
                        logger.info(
                            f"Admin notified via Telegram: admin_id={admin.id}, "
                            f"tg_user_id={admin.tg_user_id}, ticket_id={ticket_id}"
                        )
                    
                    elif admin.max_user_id:
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
                            f"Admin has no messenger ID: admin_id={admin.id}"
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
            # Close bot sessions
            if tg_bot and tg_bot.session:
                await tg_bot.session.close()
            if max_bot and max_bot.session:
                await max_bot.session.close()
        
        # Send to escalation channels based on ticket type
        channels_notified = []
        
        # Helper function to determine messenger type
        def is_max_chat_id(chat_id: str) -> bool:
            """Determine if chat_id is for MAX messenger."""
            try:
                chat_id_int = int(chat_id)
                # MAX chat IDs are typically very long negative numbers (> 10^13 in absolute value)
                # Telegram chat IDs are shorter (< 10^13 in absolute value)
                return abs(chat_id_int) > 10000000000000
            except (ValueError, TypeError):
                return False
        
        # Re-initialize bots for channel notifications
        tg_bot = None
        max_bot = None
        
        try:
            if TG_BOT_TOKEN:
                tg_bot = Bot(
                    token=TG_BOT_TOKEN,
                    default=DefaultBotProperties(parse_mode="HTML")
                )
            
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
                    elif not is_max and tg_bot:
                        try:
                            await tg_bot.send_message(
                                chat_id=manager_channel,
                                text=notification_text,
                                parse_mode="HTML"
                            )
                            channels_notified.append("escalation_manager_channel (Telegram)")
                            logger.info(
                                f"Escalation notification sent to Telegram manager channel: {manager_channel}, "
                                f"ticket_id={ticket_id}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to send escalation to Telegram manager channel {manager_channel}: {e}",
                                exc_info=True
                            )
                    else:
                        logger.warning(
                            f"Cannot send to manager channel {manager_channel}: "
                            f"{'MAX' if is_max else 'Telegram'} bot not available"
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
                    elif not is_max and tg_bot:
                        try:
                            await tg_bot.send_message(
                                chat_id=duty_channel,
                                text=notification_text,
                                parse_mode="HTML"
                            )
                            channels_notified.append("escalation_duty_channel (Telegram)")
                            logger.info(
                                f"Escalation notification sent to Telegram duty channel: {duty_channel}, "
                                f"ticket_id={ticket_id}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to send escalation to Telegram duty channel {duty_channel}: {e}",
                                exc_info=True
                            )
                    else:
                        logger.warning(
                            f"Cannot send to duty channel {duty_channel}: "
                            f"{'MAX' if is_max else 'Telegram'} bot not available"
                        )
        
        finally:
            # Close bot sessions
            if tg_bot and tg_bot.session:
                await tg_bot.session.close()
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
    Schedule both monitoring tasks for a new ticket.
    
    Schedules:
    - Reminder task after ESCALATION_REMINDER_TIMEOUT seconds (default: 600 = 10 min)
    - Escalation task after ESCALATION_TIMEOUT seconds (default: 1200 = 20 min)
    
    Preconditions:
    - ticket_id exists in database
    - Ticket has status NEW
    - Celery worker is running and accessible
    
    Postconditions:
    - Two tasks scheduled in Celery
    - task_ids saved to ticket record in database
    - Returns tuple (reminder_task_id, escalation_task_id)
    
    Args:
        ticket_id: ID of the ticket to monitor
    
    Returns:
        Tuple of (reminder_task_id, escalation_task_id)
    
    Raises:
        Exception: If Celery is unavailable or task scheduling fails
    
    Requirements: 1.1
    """
    try:
        # Schedule reminder task (10 minutes)
        reminder_task = check_ticket_reminder.apply_async(
            args=[ticket_id],
            countdown=ESCALATION_REMINDER_TIMEOUT
        )
        
        # Schedule escalation task (20 minutes)
        escalation_task = check_ticket_escalation.apply_async(
            args=[ticket_id],
            countdown=ESCALATION_TIMEOUT
        )
        
        logger.info(
            f"Escalation monitoring scheduled: ticket_id={ticket_id}, "
            f"reminder_task_id={reminder_task.id}, "
            f"escalation_task_id={escalation_task.id}"
        )
        
        # Save task IDs to ticket
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Ticket).where(Ticket.id == ticket_id)
            )
            ticket = result.scalar_one_or_none()
            
            if ticket:
                ticket.escalation_task_reminder_id = reminder_task.id
                ticket.escalation_task_escalation_id = escalation_task.id
                await session.commit()
                
                logger.info(
                    f"Task IDs saved to ticket: ticket_id={ticket_id}"
                )
        
        return (reminder_task.id, escalation_task.id)
    
    except Exception as e:
        logger.error(
            f"Failed to schedule escalation monitoring: ticket_id={ticket_id}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def cancel_escalation_monitoring(ticket_id: int) -> bool:
    """
    Cancel scheduled monitoring tasks for a ticket.
    
    Cancels both reminder and escalation tasks if they are still pending.
    This function is idempotent - calling it multiple times has no adverse effects.
    
    Preconditions:
    - ticket_id exists in database
    - Ticket has task_ids saved (or None if already cancelled)
    - Tasks have not yet executed
    
    Postconditions:
    - Tasks revoked in Celery (if still pending)
    - task_ids cleared in ticket record
    - Returns True if successful, False if ticket not found
    
    Args:
        ticket_id: ID of the ticket to cancel monitoring for
    
    Returns:
        True if cancellation successful, False if ticket not found
    
    Requirements: 1.2
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
            
            # Revoke reminder task
            if ticket.escalation_task_reminder_id:
                try:
                    celery_app.control.revoke(
                        ticket.escalation_task_reminder_id,
                        terminate=True
                    )
                    logger.info(
                        f"Reminder task revoked: task_id={ticket.escalation_task_reminder_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to revoke reminder task: "
                        f"task_id={ticket.escalation_task_reminder_id}, error={e}"
                    )
            
            # Revoke escalation task
            if ticket.escalation_task_escalation_id:
                try:
                    celery_app.control.revoke(
                        ticket.escalation_task_escalation_id,
                        terminate=True
                    )
                    logger.info(
                        f"Escalation task revoked: task_id={ticket.escalation_task_escalation_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to revoke escalation task: "
                        f"task_id={ticket.escalation_task_escalation_id}, error={e}"
                    )
            
            # Clear task IDs in database
            ticket.escalation_task_reminder_id = None
            ticket.escalation_task_escalation_id = None
            await session.commit()
            
            logger.info(
                f"Escalation monitoring cancelled: ticket_id={ticket_id}"
            )
            
            return True
    
    except Exception as e:
        logger.error(
            f"Failed to cancel escalation monitoring: ticket_id={ticket_id}, "
            f"error={e}",
            exc_info=True
        )
        return False

