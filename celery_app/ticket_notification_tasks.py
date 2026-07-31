"""
Ticket Notification Tasks for Celery.

Handles periodic checks for tickets that need notifications:
- Tickets created during non-working hours
- Tickets created during extended hours
- Sends notifications when work mode changes to REGULAR
"""

import asyncio
import logging
from datetime import datetime, timedelta

import pytz
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from celery_app.celery_config import app
from constants import AsyncSessionLocal, MAX_BOT_TOKEN, TG_BOT_TOKEN
from database.models import (
    File_Attachment,
    Staff_Member,
    StaffRole,
    Ticket,
    TicketStatus,
    TicketType,
    User,
    WorkMode,
)
from services.calendar_service import get_current_work_mode
from services.ticket_service import send_staff_notification

logger = logging.getLogger(__name__)

MOSCOW_TZ = pytz.timezone('Europe/Moscow')


@app.task(
    bind=True,
    name="celery_app.ticket_notification_tasks.process_pending_tickets",
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def process_pending_tickets_task(self) -> dict:
    """
    Process INVOICE and RENEWAL tickets created during non-working/extended hours.

    Runs at the start of regular working hours (8:00 AM Moscow time) and also
    triggered by work mode transition monitor.
    """
    try:
        return asyncio.run(_process_pending_tickets_async())
    except Exception as e:
        logger.error(f"Fatal error in process_pending_tickets_task: {e}", exc_info=True)
        try:
            raise self.retry(exc=e, countdown=300 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for process_pending_tickets_task")
            return {"status": "error", "error": str(e)}


async def _process_pending_tickets_async() -> dict:
    """
    Process INVOICE and RENEWAL tickets created during non-working/extended hours.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from constants import DB_URL, SQL_ECHO

    # Create a fresh engine bound to the current event loop (required for asyncpg + solo pool)
    task_engine = create_async_engine(DB_URL, echo=SQL_ECHO, pool_pre_ping=True)
    TaskSession = async_sessionmaker(bind=task_engine, class_=AsyncSession, expire_on_commit=False)

    logger.info("Starting process_pending_tickets_task")
    
    stats = {
        "total_processed": 0,
        "invoice_tickets": 0,
        "renewal_tickets": 0,
        "support_tickets": 0,
        "consultation_tickets": 0,
        "notifications_sent": 0,
        "errors": 0,
    }
    
    try:
        async with TaskSession() as session:
            # Check current work mode
            work_mode = await get_current_work_mode(session)
            
            # NON_WORKING — nothing to do yet, tickets stay in queue
            if work_mode == WorkMode.NON_WORKING:
                logger.info("Still in NON_WORKING mode. Skipping pending ticket processing.")
                return stats
            
            # EXTENDED — only TECHNICAL_SUPPORT and CONSULTATION have duty staff available.
            # INVOICE and RENEWAL have no manager on duty in EXTENDED, so they stay queued
            # until REGULAR hours. We still process TP/CONSULTATION here.
            # REGULAR — process all ticket types.
            process_invoice_renewal = (work_mode == WorkMode.REGULAR)
            
            if work_mode == WorkMode.EXTENDED:
                logger.info(
                    "In EXTENDED work mode — processing TECHNICAL_SUPPORT and CONSULTATION only. "
                    "INVOICE and RENEWAL will be processed when REGULAR hours start."
                )
            
            # Get current time in Moscow timezone
            current_time = datetime.now(MOSCOW_TZ)
            
            # Find tickets created in the last 336 hours (14 days) that are still NEW.
            # 336h window covers extended holiday periods (e.g. 7-day May holidays)
            # with a comfortable margin. Previously 72h which was too short.
            # Strip timezone info: DB stores TIMESTAMP WITHOUT TIME ZONE (naive UTC/Moscow)
            cutoff_time = (current_time - timedelta(hours=336)).replace(tzinfo=None)
            
            # Determine which ticket types to process based on work mode:
            # REGULAR  → all types (INVOICE, RENEWAL, TECHNICAL_SUPPORT, CONSULTATION)
            # EXTENDED → only types with duty staff (TECHNICAL_SUPPORT, CONSULTATION)
            if process_invoice_renewal:
                ticket_types_to_process = [
                    TicketType.INVOICE, TicketType.RENEWAL,
                    TicketType.TECHNICAL_SUPPORT, TicketType.CONSULTATION,
                ]
            else:
                ticket_types_to_process = [
                    TicketType.TECHNICAL_SUPPORT, TicketType.CONSULTATION,
                ]

            stmt = select(Ticket).where(
                and_(
                    Ticket.ticket_status == TicketStatus.NEW,
                    Ticket.created_at >= cutoff_time,
                    Ticket.ticket_type.in_(ticket_types_to_process),
                    Ticket.queue_notification_sent_at.is_(None),
                )
            ).options(
                selectinload(Ticket.user).selectinload(User.max_messenger_data),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.file_attachments),
            )
            
            result = await session.execute(stmt)
            pending_tickets = result.scalars().all()
            
            logger.info(f"Found {len(pending_tickets)} pending tickets to process")
            
            # Initialize MAX bot only
            from maxapi import Bot as MAXBot
            from maxapi.enums.parse_mode import ParseMode

            max_bot = MAXBot(token=MAX_BOT_TOKEN, parse_mode=ParseMode.HTML) if MAX_BOT_TOKEN else None
            
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
                        
                        # Mark as notified BEFORE processing (so escalation can use this timestamp)
                        ticket.queue_notification_sent_at = datetime.now(MOSCOW_TZ).replace(tzinfo=None)
                        await session.commit()
                        
                        sent = await _process_invoice_ticket(
                            ticket, max_bot, messenger_type, 
                            messenger_id, session, stats
                        )
                    
                    elif ticket.ticket_type == TicketType.RENEWAL:
                        stats["renewal_tickets"] += 1
                        
                        # Mark as notified BEFORE processing (so escalation can use this timestamp)
                        ticket.queue_notification_sent_at = datetime.now(MOSCOW_TZ).replace(tzinfo=None)
                        await session.commit()
                        
                        sent = await _process_renewal_ticket(
                            ticket, max_bot, messenger_type,
                            messenger_id, session, stats
                        )
                    
                    elif ticket.ticket_type == TicketType.TECHNICAL_SUPPORT:
                        stats["support_tickets"] += 1
                        
                        # Mark as notified BEFORE processing (so escalation can use this timestamp)
                        ticket.queue_notification_sent_at = datetime.now(MOSCOW_TZ).replace(tzinfo=None)
                        await session.commit()
                        
                        sent = await _process_support_ticket(
                            ticket, max_bot, session, stats, work_mode=work_mode
                        )
                    
                    elif ticket.ticket_type == TicketType.CONSULTATION:
                        stats["consultation_tickets"] += 1
                        
                        # Mark as notified BEFORE processing (so escalation can use this timestamp)
                        ticket.queue_notification_sent_at = datetime.now(MOSCOW_TZ).replace(tzinfo=None)
                        await session.commit()
                        
                        sent = await _process_consultation_ticket(
                            ticket, max_bot, session, stats, work_mode=work_mode
                        )
                    else:
                        sent = False
                    
                    # If notification failed, clear the timestamp so it will be retried
                    if not sent:
                        ticket.queue_notification_sent_at = None
                        await session.commit()
                        logger.warning(
                            f"Ticket {ticket.id} notification failed - will retry on next run"
                        )
                    else:
                        logger.info(
                            f"Ticket {ticket.id} processed from queue successfully"
                        )
                
                except Exception as e:
                    stats["errors"] += 1
                    logger.error(
                        f"Error processing ticket {ticket.id}: {e}",
                        exc_info=True
                    )
            
            # Close bot session
            if max_bot and max_bot.session:
                await max_bot.session.close()
            
            logger.info(f"Completed process_pending_tickets_task: {stats}")
            return stats

    except Exception as e:
        logger.error(f"Fatal error in _process_pending_tickets_async: {e}", exc_info=True)
        stats["errors"] += 1
        return stats
    finally:
        await task_engine.dispose()


async def _forward_ticket_attachments(
    ticket: Ticket,
    staff_chat_id: int,
    max_bot,
    session: AsyncSession,
) -> None:
    """
    Forward file attachments stored in DB (from non-working hours ticket creation)
    to a staff chat via MAX bot.

    Sends a link instead of re-uploading to avoid .bin filename issues.
    """
    from bots.max_bot.messenger_adapter import MAXMessengerAdapter

    if not ticket.file_attachments:
        return

    adapter = MAXMessengerAdapter(bot=max_bot)
    user_name = ticket.user.full_name if ticket.user else "Клиент"
    caption = f"📎 Вложение к заявке #{ticket.id} от {user_name}"

    for fa in ticket.file_attachments:
        file_url = fa.max_file_url or (
            fa.telegram_file_id
            if fa.telegram_file_id and fa.telegram_file_id.startswith("http")
            else None
        )
        if not file_url:
            continue

        try:
            ft_val = fa.file_type.value if fa.file_type else "document"
            is_image = ft_val == "image"
            
            logger.info(
                f"Processing queued attachment: ticket_id={ticket.id}, "
                f"file_type={ft_val}, file_name={fa.file_name}, is_image={is_image}"
            )

            if is_image:
                # Images — download and send as photo
                import uuid
                from pathlib import Path
                temp_dir = Path("media/temp")
                temp_dir.mkdir(parents=True, exist_ok=True)
                dest_name = f"queue_{ticket.id}_{uuid.uuid4()}.jpg"
                try:
                    local_path = await adapter.download_file(
                        file_url=file_url,
                        destination=f"media/temp/{dest_name}"
                    )
                    await adapter.send_photo(
                        chat_id=staff_chat_id,
                        photo_path=local_path,
                        caption=caption,
                        parse_mode="HTML"
                    )
                    try:
                        Path(local_path).unlink()
                    except Exception:
                        pass
                except Exception as img_error:
                    logger.error(f"Failed to send image: {img_error}")
                    # Fallback to link
                    notify_text = f"{caption}\n\n📷 <a href=\"{file_url}\">Скачать изображение</a>"
                    await adapter.send_message(
                        chat_id=staff_chat_id,
                        text=notify_text,
                        parse_mode="HTML"
                    )
            elif ft_val == "other":
                # Voice messages — download and send as document (same as client→manager pattern)
                import uuid
                from pathlib import Path
                temp_dir = Path("media/temp")
                temp_dir.mkdir(parents=True, exist_ok=True)
                dest_name = f"queue_{ticket.id}_{uuid.uuid4()}.ogg"
                try:
                    local_path = await adapter.download_file(
                        file_url=file_url,
                        destination=f"media/temp/{dest_name}"
                    )
                    await adapter.send_document(
                        chat_id=staff_chat_id,
                        document_path=local_path,
                        caption=caption,
                        parse_mode="HTML"
                    )
                    try:
                        Path(local_path).unlink()
                    except Exception:
                        pass
                except Exception as voice_error:
                    logger.error(f"Failed to send voice: {voice_error}")
                    # Fallback to link
                    notify_text = f"{caption}\n\n🎤 <a href=\"{file_url}\">Голосовое сообщение</a>"
                    await adapter.send_message(
                        chat_id=staff_chat_id,
                        text=notify_text,
                        parse_mode="HTML"
                    )
            else:
                # Documents/files — send link to avoid .bin filename issues
                notify_text = f"{caption}\n\n📎 <a href=\"{file_url}\">Скачать файл</a>"
                await adapter.send_message(
                    chat_id=staff_chat_id,
                    text=notify_text,
                    parse_mode="HTML"
                )

            logger.info(
                f"Queued attachment forwarded: ticket_id={ticket.id}, "
                f"staff_chat_id={staff_chat_id}, file={fa.file_name}"
            )

        except Exception as e:
            logger.error(
                f"Failed to forward queued attachment: ticket_id={ticket.id}, "
                f"file={fa.file_name}, error={e}",
                exc_info=True
            )


async def _process_invoice_ticket(
    ticket: Ticket,
    max_bot,
    messenger_type: str,
    messenger_id: int,
    session: AsyncSession,
    stats: dict
) -> bool:
    """
    Process INVOICE ticket - notify manager or admins.
    Supports MAX messenger only.
    
    Re-runs the manager assignment chain at processing time so changes made
    while the ticket was queued are respected.
    
    Returns True if at least one notification was sent successfully.
    """
    from database.models import MAX_Messenger_Data, Staff_Member

    from services.ticket_service import determine_assigned_manager

    previous_staff_id = ticket.assigned_staff_id
    new_staff_id, has_manager = await determine_assigned_manager(
        session=session,
        user_id=ticket.user_id,
        assign_admin_if_no_manager=True,
    )
    ticket.assigned_staff_id = new_staff_id
    await session.commit()
    logger.info(
        "Invoice ticket %s assignment refreshed from queue: old_staff=%s, "
        "new_staff=%s, has_manager=%s",
        ticket.id,
        previous_staff_id,
        new_staff_id,
        has_manager,
    )

    if ticket.assigned_staff_id:
        # Notify assigned manager
        logger.info(
            f"Processing invoice ticket {ticket.id} from queue: "
            f"assigned_staff_id={ticket.assigned_staff_id}"
        )

        notification_sent = await send_staff_notification(
            bot=max_bot,
            staff_id=ticket.assigned_staff_id,
            ticket=ticket,
            routing_info={
                "work_mode": "regular",
                "expected_response_time": "в течение рабочего дня",
                "from_queue": True,
            },
            session=session,
        )
        
        if notification_sent:
            stats["notifications_sent"] += 1
            logger.info(
                f"Manager notification sent for ticket {ticket.id}, "
                f"staff_id={ticket.assigned_staff_id}, messenger={messenger_type}"
            )
            # Forward attachments to manager
            if ticket.file_attachments:
                try:
                    from bots.max_bot.utils.staff_chat_resolver import get_staff_chat_id
                    staff_chat_id = await get_staff_chat_id(session, ticket.assigned_staff_id)
                    if staff_chat_id:
                        await _forward_ticket_attachments(ticket, staff_chat_id, max_bot, session)
                except Exception as e:
                    logger.error(
                        f"Failed to forward attachments for invoice ticket {ticket.id}: {e}",
                        exc_info=True
                    )
            
            # Schedule escalation monitoring now that working hours have started
            try:
                from celery_app.escalation_tasks import schedule_escalation_monitoring
                await schedule_escalation_monitoring(ticket_id=ticket.id)
                logger.info(
                    f"Escalation monitoring scheduled for queued invoice ticket {ticket.id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to schedule escalation for queued invoice ticket {ticket.id}: {e}",
                    exc_info=True
                )
        else:
            logger.error(
                f"Failed to send manager notification for ticket {ticket.id}, "
                f"staff_id={ticket.assigned_staff_id} - notification will be retried"
            )
        return notification_sent
    else:
        # No manager - notify all admins
        from services.escalation_service import get_active_admins
        
        admins = await get_active_admins(session)
        any_sent = False
        notified_chat_ids = []
        
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
                if ticket.organization and ticket.organization.organization_name:
                    admin_message += f"\n<b>Организация:</b> {ticket.organization.organization_name} (ИНН: {ticket.organization_inn})\n"
                else:
                    admin_message += f"\n<b>Организация:</b> ИНН: {ticket.organization_inn} (название не указано)\n"
            
            # Add delivery method information
            if hasattr(ticket, 'delivery_method') and ticket.delivery_method:
                delivery_method_names = {
                    "telegram": "💬 В чат",
                    "email": "📧 На Email",
                    "none": "❌ Не указан"
                }
                delivery_method_text = delivery_method_names.get(
                    ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method),
                    str(ticket.delivery_method)
                )
                admin_message += f"<b>Способ получения:</b> {delivery_method_text}\n"
                
                # Add delivery email if method is email
                if (ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method)) == "email":
                    if hasattr(ticket, 'delivery_email') and ticket.delivery_email:
                        admin_message += f"<b>Email для доставки:</b> {ticket.delivery_email}\n"
            
            if ticket.description:
                desc_preview = ticket.description[:150]
                if len(ticket.description) > 150:
                    desc_preview += "..."
                admin_message += f"\n<b>Описание:</b>\n{desc_preview}\n"
            
            admin_message += (
                f"\n❗️ <b>У клиента не назначен менеджер!</b>\n"
                f"Необходимо назначить менеджера для обработки заявки."
            )
            
            # Build keyboard with "К заявке" button
            from bots.max_bot.payloads import ManagerViewTicketPayload
            from maxapi.types.attachments.buttons import CallbackButton
            from maxapi.types.attachments.attachment import ButtonsPayload
            
            buttons = [[
                CallbackButton(
                    text="📋 К заявке",
                    payload=ManagerViewTicketPayload(ticket_id=ticket.id).pack()
                )
            ]]
            
            for admin in admins:
                try:
                    # Send via MAX only
                    if max_bot:
                        # Get MAX chat_id with fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
                        chat_id = admin.max_chat_id
                        
                        # Fallback to MAX_Messenger_Data if not in Staff_Member
                        if not chat_id and admin.max_user_id:
                            stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                                MAX_Messenger_Data.max_user_id == admin.max_user_id
                            )
                            result_chat = await session.execute(stmt_chat)
                            chat_id = result_chat.scalar_one_or_none()
                            
                            if chat_id:
                                logger.info(
                                    f"Using fallback chat_id from MAX_Messenger_Data for admin {admin.id} "
                                    f"(max_user_id={admin.max_user_id})"
                                )
                        
                        if chat_id is None:
                            logger.error(
                                f"No MAX chat_id found for admin: admin_id={admin.id}, "
                                f"max_user_id={admin.max_user_id}"
                            )
                            continue
                        
                        # Send via MAX with keyboard
                        await max_bot.send_message(
                            chat_id=chat_id,
                            text=admin_message,
                            attachments=[ButtonsPayload(buttons=buttons).pack()]
                        )
                        stats["notifications_sent"] += 1
                        any_sent = True
                        notified_chat_ids.append(chat_id)
                        logger.info(
                            f"Admin notification sent via MAX for ticket {ticket.id}, "
                            f"admin_id={admin.id}"
                        )
                    
                except Exception as e:
                    logger.error(
                        f"Failed to send admin notification for ticket {ticket.id}, "
                        f"admin_id={admin.id}: {e}",
                        exc_info=True
                    )
        if ticket.file_attachments and notified_chat_ids:
            for chat_id in notified_chat_ids:
                try:
                    await _forward_ticket_attachments(
                        ticket,
                        chat_id,
                        max_bot,
                        session,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to forward attachments to admin chat %s "
                        "for invoice ticket %s: %s",
                        chat_id,
                        ticket.id,
                        e,
                        exc_info=True,
                    )

        return any_sent


async def _process_renewal_ticket(
    ticket: Ticket,
    max_bot,
    messenger_type: str,
    messenger_id: int,
    session: AsyncSession,
    stats: dict
) -> bool:
    """
    Process RENEWAL ticket - notify assigned manager.
    Supports MAX messenger only.
    
    Re-checks manager availability at the time of processing: if the originally
    assigned manager is now inactive or not working today, the backup chain is
    traversed and the ticket is reassigned before sending the notification.
    
    Returns True if at least one notification was sent successfully.
    """
    # Re-check manager availability if one was assigned
    if ticket.assigned_staff_id:
        from database.models import Staff_Member

        stmt_mgr = select(Staff_Member).where(Staff_Member.id == ticket.assigned_staff_id)
        result_mgr = await session.execute(stmt_mgr)
        current_manager = result_mgr.scalar_one_or_none()

        manager_available = (
            current_manager is not None
            and current_manager.is_active
            and current_manager.is_working_today
        )

        if not manager_available:
            logger.warning(
                f"Assigned manager for renewal ticket {ticket.id} is unavailable "
                f"(staff_id={ticket.assigned_staff_id}, "
                f"is_active={current_manager.is_active if current_manager else 'N/A'}, "
                f"is_working_today={current_manager.is_working_today if current_manager else 'N/A'}). "
                f"Re-running assignment via backup chain."
            )
            # Re-run the full backup chain to find an available manager
            from services.ticket_service import determine_assigned_manager
            new_staff_id, has_manager = await determine_assigned_manager(
                session=session,
                user_id=ticket.user_id,
                assign_admin_if_no_manager=True,
            )
            if new_staff_id:
                ticket.assigned_staff_id = new_staff_id
                await session.commit()
                logger.info(
                    f"Renewal ticket {ticket.id} reassigned: "
                    f"old_staff={ticket.assigned_staff_id}, new_staff={new_staff_id}, "
                    f"has_manager={has_manager}"
                )
            else:
                # No one available at all — fall through to admin notification below
                ticket.assigned_staff_id = None
                await session.commit()

    if not ticket.assigned_staff_id:
        logger.warning(
            f"Renewal ticket {ticket.id} has no assigned manager, notifying admins"
        )
        # Fallback: notify all admins
        from services.escalation_service import get_active_admins
        from database.models import MAX_Messenger_Data
        from sqlalchemy import select as sa_select

        admins = await get_active_admins(session)
        if not admins:
            logger.error(f"No admins available to notify for renewal ticket {ticket.id}")
            return False
        
        any_sent = False
        notified_chat_ids = []
        admin_message = (
            f"⚠️ <b>Заявка на продление без назначенного менеджера</b>\n\n"
            f"<b>Заявка:</b> #{ticket.id}\n"
            f"<b>Создана:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"<b>Тип:</b> Продление подписки\n\n"
            f"<b>Клиент:</b>\n"
            f"• ФИО: {ticket.user.full_name or 'Не указано'}\n"
            f"• Телефон: {ticket.user.phone_number or 'Не указан'}\n\n"
            f"❗️ <b>У клиента не назначен менеджер!</b>\n"
            f"Необходимо назначить менеджера для обработки заявки."
        )

        # Build keyboard with "К заявке" button
        from bots.max_bot.payloads import ManagerViewTicketPayload
        from maxapi.types.attachments.buttons import CallbackButton
        from maxapi.types.attachments.attachment import ButtonsPayload
        
        buttons = [[
            CallbackButton(
                text="📋 К заявке",
                payload=ManagerViewTicketPayload(ticket_id=ticket.id).pack()
            )
        ]]

        for admin in admins:
            try:
                if max_bot:
                    # Get MAX chat_id with fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
                    chat_id = admin.max_chat_id
                    
                    # Fallback to MAX_Messenger_Data if not in Staff_Member
                    if not chat_id and admin.max_user_id:
                        stmt_chat = sa_select(MAX_Messenger_Data.max_chat_id).where(
                            MAX_Messenger_Data.max_user_id == admin.max_user_id
                        )
                        result_chat = await session.execute(stmt_chat)
                        chat_id = result_chat.scalar_one_or_none()
                        
                        if chat_id:
                            logger.info(
                                f"Using fallback chat_id from MAX_Messenger_Data for admin {admin.id} "
                                f"(max_user_id={admin.max_user_id})"
                            )
                    
                    if chat_id:
                        await max_bot.send_message(
                            chat_id=chat_id,
                            text=admin_message,
                            attachments=[ButtonsPayload(buttons=buttons).pack()]
                        )
                        stats["notifications_sent"] += 1
                        any_sent = True
                        notified_chat_ids.append(chat_id)
                        logger.info(
                            f"Admin notified for unassigned renewal ticket {ticket.id}, "
                            f"admin_id={admin.id}"
                        )
            except Exception as e:
                logger.error(
                    f"Failed to notify admin for renewal ticket {ticket.id}, "
                    f"admin_id={admin.id}: {e}",
                    exc_info=True
                )
        if ticket.file_attachments and notified_chat_ids:
            for chat_id in notified_chat_ids:
                try:
                    await _forward_ticket_attachments(
                        ticket,
                        chat_id,
                        max_bot,
                        session,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to forward attachments to admin chat %s "
                        "for renewal ticket %s: %s",
                        chat_id,
                        ticket.id,
                        e,
                        exc_info=True,
                    )

        return any_sent

    notification_sent = await send_staff_notification(
        bot=max_bot,
        staff_id=ticket.assigned_staff_id,
        ticket=ticket,
        routing_info={
            "work_mode": "regular",
            "expected_response_time": "в течение рабочего дня",
            "from_queue": True  # Mark as from queue
        },
        session=session
    )
    
    if notification_sent:
        stats["notifications_sent"] += 1
        logger.info(
            f"Manager notification sent for renewal ticket {ticket.id}, "
            f"staff_id={ticket.assigned_staff_id}, messenger={messenger_type}"
        )

        if ticket.file_attachments:
            try:
                from bots.max_bot.utils.staff_chat_resolver import get_staff_chat_id

                staff_chat_id = await get_staff_chat_id(
                    session,
                    ticket.assigned_staff_id,
                )
                if staff_chat_id:
                    await _forward_ticket_attachments(
                        ticket,
                        staff_chat_id,
                        max_bot,
                        session,
                    )
            except Exception as e:
                logger.error(
                    "Failed to forward attachments for renewal ticket %s: %s",
                    ticket.id,
                    e,
                    exc_info=True,
                )
        
        # Schedule escalation monitoring now that working hours have started
        try:
            from celery_app.escalation_tasks import schedule_escalation_monitoring
            await schedule_escalation_monitoring(ticket_id=ticket.id)
            logger.info(
                f"Escalation monitoring scheduled for queued renewal ticket {ticket.id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to schedule escalation for queued renewal ticket {ticket.id}: {e}",
                exc_info=True
            )
    
    return notification_sent


async def _process_support_ticket(
    ticket: Ticket,
    max_bot,
    session: AsyncSession,
    stats: dict,
    work_mode: WorkMode = WorkMode.REGULAR,
) -> bool:
    """
    Process TECHNICAL_SUPPORT ticket created during non-working hours.

    In REGULAR mode, assigns the ticket through the existing round-robin.
    In EXTENDED mode, assigns it to the configured duty engineer. Falls back
    to admins when the recipient for the current mode is unavailable.
    Schedules escalation monitoring after successful notification.

    Returns True if at least one notification was sent successfully.
    """
    from database.models import MAX_Messenger_Data
    from services.escalation_service import get_active_admins
    from services.round_robin_service import get_next_support_staff
    from services.ticket_service import _get_duty_engineer
    from utils.timezone_helpers import get_moscow_now_naive

    # Calculate time since creation (for display in notification)
    elapsed = get_moscow_now_naive() - ticket.created_at
    minutes = int(elapsed.total_seconds() // 60)

    user_name = ticket.user.full_name if ticket.user else "Неизвестно"
    user_phone = ticket.user.phone_number if ticket.user else "Не указано"

    notification_text = (
        f"🛠 <b>Заявка ТП из очереди (нерабочее время)</b>\n\n"
        f"<b>Заявка:</b> #{ticket.id}\n"
        f"<b>Создана:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"<b>Клиент:</b> {user_name}\n"
        f"<b>Телефон:</b> {user_phone}\n"
    )

    if ticket.description:
        desc_preview = ticket.description[:150]
        if len(ticket.description) > 150:
            desc_preview += "..."
        notification_text += f"\n<b>Описание:</b>\n{desc_preview}\n"

    notification_text += (
        f"\n⏱ <b>Ожидала в очереди:</b> {minutes} мин\n"
        f"💬 <b>Клиенту сообщено:</b> \"Техподдержка ответит в ближайший рабочий период\"\n"
        f"⚠️ <b>Требуется взять заявку в работу</b>"
    )

    # Build keyboard with "К заявке" button
    from bots.max_bot.payloads import ManagerViewTicketPayload
    from maxapi.types.attachments.buttons import CallbackButton
    from maxapi.types.attachments.attachment import ButtonsPayload

    buttons = [[
        CallbackButton(
            text="📋 К заявке",
            payload=ManagerViewTicketPayload(ticket_id=ticket.id).pack()
        )
    ]]

    if work_mode == WorkMode.EXTENDED:
        recipient = await _get_duty_engineer(session)
        recipient_kind = "duty engineer"
    else:
        recipient = await get_next_support_staff(session)
        recipient_kind = "round-robin support specialist"
    no_staff_suffix = ""

    if recipient is None:
        # No support staff — fall back to ALL admins with reason
        logger.warning(
            f"No {recipient_kind} found for queued support ticket {ticket.id}, "
            f"falling back to admins"
        )
        admins = await get_active_admins(session)
        if not admins:
            logger.error(f"No admins available to notify for support ticket {ticket.id}")
            return False

        no_staff_suffix = (
            "\n\n⚠️ <b>Причина уведомления администратора:</b> "
            f"Не найден получатель для режима {work_mode.value}. "
            "Заявка требует ручного назначения."
        )

        # Notify all admins (no round-robin assignment — ticket stays unassigned)
        notified_chat_ids: list[int] = []
        for admin in admins:
            try:
                if max_bot:
                    chat_id = admin.max_chat_id
                    if not chat_id and admin.max_user_id:
                        stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                            MAX_Messenger_Data.max_user_id == admin.max_user_id
                        )
                        result_chat = await session.execute(stmt_chat)
                        chat_id = result_chat.scalar_one_or_none()
                    if chat_id:
                        await max_bot.send_message(
                            chat_id=chat_id,
                            text=notification_text + no_staff_suffix,
                            attachments=[ButtonsPayload(buttons=buttons).pack()]
                        )
                        stats["notifications_sent"] += 1
                        notified_chat_ids.append(chat_id)
                        logger.info(
                            f"Admin notified (no support staff) for queued support ticket "
                            f"{ticket.id}, admin_id={admin.id}"
                        )
            except Exception as e:
                logger.error(
                    f"Failed to notify admin {admin.id} for support ticket {ticket.id}: {e}",
                    exc_info=True,
                )

        if ticket.file_attachments and notified_chat_ids:
            for chat_id in notified_chat_ids:
                try:
                    await _forward_ticket_attachments(ticket, chat_id, max_bot, session)
                except Exception as e:
                    logger.error(
                        f"Failed to forward attachments to chat {chat_id} "
                        f"for support ticket {ticket.id}: {e}",
                        exc_info=True,
                    )

        if notified_chat_ids:
            try:
                from celery_app.escalation_tasks import schedule_technical_support_monitoring
                await schedule_technical_support_monitoring(ticket_id=ticket.id)
            except Exception as e:
                logger.error(
                    f"Failed to schedule escalation for queued support ticket {ticket.id}: {e}",
                    exc_info=True,
                )

        return bool(notified_chat_ids)

    # Persist the assignment
    ticket.assigned_staff_id = recipient.id
    await session.commit()

    notified_chat_ids = []

    try:
        if max_bot:
            # Get MAX chat_id with fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
            chat_id = recipient.max_chat_id

            if not chat_id and recipient.max_user_id:
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == recipient.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                chat_id = result_chat.scalar_one_or_none()

                if chat_id:
                    logger.info(
                        f"Using fallback chat_id from MAX_Messenger_Data for recipient {recipient.id} "
                        f"(max_user_id={recipient.max_user_id})"
                    )

            if chat_id:
                text = notification_text + no_staff_suffix
                await max_bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    attachments=[ButtonsPayload(buttons=buttons).pack()]
                )
                stats["notifications_sent"] += 1
                notified_chat_ids.append(chat_id)
                logger.info(
                    f"Recipient notified for queued support ticket {ticket.id}, "
                    f"recipient_id={recipient.id}"
                )
            else:
                logger.warning(
                    f"No MAX chat_id for recipient {recipient.id}, "
                    f"max_user_id={recipient.max_user_id}"
                )
    except Exception as e:
        logger.error(
            f"Failed to notify recipient {recipient.id} for support ticket {ticket.id}: {e}",
            exc_info=True
        )

    # Forward attachments to notified recipient
    if ticket.file_attachments and notified_chat_ids:
        for chat_id in notified_chat_ids:
            try:
                await _forward_ticket_attachments(ticket, chat_id, max_bot, session)
            except Exception as e:
                logger.error(
                    f"Failed to forward attachments to chat {chat_id} "
                    f"for support ticket {ticket.id}: {e}",
                    exc_info=True
                )

    # Schedule escalation monitoring now that working hours have started
    if notified_chat_ids:
        try:
            from celery_app.escalation_tasks import schedule_technical_support_monitoring
            await schedule_technical_support_monitoring(ticket_id=ticket.id)
            logger.info(
                f"Escalation monitoring scheduled for queued support ticket {ticket.id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to schedule escalation for queued support ticket {ticket.id}: {e}",
                exc_info=True
            )

    return bool(notified_chat_ids)


async def _process_consultation_ticket(
    ticket: Ticket,
    max_bot,
    session: AsyncSession,
    stats: dict,
    work_mode: WorkMode = WorkMode.REGULAR,
) -> bool:
    """
    Process CONSULTATION ticket created during non-working hours.

    In REGULAR mode, assigns the ticket through the existing round-robin.
    In EXTENDED mode, assigns it to the configured duty estimate specialist.
    Falls back to admins when the recipient for the current mode is unavailable.

    Returns True if at least one notification was sent successfully.
    """
    from database.models import MAX_Messenger_Data
    from services.escalation_service import get_active_admins
    from services.round_robin_service import get_next_consultation_specialist
    from services.ticket_service import _get_duty_estimate_specialist
    from utils.timezone_helpers import get_moscow_now_naive

    # Calculate time since creation (for display in notification)
    elapsed = get_moscow_now_naive() - ticket.created_at
    minutes = int(elapsed.total_seconds() // 60)

    user_name = ticket.user.full_name if ticket.user else "Неизвестно"
    user_phone = ticket.user.phone_number if ticket.user else "Не указано"

    notification_text = (
        f"💬 <b>Заявка на консультацию из очереди</b>\n\n"
        f"<b>Заявка:</b> #{ticket.id}\n"
        f"<b>Создана:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"<b>Клиент:</b> {user_name}\n"
        f"<b>Телефон:</b> {user_phone}\n"
    )

    if ticket.organization_inn:
        if ticket.organization and ticket.organization.organization_name:
            notification_text += f"<b>Организация:</b> {ticket.organization.organization_name} (ИНН: <code>{ticket.organization_inn}</code>)\n"
        else:
            notification_text += f"<b>Организация:</b> ИНН: <code>{ticket.organization_inn}</code> (название не указано)\n"

    if ticket.gs_keys:
        keys_text = ", ".join([key.key_number for key in ticket.gs_keys])
        notification_text += f"<b>Ключи ГС:</b> {keys_text}\n"

    if ticket.description:
        desc_preview = ticket.description[:150]
        if len(ticket.description) > 150:
            desc_preview += "..."
        notification_text += f"\n<b>Описание:</b>\n{desc_preview}\n"

    notification_text += (
        f"\n⏱ <b>Ожидала в очереди:</b> {minutes} мин\n"
        f"💬 <b>Клиенту сообщено:</b> \"Специалист ответит в ближайший рабочий период\"\n"
        f"⚠️ <b>Требуется взять заявку в работу</b>"
    )

    from bots.max_bot.payloads import ManagerViewTicketPayload
    from maxapi.types.attachments.buttons import CallbackButton
    from maxapi.types.attachments.attachment import ButtonsPayload

    buttons = [[
        CallbackButton(
            text="📋 К заявке",
            payload=ManagerViewTicketPayload(ticket_id=ticket.id).pack()
        )
    ]]

    if work_mode == WorkMode.EXTENDED:
        recipient = await _get_duty_estimate_specialist(session)
        recipient_kind = "duty estimate specialist"
    else:
        recipient = await get_next_consultation_specialist(session)
        recipient_kind = "round-robin consultation specialist"
    no_specialist_suffix = ""

    if recipient is None:
        # Fall back to ALL admins with reason
        logger.warning(
            f"No {recipient_kind} found for queued consultation ticket {ticket.id}, "
            f"falling back to admins"
        )
        admins = await get_active_admins(session)
        if not admins:
            logger.error(f"No admins available to notify for consultation ticket {ticket.id}")
            return False

        no_specialist_suffix = (
            "\n\n⚠️ <b>Причина уведомления администратора:</b> "
            f"Не найден получатель для режима {work_mode.value}. "
            "Заявка требует ручного назначения."
        )

        # Notify all admins (no round-robin assignment — ticket stays unassigned)
        notified_chat_ids: list[int] = []
        for admin in admins:
            try:
                if max_bot:
                    chat_id = admin.max_chat_id
                    if not chat_id and admin.max_user_id:
                        stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                            MAX_Messenger_Data.max_user_id == admin.max_user_id
                        )
                        result_chat = await session.execute(stmt_chat)
                        chat_id = result_chat.scalar_one_or_none()
                    if chat_id:
                        await max_bot.send_message(
                            chat_id=chat_id,
                            text=notification_text + no_specialist_suffix,
                            attachments=[ButtonsPayload(buttons=buttons).pack()]
                        )
                        stats["notifications_sent"] += 1
                        notified_chat_ids.append(chat_id)
                        logger.info(
                            f"Admin notified (no specialists) for queued consultation ticket "
                            f"{ticket.id}, admin_id={admin.id}"
                        )
            except Exception as e:
                logger.error(
                    f"Failed to notify admin {admin.id} for consultation ticket {ticket.id}: {e}",
                    exc_info=True,
                )

        if ticket.file_attachments and notified_chat_ids:
            for chat_id in notified_chat_ids:
                try:
                    await _forward_ticket_attachments(ticket, chat_id, max_bot, session)
                except Exception as e:
                    logger.error(
                        f"Failed to forward attachments to chat {chat_id} "
                        f"for consultation ticket {ticket.id}: {e}",
                        exc_info=True,
                    )

        if notified_chat_ids:
            try:
                from celery_app.escalation_tasks import schedule_technical_support_monitoring
                await schedule_technical_support_monitoring(ticket_id=ticket.id)
            except Exception as e:
                logger.error(
                    f"Failed to schedule escalation for queued consultation ticket {ticket.id}: {e}",
                    exc_info=True,
                )

        return bool(notified_chat_ids)

    # Persist the assignment
    ticket.assigned_staff_id = recipient.id
    await session.commit()

    notified_chat_ids = []

    try:
        if max_bot:
            # Get MAX chat_id with fallback: Staff_Member.max_chat_id → MAX_Messenger_Data
            chat_id = recipient.max_chat_id

            # Fallback to MAX_Messenger_Data if not in Staff_Member
            if not chat_id and recipient.max_user_id:
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == recipient.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                chat_id = result_chat.scalar_one_or_none()

                if chat_id:
                    logger.info(
                        f"Using fallback chat_id from MAX_Messenger_Data for recipient {recipient.id} "
                        f"(max_user_id={recipient.max_user_id})"
                    )

            if chat_id:
                text = notification_text + no_specialist_suffix
                await max_bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    attachments=[ButtonsPayload(buttons=buttons).pack()]
                )
                stats["notifications_sent"] += 1
                notified_chat_ids.append(chat_id)
                logger.info(
                    f"Recipient notified for queued consultation ticket {ticket.id}, "
                    f"recipient_id={recipient.id}"
                )
            else:
                logger.warning(
                    f"No MAX chat_id for recipient {recipient.id}, "
                    f"max_user_id={recipient.max_user_id}"
                )
    except Exception as e:
        logger.error(
            f"Failed to notify recipient {recipient.id} for consultation ticket {ticket.id}: {e}",
            exc_info=True
        )

    # Forward attachments to notified recipient
    if ticket.file_attachments and notified_chat_ids:
        for chat_id in notified_chat_ids:
            try:
                await _forward_ticket_attachments(ticket, chat_id, max_bot, session)
            except Exception as e:
                logger.error(
                    f"Failed to forward attachments to chat {chat_id} "
                    f"for consultation ticket {ticket.id}: {e}",
                    exc_info=True
                )

    # Schedule escalation monitoring now that working hours have started
    if notified_chat_ids:
        try:
            from celery_app.escalation_tasks import schedule_technical_support_monitoring
            await schedule_technical_support_monitoring(ticket_id=ticket.id)
            logger.info(
                f"Escalation monitoring scheduled for queued consultation ticket {ticket.id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to schedule escalation for queued consultation ticket {ticket.id}: {e}",
                exc_info=True
            )

    return bool(notified_chat_ids)
