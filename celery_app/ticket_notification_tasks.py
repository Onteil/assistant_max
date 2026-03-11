"""
Ticket Notification Tasks for Celery.

Handles periodic checks for tickets that need notifications:
- Tickets created during non-working hours
- Tickets created during extended hours
- Sends notifications when work mode changes to REGULAR
"""

import logging
from datetime import datetime, timedelta

import pytz
from celery import Task
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from celery_app.celery_config import app
from constants import AsyncSessionLocal, MAX_BOT_TOKEN, TG_BOT_TOKEN
from database.models import (
    Staff_Member,
    StaffRole,
    Ticket,
    TicketStatus,
    TicketType,
    WorkMode,
)
from services.calendar_service import get_current_work_mode
from services.ticket_service import send_staff_notification

logger = logging.getLogger(__name__)

MOSCOW_TZ = pytz.timezone('Europe/Moscow')


class AsyncTask(Task):
    """Base task class with async support."""
    
    def __call__(self, *args, **kwargs):
        import asyncio
        return asyncio.run(self.run_async(*args, **kwargs))
    
    async def run_async(self, *args, **kwargs):
        raise NotImplementedError()


@app.task(
    bind=True,
    base=AsyncTask,
    name="celery_app.ticket_notification_tasks.process_pending_tickets",
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
async def process_pending_tickets_task(self) -> dict:
    """
    Process INVOICE and RENEWAL tickets created during non-working/extended hours.
    
    This task runs at the start of regular working hours (9:00 AM Moscow time).
    It finds all NEW INVOICE and RENEWAL tickets and sends notifications
    to assigned managers or admins.
    
    NOTE: TECHNICAL_SUPPORT tickets are NOT processed here because:
    - In REGULAR hours: notifications are sent immediately to all support staff
    - In EXTENDED hours: notifications are sent immediately to duty engineer
    - In NON_WORKING hours: tickets wait without notifications (as per requirements)
    
    Ticket Types Processed:
    - INVOICE: Notify assigned manager or admins if no manager
    - RENEWAL: Notify assigned manager
    
    Returns:
        dict: Statistics about processed tickets
    """
    logger.info("Starting process_pending_tickets_task")
    
    stats = {
        "total_processed": 0,
        "invoice_tickets": 0,
        "renewal_tickets": 0,
        "notifications_sent": 0,
        "errors": 0,
    }
    
    try:
        async with AsyncSessionLocal() as session:
            # Check current work mode
            work_mode = await get_current_work_mode(session)
            
            if work_mode != WorkMode.REGULAR:
                logger.info(
                    f"Not in REGULAR work mode (current: {work_mode.value}). "
                    f"Skipping pending ticket processing."
                )
                return stats
            
            # Get current time in Moscow timezone
            current_time = datetime.now(MOSCOW_TZ)
            
            # Find tickets created in the last 24 hours that are still NEW
            # and don't have assigned staff (or need notification)
            yesterday = current_time - timedelta(hours=24)
            
            stmt = select(Ticket).where(
                and_(
                    Ticket.ticket_status == TicketStatus.NEW,
                    Ticket.created_at >= yesterday,
                    # Only process INVOICE and RENEWAL tickets
                    # TECHNICAL_SUPPORT tickets are handled immediately or wait without notifications
                    Ticket.ticket_type.in_([TicketType.INVOICE, TicketType.RENEWAL])
                )
            )
            
            result = await session.execute(stmt)
            pending_tickets = result.scalars().all()
            
            logger.info(f"Found {len(pending_tickets)} pending tickets to process")
            
            # Initialize MAX bot only
            from maxapi import Bot as MAXBot
            from database.models import MAX_Messenger_Data
            
            max_bot = MAXBot(token=MAX_BOT_TOKEN) if MAX_BOT_TOKEN else None
            
            for ticket in pending_tickets:
                try:
                    stats["total_processed"] += 1
                    
                    # Determine which messenger to use and get appropriate ID (MAX only)
                    messenger_type = None
                    messenger_id = None
                    
                    if ticket.user.max_user_id and max_bot:
                        messenger_type = "max"
                        messenger_id = ticket.user.max_user_id
                    
                    if not messenger_type:
                        logger.warning(
                            f"No MAX bot available for ticket {ticket.id} "
                            f"(user has no MAX messenger ID)"
                        )
                        continue
                    
                    # Process based on ticket type
                    if ticket.ticket_type == TicketType.INVOICE:
                        stats["invoice_tickets"] += 1
                        await _process_invoice_ticket(
                            ticket, max_bot, messenger_type, 
                            messenger_id, session, stats
                        )
                    
                    elif ticket.ticket_type == TicketType.RENEWAL:
                        stats["renewal_tickets"] += 1
                        await _process_renewal_ticket(
                            ticket, max_bot, messenger_type,
                            messenger_id, session, stats
                        )
                
                except Exception as e:
                    stats["errors"] += 1
                    logger.error(
                        f"Error processing ticket {ticket.id}: {e}",
                        exc_info=True
                    )
            
            # Close bot session
            if max_bot:
                await max_bot.close()
            
            logger.info(
                f"Completed process_pending_tickets_task: {stats}"
            )
            
            return stats
    
    except Exception as e:
        logger.error(
            f"Fatal error in process_pending_tickets_task: {e}",
            exc_info=True
        )
        stats["errors"] += 1
        return stats


async def _process_invoice_ticket(
    ticket: Ticket,
    max_bot,
    messenger_type: str,
    messenger_id: int,
    session: AsyncSession,
    stats: dict
) -> None:
    """
    Process INVOICE ticket - notify manager or admins.
    Supports MAX messenger only.
    
    Args:
        ticket: Ticket object
        max_bot: MAX bot instance (or None)
        messenger_type: "max"
        messenger_id: max_user_id
        session: Database session
        stats: Statistics dictionary to update
    """
    from database.models import MAX_Messenger_Data
    
    if ticket.assigned_staff_id:
        # Notify assigned manager
        notification_sent = await send_staff_notification(
            bot=max_bot,
            staff_id=ticket.assigned_staff_id,
            ticket=ticket,
            routing_info={
                "work_mode": "regular",
                "expected_response_time": "в течение рабочего дня"
            },
            session=session
        )
        
        if notification_sent:
            stats["notifications_sent"] += 1
            logger.info(
                f"Manager notification sent for ticket {ticket.id}, "
                f"staff_id={ticket.assigned_staff_id}, messenger={messenger_type}"
            )
    else:
        # No manager - notify all admins
        from services.escalation_service import get_active_admins
        
        admins = await get_active_admins(session)
        
        if admins:
            admin_message = (
                f"⚠️ <b>Заявка на счет без назначенного менеджера</b>\n\n"
                f"<b>Заявка:</b> #{ticket.id}\n"
                f"<b>Создана:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"<b>Тип:</b> Запрос счета\n\n"
                f"<b>Клиент:</b>\n"
                f"• ФИО: {ticket.user.full_name or 'Не указано'}\n"
                f"• Телефон: {ticket.user.phone_number or 'Не указан'}\n"
            )
            
            if ticket.user.max_user_id:
                admin_message += f"• MAX ID: {ticket.user.max_user_id}\n"
            
            if ticket.organization_inn:
                admin_message += f"\n<b>Организация:</b> {ticket.organization_inn}\n"
            
            if ticket.description:
                desc_preview = ticket.description[:150]
                if len(ticket.description) > 150:
                    desc_preview += "..."
                admin_message += f"\n<b>Описание:</b>\n{desc_preview}\n"
            
            admin_message += (
                f"\n❗️ <b>У клиента не назначен менеджер!</b>\n"
                f"Необходимо назначить менеджера для обработки заявки."
            )
            
            for admin in admins:
                try:
                    # Send via MAX only
                    if admin.max_user_id and max_bot:
                        # Get MAX chat_id from database
                        stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                            MAX_Messenger_Data.max_user_id == admin.max_user_id
                        )
                        result_chat = await session.execute(stmt_chat)
                        chat_id = result_chat.scalar_one_or_none()
                        
                        if chat_id is None:
                            logger.error(
                                f"No MAX chat_id found for admin: admin_id={admin.id}, "
                                f"max_user_id={admin.max_user_id}"
                            )
                            continue
                        
                        # Send via MAX
                        await max_bot.send_message(
                            chat_id=chat_id,
                            text=admin_message
                        )
                        stats["notifications_sent"] += 1
                        logger.info(
                            f"Admin notification sent via MAX for ticket {ticket.id}, "
                            f"admin_id={admin.id}"
                        )
                            f"Admin notification sent via MAX for ticket {ticket.id}, "
                            f"admin_id={admin.id}, chat_id={chat_id}"
                        )
                    
                except Exception as e:
                    logger.error(
                        f"Failed to send admin notification for ticket {ticket.id}, "
                        f"admin_id={admin.id}: {e}",
                        exc_info=True
                    )


async def _process_renewal_ticket(
    ticket: Ticket,
    max_bot,
    messenger_type: str,
    messenger_id: int,
    session: AsyncSession,
    stats: dict
) -> None:
    """
    Process RENEWAL ticket - notify assigned manager.
    Supports MAX messenger only.
    
    Args:
        ticket: Ticket object
        max_bot: MAX bot instance (or None)
        messenger_type: "max"
        messenger_id: max_user_id
        session: Database session
        stats: Statistics dictionary to update
    """
    if not ticket.assigned_staff_id:
        logger.warning(
            f"Renewal ticket {ticket.id} has no assigned manager"
        )
        return
    
    notification_sent = await send_staff_notification(
        bot=max_bot,
        staff_id=ticket.assigned_staff_id,
        ticket=ticket,
        routing_info={
            "work_mode": "regular",
            "expected_response_time": "в течение рабочего дня"
        },
        session=session
    )
    
    if notification_sent:
        stats["notifications_sent"] += 1
        logger.info(
            f"Manager notification sent for renewal ticket {ticket.id}, "
            f"staff_id={ticket.assigned_staff_id}, messenger={messenger_type}"
        )
