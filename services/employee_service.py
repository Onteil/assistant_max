"""
Employee service layer for managing employee interface operations.

Provides async functions for employee ticket management, ticket card formatting,
action keyboard generation, signature handling, and time calculations.

Requirements: 1.2, 2.1, 2.2, 2.3, 2.4, 2.6, 3.1, 3.2, 3.3, 5.1, 19.1, 19.2, 19.3, 19.4, 19.5
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    Action_Log,
    ActionType,
    File_Attachment,
    FileType,
    Message,
    SenderType,
    Staff_Member,
    StaffRole,
    Ticket,
    TicketStatus,
    TicketType,
    User,
)

logger = logging.getLogger(__name__)


# ========== Active Tickets Query ==========


async def get_employee_active_tickets(
    session: AsyncSession,
    employee_id: int
) -> list[Ticket]:
    """
    Get all active tickets assigned to employee.
    
    Returns tickets with status NEW, IN_PROGRESS, or WAITING_CLIENT,
    ordered by created_at ascending (oldest first).
    
    Args:
        session: Database session
        employee_id: Telegram user ID of the employee
    
    Returns:
        List of active Ticket objects ordered by created_at
    
    Requirements: 1.2
    """
    try:
        stmt = (
            select(Ticket)
            .where(
                and_(
                    Ticket.assigned_staff_id == employee_id,
                    Ticket.ticket_status.in_([
                        TicketStatus.NEW,
                        TicketStatus.IN_PROGRESS,
                        TicketStatus.WAITING_CLIENT
                    ])
                )
            )
            .order_by(Ticket.created_at.asc())
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys)
            )
        )
        
        result = await session.execute(stmt)
        tickets = result.scalars().all()
        
        logger.info(f"Retrieved {len(tickets)} active tickets for employee {employee_id}")
        return list(tickets)
        
    except Exception as e:
        logger.error(f"Error retrieving active tickets for employee {employee_id}: {e}", exc_info=True)
        raise


# ========== Ticket Card Formatting ==========


async def format_ticket_card(
    ticket: Ticket,
    session: AsyncSession
) -> str:
    """
    Format ticket information as text card.
    
    Includes:
    - Ticket number and type
    - Client information
    - Subject/description
    - Elapsed time
    - Current status
    - File attachment count
    
    Args:
        ticket: Ticket object to format
        session: Database session
    
    Returns:
        Formatted ticket card as string
    
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.6
    """
    try:
        # Ticket header
        ticket_type_text = "Счет" if ticket.ticket_type == TicketType.INVOICE else "ТП"
        lines = [
            f"🎫 Тикет #{ticket.id} ({ticket_type_text})",
            ""
        ]
        
        # Client information
        client_name = ticket.user.full_name or ticket.user.first_name or "Неизвестно"
        lines.append(f"👤 Клиент: {client_name}")
        
        # Status
        status_emoji = {
            TicketStatus.NEW: "🆕",
            TicketStatus.IN_PROGRESS: "⚙️",
            TicketStatus.WAITING_CLIENT: "⏳",
            TicketStatus.CLOSED: "✅",
            TicketStatus.CANCELLED: "❌"
        }
        status_text = {
            TicketStatus.NEW: "Новое",
            TicketStatus.IN_PROGRESS: "В работе",
            TicketStatus.WAITING_CLIENT: "Ожидание клиента",
            TicketStatus.CLOSED: "Закрыто",
            TicketStatus.CANCELLED: "Отменено"
        }
        emoji = status_emoji.get(ticket.ticket_status, "")
        status = status_text.get(ticket.ticket_status, str(ticket.ticket_status.value))
        lines.append(f"{emoji} Статус: {status}")
        lines.append("")
        
        # Type-specific fields
        if ticket.ticket_type == TicketType.INVOICE:
            # Invoice type: show organization INN and GS keys if available
            if ticket.organization_inn:
                org_name = ticket.organization.organization_name if ticket.organization else ""
                if org_name:
                    lines.append(f"🏢 Организация: {org_name}")
                lines.append(f"📋 ИНН: {ticket.organization_inn}")
            
            if ticket.gs_keys:
                key_numbers = [key.key_number for key in ticket.gs_keys]
                lines.append(f"🔑 Ключи ГС: {', '.join(key_numbers)}")
            
            if ticket.description:
                lines.append(f"📝 Описание: {ticket.description}")
        
        elif ticket.ticket_type == TicketType.TECHNICAL_SUPPORT:
            # Technical support type: show problem description and related GS key
            if ticket.description:
                lines.append(f"❓ Проблема: {ticket.description}")
            
            if ticket.gs_keys:
                key_numbers = [key.key_number for key in ticket.gs_keys]
                lines.append(f"🔑 Связанный ключ: {', '.join(key_numbers)}")
        
        lines.append("")
        
        # Elapsed time
        elapsed = await calculate_ticket_elapsed_time(ticket)
        lines.append(f"⏱ Время: {elapsed}")
        
        # File attachment count
        stmt = select(File_Attachment).where(File_Attachment.ticket_id == ticket.id)
        result = await session.execute(stmt)
        attachments = result.scalars().all()
        if attachments:
            lines.append(f"📎 Вложений: {len(attachments)}")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error formatting ticket card for ticket {ticket.id}: {e}", exc_info=True)
        raise


# ========== Action Keyboard Generation ==========


async def get_ticket_action_keyboard(
    ticket: Ticket
) -> InlineKeyboardMarkup:
    """
    Generate inline keyboard for ticket based on current status.
    
    Status NEW: [Взять в работу] [🔄 Передать] [📁 История] [❌ Выйти из фокуса]
    Status IN_PROGRESS: [✅ Закрыть] [⏳ Ждем клиента] [🔄 Передать] [📁 История] [❌ Выйти из фокуса]
    Status WAITING_CLIENT: [✅ Закрыть] [🔄 Передать] [📁 История] [❌ Выйти из фокуса]
    
    Args:
        ticket: Ticket object
    
    Returns:
        InlineKeyboardMarkup with action buttons
    
    Requirements: 3.1, 3.2, 3.3
    """
    try:
        # Import here to avoid circular import
        from bots.tg_bot.callback_datas import TicketActionCallback
        
        buttons = []
        
        if ticket.ticket_status == TicketStatus.NEW:
            # NEW status buttons
            buttons.append([
                InlineKeyboardButton(
                    text="Взять в работу",
                    callback_data=TicketActionCallback(
                        action="take_ticket",
                        ticket_id=ticket.id
                    ).pack()
                )
            ])
            buttons.append([
                InlineKeyboardButton(
                    text="🔄 Передать",
                    callback_data=TicketActionCallback(
                        action="transfer_ticket",
                        ticket_id=ticket.id
                    ).pack()
                ),
                InlineKeyboardButton(
                    text="📁 История",
                    callback_data=TicketActionCallback(
                        action="view_history",
                        ticket_id=ticket.id
                    ).pack()
                )
            ])
            buttons.append([
                InlineKeyboardButton(
                    text="❌ Выйти из фокуса",
                    callback_data=TicketActionCallback(
                        action="exit_focus",
                        ticket_id=ticket.id
                    ).pack()
                )
            ])
        
        elif ticket.ticket_status == TicketStatus.IN_PROGRESS:
            # IN_PROGRESS status buttons
            buttons.append([
                InlineKeyboardButton(
                    text="✅ Закрыть",
                    callback_data=TicketActionCallback(
                        action="close_ticket",
                        ticket_id=ticket.id
                    ).pack()
                ),
                InlineKeyboardButton(
                    text="⏳ Ждем клиента",
                    callback_data=TicketActionCallback(
                        action="set_waiting",
                        ticket_id=ticket.id
                    ).pack()
                )
            ])
            buttons.append([
                InlineKeyboardButton(
                    text="🔄 Передать",
                    callback_data=TicketActionCallback(
                        action="transfer_ticket",
                        ticket_id=ticket.id
                    ).pack()
                ),
                InlineKeyboardButton(
                    text="📁 История",
                    callback_data=TicketActionCallback(
                        action="view_history",
                        ticket_id=ticket.id
                    ).pack()
                )
            ])
            buttons.append([
                InlineKeyboardButton(
                    text="❌ Выйти из фокуса",
                    callback_data=TicketActionCallback(
                        action="exit_focus",
                        ticket_id=ticket.id
                    ).pack()
                )
            ])
        
        elif ticket.ticket_status == TicketStatus.WAITING_CLIENT:
            # WAITING_CLIENT status buttons
            buttons.append([
                InlineKeyboardButton(
                    text="✅ Закрыть",
                    callback_data=TicketActionCallback(
                        action="close_ticket",
                        ticket_id=ticket.id
                    ).pack()
                )
            ])
            buttons.append([
                InlineKeyboardButton(
                    text="🔄 Передать",
                    callback_data=TicketActionCallback(
                        action="transfer_ticket",
                        ticket_id=ticket.id
                    ).pack()
                ),
                InlineKeyboardButton(
                    text="📁 История",
                    callback_data=TicketActionCallback(
                        action="view_history",
                        ticket_id=ticket.id
                    ).pack()
                )
            ])
            buttons.append([
                InlineKeyboardButton(
                    text="❌ Выйти из фокуса",
                    callback_data=TicketActionCallback(
                        action="exit_focus",
                        ticket_id=ticket.id
                    ).pack()
                )
            ])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
        
    except Exception as e:
        logger.error(f"Error generating action keyboard for ticket {ticket.id}: {e}", exc_info=True)
        raise


# ========== Employee Signature ==========


async def get_employee_signature(
    session: AsyncSession,
    employee_id: int
) -> str:
    """
    Get formatted employee signature.
    
    Format: "Name Surname, role/department"
    Retrieved from Staff_Member.full_name and Staff_Member.position
    
    Args:
        session: Database session
        employee_id: Telegram user ID of the employee
    
    Returns:
        Formatted signature string
    
    Raises:
        ValueError: If employee not found
    
    Requirements: 5.1
    """
    try:
        stmt = select(Staff_Member).where(Staff_Member.tg_user_id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            raise ValueError(f"Employee {employee_id} not found")
        
        signature = f"{employee.full_name}, {employee.position}"
        
        logger.debug(f"Retrieved signature for employee {employee_id}: {signature}")
        return signature
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error retrieving signature for employee {employee_id}: {e}", exc_info=True)
        raise


# ========== Time Calculations ==========


async def calculate_ticket_elapsed_time(
    ticket: Ticket
) -> str:
    """
    Calculate and format elapsed time for ticket.
    
    For active tickets: time from created_at to now
    For WAITING_CLIENT: time since status change
    For closed tickets: time from created_at to closed_at
    
    Format: "Xh Ym" or "Xd Yh"
    
    Args:
        ticket: Ticket object
    
    Returns:
        Formatted elapsed time string
    
    Requirements: 19.1, 19.2, 19.3, 19.4, 19.5
    """
    try:
        now = datetime.utcnow()
        
        # Determine start and end times based on ticket status
        if ticket.ticket_status == TicketStatus.CLOSED:
            # Closed tickets: from created_at to closed_at
            start_time = ticket.created_at
            end_time = ticket.closed_at or now
        elif ticket.ticket_status == TicketStatus.WAITING_CLIENT:
            # Waiting for client: time since status change (use updated_at as proxy)
            start_time = ticket.updated_at or ticket.created_at
            end_time = now
        else:
            # Active tickets: from created_at to now
            start_time = ticket.created_at
            end_time = now
        
        # Calculate elapsed time
        elapsed = end_time - start_time
        
        # Format based on duration
        total_seconds = int(elapsed.total_seconds())
        total_minutes = total_seconds // 60
        total_hours = total_minutes // 60
        total_days = total_hours // 24
        
        if total_hours < 24:
            # Less than 24 hours: format as "Xh Ym"
            hours = total_hours
            minutes = total_minutes % 60
            return f"{hours}ч {minutes}м"
        else:
            # 24 hours or more: format as "Xd Yh"
            days = total_days
            hours = total_hours % 24
            return f"{days}д {hours}ч"
        
    except Exception as e:
        logger.error(f"Error calculating elapsed time for ticket {ticket.id}: {e}", exc_info=True)
        return "Неизвестно"


# ========== Employee Transfer ==========


async def get_available_employees_for_transfer(
    session: AsyncSession,
    ticket: Ticket,
    current_employee_id: int
) -> list[Staff_Member]:
    """
    Get list of employees available for ticket transfer.
    
    Filters by:
    - is_active = True
    - Appropriate role for ticket type:
      * INVOICE → MANAGER or ADMINISTRATOR
      * TECHNICAL_SUPPORT → TECHNICAL_SUPPORT, DUTY_ENGINEER, or ADMINISTRATOR
    - Excludes current assigned employee
    
    Args:
        session: Database session
        ticket: Ticket object to transfer
        current_employee_id: Current assigned employee's Telegram ID
    
    Returns:
        List of available Staff_Member objects
    
    Requirements: 8.1, 17.1, 17.2, 17.3, 17.4, 17.5
    """
    try:
        # Determine appropriate roles based on ticket type
        if ticket.ticket_type == TicketType.INVOICE:
            # Invoice tickets can be handled by Managers or Administrators
            allowed_roles = [StaffRole.MANAGER, StaffRole.ADMINISTRATOR]
        elif ticket.ticket_type == TicketType.TECHNICAL_SUPPORT:
            # Technical support tickets can be handled by TS, Duty Engineers, or Administrators
            allowed_roles = [
                StaffRole.TECHNICAL_SUPPORT,
                StaffRole.DUTY_ENGINEER,
                StaffRole.ADMINISTRATOR
            ]
        else:
            # For other ticket types (e.g., RENEWAL), allow all roles
            allowed_roles = [
                StaffRole.MANAGER,
                StaffRole.TECHNICAL_SUPPORT,
                StaffRole.DUTY_ENGINEER,
                StaffRole.ADMINISTRATOR
            ]
        
        # Query available employees
        stmt = (
            select(Staff_Member)
            .where(
                and_(
                    Staff_Member.is_active,
                    Staff_Member.staff_role.in_(allowed_roles),
                    Staff_Member.tg_user_id != current_employee_id
                )
            )
            .order_by(Staff_Member.full_name.asc())
        )
        
        result = await session.execute(stmt)
        employees = result.scalars().all()
        
        logger.info(
            f"Found {len(employees)} available employees for transfer: "
            f"ticket_id={ticket.id}, ticket_type={ticket.ticket_type.value}, "
            f"current_employee_id={current_employee_id}"
        )
        
        return list(employees)
        
    except Exception as e:
        logger.error(
            f"Error getting available employees for transfer: "
            f"ticket_id={ticket.id}, current_employee_id={current_employee_id}, error={e}",
            exc_info=True
        )
        raise


# ========== Ticket History ==========


async def format_ticket_history(
    session: AsyncSession,
    ticket_id: int,
    page: int = 0,
    page_size: int = 10
) -> tuple[str, bool]:
    """
    Format ticket history for display.
    
    Returns:
    - Formatted history text with messages and events
    - Boolean indicating if more pages exist
    
    Includes:
    - All messages with sender name and timestamp
    - File attachments with file names
    - Status change events
    - Transfer events
    
    Args:
        session: Database session
        ticket_id: Ticket ID to retrieve history for
        page: Page number (0-indexed)
        page_size: Number of items per page
    
    Returns:
        Tuple of (formatted_history_text, has_more_pages)
    
    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
    """
    try:
        from database.models import Message, Action_Log, ActionType
        
        # Query all messages for the ticket
        messages_stmt = (
            select(Message)
            .where(Message.ticket_id == ticket_id)
            .order_by(Message.sent_at.asc())
            .options(selectinload(Message.file_attachments))
        )
        messages_result = await session.execute(messages_stmt)
        messages = messages_result.scalars().all()
        
        # Query action logs for status changes and transfers
        action_logs_stmt = (
            select(Action_Log)
            .where(
                and_(
                    Action_Log.ticket_id == ticket_id,
                    Action_Log.action_type.in_([
                        ActionType.STATUS_CHANGED,
                        ActionType.TICKET_ASSIGNED,
                        ActionType.TICKET_CLOSED
                    ])
                )
            )
            .order_by(Action_Log.action_timestamp.asc())
        )
        action_logs_result = await session.execute(action_logs_stmt)
        action_logs = action_logs_result.scalars().all()
        
        # Combine messages and events into a single timeline
        timeline_items = []
        
        # Add messages to timeline
        for message in messages:
            timeline_items.append({
                'type': 'message',
                'timestamp': message.sent_at,
                'data': message
            })
        
        # Add action logs to timeline
        for log in action_logs:
            timeline_items.append({
                'type': 'action',
                'timestamp': log.action_timestamp,
                'data': log
            })
        
        # Sort timeline by timestamp
        timeline_items.sort(key=lambda x: x['timestamp'])
        
        # Calculate pagination
        total_items = len(timeline_items)
        start_idx = page * page_size
        end_idx = start_idx + page_size
        has_more_pages = end_idx < total_items
        
        # Get items for current page
        page_items = timeline_items[start_idx:end_idx]
        
        # Format history text
        lines = [f"📁 История тикета #{ticket_id}", ""]
        
        if not page_items:
            lines.append("История пуста")
        else:
            for item in page_items:
                timestamp = item['timestamp'].strftime("%d.%m.%Y %H:%M")
                
                if item['type'] == 'message':
                    message = item['data']
                    
                    # Determine sender name
                    if message.sender_type == SenderType.USER:
                        # Query user to get name
                        from database.models import User
                        user_stmt = select(User).where(User.tg_user_id == message.sender_id)
                        user_result = await session.execute(user_stmt)
                        user = user_result.scalar_one_or_none()
                        sender_name = user.full_name or user.first_name if user else "Клиент"
                        sender_emoji = "👤"
                    elif message.sender_type == SenderType.STAFF:
                        # Query staff member to get name
                        staff_stmt = select(Staff_Member).where(Staff_Member.tg_user_id == message.sender_id)
                        staff_result = await session.execute(staff_stmt)
                        staff = staff_result.scalar_one_or_none()
                        sender_name = staff.full_name if staff else "Сотрудник"
                        sender_emoji = "👨‍💼"
                    else:
                        sender_name = "Система"
                        sender_emoji = "🤖"
                    
                    # Format message
                    lines.append(f"{sender_emoji} {sender_name} ({timestamp}):")
                    lines.append(f"  {message.message_text}")
                    
                    # Add file attachments if any
                    if message.file_attachments:
                        for attachment in message.file_attachments:
                            file_name = attachment.file_name or "файл"
                            file_type_emoji = {
                                FileType.PDF: "📄",
                                FileType.IMAGE: "🖼",
                                FileType.DOCUMENT: "📎",
                                FileType.OTHER: "📎"
                            }.get(attachment.file_type, "📎")
                            lines.append(f"  {file_type_emoji} {file_name}")
                    
                    lines.append("")
                
                elif item['type'] == 'action':
                    log = item['data']
                    
                    # Format action log event
                    if log.action_type == ActionType.STATUS_CHANGED:
                        details = log.action_details or {}
                        old_status = details.get('old_status', 'неизвестно')
                        new_status = details.get('new_status', 'неизвестно')
                        lines.append(f"🔄 Статус изменен: {old_status} → {new_status} ({timestamp})")
                    
                    elif log.action_type == ActionType.TICKET_ASSIGNED:
                        details = log.action_details or {}
                        
                        # Check if this is a transfer (has source_staff_id)
                        if 'source_staff_id' in details:
                            # This is a transfer
                            source_id = details.get('source_staff_id')
                            target_id = details.get('target_staff_id') or log.staff_id
                            
                            # Get source employee name
                            if source_id:
                                source_stmt = select(Staff_Member).where(Staff_Member.tg_user_id == source_id)
                                source_result = await session.execute(source_stmt)
                                source_staff = source_result.scalar_one_or_none()
                                source_name = source_staff.full_name if source_staff else "Неизвестно"
                            else:
                                source_name = "Неизвестно"
                            
                            # Get target employee name
                            if target_id:
                                target_stmt = select(Staff_Member).where(Staff_Member.tg_user_id == target_id)
                                target_result = await session.execute(target_stmt)
                                target_staff = target_result.scalar_one_or_none()
                                target_name = target_staff.full_name if target_staff else "Неизвестно"
                            else:
                                target_name = "Неизвестно"
                            
                            lines.append(f"🔄 Тикет передан: {source_name} → {target_name} ({timestamp})")
                        else:
                            # This is an initial assignment
                            staff_id = log.staff_id
                            if staff_id:
                                staff_stmt = select(Staff_Member).where(Staff_Member.tg_user_id == staff_id)
                                staff_result = await session.execute(staff_stmt)
                                staff = staff_result.scalar_one_or_none()
                                staff_name = staff.full_name if staff else "Неизвестно"
                            else:
                                staff_name = "Неизвестно"
                            
                            lines.append(f"✅ Тикет назначен: {staff_name} ({timestamp})")
                    
                    elif log.action_type == ActionType.TICKET_CLOSED:
                        lines.append(f"✅ Тикет закрыт ({timestamp})")
                    
                    lines.append("")
        
        # Add pagination info if there are more pages
        if has_more_pages:
            lines.append(f"📄 Страница {page + 1} (есть еще)")
        elif page > 0:
            lines.append(f"📄 Страница {page + 1} (последняя)")
        
        history_text = "\n".join(lines)
        
        logger.info(
            f"Formatted ticket history: ticket_id={ticket_id}, page={page}, "
            f"items_on_page={len(page_items)}, has_more={has_more_pages}"
        )
        
        return history_text, has_more_pages
        
    except Exception as e:
        logger.error(
            f"Error formatting ticket history: ticket_id={ticket_id}, page={page}, error={e}",
            exc_info=True
        )
        raise


# ========== Multi-Ticket Notification ==========


async def should_notify_non_focused_ticket(
    employee_id: int,
    ticket_id: int,
    fsm_storage: Any
) -> bool:
    """
    Check if employee should receive a notification for a non-focused ticket.
    
    Returns True if:
    - Employee is in focus mode on a different ticket
    - The incoming message is for a ticket they're assigned to but not focused on
    
    Args:
        employee_id: Telegram user ID of the employee
        ticket_id: Ticket ID receiving the message
        fsm_storage: FSM storage instance to check current focus state
    
    Returns:
        Boolean indicating if notification should be sent
    
    Requirements: 13.4
    """
    try:
        # This is a placeholder - actual implementation would need to:
        # 1. Get employee's current FSM state from storage
        # 2. Check if they're in focus mode
        # 3. Check if focused_ticket_id != ticket_id
        # 4. Return True if conditions met
        
        # For now, return False as this requires FSM storage access
        # which is better handled at the handler level
        return False
        
    except Exception as e:
        logger.error(
            f"Error checking non-focused notification: employee_id={employee_id}, "
            f"ticket_id={ticket_id}, error={e}",
            exc_info=True
        )
        return False


# ========== Archive Search ==========


async def search_closed_tickets(
    session: AsyncSession,
    search_criteria: str
) -> list[Ticket]:
    """
    Search closed tickets by criteria.
    
    Supports:
    - Ticket number (exact match) - format: "#123" or "123"
    - Client name (partial match) - any text without # or date format
    - Date range (format: "YYYY-MM-DD to YYYY-MM-DD" or "DD.MM.YYYY to DD.MM.YYYY")
    
    Returns tickets with status CLOSED or CANCELLED.
    
    Args:
        session: Database session
        search_criteria: Search string from user
    
    Returns:
        List of matching tickets
    
    Requirements: 11.2, 11.3, 11.4, 11.5
    """
    from datetime import datetime
    from sqlalchemy import select, or_, and_, func
    from database.models import Ticket, TicketStatus
    
    try:
        criteria = search_criteria.strip()
        logger.info(f"Searching closed tickets with criteria: {criteria}")
        
        # Base query for closed tickets
        query = (
            select(Ticket)
            .join(User, Ticket.tg_user_id == User.tg_user_id)
            .where(
                or_(
                    Ticket.ticket_status == TicketStatus.CLOSED,
                    Ticket.ticket_status == TicketStatus.CANCELLED
                )
            )
        )
        
        # Parse search criteria
        
        # 1. Check if it's a ticket number (starts with # or is numeric)
        if criteria.startswith("#"):
            ticket_num = criteria[1:].strip()
            if ticket_num.isdigit():
                query = query.where(Ticket.id == int(ticket_num))
                logger.info(f"Searching by ticket number: {ticket_num}")
        elif criteria.isdigit():
            query = query.where(Ticket.id == int(criteria))
            logger.info(f"Searching by ticket number: {criteria}")
        
        # 2. Check if it's a date range
        elif " to " in criteria.lower() or " по " in criteria.lower():
            # Support both English "to" and Russian "по"
            separator = " to " if " to " in criteria.lower() else " по "
            parts = criteria.lower().split(separator)
            
            if len(parts) == 2:
                try:
                    # Try parsing different date formats
                    date_from_str = parts[0].strip()
                    date_to_str = parts[1].strip()
                    
                    # Try YYYY-MM-DD format first
                    try:
                        date_from = datetime.strptime(date_from_str, "%Y-%m-%d")
                        date_to = datetime.strptime(date_to_str, "%Y-%m-%d")
                    except ValueError:
                        # Try DD.MM.YYYY format
                        date_from = datetime.strptime(date_from_str, "%d.%m.%Y")
                        date_to = datetime.strptime(date_to_str, "%d.%m.%Y")
                    
                    # Set time to end of day for date_to
                    date_to = date_to.replace(hour=23, minute=59, second=59)
                    
                    query = query.where(
                        and_(
                            Ticket.closed_at >= date_from,
                            Ticket.closed_at <= date_to
                        )
                    )
                    logger.info(f"Searching by date range: {date_from} to {date_to}")
                    
                except ValueError as e:
                    logger.warning(f"Failed to parse date range: {criteria}, error: {e}")
                    # If date parsing fails, treat as client name search
                    query = query.where(
                        func.lower(User.full_name).contains(criteria.lower())
                    )
                    logger.info(f"Date parse failed, searching by client name: {criteria}")
        
        # 3. Otherwise, treat as client name search
        else:
            query = query.where(
                func.lower(User.full_name).contains(criteria.lower())
            )
            logger.info(f"Searching by client name: {criteria}")
        
        # Order by closed_at descending (most recent first)
        query = query.order_by(Ticket.closed_at.desc())
        
        # Execute query
        result = await session.execute(query)
        tickets = list(result.scalars().all())
        
        logger.info(f"Found {len(tickets)} closed tickets matching criteria: {criteria}")
        return tickets
        
    except Exception as e:
        logger.error(
            f"Error searching closed tickets: criteria={search_criteria}, error={e}",
            exc_info=True
        )
        raise


async def format_archive_search_results(
    tickets: list[Ticket],
    session: AsyncSession
) -> str:
    """
    Format archive search results for display.
    
    Shows ticket number, type, client name, closed date, and final status.
    
    Args:
        tickets: List of tickets to format
        session: Database session
    
    Returns:
        Formatted text string
    
    Requirements: 11.3
    """
    try:
        if not tickets:
            return "Тикеты не найдены."
        
        result_lines = []
        
        for ticket in tickets:
            # Get user info
            user = await session.get(User, ticket.tg_user_id)
            client_name = user.full_name if user else "Неизвестный клиент"
            
            # Format ticket type
            ticket_type_str = "Счет" if ticket.ticket_type.value == "invoice" else "ТП"
            
            # Format status
            status_map = {
                "closed": "Закрыто",
                "cancelled": "Отменено"
            }
            status_str = status_map.get(ticket.ticket_status.value, ticket.ticket_status.value)
            
            # Format closed date
            closed_date_str = "Не указано"
            if ticket.closed_at:
                closed_date_str = ticket.closed_at.strftime("%d.%m.%Y %H:%M")
            
            # Build result line
            result_lines.append(
                f"#{ticket.id} | {ticket_type_str} | {client_name}\n"
                f"Закрыто: {closed_date_str} | Статус: {status_str}"
            )
        
        return "\n\n".join(result_lines)
        
    except Exception as e:
        logger.error(
            f"Error formatting archive search results: error={e}",
            exc_info=True
        )
        raise
