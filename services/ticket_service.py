"""
Ticket service layer for managing ticket-related database operations.

Provides async functions for ticket CRUD operations, manager assignment logic,
calendar-based work mode detection, routing logic, and staff notifications.

Requirements: 10.1-10.8, 11.1-11.5, 15.1-15.6
"""

import logging
from datetime import date, datetime, time
from typing import Any

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
    Ticket,
    TicketStatus,
    TicketType,
    User,
    WorkMode,
    ticket_keys,
)
from services.validation_service import classify_file_type

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
            - tg_user_id (int, required)
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
        if "tg_user_id" not in ticket_data:
            raise ValueError("tg_user_id is required")
        
        # Create ticket
        ticket = Ticket(
            ticket_type=ticket_data["ticket_type"],
            ticket_status=TicketStatus.NEW,
            tg_user_id=ticket_data["tg_user_id"],
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
                        added_at=datetime.utcnow()
                    )
                )
        
        # Log ticket creation
        await _log_action(
            session=session,
            action_type=ActionType.TICKET_CREATED,
            tg_user_id=ticket.tg_user_id,
            ticket_id=ticket.id,
            action_details={
                "ticket_type": ticket.ticket_type.value,
                "ticket_status": ticket.ticket_status.value,
                "assigned_staff_id": ticket.assigned_staff_id,
                "organization_inn": ticket.organization_inn,
                "key_count": len(selected_key_ids)
            }
        )
        
        logger.info(
            f"Ticket created: id={ticket.id}, type={ticket.ticket_type.value}, "
            f"user={ticket.tg_user_id}, assigned_staff={ticket.assigned_staff_id}"
        )
        
        return ticket
    
    except ValueError as e:
        logger.error(f"Validation error creating ticket: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error creating ticket: tg_user_id={ticket_data.get('tg_user_id')}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def determine_assigned_manager(
    session: AsyncSession,
    tg_user_id: int,
    organization_inn: str | None = None
) -> int | None:
    """
    Determine assigned manager based on Manager_Assignment or default_manager_id.
    
    Logic:
    1. If organization_inn provided, check Manager_Assignment for user-organization pair
    2. If no organization-specific manager, use user's default_manager_id
    3. If no manager found, return None
    
    Args:
        session: Database session
        tg_user_id: Telegram user ID
        organization_inn: Organization INN (optional)
    
    Returns:
        Staff member ID (tg_user_id) or None if no manager assigned
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 10.2, 10.3
    """
    try:
        # Check for organization-specific manager assignment
        if organization_inn:
            result = await session.execute(
                select(Manager_Assignment.manager_id).where(
                    and_(
                        Manager_Assignment.tg_user_id == tg_user_id,
                        Manager_Assignment.organization_inn == organization_inn
                    )
                )
            )
            manager_id = result.scalar_one_or_none()
            
            if manager_id:
                logger.debug(
                    f"Organization-specific manager found: tg_user_id={tg_user_id}, "
                    f"inn={organization_inn}, manager_id={manager_id}"
                )
                return manager_id
        
        # Fallback to user's default manager
        result = await session.execute(
            select(User.default_manager_id).where(User.tg_user_id == tg_user_id)
        )
        default_manager_id = result.scalar_one_or_none()
        
        if default_manager_id:
            logger.debug(
                f"Default manager found: tg_user_id={tg_user_id}, "
                f"manager_id={default_manager_id}"
            )
        else:
            logger.warning(
                f"No manager found for user: tg_user_id={tg_user_id}, "
                f"organization_inn={organization_inn}"
            )
        
        return default_manager_id
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error determining assigned manager: tg_user_id={tg_user_id}, "
            f"organization_inn={organization_inn}, error={e}",
            exc_info=True
        )
        raise


async def get_current_work_mode(session: AsyncSession) -> WorkMode:
    """
    Query Calendar_Rule table for current time and determine work mode.
    
    Checks current date and time against calendar rules with priority ordering.
    Returns REGULAR, EXTENDED, or NON_WORKING based on matching rules.
    
    Args:
        session: Database session
    
    Returns:
        WorkMode enum value (REGULAR, EXTENDED, or NON_WORKING)
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 11.1, 11.2, 11.3, 15.2, 15.3, 15.4
    """
    try:
        now = datetime.now()
        current_date = now.date()
        current_time = now.time()
        
        # Query calendar rules for current date, ordered by priority (highest first)
        result = await session.execute(
            select(Calendar_Rule)
            .where(
                and_(
                    Calendar_Rule.start_date <= current_date,
                    Calendar_Rule.end_date >= current_date
                )
            )
            .order_by(Calendar_Rule.rule_priority.desc())
        )
        rules = result.scalars().all()
        
        if not rules:
            logger.warning(
                f"No calendar rules found for date: {current_date}, "
                f"defaulting to NON_WORKING"
            )
            return WorkMode.NON_WORKING
        
        # Check each rule (highest priority first)
        for rule in rules:
            # NON_WORKING mode doesn't have time constraints
            if rule.work_mode == WorkMode.NON_WORKING:
                logger.debug(
                    f"Work mode determined: NON_WORKING (rule_id={rule.id}, "
                    f"priority={rule.rule_priority})"
                )
                return WorkMode.NON_WORKING
            
            # Check if current time falls within rule's working hours
            if rule.work_start_time and rule.work_end_time:
                if rule.work_start_time <= current_time <= rule.work_end_time:
                    logger.debug(
                        f"Work mode determined: {rule.work_mode.value} "
                        f"(rule_id={rule.id}, priority={rule.rule_priority}, "
                        f"time_range={rule.work_start_time}-{rule.work_end_time})"
                    )
                    return rule.work_mode
        
        # No matching time range found, default to NON_WORKING
        logger.debug(
            f"Current time {current_time} outside all working hours, "
            f"defaulting to NON_WORKING"
        )
        return WorkMode.NON_WORKING
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error determining work mode: error={e}",
            exc_info=True
        )
        raise


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
    routing_info: dict[str, Any] | None = None
) -> bool:
    """
    Send Telegram notification to staff member about new ticket.
    
    Args:
        bot: Aiogram Bot instance
        staff_id: Staff member Telegram ID
        ticket: Ticket object
        routing_info: Optional routing information for context
    
    Returns:
        True if notification sent successfully, False otherwise
    
    Requirements: 10.8, 15.6
    """
    try:
        # Build notification message
        ticket_type_names = {
            TicketType.INVOICE: "📄 Запрос счета",
            TicketType.TECHNICAL_SUPPORT: "🔧 Техническая поддержка",
            TicketType.RENEWAL: "🔄 Продление подписки"
        }
        
        message_text = (
            f"🔔 <b>Новое обращение #{ticket.id}</b>\n\n"
            f"<b>Тип:</b> {ticket_type_names.get(ticket.ticket_type, ticket.ticket_type.value)}\n"
            f"<b>От пользователя:</b> {ticket.tg_user_id}\n"
        )
        
        if ticket.organization_inn:
            message_text += f"<b>Организация:</b> {ticket.organization_inn}\n"
        
        if ticket.description:
            # Truncate long descriptions
            description = ticket.description[:200]
            if len(ticket.description) > 200:
                description += "..."
            message_text += f"\n<b>Описание:</b>\n{description}\n"
        
        if routing_info and routing_info.get("expected_response_time"):
            message_text += f"\n<b>Ожидаемое время ответа:</b> {routing_info['expected_response_time']}"
        
        # Send notification
        await bot.send_message(
            chat_id=staff_id,
            text=message_text,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Staff notification sent: ticket_id={ticket.id}, staff_id={staff_id}"
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
                header = f"🔄 <b>Тикет #{ticket.id} передан вам от {source_employee_name}</b>\n\n"
            else:
                header = f"🔄 <b>Тикет #{ticket.id} передан вам</b>\n\n"
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
            sent_at=datetime.utcnow()
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
    employee_id: int
) -> Ticket:
    """
    Take ticket into work.
    
    Changes ticket status from NEW to IN_PROGRESS, stops escalation timer,
    and logs the action.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
        employee_id: Employee's Telegram ID
    
    Returns:
        Updated Ticket object
    
    Raises:
        ValueError: If ticket not found or invalid status
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
        
        # Update ticket status and stop escalation timer
        old_status = ticket.ticket_status
        ticket.ticket_status = TicketStatus.IN_PROGRESS
        ticket.escalated_at = None
        ticket.updated_at = datetime.utcnow()
        
        # Log action
        await _log_action(
            session=session,
            action_type=ActionType.TICKET_ASSIGNED,
            ticket_id=ticket_id,
            staff_id=employee_id,
            action_details={
                "old_status": old_status.value,
                "new_status": TicketStatus.IN_PROGRESS.value,
                "action": "take_into_work"
            }
        )
        
        logger.info(
            f"Ticket taken into work: ticket_id={ticket_id}, employee_id={employee_id}, "
            f"old_status={old_status.value}"
        )
        
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
    employee_id: int
) -> Ticket:
    """
    Set ticket status to WAITING_CLIENT.
    
    Changes ticket status to WAITING_CLIENT and logs the action.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
        employee_id: Employee's Telegram ID
    
    Returns:
        Updated Ticket object
    
    Raises:
        ValueError: If ticket not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 3.6
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
        
        # Update ticket status
        old_status = ticket.ticket_status
        ticket.ticket_status = TicketStatus.WAITING_CLIENT
        ticket.updated_at = datetime.utcnow()
        
        # Log action
        await _log_action(
            session=session,
            action_type=ActionType.STATUS_CHANGED,
            ticket_id=ticket_id,
            staff_id=employee_id,
            action_details={
                "old_status": old_status.value,
                "new_status": TicketStatus.WAITING_CLIENT.value
            }
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
    final_comment: str
) -> Ticket:
    """
    Close ticket with final comment.
    
    Stores final comment as a message, changes status to CLOSED,
    sets closed_at timestamp, and logs the action.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
        employee_id: Employee's Telegram ID
        final_comment: Final comment text
    
    Returns:
        Updated Ticket object
    
    Raises:
        ValueError: If ticket not found
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
            staff_id=employee_id,
            action_details={
                "old_status": old_status.value,
                "final_comment_length": len(final_comment)
            }
        )
        
        logger.info(
            f"Ticket closed: ticket_id={ticket_id}, employee_id={employee_id}, "
            f"old_status={old_status.value}"
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


async def transfer_ticket(
    session: AsyncSession,
    ticket_id: int,
    source_employee_id: int,
    target_employee_id: int
) -> Ticket:
    """
    Transfer ticket to another employee.
    
    Updates assigned_staff_id and logs the transfer action with both
    source and target employee IDs.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
        source_employee_id: Source employee's Telegram ID
        target_employee_id: Target employee's Telegram ID
    
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
        
        # Verify target employee exists
        result = await session.execute(
            select(Staff_Member).where(Staff_Member.tg_user_id == target_employee_id)
        )
        target_employee = result.scalar_one_or_none()
        
        if not target_employee:
            error_msg = f"Target employee not found: employee_id={target_employee_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Update ticket assignment
        old_assigned_staff_id = ticket.assigned_staff_id
        ticket.assigned_staff_id = target_employee_id
        ticket.updated_at = datetime.utcnow()
        
        # Log transfer action
        await _log_action(
            session=session,
            action_type=ActionType.TICKET_ASSIGNED,
            ticket_id=ticket_id,
            staff_id=target_employee_id,
            action_details={
                "action": "transfer",
                "source_employee_id": source_employee_id,
                "target_employee_id": target_employee_id,
                "old_assigned_staff_id": old_assigned_staff_id
            }
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
    
    Internal helper to find active staff member with DUTY_ENGINEER role.
    
    Args:
        session: Database session
    
    Returns:
        Staff_Member object or None if no duty engineer found
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
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
            logger.warning("No active duty engineer found")
        
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
    tg_user_id: int | None = None,
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
        tg_user_id: User ID (optional)
        ticket_id: Ticket ID (optional)
        staff_id: Staff member ID (optional)
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
            tg_user_id=tg_user_id,
            ticket_id=ticket_id,
            staff_id=staff_id,
            action_details=action_details,
            action_timestamp=datetime.utcnow()
        )
        
        session.add(action_log)
        await session.flush()
        
        logger.debug(
            f"Action logged: type={action_type.value}, tg_user_id={tg_user_id}, "
            f"ticket_id={ticket_id}"
        )
        
        return action_log
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error logging action: action_type={action_type.value}, "
            f"tg_user_id={tg_user_id}, error={e}",
            exc_info=True
        )
        raise


# ========== Employee Messaging Functions ==========


async def send_message_to_client(
    bot: Bot,
    session: AsyncSession,
    ticket_id: int,
    employee_id: int,
    message_text: str,
    file_id: str | None = None,
    file_type: Any | None = None
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
        # Get ticket
        result = await session.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Get employee signature
        from services.employee_service import get_employee_signature
        signature = await get_employee_signature(session, employee_id)
        
        # Append signature to message
        message_with_signature = f"{message_text}\n\n{signature}"
        
        # Send message to client
        try:
            if file_id:
                # Send file with caption
                from database.models import FileType
                
                if file_type == FileType.IMAGE:
                    await bot.send_photo(
                        chat_id=ticket.tg_user_id,
                        photo=file_id,
                        caption=message_with_signature
                    )
                else:
                    await bot.send_document(
                        chat_id=ticket.tg_user_id,
                        document=file_id,
                        caption=message_with_signature
                    )
                
                logger.info(
                    f"File sent to client: ticket_id={ticket_id}, "
                    f"employee_id={employee_id}, file_type={file_type}"
                )
            else:
                # Send text message
                await bot.send_message(
                    chat_id=ticket.tg_user_id,
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
        
        # Log action
        await _log_action(
            session=session,
            action_type=ActionType.MESSAGE_SENT,
            ticket_id=ticket_id,
            staff_id=employee_id,
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
        # Get ticket
        result = await session.execute(
            select(Ticket).where(Ticket.id == ticket_id)
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
            
            file_attachment = File_Attachment(
                ticket_id=ticket_id,
                message_id=message.id,
                file_type=file_type,
                telegram_file_id=file_id,
                file_name=client_message.document.file_name if client_message.document else None,
                file_size=client_message.document.file_size if client_message.document else None,
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
                # Check if employee is in focus mode on a different ticket
                is_non_focused_notification = (
                    employee_focused_ticket_id is not None and 
                    employee_focused_ticket_id != ticket_id
                )
                
                # Build context message for employee
                if is_non_focused_notification:
                    # Employee is focused on a different ticket - send notification
                    context_text = (
                        f"🔔 Новое сообщение на тикете #{ticket_id} (не в фокусе):\n\n"
                        f"{message_text}\n\n"
                        f"💡 Вы сейчас в фокусе на тикете #{employee_focused_ticket_id}. "
                        f"Используйте /employee для переключения."
                    )
                else:
                    # Normal notification
                    context_text = (
                        f"💬 Новое сообщение от клиента (Тикет #{ticket_id}):\n\n"
                        f"{message_text}"
                    )
                
                if file_id:
                    # Forward file with context
                    from database.models import FileType
                    
                    if file_type == FileType.IMAGE:
                        await bot.send_photo(
                            chat_id=ticket.assigned_staff_id,
                            photo=file_id,
                            caption=context_text
                        )
                    else:
                        await bot.send_document(
                            chat_id=ticket.assigned_staff_id,
                            document=file_id,
                            caption=context_text
                        )
                else:
                    # Send text message
                    await bot.send_message(
                        chat_id=ticket.assigned_staff_id,
                        text=context_text
                    )
                
                logger.info(
                    f"Client message forwarded to employee: ticket_id={ticket_id}, "
                    f"employee_id={ticket.assigned_staff_id}, "
                    f"non_focused={is_non_focused_notification}"
                )
            
            except Exception as e:
                logger.error(
                    f"Error forwarding client message to employee: ticket_id={ticket_id}, "
                    f"employee_id={ticket.assigned_staff_id}, error={e}",
                    exc_info=True
                )
                # Don't fail the operation if forwarding fails
        
        # Log action
        await _log_action(
            session=session,
            action_type=ActionType.MESSAGE_SENT,
            ticket_id=ticket_id,
            tg_user_id=client_message.from_user.id,
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
