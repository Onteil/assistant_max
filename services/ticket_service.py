"""
Ticket service layer for managing ticket-related database operations.

Provides async functions for ticket CRUD operations, manager assignment logic,
calendar-based work mode detection, routing logic, and staff notifications.

Requirements: 10.1-10.8, 11.1-11.5, 15.1-15.6
"""

import logging
from datetime import date, datetime, time
from typing import Any

from utils.timezone_helpers import get_moscow_now_naive, format_moscow_datetime

from aiogram import Bot
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    ActionType,
    Action_Log,
    Calendar_Rule,
    Manager_Assignment,
    Message,
    MessageType,
    SenderType,
    Staff_Member,
    StaffRole,
    SurveyType,
    Ticket,
    TicketStatus,
    TicketType,
    User,
    WorkMode,
    ticket_keys,
)
from services.validation_service import classify_file_type
from services.calendar_service import get_current_work_mode
from services.nps_service import schedule_survey

logger = logging.getLogger(__name__)


# ========== Ticket CRUD Operations ==========


async def create_ticket(
    session: AsyncSession,
    ticket_data: dict[str, Any]
) -> Ticket:
    """
    Create ticket record with associations.
    
    Args:
        session: Database session
        ticket_data: Dictionary containing ticket fields:
            - ticket_type (TicketType, required)
            - user_id (int, required) - Internal user ID (primary key)
            - assigned_staff_id (int, optional)
            - organization_inn (str, optional)
            - description (str, optional)
            - delivery_method (DeliveryMethod, optional)
            - delivery_email (str, optional)
            - selected_key_ids (list[int], optional) - for ticket_keys associations
    
    Returns:
        Created Ticket object
    
    Raises:
        ValueError: If required fields missing or user not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 10.1, 10.4, 10.5, 10.6
    """
    try:
        # Validate required fields
        if "ticket_type" not in ticket_data:
            raise ValueError("ticket_type is required")
        if "user_id" not in ticket_data:
            raise ValueError("user_id is required")
        
        # Create ticket
        ticket = Ticket(
            ticket_type=ticket_data["ticket_type"],
            ticket_status=TicketStatus.NEW,
            user_id=ticket_data["user_id"],
            assigned_staff_id=ticket_data.get("assigned_staff_id"),
            organization_inn=ticket_data.get("organization_inn"),
            description=ticket_data.get("description"),
            delivery_method=ticket_data.get("delivery_method"),
            delivery_email=ticket_data.get("delivery_email"),
            escalation_level=0
        )
        
        session.add(ticket)
        await session.flush()  # Get ticket.id
        
        # Create ticket_keys associations if provided
        selected_key_ids = ticket_data.get("selected_key_ids", [])
        if selected_key_ids:
            for key_id in selected_key_ids:
                await session.execute(
                    ticket_keys.insert().values(
                        ticket_id=ticket.id,
                        key_id=key_id,
                        added_at=get_moscow_now_naive()
                    )
                )
        
        # Log ticket creation
        await _log_action(
            session=session,
            action_type=ActionType.TICKET_CREATED,
            user_id=ticket.user_id,
            ticket_id=ticket.id,
            action_details={
                "ticket_type": ticket.ticket_type.value,
                "ticket_status": ticket.ticket_status.value,
                "assigned_staff_id": ticket.assigned_staff_id,
                "organization_inn": ticket.organization_inn,
                "key_count": len(selected_key_ids)
            }
        )
        
        # Log ticket creation to i-TAT audit API
        try:
            # Get user to extract max_user_id with eager loading of max_messenger_data
            from sqlalchemy.orm import selectinload
            user_stmt = select(User).where(User.id == ticket.user_id).options(
                selectinload(User.max_messenger_data)
            )
            user_result = await session.execute(user_stmt)
            user = user_result.scalar_one_or_none()
            
            if user and user.max_messenger_data:
                from bots.max_bot.utils.audit_logger import log_ticket_created
                await log_ticket_created(
                    ticket_id=f"TKT_{ticket.id}",
                    user_id=ticket.user_id,
                    ticket_type=ticket.ticket_type.value,
                    max_user_id=user.max_messenger_data.max_user_id
                )
        except Exception as audit_error:
            logger.error(f"Failed to log ticket creation to audit: {audit_error}")
            # Continue - don't fail ticket creation due to audit logging issues
        
        # Schedule escalation monitoring for NEW tickets
        # Requirements: FR-1.1.1, FR-1.1.2, NFR-2.2.1, TECH_SPEC 14.2
        # IMPORTANT: Do NOT schedule escalation in NON_WORKING mode
        if ticket.ticket_status == TicketStatus.NEW:
            try:
                # Check current work mode - escalation only in REGULAR/EXTENDED modes
                work_mode = await get_current_work_mode(session)
                
                if work_mode != WorkMode.NON_WORKING:
                    # Import here to avoid circular dependency
                    from celery_app.escalation_tasks import schedule_escalation_monitoring
                    
                    reminder_task_id, escalation_task_id = await schedule_escalation_monitoring(
                        ticket_id=ticket.id
                    )
                    
                    # Save task IDs to ticket in the same transaction
                    # Note: schedule_escalation_monitoring also saves them, but we ensure
                    # they're saved in this transaction for consistency
                    ticket.escalation_task_reminder_id = reminder_task_id
                    ticket.escalation_task_escalation_id = escalation_task_id
                    
                    logger.info(
                        f"Escalation monitoring scheduled: ticket_id={ticket.id}, "
                        f"work_mode={work_mode.value}, "
                        f"reminder_task_id={reminder_task_id}, "
                        f"escalation_task_id={escalation_task_id}"
                    )
                else:
                    # NON_WORKING mode - ticket queued, no escalation
                    logger.info(
                        f"Ticket {ticket.id} created in NON_WORKING mode - "
                        f"escalation not scheduled (will be processed in next working period)"
                    )
            
            except Exception as e:
                # NFR-2.2.1: Celery unavailability should not block ticket creation
                logger.error(
                    f"Failed to schedule escalation monitoring for ticket {ticket.id}: {e}",
                    exc_info=True
                )
                logger.warning(
                    f"Ticket {ticket.id} created without escalation monitoring. "
                    f"Manual intervention may be required."
                )
                # Continue - ticket is still created successfully
        
        # Refresh ticket with relationships for notification
        # This ensures user, gs_keys, and organization are loaded before returning
        await session.refresh(ticket, ["user", "gs_keys", "organization"])
        
        logger.info(
            f"Ticket created: id={ticket.id}, type={ticket.ticket_type.value}, "
            f"user_id={ticket.user_id}, assigned_staff={ticket.assigned_staff_id}"
        )
        
        return ticket
    
    except ValueError as e:
        logger.error(f"Validation error creating ticket: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error creating ticket: user_id={ticket_data.get('user_id')}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def determine_assigned_manager(
    session: AsyncSession,
    user_id: int,
    assign_admin_if_no_manager: bool = False
) -> tuple[int | None, bool]:
    """
    Determine assigned manager based on user's default_manager_id.
    
    Logic:
    1. Use user's default_manager_id
    2. If no manager found and assign_admin_if_no_manager=True, assign first active admin
    3. If no manager found and assign_admin_if_no_manager=False, return None
    
    Args:
        session: Database session
        user_id: Internal user ID (primary key)
        assign_admin_if_no_manager: If True, assign first active admin when no manager found
    
    Returns:
        Tuple of (Staff member ID or None, has_assigned_manager: bool)
        - Staff member ID: Internal staff ID or None if no staff assigned
        - has_assigned_manager: True if user had assigned manager, False if admin fallback used
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 10.2, 10.3
    """
    try:
        # Get user's default manager
        result = await session.execute(
            select(User.default_manager_id).where(User.id == user_id)
        )
        default_manager_id = result.scalar_one_or_none()
        
        if default_manager_id:
            logger.debug(
                f"Default manager found: user_id={user_id}, "
                f"manager_id={default_manager_id}"
            )
            return default_manager_id, True
        
        # No manager found - assign admin if requested
        if assign_admin_if_no_manager:
            from services.escalation_service import get_active_admins
            
            admins = await get_active_admins(session)
            if admins:
                # Assign first active admin
                assigned_admin_id = admins[0].id
                logger.info(
                    f"No manager found for user, assigning admin: user_id={user_id}, "
                    f"admin_id={assigned_admin_id}, admin_name={admins[0].full_name}"
                )
                return assigned_admin_id, False
            else:
                logger.error(
                    f"No manager and no active admins found for user: user_id={user_id}"
                )
                return None, False
        
        logger.warning(
            f"No manager found for user: user_id={user_id}"
        )
        return None, False
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error determining assigned manager: user_id={user_id}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def check_support_staff_availability(session: AsyncSession) -> bool:
    """
    Check if there are active support staff members available.
    
    Args:
        session: Database session
    
    Returns:
        True if support staff available, False otherwise
    
    Requirements: Support staff availability check
    """
    try:
        from database.models import Staff_Member, StaffRole
        
        stmt = select(Staff_Member).where(
            and_(
                Staff_Member.staff_role == StaffRole.TECHNICAL_SUPPORT,
                Staff_Member.is_active == True
            )
        )
        
        result = await session.execute(stmt)
        support_staff = result.scalars().first()
        
        has_support = support_staff is not None
        logger.debug(f"Support staff availability check: {has_support}")
        
        return has_support
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error checking support staff availability: error={e}",
            exc_info=True
        )
        return False



async def route_ticket(
    session: AsyncSession,
    ticket: Ticket,
    work_mode: WorkMode
) -> dict[str, Any]:
    """
    Route ticket based on type and work mode.
    
    Routing logic:
    - INVOICE tickets: Always route to assigned manager
    - RENEWAL tickets: Always route to assigned manager
    - TECHNICAL_SUPPORT tickets:
        - REGULAR mode: Route to support team group
        - EXTENDED mode: Route to duty engineer
        - NON_WORKING mode: Queue for next working period
    
    Args:
        session: Database session
        ticket: Ticket object to route
        work_mode: Current work mode
    
    Returns:
        Dictionary with routing information:
            - target_type: "manager" | "support_team" | "duty_engineer" | "queued"
            - target_id: Staff member ID or None
            - expected_response_time: Human-readable response time estimate
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 10.7, 10.8, 11.4, 11.5, 15.2, 15.3, 15.4, 15.6
    """
    try:
        routing_info = {
            "target_type": None,
            "target_id": None,
            "expected_response_time": None
        }
        
        # Route INVOICE and RENEWAL tickets to assigned manager
        if ticket.ticket_type in [TicketType.INVOICE, TicketType.RENEWAL]:
            routing_info["target_type"] = "manager"
            routing_info["target_id"] = ticket.assigned_staff_id
            
            if work_mode == WorkMode.REGULAR:
                routing_info["expected_response_time"] = "в течение рабочего дня"
            elif work_mode == WorkMode.EXTENDED:
                routing_info["expected_response_time"] = "в расширенные часы работы"
            else:
                routing_info["expected_response_time"] = "в следующий рабочий день"
            
            logger.debug(
                f"Ticket routed to manager: ticket_id={ticket.id}, "
                f"type={ticket.ticket_type.value}, manager_id={ticket.assigned_staff_id}"
            )
        
        # Route TECHNICAL_SUPPORT tickets based on work mode
        elif ticket.ticket_type == TicketType.TECHNICAL_SUPPORT:
            if work_mode == WorkMode.REGULAR:
                # Route to support team group
                routing_info["target_type"] = "support_team"
                routing_info["target_id"] = None  # Group chat, not individual
                routing_info["expected_response_time"] = "в течение 2 часов"
                
                logger.debug(
                    f"Ticket routed to support team: ticket_id={ticket.id}, "
                    f"work_mode={work_mode.value}"
                )
            
            elif work_mode == WorkMode.EXTENDED:
                # Route to duty engineer
                duty_engineer = await _get_duty_engineer(session)
                routing_info["target_type"] = "duty_engineer"
                routing_info["target_id"] = duty_engineer.tg_user_id if duty_engineer else None
                routing_info["expected_response_time"] = "в течение 4 часов"
                
                logger.debug(
                    f"Ticket routed to duty engineer: ticket_id={ticket.id}, "
                    f"work_mode={work_mode.value}, engineer_id={routing_info['target_id']}"
                )
            
            else:  # NON_WORKING
                # Queue for next working period
                routing_info["target_type"] = "queued"
                routing_info["target_id"] = None
                routing_info["expected_response_time"] = "в следующий рабочий день"
                
                logger.debug(
                    f"Ticket queued for next working period: ticket_id={ticket.id}, "
                    f"work_mode={work_mode.value}"
                )
        
        return routing_info
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error routing ticket: ticket_id={ticket.id}, error={e}",
            exc_info=True
        )
        raise


async def send_staff_notification(
    bot: Bot,
    staff_id: int,
    ticket: Ticket,
    routing_info: dict[str, Any] | None = None,
    session: AsyncSession | None = None
) -> bool:
    """
    Send notification to staff member about new ticket (supports both Telegram and MAX).
    
    Args:
        bot: Bot instance (Aiogram Bot or maxapi Bot)
        staff_id: Staff member internal ID (from staff_members table)
        ticket: Ticket object (should have user and gs_keys relationships loaded)
        routing_info: Optional routing information for context
        session: Optional database session (if not provided, creates new one)
    
    Returns:
        True if notification sent successfully, False otherwise
    
    Requirements: 10.8, 15.6
    
    Note: Caller should ensure ticket.user and ticket.gs_keys are loaded before calling.
    """
    from database.models import Staff_Member, MAX_Messenger_Data
    from sqlalchemy import select
    from constants import get_session
    from maxapi.enums.parse_mode import ParseMode
    
    try:
        # Determine bot type by checking class name
        is_max_bot = bot.__class__.__name__ == 'Bot' and hasattr(bot, 'api_url')
        
        # Get staff member to retrieve messenger ID
        if session:
            stmt = select(Staff_Member).where(Staff_Member.id == staff_id)
            result = await session.execute(stmt)
            staff = result.scalar_one_or_none()
        else:
            async with get_session() as new_session:
                stmt = select(Staff_Member).where(Staff_Member.id == staff_id)
                result = await new_session.execute(stmt)
                staff = result.scalar_one_or_none()
        
        if not staff:
            logger.error(f"Staff member not found: staff_id={staff_id}")
            return False
        
        # Determine which messenger to use and get appropriate chat ID
        messenger_id = None
        chat_id = None
        
        if is_max_bot:
            # MAX bot: use max_user_id and query for chat_id
            if not staff.max_user_id:
                logger.error(
                    f"Staff member has no MAX user ID: staff_id={staff_id}, "
                    f"staff_name={staff.full_name}"
                )
                return False
            
            messenger_id = staff.max_user_id
            
            # Query MAX_Messenger_Data for chat_id
            if session:
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == staff.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                chat_id = result_chat.scalar_one_or_none()
            else:
                async with get_session() as new_session:
                    stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                        MAX_Messenger_Data.max_user_id == staff.max_user_id
                    )
                    result_chat = await new_session.execute(stmt_chat)
                    chat_id = result_chat.scalar_one_or_none()
            
            if not chat_id:
                logger.error(
                    f"No MAX chat_id found for staff member: staff_id={staff_id}, "
                    f"max_user_id={staff.max_user_id}, staff_name={staff.full_name}"
                )
                return False
        else:
            # Telegram bot: use tg_user_id directly as chat_id
            if not staff.tg_user_id:
                logger.error(
                    f"Staff member has no Telegram user ID: staff_id={staff_id}, "
                    f"staff_name={staff.full_name}"
                )
                return False
            
            messenger_id = staff.tg_user_id
            chat_id = staff.tg_user_id
        
        # Build notification message
        ticket_type_names = {
            TicketType.INVOICE: "📄 Запрос счета",
            TicketType.TECHNICAL_SUPPORT: "🔧 Техническая поддержка",
            TicketType.RENEWAL: "🔄 Продление подписки"
        }
        
        # Format created_at as Moscow time (already stored in Moscow timezone)
        created_at_str = format_moscow_datetime(ticket.created_at)
        
        # Check if this is a queued ticket (sent from queue task)
        from_queue = routing_info and routing_info.get("from_queue", False)
        
        # Build formatted message with emoji and structured lists
        if from_queue:
            message_text = f"🔔 <b>Новое обращение #{ticket.id}</b>\n"
            message_text += f"⚠️ <b>ЗАЯВКА ИЗ ОЧЕРЕДИ</b> (создана в нерабочее время)\n\n"
        else:
            message_text = f"🔔 <b>Новое обращение #{ticket.id}</b>\n\n"
        
        # Ticket type with emoji
        message_text += f"📋 <b>Тип:</b> {ticket_type_names.get(ticket.ticket_type, ticket.ticket_type.value)}\n"
        
        # User information
        message_text += f"👤 <b>От пользователя:</b> {ticket.user.full_name or ticket.user.phone_number}\n"
        message_text += f"🆔 <b>ID пользователя:</b> <code>{ticket.user.tg_user_id or ticket.user.max_user_id}</code>\n"
        
        # Organization(s) - formatted as numbered list if multiple
        if ticket.organization_inn:
            # Check if there are multiple organizations (comma-separated)
            orgs = [org.strip() for org in ticket.organization_inn.split(',') if org.strip()]
            if len(orgs) > 1:
                message_text += f"\n🏢 <b>Организации:</b>\n"
                for idx, org in enumerate(orgs, 1):
                    message_text += f"   {idx}. <code>{org}</code>\n"
            else:
                message_text += f"\n🏢 <b>Организация:</b> <code>{ticket.organization_inn}</code>\n"
        
        # GS Keys - formatted as numbered list
        try:
            if ticket.gs_keys and len(ticket.gs_keys) > 0:
                if len(ticket.gs_keys) > 1:
                    message_text += f"🔑 <b>Ключи ГС:</b>\n"
                    for idx, key in enumerate(ticket.gs_keys, 1):
                        message_text += f"   {idx}. <code>{key.key_number}</code>\n"
                else:
                    message_text += f"🔑 <b>Ключ ГС:</b> <code>{ticket.gs_keys[0].key_number}</code>\n"
        except Exception as e:
            logger.warning(f"Failed to access gs_keys for ticket {ticket.id}: {e}")
        
        # Email if present
        try:
            if hasattr(ticket.user, 'email') and ticket.user.email:
                message_text += f"📧 <b>Email:</b> {ticket.user.email}\n"
        except Exception as e:
            logger.warning(f"Failed to access user email for ticket {ticket.id}: {e}")
        
        # Created timestamp
        message_text += f"\n📅 <b>Дата создания:</b> {created_at_str}\n"
        
        # Delivery method
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
            message_text += f"📦 <b>Способ получения:</b> {delivery_method_text}\n"
            
            # Add delivery email if method is email
            if (ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method)) == "email":
                if hasattr(ticket, 'delivery_email') and ticket.delivery_email:
                    message_text += f"   └─ <b>Email для доставки:</b> {ticket.delivery_email}\n"
        
        # Description
        if ticket.description:
            # Truncate long descriptions
            description = ticket.description[:200]
            if len(ticket.description) > 200:
                description += "..."
            message_text += f"\n📝 <b>Описание:</b>\n{description}\n"
        else:
            message_text += f"\n📝 <b>Описание:</b> <i>Без описания</i>\n"
        
        # Add user expectation context for queued tickets
        if from_queue:
            message_text += f"\n💬 <b>Клиенту сообщено:</b> "
            if ticket.ticket_type == TicketType.INVOICE:
                message_text += f"\"Ваш менеджер увидит запрос первым делом в начале рабочего дня\"\n"
            elif ticket.ticket_type == TicketType.TECHNICAL_SUPPORT:
                message_text += f"\"Техподдержка ответит в начале рабочего дня\"\n"
            elif ticket.ticket_type == TicketType.RENEWAL:
                message_text += f"\"Менеджер свяжется с вами в начале рабочего дня\"\n"
        
        if routing_info and routing_info.get("expected_response_time"):
            message_text += f"\n⏱ <b>Ожидаемое время ответа:</b> {routing_info['expected_response_time']}"
        
        # Build keyboard with "К заявке" button for MAX bot
        if is_max_bot:
            from bots.max_bot.payloads import ManagerViewTicketPayload
            from maxapi.types.attachments.buttons import CallbackButton
            from maxapi.types.attachments.attachment import ButtonsPayload
            
            buttons = [[
                CallbackButton(
                    text="📋 К заявке",
                    payload=ManagerViewTicketPayload(ticket_id=ticket.id).pack()
                )
            ]]
            
            # Send notification with keyboard
            await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode=ParseMode.HTML,
                attachments=[ButtonsPayload(buttons=buttons).pack()]
            )
        else:
            # Telegram bot or MAX without keyboard
            await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode=ParseMode.HTML
            )
        
        logger.info(
            f"Staff notification sent: ticket_id={ticket.id}, staff_id={staff_id}, "
            f"messenger_id={messenger_id}, chat_id={chat_id}"
        )
        return True
    
    except Exception as e:
        logger.error(
            f"Error sending staff notification: ticket_id={ticket.id}, "
            f"staff_id={staff_id}, error={e}",
            exc_info=True
        )
        return False


async def send_employee_ticket_notification(
    bot: Bot,
    session: AsyncSession,
    employee_id: int,
    ticket: Ticket,
    is_transfer: bool = False,
    source_employee_name: str | None = None
) -> bool:
    """
    Send employee interface notification with full ticket card and action buttons.
    
    This function sends a notification to an employee when a new ticket is assigned
    or when a ticket is transferred to them. The notification includes the full
    ticket card with inline action buttons for immediate interaction.
    
    Args:
        bot: Aiogram Bot instance
        session: Database session
        employee_id: Employee's Telegram ID
        ticket: Ticket object
        is_transfer: True if this is a transfer notification, False for new assignment
        source_employee_name: Name of employee who transferred the ticket (optional)
    
    Returns:
        True if notification sent successfully, False otherwise
    
    Requirements: 10.6, 18.2, 18.4
    """
    try:
        from services.employee_service import format_ticket_card, get_ticket_action_keyboard
        
        # Format ticket card
        ticket_card_text = await format_ticket_card(ticket, session)
        
        # Add notification header
        if is_transfer:
            if source_employee_name:
                header = f"🔄 <b>Заявка #{ticket.id} передана вам от {source_employee_name}</b>\n\n"
            else:
                header = f"🔄 <b>Заявка #{ticket.id} передана вам</b>\n\n"
        else:
            header = f"🔔 <b>Новый тикет #{ticket.id} назначен вам</b>\n\n"
        
        message_text = header + ticket_card_text
        
        # Get action keyboard
        keyboard = await get_ticket_action_keyboard(ticket)
        
        # Send notification with ticket card and action buttons
        await bot.send_message(
            chat_id=employee_id,
            text=message_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        logger.info(
            f"Employee ticket notification sent: ticket_id={ticket.id}, "
            f"employee_id={employee_id}, is_transfer={is_transfer}"
        )
        return True
    
    except Exception as e:
        logger.error(
            f"Error sending employee ticket notification: ticket_id={ticket.id}, "
            f"employee_id={employee_id}, is_transfer={is_transfer}, error={e}",
            exc_info=True
        )
        return False


async def send_new_ticket_assignment_notification(
    bot: Bot,
    session: AsyncSession,
    employee_id: int,
    ticket: Ticket
) -> bool:
    """
    Send notification to employee when a new ticket is assigned to them.
    
    Sends a notification with the full ticket card and action buttons,
    allowing the employee to immediately take action on the new ticket.
    
    Args:
        bot: Aiogram Bot instance
        session: Database session
        employee_id: Employee's Telegram ID
        ticket: Ticket object
    
    Returns:
        True if notification sent successfully, False otherwise
    
    Requirements: 10.6, 18.2
    """
    return await send_employee_ticket_notification(
        bot=bot,
        session=session,
        employee_id=employee_id,
        ticket=ticket,
        is_transfer=False
    )


async def send_ticket_transfer_notification(
    bot: Bot,
    session: AsyncSession,
    target_employee_id: int,
    ticket: Ticket,
    source_employee_id: int | None = None
) -> bool:
    """
    Send notification to employee when a ticket is transferred to them.
    
    Sends a notification with the full ticket card, action buttons, and
    indication that the ticket was transferred from another employee.
    
    Args:
        bot: Aiogram Bot instance
        session: Database session
        target_employee_id: Target employee's Telegram ID
        ticket: Ticket object
        source_employee_id: Source employee's Telegram ID (optional)
    
    Returns:
        True if notification sent successfully, False otherwise
    
    Requirements: 18.3, 18.4
    """
    try:
        # Get source employee name if provided
        source_employee_name = None
        if source_employee_id:
            result = await session.execute(
                select(Staff_Member.full_name).where(
                    Staff_Member.tg_user_id == source_employee_id
                )
            )
            source_employee_name = result.scalar_one_or_none()
        
        return await send_employee_ticket_notification(
            bot=bot,
            session=session,
            employee_id=target_employee_id,
            ticket=ticket,
            is_transfer=True,
            source_employee_name=source_employee_name
        )
    
    except Exception as e:
        logger.error(
            f"Error sending ticket transfer notification: ticket_id={ticket.id}, "
            f"target_employee_id={target_employee_id}, "
            f"source_employee_id={source_employee_id}, error={e}",
            exc_info=True
        )
        return False


async def add_ticket_message(
    session: AsyncSession,
    ticket_id: int,
    sender_type: SenderType,
    sender_id: int | None,
    message_text: str,
    message_type: MessageType = MessageType.TEXT
) -> Message:
    """
    Create message record in ticket conversation.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
        sender_type: Type of sender (USER, STAFF, SYSTEM)
        sender_id: Sender's Telegram ID (optional for SYSTEM messages)
        message_text: Message content
        message_type: Type of message (default: TEXT)
    
    Returns:
        Created Message object
    
    Raises:
        ValueError: If ticket not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
    """
    try:
        # Verify ticket exists
        result = await session.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found for message addition: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Create message
        message = Message(
            ticket_id=ticket_id,
            sender_type=sender_type,
            sender_id=sender_id,
            message_text=message_text,
            message_type=message_type,
            sent_at=get_moscow_now_naive()
        )
        
        session.add(message)
        await session.flush()
        
        logger.debug(
            f"Message added to ticket: ticket_id={ticket_id}, message_id={message.id}, "
            f"sender_type={sender_type.value}"
        )
        
        return message
    
    except ValueError as e:
        logger.error(f"Validation error adding ticket message: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error adding ticket message: ticket_id={ticket_id}, error={e}",
            exc_info=True
        )
        raise


# ========== Employee Ticket Operations ==========


async def take_ticket_into_work(
    session: AsyncSession,
    ticket_id: int,
    employee_id: int,
    messenger: str = "telegram"
) -> Ticket:
    """
    Take ticket into work.
    
    Changes ticket status from NEW to IN_PROGRESS, stops escalation timer,
    and logs the action. For TECHNICAL_SUPPORT tickets without assigned staff,
    assigns the ticket to the staff member taking it.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
        employee_id: Employee's messenger user ID (Telegram or MAX)
        messenger: Messenger type ("telegram" or "max")
    
    Returns:
        Updated Ticket object
    
    Raises:
        ValueError: If ticket not found, staff not found, or invalid status
        SQLAlchemyError: If database operation fails
    
    Requirements: 3.4, 4.1, 12.2
    """
    try:
        # Get ticket
        result = await session.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Get staff member by messenger user ID to get internal staff ID
        from database.models import Staff_Member
        if messenger == "telegram":
            staff_stmt = select(Staff_Member).where(Staff_Member.tg_user_id == employee_id)
        else:  # max
            staff_stmt = select(Staff_Member).where(Staff_Member.max_user_id == employee_id)
        
        staff_result = await session.execute(staff_stmt)
        staff_member = staff_result.scalar_one_or_none()
        
        if not staff_member:
            error_msg = f"Staff member not found: messenger={messenger}, user_id={employee_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Update ticket status, assign staff (for TECHNICAL_SUPPORT only), and stop escalation timer
        old_status = ticket.ticket_status
        old_assigned_staff_id = ticket.assigned_staff_id
        ticket.ticket_status = TicketStatus.IN_PROGRESS
        
        # For TECHNICAL_SUPPORT tickets, assign to staff member when they take it
        # For other ticket types (INVOICE, RENEWAL), assigned_staff_id is already set at creation
        if ticket.ticket_type == TicketType.TECHNICAL_SUPPORT and not ticket.assigned_staff_id:
            ticket.assigned_staff_id = staff_member.id
        
        ticket.escalated_at = None
        ticket.updated_at = datetime.utcnow()
        
        # Cancel escalation monitoring tasks
        try:
            # Import here to avoid circular dependency
            from celery_app.escalation_tasks import cancel_escalation_monitoring
            
            await cancel_escalation_monitoring(ticket_id)
            logger.info(f"Escalation monitoring cancelled: ticket_id={ticket_id}")
        except Exception as e:
            logger.warning(
                f"Failed to cancel escalation monitoring: ticket_id={ticket_id}, error={e}"
            )
            # Don't fail the operation if cancellation fails
        
        # Log action using internal staff ID
        action_details = {
            "old_status": old_status.value,
            "new_status": TicketStatus.IN_PROGRESS.value,
            "action": "take_into_work",
            "messenger": messenger,
            "messenger_user_id": employee_id
        }
        
        # Include assignment info if ticket was assigned
        if old_assigned_staff_id != ticket.assigned_staff_id:
            action_details["old_assigned_staff_id"] = old_assigned_staff_id
            action_details["new_assigned_staff_id"] = ticket.assigned_staff_id
        
        await _log_action(
            session=session,
            action_type=ActionType.TICKET_ASSIGNED,
            ticket_id=ticket_id,
            staff_id=staff_member.id,  # Use internal staff ID, not messenger user ID
            action_details=action_details
        )
        
        # Log status change to I-TAT API
        try:
            from bots.max_bot.utils.itat_logging import log_ticket_assignment_to_itat
            await log_ticket_assignment_to_itat(
                session=session,
                ticket=ticket,
                staff_id=staff_member.id,
                action="taken"
            )
        except Exception as e:
            # Log error but don't fail the operation
            logger.error(
                f"Failed to log ticket assignment to I-TAT API: ticket_id={ticket_id}, error={e}",
                exc_info=True
            )
        
        # Log with assignment info if changed
        log_msg = (
            f"Ticket taken into work: ticket_id={ticket_id}, staff_id={staff_member.id}, "
            f"messenger={messenger}, messenger_user_id={employee_id}, old_status={old_status.value}"
        )
        if old_assigned_staff_id != ticket.assigned_staff_id:
            log_msg += f", assigned_staff_id={ticket.assigned_staff_id} (was {old_assigned_staff_id})"
        
        logger.info(log_msg)
        
        return ticket
    
    except ValueError as e:
        logger.error(f"Validation error taking ticket into work: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error taking ticket into work: ticket_id={ticket_id}, "
            f"employee_id={employee_id}, error={e}",
            exc_info=True
        )
        raise


async def set_ticket_waiting_client(
    session: AsyncSession,
    ticket_id: int,
    employee_id: int,
    messenger: str = "telegram"
) -> Ticket:
    """
    Set ticket status to WAITING_CLIENT.
    
    Changes ticket status to WAITING_CLIENT and logs the action.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
        employee_id: Employee's messenger user ID
        messenger: Messenger type ("telegram" or "max")
    
    Returns:
        Updated Ticket object
    
    Raises:
        ValueError: If ticket not found or staff not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 3.6
    """
    try:
        # Get ticket with eager loading
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys)
            )
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Get internal staff ID
        staff_id = await _get_staff_internal_id(session, employee_id, messenger)
        
        # Update ticket status
        old_status = ticket.ticket_status
        ticket.ticket_status = TicketStatus.WAITING_CLIENT
        ticket.updated_at = datetime.utcnow()
        
        # Log action
        await _log_action(
            session=session,
            action_type=ActionType.STATUS_CHANGED,
            ticket_id=ticket_id,
            staff_id=staff_id,
            action_details={
                "old_status": old_status.value,
                "new_status": TicketStatus.WAITING_CLIENT.value
            }
        )
        
        # Log status change to I-TAT API
        try:
            from bots.max_bot.utils.itat_logging import log_ticket_status_change_to_itat
            await log_ticket_status_change_to_itat(
                session=session,
                ticket=ticket,
                old_status=old_status,
                new_status=TicketStatus.WAITING_CLIENT,
                staff_id=staff_id,
                comment="Заявка переведена в статус 'Ожидание клиента'"
            )
        except Exception as e:
            # Log error but don't fail the operation
            logger.error(
                f"Failed to log status change to I-TAT API: ticket_id={ticket_id}, error={e}",
                exc_info=True
            )
        
        logger.info(
            f"Ticket status changed to WAITING_CLIENT: ticket_id={ticket_id}, "
            f"employee_id={employee_id}, old_status={old_status.value}"
        )
        
        return ticket
    
    except ValueError as e:
        logger.error(f"Validation error setting ticket waiting client: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error setting ticket waiting client: ticket_id={ticket_id}, "
            f"employee_id={employee_id}, error={e}",
            exc_info=True
        )
        raise


async def close_ticket(
    session: AsyncSession,
    ticket_id: int,
    employee_id: int,
    final_comment: str,
    messenger: str = "telegram"
) -> Ticket:
    """
    Close ticket with final comment.
    
    Stores final comment as a message, changes status to CLOSED,
    sets closed_at timestamp, and logs the action.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
        employee_id: Employee's messenger user ID
        final_comment: Final comment text
        messenger: Messenger type ("telegram" or "max")
    
    Returns:
        Updated Ticket object
    
    Raises:
        ValueError: If ticket not found or staff not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 3.5, 7.3, 14.2
    """
    try:
        # Get ticket
        result = await session.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Get internal staff ID
        staff_id = await _get_staff_internal_id(session, employee_id, messenger)
        
        # Store final comment as message
        await add_ticket_message(
            session=session,
            ticket_id=ticket_id,
            sender_type=SenderType.STAFF,
            sender_id=employee_id,
            message_text=final_comment,
            message_type=MessageType.TEXT
        )
        
        # Update ticket status and set closed_at
        old_status = ticket.ticket_status
        ticket.ticket_status = TicketStatus.CLOSED
        ticket.closed_at = datetime.utcnow()
        ticket.updated_at = datetime.utcnow()
        
        # Log action
        await _log_action(
            session=session,
            action_type=ActionType.TICKET_CLOSED,
            ticket_id=ticket_id,
            staff_id=staff_id,
            action_details={
                "old_status": old_status.value,
                "final_comment_length": len(final_comment)
            }
        )
        
        # Log status change to I-TAT API
        try:
            from bots.max_bot.utils.itat_logging import log_ticket_status_change_to_itat
            await log_ticket_status_change_to_itat(
                session=session,
                ticket=ticket,
                old_status=old_status,
                new_status=TicketStatus.CLOSED,
                staff_id=staff_id,
                comment=f"Заявка закрыта. Финальный комментарий: {final_comment[:100]}{'...' if len(final_comment) > 100 else ''}"
            )
        except Exception as e:
            # Log error but don't fail the operation
            logger.error(
                f"Failed to log ticket closure to I-TAT API: ticket_id={ticket_id}, error={e}",
                exc_info=True
            )
        
        logger.info(
            f"Ticket closed: ticket_id={ticket_id}, employee_id={employee_id}, "
            f"old_status={old_status.value}"
        )
        
        # Trigger NPS survey for TECH_SUPPORT tickets
        if ticket.ticket_type == TicketType.TECHNICAL_SUPPORT:
            try:
                # Check if survey already scheduled for this ticket (duplicate prevention)
                from database.models import NPS_Response
                existing_survey = await session.execute(
                    select(NPS_Response).where(
                        and_(
                            NPS_Response.trigger_event_id == ticket_id,
                            NPS_Response.survey_type == SurveyType.SERVICE_QUALITY
                        )
                    )
                )
                if existing_survey.scalar_one_or_none() is None:
                    # No existing survey, schedule new one
                    scheduled, reason = await schedule_survey(
                        session=session,
                        user_id=ticket.user_id,
                        survey_type=SurveyType.SERVICE_QUALITY,
                        trigger_event_id=ticket_id,
                        event_date=ticket.closed_at
                    )
                    
                    if scheduled:
                        logger.info(
                            f"NPS survey scheduled for closed ticket: ticket_id={ticket_id}, "
                            f"user_id={ticket.user_id}"
                        )
                    else:
                        logger.info(
                            f"NPS survey suppressed for closed ticket: ticket_id={ticket_id}, "
                            f"user_id={ticket.user_id}, reason={reason}"
                        )
                else:
                    logger.info(
                        f"NPS survey already exists for ticket: ticket_id={ticket_id}, "
                        f"skipping duplicate"
                    )
            except Exception as e:
                # Log error but don't fail ticket closure
                logger.error(
                    f"Error scheduling NPS survey for ticket: ticket_id={ticket_id}, "
                    f"user_id={ticket.user_id}, error={e}",
                    exc_info=True
                )
        
        return ticket
    
    except ValueError as e:
        logger.error(f"Validation error closing ticket: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error closing ticket: ticket_id={ticket_id}, "
            f"employee_id={employee_id}, error={e}",
            exc_info=True
        )
        raise


async def close_ticket_with_notification(
    session: AsyncSession,
    ticket_id: int,
    employee_id: int,
    final_comment: str,
    messenger_adapter,
    file_id: str | None = None,
    file_type: Any | None = None,
    max_media_type: str | None = None,
    messenger: str = "max"
) -> Ticket:
    """
    Close ticket with final comment and send notification to client.
    
    This function combines ticket closure with client notification.
    It sends the final comment to the client first, then closes the ticket.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
        employee_id: Employee's messenger user ID
        final_comment: Final comment text
        messenger_adapter: Messenger adapter for sending notifications
        file_id: Optional file URL/ID for attachments
        file_type: Optional file type enum
        max_media_type: Optional MAX media type (image, file, voice, video, audio)
        messenger: Messenger type ("telegram" or "max")
    
    Returns:
        Updated Ticket object
    
    Raises:
        ValueError: If ticket not found or staff not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 3.5, 7.3, 14.2
    """
    try:
        # Get ticket with user data for notification
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user).selectinload(User.max_messenger_data)
            )
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Get internal staff ID
        staff_id = await _get_staff_internal_id(session, employee_id, messenger)
        
        # Send final comment to client with closure notification
        if ticket.user.max_messenger_data:
            try:
                # Format closure notification message
                closure_message = f"✅ <b>Заявка #{ticket_id} закрыта</b>\n\n{final_comment}"
                
                # Send final comment to client via MAX
                await send_message_to_client_max(
                    messenger_adapter=messenger_adapter,
                    session=session,
                    ticket_id=ticket_id,
                    employee_id=staff_id,  # Use internal staff ID
                    message_text=closure_message,
                    file_id=file_id,
                    file_type=file_type,
                    max_media_type=max_media_type,
                    messenger=messenger,
                    include_reply_button=False  # No reply button for final comments
                )
                
                logger.info(
                    f"Final comment sent to client: ticket_id={ticket_id}, "
                    f"employee_id={employee_id}, has_file={bool(file_id)}"
                )
            
            except Exception as e:
                logger.error(
                    f"Failed to send final comment to client: ticket_id={ticket_id}, "
                    f"employee_id={employee_id}, error={e}",
                    exc_info=True
                )
                # Continue with ticket closure even if notification fails
        else:
            logger.warning(
                f"Client has no MAX messenger data, skipping notification: "
                f"ticket_id={ticket_id}, user_id={ticket.user.id}"
            )
        
        # Store final comment as message in database
        await add_ticket_message(
            session=session,
            ticket_id=ticket_id,
            sender_type=SenderType.STAFF,
            sender_id=employee_id,
            message_text=final_comment,
            message_type=MessageType.DOCUMENT if file_id else MessageType.TEXT
        )
        
        # Update ticket status and set closed_at
        old_status = ticket.ticket_status
        ticket.ticket_status = TicketStatus.CLOSED
        ticket.closed_at = datetime.utcnow()
        ticket.updated_at = datetime.utcnow()
        
        # Log action
        await _log_action(
            session=session,
            action_type=ActionType.TICKET_CLOSED,
            ticket_id=ticket_id,
            staff_id=staff_id,
            action_details={
                "old_status": old_status.value,
                "final_comment_length": len(final_comment),
                "has_attachment": bool(file_id),
                "notification_sent": bool(ticket.user.max_messenger_data)
            }
        )
        
        # Log status change to I-TAT API
        try:
            from bots.max_bot.utils.itat_logging import log_ticket_status_change_to_itat
            await log_ticket_status_change_to_itat(
                session=session,
                ticket=ticket,
                old_status=old_status,
                new_status=TicketStatus.CLOSED,
                staff_id=staff_id,
                comment=f"Заявка закрыта с уведомлением клиента. Финальный комментарий: {final_comment[:100]}{'...' if len(final_comment) > 100 else ''}"
            )
        except Exception as e:
            # Log error but don't fail the operation
            logger.error(
                f"Failed to log ticket closure to I-TAT API: ticket_id={ticket_id}, error={e}",
                exc_info=True
            )
        
        logger.info(
            f"Ticket closed with notification: ticket_id={ticket_id}, "
            f"employee_id={employee_id}, old_status={old_status.value}"
        )
        
        # Trigger NPS survey for TECH_SUPPORT tickets
        if ticket.ticket_type == TicketType.TECHNICAL_SUPPORT:
            try:
                # Check if survey already scheduled for this ticket (duplicate prevention)
                from database.models import NPS_Response
                existing_survey = await session.execute(
                    select(NPS_Response).where(
                        and_(
                            NPS_Response.trigger_event_id == ticket_id,
                            NPS_Response.survey_type == SurveyType.SERVICE_QUALITY
                        )
                    )
                )
                if existing_survey.scalar_one_or_none() is None:
                    # No existing survey, schedule new one
                    scheduled, reason = await schedule_survey(
                        session=session,
                        user_id=ticket.user_id,
                        survey_type=SurveyType.SERVICE_QUALITY,
                        trigger_event_id=ticket_id,
                        event_date=ticket.closed_at
                    )
                    
                    if scheduled:
                        logger.info(
                            f"NPS survey scheduled for closed ticket: ticket_id={ticket_id}, "
                            f"user_id={ticket.user_id}"
                        )
                    else:
                        logger.info(
                            f"NPS survey suppressed for closed ticket: ticket_id={ticket_id}, "
                            f"user_id={ticket.user_id}, reason={reason}"
                        )
                else:
                    logger.info(
                        f"NPS survey already exists for ticket: ticket_id={ticket_id}, "
                        f"skipping duplicate"
                    )
            except Exception as e:
                # Log error but don't fail ticket closure
                logger.error(
                    f"Error scheduling NPS survey for ticket: ticket_id={ticket_id}, "
                    f"user_id={ticket.user_id}, error={e}",
                    exc_info=True
                )
        
        return ticket
    
    except ValueError as e:
        logger.error(f"Validation error closing ticket with notification: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error closing ticket with notification: ticket_id={ticket_id}, "
            f"employee_id={employee_id}, error={e}",
            exc_info=True
        )
        raise


async def transfer_ticket(
    session: AsyncSession,
    ticket_id: int,
    source_employee_id: int,
    target_employee_id: int,
    messenger: str = "telegram"
) -> Ticket:
    """
    Transfer ticket to another employee.
    
    Updates assigned_staff_id and logs the transfer action with both
    source and target employee IDs.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
        source_employee_id: Source employee's messenger user ID
        target_employee_id: Target employee's messenger user ID
        messenger: Messenger type ("telegram" or "max")
    
    Returns:
        Updated Ticket object
    
    Raises:
        ValueError: If ticket not found or target employee invalid
        SQLAlchemyError: If database operation fails
    
    Requirements: 8.2, 8.3, 8.4, 8.5, 8.6
    """
    try:
        # Get ticket
        result = await session.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Verify target employee exists and get their internal ID
        if messenger == "telegram":
            stmt = select(Staff_Member).where(
                Staff_Member.tg_user_id == target_employee_id,
                Staff_Member.is_active == True
            )
        else:  # max
            stmt = select(Staff_Member).where(
                Staff_Member.max_user_id == target_employee_id,
                Staff_Member.is_active == True
            )
        
        result = await session.execute(stmt)
        target_employee = result.scalar_one_or_none()
        
        if not target_employee:
            error_msg = f"Target employee not found: messenger={messenger}, employee_id={target_employee_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Update ticket assignment with internal staff ID
        old_assigned_staff_id = ticket.assigned_staff_id
        ticket.assigned_staff_id = target_employee.id  # Use internal ID, not tg_user_id
        ticket.updated_at = datetime.utcnow()
        
        # Get internal staff ID for logging
        target_staff_internal_id = await _get_staff_internal_id(session, target_employee_id, messenger)
        
        # Log transfer action using internal staff ID
        await _log_action(
            session=session,
            action_type=ActionType.TICKET_ASSIGNED,
            ticket_id=ticket_id,
            staff_id=target_staff_internal_id,
            action_details={
                "action": "transfer",
                "source_employee_id": source_employee_id,
                "target_employee_id": target_employee_id,
                "old_assigned_staff_id": old_assigned_staff_id
            }
        )
        
        # Log transfer to I-TAT API
        try:
            from bots.max_bot.utils.itat_logging import log_ticket_assignment_to_itat
            await log_ticket_assignment_to_itat(
                session=session,
                ticket=ticket,
                staff_id=target_staff_internal_id,
                action="transferred"
            )
        except Exception as e:
            # Log error but don't fail the operation
            logger.error(
                f"Failed to log ticket transfer to I-TAT API: ticket_id={ticket_id}, error={e}",
                exc_info=True
            )
        
        logger.info(
            f"Ticket transferred: ticket_id={ticket_id}, "
            f"source_employee_id={source_employee_id}, "
            f"target_employee_id={target_employee_id}"
        )
        
        return ticket
    
    except ValueError as e:
        logger.error(f"Validation error transferring ticket: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error transferring ticket: ticket_id={ticket_id}, "
            f"source_employee_id={source_employee_id}, "
            f"target_employee_id={target_employee_id}, error={e}",
            exc_info=True
        )
        raise


# ========== Helper Functions ==========


async def _get_duty_engineer(session: AsyncSession) -> Staff_Member | None:
    """
    Get duty engineer for extended hours support.
    
    Retrieves the designated duty support account from system settings.
    Falls back to finding any active staff member with DUTY_ENGINEER role
    if no specific account is configured.
    
    Args:
        session: Database session
    
    Returns:
        Staff_Member object or None if no duty engineer found
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 7.1 (Передача техподдержке по времени - Продленное время)
    """
    try:
        # First, try to get designated duty support account from settings
        from services.settings_service import get_setting
        
        duty_account_id = await get_setting(session, "duty_support_account")
        
        if duty_account_id:
            # Get staff member by internal ID
            result = await session.execute(
                select(Staff_Member).where(
                    and_(
                        Staff_Member.id == int(duty_account_id),
                        Staff_Member.is_active == True
                    )
                )
            )
            duty_engineer = result.scalar_one_or_none()
            
            if duty_engineer:
                logger.info(f"Duty engineer found from settings: staff_id={duty_engineer.id}")
                return duty_engineer
            else:
                logger.warning(
                    f"Configured duty support account not found or inactive: "
                    f"staff_id={duty_account_id}"
                )
        
        # Fallback: find any active staff member with DUTY_ENGINEER role
        result = await session.execute(
            select(Staff_Member).where(
                and_(
                    Staff_Member.staff_role == StaffRole.DUTY_ENGINEER,
                    Staff_Member.is_active == True
                )
            ).limit(1)
        )
        duty_engineer = result.scalar_one_or_none()
        
        if not duty_engineer:
            logger.warning("No active duty engineer found (neither configured nor by role)")
        else:
            logger.info(
                f"Duty engineer found by role fallback: staff_id={duty_engineer.id}"
            )
        
        return duty_engineer
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error getting duty engineer: error={e}",
            exc_info=True
        )
        raise


async def _log_action(
    session: AsyncSession,
    action_type: ActionType,
    user_id: int | None = None,
    ticket_id: int | None = None,
    staff_id: int | None = None,
    action_details: dict[str, Any] | None = None
) -> Action_Log:
    """
    Create action log entry.
    
    Internal helper function for logging significant ticket actions.
    
    Args:
        session: Database session
        action_type: Type of action being logged
        user_id: Internal user ID (optional)
        ticket_id: Ticket ID (optional)
        staff_id: Staff member INTERNAL ID (optional) - NOT messenger user ID!
        action_details: Additional details as JSON (optional)
    
    Returns:
        Created Action_Log object
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 32.1, 32.2, 32.3, 32.4, 32.5
    """
    try:
        action_log = Action_Log(
            action_type=action_type,
            user_id=user_id,
            ticket_id=ticket_id,
            staff_id=staff_id,
            action_details=action_details,
            action_timestamp=datetime.utcnow()
        )
        
        session.add(action_log)
        await session.flush()
        
        logger.debug(
            f"Action logged: type={action_type.value}, user_id={user_id}, "
            f"ticket_id={ticket_id}"
        )
        
        return action_log
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error logging action: action_type={action_type.value}, "
            f"user_id={user_id}, error={e}",
            exc_info=True
        )
        raise


async def _get_staff_internal_id(
    session: AsyncSession,
    messenger_user_id: int,
    messenger: str = "telegram"
) -> int:
    """
    Get internal staff ID from messenger user ID.
    
    Helper function to convert messenger-specific user ID to internal staff database ID.
    
    Args:
        session: Database session
        messenger_user_id: Messenger user ID (Telegram or MAX)
        messenger: Messenger type ("telegram" or "max")
    
    Returns:
        Internal staff member ID
    
    Raises:
        ValueError: If staff member not found
    """
    from database.models import Staff_Member
    
    if messenger == "telegram":
        stmt = select(Staff_Member).where(Staff_Member.tg_user_id == messenger_user_id)
    else:  # max
        stmt = select(Staff_Member).where(Staff_Member.max_user_id == messenger_user_id)
    
    result = await session.execute(stmt)
    staff_member = result.scalar_one_or_none()
    
    if not staff_member:
        error_msg = f"Staff member not found: messenger={messenger}, user_id={messenger_user_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    return staff_member.id


# ========== Employee Messaging Functions ==========


async def send_message_to_client(
    bot: Bot,
    session: AsyncSession,
    ticket_id: int,
    employee_id: int,
    message_text: str,
    file_id: str | None = None,
    file_type: Any | None = None,
    telegram_media_type: str | None = None,
    messenger: str = "telegram"
) -> Message:
    """
    Send message from employee to client.
    
    Appends employee signature to message_text, sends message to client via bot,
    stores message in Messages table with sender_type STAFF, and logs the action.
    If file_id is provided, stores file attachment and sends file to client.
    
    Args:
        bot: Aiogram Bot instance
        session: Database session
        ticket_id: Ticket ID
        employee_id: Employee's messenger user ID
        message_text: Message text (signature will be appended)
        file_id: Telegram file ID (optional)
        file_type: FileType enum value (optional, required if file_id provided)
        messenger: Messenger type ("telegram" or "max")
    
    Returns:
        Created Message object
    
    Raises:
        ValueError: If ticket not found, employee not found, or staff not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 4.2, 4.3, 4.4, 5.1, 5.2, 6.5, 6.6
    
    Args:
        bot: Aiogram Bot instance
        session: Database session
        ticket_id: Ticket ID
        employee_id: Employee's Telegram ID
        message_text: Message text (signature will be appended)
        file_id: Telegram file ID (optional)
        file_type: FileType enum value (optional, required if file_id provided)
    
    Returns:
        Created Message object
    
    Raises:
        ValueError: If ticket not found or employee not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 4.2, 4.3, 4.4, 5.1, 5.2, 6.5, 6.6
    """
    try:
        # Get ticket with eager loading for user
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.user))
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Get employee signature
        from services.employee_service import get_employee_signature
        signature = await get_employee_signature(session, employee_id)
        
        # Format message with signature at top: ticket number emoji, manager name, signature
        # Example: "📋 Заявка #123 | 👤 Иван Иванов, Менеджер\n\n[message text]"
        message_with_signature = f"📋 Заявка #{ticket_id}, 👤 {signature}\n\n{message_text}"
        
        # Send message to client
        try:
            if file_id:
                # Send file with caption using appropriate Telegram method
                from database.models import FileType
                
                if file_type == FileType.IMAGE:
                    await bot.send_photo(
                        chat_id=ticket.user.tg_user_id,
                        photo=file_id,
                        caption=message_with_signature
                    )
                elif telegram_media_type == "voice":
                    await bot.send_voice(
                        chat_id=ticket.user.tg_user_id,
                        voice=file_id,
                        caption=message_with_signature
                    )
                elif telegram_media_type == "video":
                    await bot.send_video(
                        chat_id=ticket.user.tg_user_id,
                        video=file_id,
                        caption=message_with_signature
                    )
                elif telegram_media_type == "audio":
                    await bot.send_audio(
                        chat_id=ticket.user.tg_user_id,
                        audio=file_id,
                        caption=message_with_signature
                    )
                elif telegram_media_type == "video_note":
                    # Video notes don't support captions, send as separate message
                    await bot.send_video_note(
                        chat_id=ticket.user.tg_user_id,
                        video_note=file_id
                    )
                    if message_with_signature:
                        await bot.send_message(
                            chat_id=ticket.user.tg_user_id,
                            text=message_with_signature
                        )
                else:
                    # For documents and other file types
                    await bot.send_document(
                        chat_id=ticket.user.tg_user_id,
                        document=file_id,
                        caption=message_with_signature
                    )
                
                logger.info(
                    f"File sent to client: ticket_id={ticket_id}, "
                    f"employee_id={employee_id}, file_type={file_type}, "
                    f"telegram_media_type={telegram_media_type}"
                )
            else:
                # Send text message
                await bot.send_message(
                    chat_id=ticket.user.tg_user_id,
                    text=message_with_signature
                )
                
                logger.info(
                    f"Message sent to client: ticket_id={ticket_id}, "
                    f"employee_id={employee_id}"
                )
        
        except Exception as e:
            logger.error(
                f"Error sending message to client via Telegram: ticket_id={ticket_id}, "
                f"client_id={ticket.tg_user_id}, error={e}",
                exc_info=True
            )
            raise
        
        # Store message in database
        message = await add_ticket_message(
            session=session,
            ticket_id=ticket_id,
            sender_type=SenderType.STAFF,
            sender_id=employee_id,
            message_text=message_text,  # Store original message without signature
            message_type=MessageType.DOCUMENT if file_id else MessageType.TEXT
        )
        
        # Store file attachment if provided
        if file_id:
            from database.models import File_Attachment, UploaderType
            
            file_attachment = File_Attachment(
                ticket_id=ticket_id,
                message_id=message.id,
                file_type=file_type,
                telegram_file_id=file_id,
                uploader_id=employee_id,
                uploader_type=UploaderType.STAFF,
                uploaded_at=datetime.utcnow()
            )
            
            session.add(file_attachment)
            await session.flush()
            
            logger.debug(
                f"File attachment stored: ticket_id={ticket_id}, "
                f"message_id={message.id}, file_type={file_type}"
            )
        
        # Get internal staff ID
        staff_id = await _get_staff_internal_id(session, employee_id, messenger)
        
        # Log action
        await _log_action(
            session=session,
            action_type=ActionType.MESSAGE_SENT,
            ticket_id=ticket_id,
            staff_id=staff_id,
            action_details={
                "message_type": "file" if file_id else "text",
                "has_signature": True
            }
        )
        
        return message
    
    except ValueError as e:
        logger.error(f"Validation error sending message to client: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error sending message to client: ticket_id={ticket_id}, "
            f"employee_id={employee_id}, error={e}",
            exc_info=True
        )
        raise


async def handle_client_message_to_ticket(
    bot: Bot,
    session: AsyncSession,
    ticket_id: int,
    client_message: Message,
    employee_focused_ticket_id: int | None = None
) -> None:
    """
    Handle incoming client message to ticket.
    
    Stores message in Messages table with sender_type USER, changes ticket status
    from WAITING_CLIENT to IN_PROGRESS if applicable, forwards message to assigned
    employee, and logs the action.
    
    If employee is in focus mode on a different ticket, sends a notification
    without changing their focus.
    
    Args:
        bot: Aiogram Bot instance
        session: Database session
        ticket_id: Ticket ID
        client_message: Aiogram Message object from client
        employee_focused_ticket_id: Optional ticket ID that employee is currently focused on
    
    Raises:
        ValueError: If ticket not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 6.1, 6.3, 6.7, 13.4
    """
    try:
        # Get ticket with user data
        from sqlalchemy.orm import selectinload
        
        result = await session.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.user))
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Determine message type and text
        message_text = ""
        message_type = MessageType.TEXT
        file_id = None
        file_type = None
        
        if client_message.text:
            message_text = client_message.text
            message_type = MessageType.TEXT
        elif client_message.photo:
            message_text = client_message.caption or "📷 Фото"
            message_type = MessageType.PHOTO
            file_id = client_message.photo[-1].file_id
            from database.models import FileType
            file_type = FileType.IMAGE
        elif client_message.document:
            message_text = client_message.caption or f"📎 {client_message.document.file_name or 'Документ'}"
            message_type = MessageType.DOCUMENT
            file_id = client_message.document.file_id
            from database.models import FileType
            
            # Classify file type based on extension
            file_name = client_message.document.file_name or ""
            file_type = classify_file_type(file_name)
        elif client_message.voice:
            message_text = "🎤 Голосовое сообщение"
            message_type = MessageType.VOICE
            file_id = client_message.voice.file_id
            from database.models import FileType
            file_type = FileType.OTHER
        elif client_message.video:
            message_text = client_message.caption or f"🎥 {client_message.video.file_name or 'Видео'}"
            message_type = MessageType.VIDEO
            file_id = client_message.video.file_id
            from database.models import FileType
            file_type = FileType.OTHER
        elif client_message.audio:
            message_text = client_message.caption or f"🎵 {client_message.audio.file_name or 'Аудио'}"
            message_type = MessageType.AUDIO
            file_id = client_message.audio.file_id
            from database.models import FileType
            file_type = FileType.OTHER
        elif client_message.video_note:
            message_text = "🎬 Видео-сообщение"
            message_type = MessageType.VIDEO_NOTE
            file_id = client_message.video_note.file_id
            from database.models import FileType
            file_type = FileType.OTHER
        
        # Store message in database
        message = await add_ticket_message(
            session=session,
            ticket_id=ticket_id,
            sender_type=SenderType.USER,
            sender_id=client_message.from_user.id,
            message_text=message_text,
            message_type=message_type
        )
        
        # Store file attachment if present
        if file_id:
            from database.models import File_Attachment, UploaderType
            
            # Determine file name and size based on media type
            file_name = None
            file_size = None
            
            if client_message.document:
                file_name = client_message.document.file_name
                file_size = client_message.document.file_size
            elif client_message.video:
                file_name = client_message.video.file_name
                file_size = client_message.video.file_size
            elif client_message.audio:
                file_name = client_message.audio.file_name
                file_size = client_message.audio.file_size
            elif client_message.voice:
                file_name = "voice.ogg"
                file_size = client_message.voice.file_size
            elif client_message.video_note:
                file_name = "video_note.mp4"
                file_size = client_message.video_note.file_size
            elif client_message.photo:
                file_name = "photo.jpg"
                file_size = client_message.photo[-1].file_size
            
            file_attachment = File_Attachment(
                ticket_id=ticket_id,
                message_id=message.id,
                file_type=file_type,
                telegram_file_id=file_id,
                file_name=file_name,
                file_size=file_size,
                uploader_id=client_message.from_user.id,
                uploader_type=UploaderType.USER,
                uploaded_at=datetime.utcnow()
            )
            
            session.add(file_attachment)
            await session.flush()
            
            logger.debug(
                f"Client file attachment stored: ticket_id={ticket_id}, "
                f"message_id={message.id}, file_type={file_type}"
            )
        
        # If ticket status is WAITING_CLIENT, change to IN_PROGRESS
        if ticket.ticket_status == TicketStatus.WAITING_CLIENT:
            old_status = ticket.ticket_status
            ticket.ticket_status = TicketStatus.IN_PROGRESS
            ticket.updated_at = datetime.utcnow()
            
            # Cancel escalation monitoring tasks
            try:
                # Import here to avoid circular dependency
                from celery_app.escalation_tasks import cancel_escalation_monitoring
                
                await cancel_escalation_monitoring(ticket_id)
                logger.info(f"Escalation monitoring cancelled: ticket_id={ticket_id}")
            except Exception as e:
                logger.warning(
                    f"Failed to cancel escalation monitoring: ticket_id={ticket_id}, error={e}"
                )
                # Don't fail the operation if cancellation fails
            
            await _log_action(
                session=session,
                action_type=ActionType.STATUS_CHANGED,
                ticket_id=ticket_id,
                tg_user_id=client_message.from_user.id,
                action_details={
                    "old_status": old_status.value,
                    "new_status": TicketStatus.IN_PROGRESS.value,
                    "reason": "client_response"
                }
            )
            
            logger.info(
                f"Ticket status changed from WAITING_CLIENT to IN_PROGRESS: "
                f"ticket_id={ticket_id}"
            )
        
        # Forward message to assigned employee
        if ticket.assigned_staff_id:
            try:
                # Get employee's Telegram user ID
                staff_result = await session.execute(
                    select(Staff_Member.tg_user_id).where(
                        Staff_Member.id == ticket.assigned_staff_id
                    )
                )
                employee_tg_id = staff_result.scalar_one_or_none()
                
                if not employee_tg_id:
                    logger.warning(
                        f"Could not find tg_user_id for staff member: "
                        f"staff_id={ticket.assigned_staff_id}"
                    )
                else:
                    # Check if employee is in focus mode on a different ticket
                    is_non_focused_notification = (
                        employee_focused_ticket_id is not None and 
                        employee_focused_ticket_id != ticket_id
                    )
                    
                    # Format client info
                    client_info_lines = []
                    client_name = ticket.user.full_name or ticket.user.first_name or "Не указано"
                    client_info_lines.append(f"👤 Клиент: {client_name}")
                    
                    if ticket.user.phone_number:
                        client_info_lines.append(f"📱 Телефон: {ticket.user.phone_number}")
                    
                    if ticket.user.email:
                        client_info_lines.append(f"📧 Email: {ticket.user.email}")
                    
                    if ticket.user.username:
                        client_info_lines.append(f"💬 Username: @{ticket.user.username}")
                    
                    client_info = "\n".join(client_info_lines)
                    
                    # Build context message for employee
                    if is_non_focused_notification:
                        # Employee is focused on a different ticket - send notification
                        context_text = (
                            f"🔔 Новое сообщение на тикете #{ticket_id} (не в фокусе):\n\n"
                            f"{client_info}\n\n"
                            f"💬 Сообщение:\n{message_text}\n\n"
                            f"💡 Вы сейчас в фокусе на тикете #{employee_focused_ticket_id}. "
                            f"Используйте /manager для переключения."
                        )
                    else:
                        # Normal notification
                        context_text = (
                            f"💬 Новое сообщение от клиента (Заявка #{ticket_id}):\n\n"
                            f"{client_info}\n\n"
                            f"💬 Сообщение:\n{message_text}"
                        )
                    
                    if file_id:
                        # Forward file with context based on message type
                        if message_type == MessageType.PHOTO:
                            await bot.send_photo(
                                chat_id=employee_tg_id,
                                photo=file_id,
                                caption=context_text
                            )
                        elif message_type == MessageType.VOICE:
                            # Send context first, then voice (voice can't have caption)
                            await bot.send_message(
                                chat_id=employee_tg_id,
                                text=context_text
                            )
                            await bot.send_voice(
                                chat_id=employee_tg_id,
                                voice=file_id
                            )
                        elif message_type == MessageType.VIDEO:
                            await bot.send_video(
                                chat_id=employee_tg_id,
                                video=file_id,
                                caption=context_text
                            )
                        elif message_type == MessageType.AUDIO:
                            await bot.send_audio(
                                chat_id=employee_tg_id,
                                audio=file_id,
                                caption=context_text
                            )
                        elif message_type == MessageType.VIDEO_NOTE:
                            # Send context first, then video note (video note can't have caption)
                            await bot.send_message(
                                chat_id=employee_tg_id,
                                text=context_text
                            )
                            await bot.send_video_note(
                                chat_id=employee_tg_id,
                                video_note=file_id
                            )
                        else:
                            # Document or other file types
                            await bot.send_document(
                                chat_id=employee_tg_id,
                                document=file_id,
                                caption=context_text
                            )
                    else:
                        # Send text message
                        await bot.send_message(
                            chat_id=employee_tg_id,
                            text=context_text
                        )
                    
                    logger.info(
                        f"Client message forwarded to employee: ticket_id={ticket_id}, "
                        f"staff_id={ticket.assigned_staff_id}, tg_user_id={employee_tg_id}, "
                        f"non_focused={is_non_focused_notification}"
                    )
            
            except Exception as e:
                logger.error(
                    f"Error forwarding client message to employee: ticket_id={ticket_id}, "
                    f"staff_id={ticket.assigned_staff_id}, error={e}",
                    exc_info=True
                )
                # Don't fail the operation if forwarding fails
        
        # Get user internal ID for logging
        result = await session.execute(
            select(User).where(User.tg_user_id == client_message.from_user.id)
        )
        user = result.scalar_one_or_none()
        user_id = user.id if user else None
        
        # Log action
        await _log_action(
            session=session,
            action_type=ActionType.MESSAGE_SENT,
            ticket_id=ticket_id,
            user_id=user_id,
            action_details={
                "message_type": message_type.value,
                "has_file": file_id is not None
            }
        )
        
        logger.info(
            f"Client message handled: ticket_id={ticket_id}, "
            f"client_id={client_message.from_user.id}, message_type={message_type.value}"
        )
    
    except ValueError as e:
        logger.error(f"Validation error handling client message: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error handling client message: ticket_id={ticket_id}, error={e}",
            exc_info=True
        )
        raise



# ========== Active Tickets Queries ==========


async def get_user_active_tickets(
    session: AsyncSession,
    user_id: int
) -> list[Ticket]:
    """
    Get all active tickets for a user.
    
    Returns tickets with status NEW, IN_PROGRESS, or WAITING_CLIENT.
    
    Args:
        session: Database session
        user_id: User ID
    
    Returns:
        List of active tickets ordered by creation date (newest first)
    
    Requirements: AC-1.3, TR-2
    """
    try:
        stmt = (
            select(Ticket)
            .where(
                and_(
                    Ticket.user_id == user_id,
                    Ticket.ticket_status.in_([
                        TicketStatus.NEW,
                        TicketStatus.IN_PROGRESS,
                        TicketStatus.WAITING_CLIENT
                    ])
                )
            )
            .order_by(Ticket.created_at.desc())
        )
        
        result = await session.execute(stmt)
        tickets = result.scalars().all()
        
        logger.info(f"Retrieved {len(tickets)} active tickets for user {user_id}")
        return list(tickets)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error getting active tickets for user {user_id}: {e}",
            exc_info=True
        )
        return []


async def get_user_active_tickets_count(
    session: AsyncSession,
    user_id: int
) -> int:
    """
    Get count of active tickets for a user.
    
    Counts tickets with status NEW, IN_PROGRESS, or WAITING_CLIENT.
    
    Args:
        session: Database session
        user_id: User ID
    
    Returns:
        Count of active tickets
    
    Requirements: AC-1.3, TR-2
    """
    try:
        from sqlalchemy import func
        
        stmt = (
            select(func.count(Ticket.id))
            .where(
                and_(
                    Ticket.user_id == user_id,
                    Ticket.ticket_status.in_([
                        TicketStatus.NEW,
                        TicketStatus.IN_PROGRESS,
                        TicketStatus.WAITING_CLIENT
                    ])
                )
            )
        )
        
        result = await session.execute(stmt)
        count = result.scalar() or 0
        
        logger.debug(f"User {user_id} has {count} active tickets")
        return count
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error counting active tickets for user {user_id}: {e}",
            exc_info=True
        )
        return 0


async def get_ticket_by_id(
    session: AsyncSession,
    ticket_id: int
) -> Ticket | None:
    """
    Get ticket by ID with eager loading of related entities.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
    
    Returns:
        Ticket object or None if not found
    """
    try:
        from sqlalchemy.orm import selectinload
        
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.assigned_staff)
            )
        )
        
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        return ticket
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error getting ticket {ticket_id}: {e}",
            exc_info=True
        )
        return None



async def send_message_to_client_max(
    messenger_adapter,
    session: AsyncSession,
    ticket_id: int,
    employee_id: int,
    message_text: str,
    file_id: str | None = None,
    file_type: Any | None = None,
    max_media_type: str | None = None,
    messenger: str = "max",
    include_reply_button: bool = True
) -> Any:
    """
    Send message from employee to client via MAX messenger.
    
    Appends employee signature to message_text, sends message to client via MAX API,
    stores message in Messages table with sender_type STAFF, and logs the action.
    
    File Handling:
    - Downloads files from MAX URLs to temporary storage
    - Re-uploads files to client's chat with appropriate type (photo/document)
    - Cleans up temporary files after sending
    - Falls back to URL links if file forwarding fails
    
    Args:
        messenger_adapter: MAXMessengerAdapter instance
        session: Database session
        ticket_id: Ticket ID
        employee_id: Internal staff member ID (primary key)
        message_text: Message text (signature will be appended)
        file_id: MAX file URL (optional)
        file_type: FileType enum value (optional, required if file_id provided)
        max_media_type: MAX media type (image, file, voice, video, audio)
        messenger: Messenger type ("max")
        include_reply_button: Whether to include "Reply to manager" button (default: True)
    
    Returns:
        Created Message object
    
    Raises:
        ValueError: If ticket not found, employee not found, or client has no MAX ID
        SQLAlchemyError: If database operation fails
    
    Requirements: 4.2, 4.3, 4.4, 5.1, 5.2, 6.5, 6.6
    """
    try:
        # Get ticket with eager loading for user and MAX messenger data
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user).selectinload(User.max_messenger_data)
            )
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Check if client has MAX messenger data
        if not ticket.user.max_messenger_data:
            error_msg = f"Client has no MAX messenger data: user_id={ticket.user.id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Get employee signature
        from services.employee_service import get_employee_signature
        signature = await get_employee_signature(session, employee_id)
        
        # Format message with signature at top
        message_with_signature = f"📋 Заявка #{ticket_id}\n\n 👤 {signature}\n\n{message_text}"
        
        # Get client's MAX chat ID from MAX messenger data table
        client_chat_id = ticket.user.max_messenger_data.max_chat_id
        
        # Build "Reply to manager" inline keyboard (only if requested)
        reply_keyboard = None
        if include_reply_button:
            from bots.max_bot.payloads import ReplyToManagerPayload
            from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
            reply_keyboard = Keyboard(
                buttons=[[
                    KeyboardButton(
                        text="💬 Ответить менеджеру",
                        payload=ReplyToManagerPayload(ticket_id=ticket_id).pack()
                    )
                ]],
                inline=True
            )
        
        # Send message to client via MAX
        try:
            if file_id:
                # For voice, audio, and image — download and re-upload to preserve native display
                # For other files — send as link (MAX API doesn't support external file URLs)
                if max_media_type in ("voice", "audio_video_note", "audio", "image"):
                    try:
                        from pathlib import Path
                        import uuid
                        
                        # Ensure temp directory exists
                        temp_dir = Path("media/temp")
                        temp_dir.mkdir(parents=True, exist_ok=True)
                        
                        # Generate unique filename
                        if max_media_type == "image":
                            unique_filename = f"ticket_{ticket_id}_staff_{uuid.uuid4()}.jpg"
                        elif max_media_type in ("voice", "audio_video_note"):
                            unique_filename = f"ticket_{ticket_id}_staff_{uuid.uuid4()}.ogg"
                        elif max_media_type == "audio":
                            unique_filename = f"ticket_{ticket_id}_staff_{uuid.uuid4()}.mp3"
                        else:
                            unique_filename = f"ticket_{ticket_id}_staff_{uuid.uuid4()}_file.bin"
                        
                        download_path = f"media/temp/{unique_filename}"
                        
                        # Download file from MAX URL
                        local_path = await messenger_adapter.download_file(
                            file_url=file_id,
                            destination=download_path
                        )
                        
                        # Send file to client based on type
                        if max_media_type == "image":
                            await messenger_adapter.send_photo(
                                chat_id=client_chat_id,
                                photo_path=local_path,
                                caption=message_with_signature,
                                keyboard=reply_keyboard,
                                parse_mode="HTML"
                            )
                        elif max_media_type in ("voice", "audio_video_note", "audio"):
                            await messenger_adapter.send_document(
                                chat_id=client_chat_id,
                                document_path=local_path,
                                caption=message_with_signature,
                                keyboard=reply_keyboard,
                                parse_mode="HTML"
                            )
                        
                        # Clean up temporary file
                        try:
                            Path(local_path).unlink()
                        except Exception as cleanup_error:
                            logger.warning(f"Failed to delete temp file {local_path}: {cleanup_error}")
                        
                        logger.info(
                            f"File sent to client via MAX: ticket_id={ticket_id}, "
                            f"employee_id={employee_id}, file_type={file_type}, "
                            f"max_media_type={max_media_type}"
                        )
                    
                    except Exception as file_error:
                        logger.error(
                            f"Failed to send file to client: ticket_id={ticket_id}, "
                            f"error={file_error}",
                            exc_info=True
                        )
                        # Fallback: send text message with file URL
                        fallback_text = (
                            f"{message_with_signature}\n\n"
                            f'📎 <a href="{file_id}">Скачать файл</a>'
                        )
                        await messenger_adapter.send_message(
                            chat_id=client_chat_id,
                            text=fallback_text,
                            keyboard=reply_keyboard,
                            parse_mode="HTML"
                        )
                        logger.info(
                            f"File URL sent to client as fallback: ticket_id={ticket_id}, "
                            f"employee_id={employee_id}"
                        )
                else:
                    # For other file types (file, video) — send as link
                    file_link_text = (
                        f"{message_with_signature}\n\n"
                        f'📎 <a href="{file_id}">Скачать файл</a>'
                    )
                    await messenger_adapter.send_message(
                        chat_id=client_chat_id,
                        text=file_link_text,
                        keyboard=reply_keyboard,
                        parse_mode="HTML"
                    )
                    
                    logger.info(
                        f"File URL sent to client via MAX: ticket_id={ticket_id}, "
                        f"employee_id={employee_id}, file_type={file_type}, "
                        f"max_media_type={max_media_type}"
                    )
            else:
                # Send text message
                await messenger_adapter.send_message(
                    chat_id=client_chat_id,
                    text=message_with_signature,
                    keyboard=reply_keyboard,
                    parse_mode="HTML"
                )
                
                logger.info(
                    f"Message sent to client via MAX: ticket_id={ticket_id}, "
                    f"employee_id={employee_id}"
                )
        
        except Exception as e:
            logger.error(
                f"Error sending message to client via MAX: ticket_id={ticket_id}, "
                f"client_id={ticket.user.max_user_id}, error={e}",
                exc_info=True
            )
            raise
        
        # Store message in database
        message = await add_ticket_message(
            session=session,
            ticket_id=ticket_id,
            sender_type=SenderType.STAFF,
            sender_id=employee_id,
            message_text=message_text,  # Store original message without signature
            message_type=MessageType.DOCUMENT if file_id else MessageType.TEXT
        )
        
        # Store file attachment if provided
        if file_id:
            from database.models import File_Attachment, UploaderType
            
            file_attachment = File_Attachment(
                ticket_id=ticket_id,
                message_id=message.id,
                file_type=file_type,
                telegram_file_id=file_id,  # Store MAX file URL in telegram_file_id field
                uploader_id=employee_id,
                uploader_type=UploaderType.STAFF,
                uploaded_at=datetime.utcnow()
            )
            
            session.add(file_attachment)
            await session.flush()
            
            logger.debug(
                f"File attachment stored: ticket_id={ticket_id}, "
                f"message_id={message.id}, file_type={file_type}"
            )
        
        # Log action (employee_id is already internal staff ID)
        await _log_action(
            session=session,
            action_type=ActionType.MESSAGE_SENT,
            ticket_id=ticket_id,
            staff_id=employee_id,
            action_details={
                "message_type": "file" if file_id else "text",
                "has_signature": True,
                "messenger": "max"
            }
        )
        
        return message
    
    except ValueError as e:
        logger.error(f"Validation error sending message to client via MAX: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error sending message to client via MAX: ticket_id={ticket_id}, "
            f"employee_id={employee_id}, error={e}",
            exc_info=True
        )
        raise


async def save_initial_ticket_attachments(
    session: AsyncSession,
    ticket_id: int,
    user_id: int,
    attachments: list[dict],
    description: str | None = None,
) -> None:
    """
    Save FSM attachments to File_Attachment table for a newly created ticket.

    Creates a system message with attachments so they appear in ticket history.
    Also saves attachments directly to ticket for Celery queue task forwarding.

    Args:
        session: Database session (caller must commit after this call)
        ticket_id: ID of the created ticket
        user_id: Internal user ID (uploader)
        attachments: List of attachment dicts from FSM context:
            {"type": "image"|"voice"|"document"|"file", "url": str, "file_name": str|None}
        description: Optional ticket description (unused, kept for API symmetry)
    """
    from database.models import File_Attachment, FileType, UploaderType, Message, MessageType, SenderType

    if not attachments:
        logger.debug(f"No attachments to save for ticket_id={ticket_id}")
        return

    logger.info(f"Saving {len(attachments)} initial attachments for ticket_id={ticket_id}")

    # Create a system message for attachments to appear in history
    system_message = Message(
        ticket_id=ticket_id,
        sender_type=SenderType.SYSTEM,
        sender_id=None,
        message_text="Вложения к заявке",
        message_type=MessageType.TEXT,
        sent_at=get_moscow_now_naive()
    )
    session.add(system_message)
    await session.flush()  # Get message ID

    logger.info(f"Created system message for attachments: message_id={system_message.id}, ticket_id={ticket_id}")

    saved_count = 0
    for att in attachments:
        att_type = att.get("type", "document")
        file_url = att.get("url")
        file_name = att.get("file_name")

        if not file_url:
            logger.warning(f"Skipping attachment without URL: ticket_id={ticket_id}, att={att}")
            continue

        # Map FSM attachment type → FileType enum
        if att_type == "image":
            file_type = FileType.IMAGE
            if not file_name:
                file_name = "image.jpg"
        elif att_type == "voice":
            file_type = FileType.OTHER
            if not file_name:
                file_name = "voice.ogg"
        else:
            file_type = FileType.DOCUMENT
            if not file_name:
                file_name = "document"

        fa = File_Attachment(
            ticket_id=ticket_id,
            message_id=system_message.id,  # Link to system message for history
            file_type=file_type,
            # telegram_file_id is NOT NULL — store MAX URL here as well
            telegram_file_id=file_url,
            max_file_url=file_url,
            file_name=file_name,
            file_size=None,
            uploader_id=user_id,
            uploader_type=UploaderType.USER,
        )
        session.add(fa)
        saved_count += 1
        logger.debug(
            f"Added attachment to session: ticket_id={ticket_id}, message_id={system_message.id}, "
            f"type={att_type}, file_type={file_type.value}, file_name={file_name}"
        )

    logger.info(
        f"Saved {saved_count} initial attachments for ticket_id={ticket_id} "
        f"with system message_id={system_message.id}"
    )
