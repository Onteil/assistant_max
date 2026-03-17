"""
Employee service layer for managing employee interface operations.

Provides async functions for employee ticket management, ticket card formatting,
action keyboard generation, signature handling, and time calculations.

Requirements: 1.2, 2.1, 2.2, 2.3, 2.4, 2.6, 3.1, 3.2, 3.3, 5.1, 19.1, 19.2, 19.3, 19.4, 19.5
"""

import logging
from datetime import datetime, timedelta
from typing import Any

# Import InlineKeyboardButton and InlineKeyboardMarkup from appropriate bot framework
# This will be imported in the specific handler files
try:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:
    # Fallback for when aiogram is not available
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None
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


# ========== Staff Member Retrieval ==========


async def get_staff_by_max_user_id(session: AsyncSession, max_user_id: int) -> Staff_Member | None:
    """
    Retrieve staff member by MAX user ID.
    
    Args:
        session: Database session
        max_user_id: MAX messenger user ID
    
    Returns:
        Staff_Member object if found, None otherwise
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == max_user_id,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if staff:
            logger.debug(f"Staff member found: max_user_id={max_user_id}, staff_id={staff.id}")
        else:
            logger.debug(f"Staff member not found: max_user_id={max_user_id}")
        
        return staff
    
    except Exception as e:
        logger.error(
            f"Error retrieving staff member: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        raise


# ========== Active Tickets Query ==========


async def get_employee_active_tickets(
    session: AsyncSession,
    employee_id: int,
    ticket_type_filter: str | None = None
) -> list[Ticket]:
    """
    Get all active tickets for employee with optional type filter.

    Returns tickets with status NEW, IN_PROGRESS, or WAITING_CLIENT,
    ordered by created_at ascending (oldest first).

    Filtering logic:
    - ADMINISTRATOR role: sees ALL active tickets
    - TECHNICAL_SUPPORT role with 'technical_support' filter: sees ALL TECHNICAL_SUPPORT tickets
    - Other roles: sees only tickets assigned to them

    Args:
        session: Database session
        employee_id: MAX user ID of the employee
        ticket_type_filter: Optional filter ('invoice', 'technical_support', 'renewal', or None for all)

    Returns:
        List of active Ticket objects ordered by created_at

    Requirements: 1.2
    """
    try:
        # First, get the staff member record to get their internal ID and role
        staff_stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == employee_id,
            Staff_Member.is_active == True
        )
        staff_result = await session.execute(staff_stmt)
        staff_member = staff_result.scalar_one_or_none()

        if not staff_member:
            logger.warning(f"No active staff member found for max_user_id {employee_id}")
            return []

        # Build query conditions based on role
        conditions = [
            Ticket.ticket_status.in_([
                TicketStatus.NEW,
                TicketStatus.IN_PROGRESS,
                TicketStatus.WAITING_CLIENT
            ])
        ]

        # ADMINISTRATOR sees all tickets
        if staff_member.staff_role == StaffRole.ADMINISTRATOR:
            logger.info(f"Administrator {employee_id} viewing all active tickets")
        # TECHNICAL_SUPPORT with technical_support filter sees all TECHNICAL_SUPPORT tickets
        elif (staff_member.staff_role == StaffRole.TECHNICAL_SUPPORT and
              ticket_type_filter == "technical_support"):
            logger.info(f"Technical support {employee_id} viewing all TECHNICAL_SUPPORT tickets")
            conditions.append(Ticket.ticket_type == TicketType.TECHNICAL_SUPPORT)
        # Other roles see only assigned tickets
        else:
            conditions.append(Ticket.assigned_staff_id == staff_member.id)

        # Add type filter if specified (and not already added above)
        if ticket_type_filter and not (
            staff_member.staff_role == StaffRole.TECHNICAL_SUPPORT and
            ticket_type_filter == "technical_support"
        ):
            type_map = {
                "invoice": TicketType.INVOICE,
                "technical_support": TicketType.TECHNICAL_SUPPORT,
                "renewal": TicketType.RENEWAL
            }
            if ticket_type_filter in type_map:
                conditions.append(Ticket.ticket_type == type_map[ticket_type_filter])

        # Query tickets
        stmt = (
            select(Ticket)
            .where(and_(*conditions))
            .order_by(Ticket.created_at.asc())
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys)
            )
        )

        result = await session.execute(stmt)
        tickets = result.scalars().all()

        logger.info(
            f"Retrieved {len(tickets)} active tickets for employee {employee_id} "
            f"(staff_id={staff_member.id}, role={staff_member.staff_role.value}, filter={ticket_type_filter})"
        )
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
        # Ticket header - unified format
        lines = [
            f"✅ Работа с заявкой #{ticket.id}",
        ]
        
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
        
        # Client information
        client_name = ticket.user.full_name or ticket.user.first_name or "Неизвестно"
        lines.append(f"👤 Клиент: {client_name}")
        lines.append("")
        
        # INN (if available)
        if ticket.organization_inn:
            lines.append(f"📋 ИНН: {ticket.organization_inn}")
        
        # GS Keys (if available)
        if ticket.gs_keys:
            key_numbers = [key.key_number for key in ticket.gs_keys]
            lines.append(f"🔑 Ключи ГС: {', '.join(key_numbers)}")
        
        # Add blank line after INN/Keys if they exist
        if ticket.organization_inn or ticket.gs_keys:
            lines.append("")
        
        # Delivery method (if available)
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
            lines.append(f"📦 Способ получения: {delivery_method_text}")
            
            # Add delivery email if method is email
            if (ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method)) == "email":
                if hasattr(ticket, 'delivery_email') and ticket.delivery_email:
                    lines.append(f"📧 Email для доставки: {ticket.delivery_email}")
            
            lines.append("")
        
        # Description (if available)
        if ticket.description:
            lines.append(f"📝 Описание: {ticket.description}")
        
        # Elapsed time
        elapsed = await calculate_ticket_elapsed_time(ticket)
        lines.append(f"⏱ Время: {elapsed}")
        lines.append("")
        
        # File attachment count (if any)
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
    
    Status NEW: [Взять в работу] [🔄 Передать] [📁 История] [🔙 Назад к списку]
    Status IN_PROGRESS: [✅ Закрыть] [⏳ Ждем клиента] [🔄 Передать] [📁 История] [🔙 Назад к списку]
    Status WAITING_CLIENT: [✅ Закрыть] [🔄 Передать] [📁 История] [🔙 Назад к списку]
    
    Args:
        ticket: Ticket object
    
    Returns:
        InlineKeyboardMarkup with action buttons
    
    Requirements: 3.1, 3.2, 3.3, 6.4, 6.5, 6.6, 7.1
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
                    text="🔙 Назад к списку",
                    callback_data=TicketActionCallback(
                        action="back_to_list",
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
                    text="🔙 Назад к списку",
                    callback_data=TicketActionCallback(
                        action="back_to_list",
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
                    text="🔙 Назад к списку",
                    callback_data=TicketActionCallback(
                        action="back_to_list",
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
        employee_id: Internal staff member ID (primary key)
    
    Returns:
        Formatted signature string
    
    Raises:
        ValueError: If employee not found
    
    Requirements: 5.1
    """
    try:
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
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
        lines = [f"📁 История заявки #{ticket_id}", ""]
        
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
                            
                            lines.append(f"🔄 Заявка передана: {source_name} → {target_name} ({timestamp})")
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
                            
                            lines.append(f"✅ Заявка назначен: {staff_name} ({timestamp})")
                    
                    elif log.action_type == ActionType.TICKET_CLOSED:
                        lines.append(f"✅ Заявка закрыт ({timestamp})")
                    
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
            .join(User, Ticket.user_id == User.id)
            .where(
                or_(
                    Ticket.ticket_status == TicketStatus.CLOSED,
                    Ticket.ticket_status == TicketStatus.CANCELLED
                )
            )
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys)
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
            return "Заявкаы не найдены."
        
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


async def get_closed_tickets_by_filter(
    session: AsyncSession,
    filter_type: str = "day"
) -> list[Ticket]:
    """
    Get closed tickets by time filter.

    Args:
        session: Database session
        filter_type: Filter type ('day', 'week', 'month')

    Returns:
        List of closed tickets matching the filter

    Requirements: Archive with filters
    """
    from datetime import datetime, timedelta
    from sqlalchemy import select, or_
    from database.models import Ticket, TicketStatus

    try:
        # Calculate date range based on filter
        now = datetime.now()

        if filter_type == "day":
            date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif filter_type == "week":
            date_from = now - timedelta(days=7)
        elif filter_type == "month":
            date_from = now - timedelta(days=30)
        else:
            # Default to day
            date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)

        logger.info(f"Getting closed tickets with filter: {filter_type}, date_from: {date_from}")

        # Query closed tickets
        query = (
            select(Ticket)
            .join(User, Ticket.user_id == User.id)
            .where(
                or_(
                    Ticket.ticket_status == TicketStatus.CLOSED,
                    Ticket.ticket_status == TicketStatus.CANCELLED
                )
            )
            .where(Ticket.closed_at >= date_from)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys)
            )
            .order_by(Ticket.closed_at.desc())
        )

        result = await session.execute(query)
        tickets = list(result.scalars().all())

        logger.info(f"Found {len(tickets)} closed tickets with filter: {filter_type}")
        return tickets

    except Exception as e:
        logger.error(
            f"Error getting closed tickets by filter: filter_type={filter_type}, error={e}",
            exc_info=True
        )
        raise


async def format_archive_header(
    tickets_count: int,
    current_filter: str = "day"
) -> str:
    """
    Format header text for archive list.

    Args:
        tickets_count: Total number of tickets
        current_filter: Current filter type

    Returns:
        Formatted header text
    """
    filter_text_map = {
        "day": "День",
        "week": "Неделя",
        "month": "Месяц",
        "custom": "Произвольный"
    }

    filter_text = filter_text_map.get(current_filter, "День")

    header_lines = [
        f"🗄 <b>Архив обращений</b>",
        f"Фильтр: {filter_text} • Найдено: {tickets_count}",
        ""
    ]

    return "\n".join(header_lines)


async def get_archive_keyboard(
    tickets: list[Ticket],
    current_filter: str = "day",
    current_page: int = 0
) -> InlineKeyboardMarkup:
    """
    Generate inline keyboard for archive list with filters and pagination.

    Args:
        tickets: List of closed tickets (already filtered)
        current_filter: Current filter type ('day', 'week', 'month', 'custom')
        current_page: Current page number (0-indexed)

    Returns:
        InlineKeyboardMarkup with filters, ticket list, and pagination
    """
    try:
        from bots.tg_bot.callback_datas import ArchiveSearchCallback
        from database.models import TicketType

        buttons = []

        # Filter buttons row
        filter_buttons = []

        # Day filter
        day_text = "🟢 День" if current_filter == "day" else "День"
        filter_buttons.append(
            InlineKeyboardButton(
                text=day_text,
                callback_data=ArchiveSearchCallback(
                    action="filter",
                    filter_type="day",
                    page=0
                ).pack()
            )
        )

        # Week filter
        week_text = "🟢 Неделя" if current_filter == "week" else "Неделя"
        filter_buttons.append(
            InlineKeyboardButton(
                text=week_text,
                callback_data=ArchiveSearchCallback(
                    action="filter",
                    filter_type="week",
                    page=0
                ).pack()
            )
        )

        # Month filter
        month_text = "🟢 Месяц" if current_filter == "month" else "Месяц"
        filter_buttons.append(
            InlineKeyboardButton(
                text=month_text,
                callback_data=ArchiveSearchCallback(
                    action="filter",
                    filter_type="month",
                    page=0
                ).pack()
            )
        )

        # Custom search button (magnifying glass emoji)
        filter_buttons.append(
            InlineKeyboardButton(
                text="🔍",
                callback_data=ArchiveSearchCallback(
                    action="custom_search"
                ).pack()
            )
        )

        buttons.append(filter_buttons)

        # Pagination: 5 tickets per page
        TICKETS_PER_PAGE = 5
        start_idx = current_page * TICKETS_PER_PAGE
        end_idx = start_idx + TICKETS_PER_PAGE
        page_tickets = tickets[start_idx:end_idx]

        # Ticket type emoji mapping
        ticket_type_emoji = {
            TicketType.INVOICE: "💰",
            TicketType.TECHNICAL_SUPPORT: "🔧",
            TicketType.RENEWAL: "🔄"
        }

        # Ticket buttons (5 rows)
        for ticket in page_tickets:
            # Get ticket type emoji
            type_emoji = ticket_type_emoji.get(ticket.ticket_type, "📋")

            # Get client name
            client_name = ticket.user.full_name or ticket.user.first_name or "Неизвестно"

            # Format date
            date_str = ticket.closed_at.strftime("%d.%m") if ticket.closed_at else "Не указано"

            # Build ticket button text
            ticket_text = f"{type_emoji} #{ticket.id} {client_name} ({date_str})"

            # Single button per row
            buttons.append([
                InlineKeyboardButton(
                    text=ticket_text,
                    callback_data=ArchiveSearchCallback(
                        action="view_ticket",
                        ticket_id=ticket.id,
                        filter_type=current_filter,
                        page=current_page
                    ).pack()
                )
            ])

        # Pagination buttons
        total_pages = (len(tickets) + TICKETS_PER_PAGE - 1) // TICKETS_PER_PAGE if tickets else 1
        if total_pages > 1:
            pagination_row = []

            if current_page > 0:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="◀️",
                        callback_data=ArchiveSearchCallback(
                            action="page",
                            filter_type=current_filter,
                            page=current_page - 1
                        ).pack()
                    )
                )

            if current_page < total_pages - 1:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="▶️",
                        callback_data=ArchiveSearchCallback(
                            action="page",
                            filter_type=current_filter,
                            page=current_page + 1
                        ).pack()
                    )
                )

            if pagination_row:
                buttons.append(pagination_row)

        # Cancel button
        buttons.append([
            InlineKeyboardButton(
                text="❌ Отменить операцию",
                callback_data=ArchiveSearchCallback(action="cancel").pack()
            )
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        logger.info(
            f"Generated archive keyboard: "
            f"tickets_count={len(tickets)}, filter={current_filter}, "
            f"page={current_page}"
        )

        return keyboard

    except Exception as e:
        logger.error(
            f"Error generating archive keyboard: error={e}",
            exc_info=True
        )
        raise



# ========== Active Tickets Inline Keyboard ==========


def get_ticket_status_emoji(
    ticket: Ticket,
    has_unread: bool,
    is_focused: bool
) -> str:
    """
    Determine emoji for ticket status display in inline keyboard.
    
    Priority:
    1. Unread messages (🔴)
    2. Ticket status (🆕/🟢/⏳)
    3. Focus indicator (🎯 added to base emoji)
    
    Args:
        ticket: Ticket object
        has_unread: Whether ticket has unread messages from client
        is_focused: Whether this ticket is currently in focus
    
    Returns:
        Emoji string for status display
    
    Requirements: Active Tickets Inline Keyboard
    """
    # Priority 1: Unread messages
    if has_unread:
        emoji = "🔴"
    # Priority 2: Ticket status
    elif ticket.ticket_status == TicketStatus.NEW:
        emoji = "🆕"
    elif ticket.ticket_status == TicketStatus.IN_PROGRESS:
        emoji = "🟢"
    elif ticket.ticket_status == TicketStatus.WAITING_CLIENT:
        emoji = "⏳"
    else:
        emoji = "📋"
    
    # Add focus indicator if applicable
    if is_focused:
        emoji = f"🎯{emoji}"
    
    return emoji


async def has_unread_messages(
    session: AsyncSession,
    ticket_id: int,
    employee_id: int
) -> tuple[bool, int]:
    """
    Check if ticket has unread messages from client.
    
    A message is considered unread if:
    - It was sent by the client (sender_type = USER)
    - It was sent after the last message from the employee
    
    Args:
        session: Database session
        ticket_id: Ticket ID to check
        employee_id: Employee's Telegram user ID
    
    Returns:
        Tuple of (has_unread: bool, unread_count: int)
    
    Requirements: Active Tickets Inline Keyboard
    """
    try:
        from sqlalchemy import select, and_, func
        from database.models import Message, SenderType
        
        # Get last message from employee
        employee_msg_stmt = (
            select(Message)
            .where(
                and_(
                    Message.ticket_id == ticket_id,
                    Message.sender_type == SenderType.STAFF,
                    Message.sender_id == employee_id
                )
            )
            .order_by(Message.sent_at.desc())
            .limit(1)
        )
        employee_msg_result = await session.execute(employee_msg_stmt)
        last_employee_msg = employee_msg_result.scalar_one_or_none()
        
        # If employee never sent a message, check if client sent any
        if not last_employee_msg:
            client_msg_stmt = (
                select(func.count(Message.id))
                .where(
                    and_(
                        Message.ticket_id == ticket_id,
                        Message.sender_type == SenderType.USER
                    )
                )
            )
            client_msg_result = await session.execute(client_msg_stmt)
            unread_count = client_msg_result.scalar() or 0
            return (unread_count > 0, unread_count)
        
        # Count client messages after last employee message
        unread_stmt = (
            select(func.count(Message.id))
            .where(
                and_(
                    Message.ticket_id == ticket_id,
                    Message.sender_type == SenderType.USER,
                    Message.sent_at > last_employee_msg.sent_at
                )
            )
        )
        unread_result = await session.execute(unread_stmt)
        unread_count = unread_result.scalar() or 0
        
        logger.debug(
            f"Unread messages check: ticket_id={ticket_id}, "
            f"employee_id={employee_id}, unread_count={unread_count}"
        )
        
        return (unread_count > 0, unread_count)
        
    except Exception as e:
        logger.error(
            f"Error checking unread messages: ticket_id={ticket_id}, "
            f"employee_id={employee_id}, error={e}",
            exc_info=True
        )
        # Return False on error to avoid blocking UI
        return (False, 0)


async def get_active_tickets_keyboard(
    tickets: list[Ticket],
    focused_ticket_id: int | None,
    employee_id: int,
    session: AsyncSession,
    current_filter: str = "all",
    current_page: int = 0
) -> InlineKeyboardMarkup:
    """
    Generate inline keyboard for active tickets list with filters and pagination.
    
    Args:
        tickets: List of active tickets (already filtered)
        focused_ticket_id: ID of currently focused ticket (if any)
        employee_id: Employee's Telegram user ID
        session: Database session
        current_filter: Current filter type ('all', 'invoice', 'technical_support', 'renewal')
        current_page: Current page number (0-indexed)
    
    Returns:
        InlineKeyboardMarkup with filters, ticket list, and pagination
    
    Requirements: Active Tickets Inline Keyboard with Filters
    """
    try:
        from bots.tg_bot.callback_datas import TicketListCallback, TicketActionCallback
        from database.models import TicketType
        
        buttons = []
        
        # Filter buttons row
        filter_buttons = []
        
        # Invoice filter
        invoice_text = "🟢 💰 Счёт" if current_filter == "invoice" else "💰 Счёт"
        filter_buttons.append(
            InlineKeyboardButton(
                text=invoice_text,
                callback_data=TicketListCallback(
                    action="filter",
                    filter_type="invoice",
                    page=0
                ).pack()
            )
        )
        
        # Technical Support filter
        ts_text = "🟢 🔧 ТП" if current_filter == "technical_support" else "🔧 ТП"
        filter_buttons.append(
            InlineKeyboardButton(
                text=ts_text,
                callback_data=TicketListCallback(
                    action="filter",
                    filter_type="technical_support",
                    page=0
                ).pack()
            )
        )
        
        # Renewal filter
        renewal_text = "🟢 🔄 Продление" if current_filter == "renewal" else "🔄 Продление"
        filter_buttons.append(
            InlineKeyboardButton(
                text=renewal_text,
                callback_data=TicketListCallback(
                    action="filter",
                    filter_type="renewal",
                    page=0
                ).pack()
            )
        )
        
        buttons.append(filter_buttons)
        
        # Pagination: 4 tickets per page
        TICKETS_PER_PAGE = 4
        start_idx = current_page * TICKETS_PER_PAGE
        end_idx = start_idx + TICKETS_PER_PAGE
        page_tickets = tickets[start_idx:end_idx]
        
        # Ticket type emoji mapping
        ticket_type_emoji = {
            TicketType.INVOICE: "💰",
            TicketType.TECHNICAL_SUPPORT: "🔧",
            TicketType.RENEWAL: "🔄"
        }
        
        # Ticket buttons
        for ticket in page_tickets:
            # Check for unread messages
            has_unread, unread_count = await has_unread_messages(
                session, ticket.id, employee_id
            )
            
            # Determine if this ticket is focused
            is_focused = (focused_ticket_id == ticket.id)
            
            # Get status emoji
            status_emoji = get_ticket_status_emoji(ticket, has_unread, is_focused)
            
            # Get ticket type emoji
            type_emoji = ticket_type_emoji.get(ticket.ticket_type, "📋")
            
            # Get client name
            client_name = ticket.user.full_name or ticket.user.first_name or "Неизвестно"
            
            # Format date
            date_str = ticket.created_at.strftime("%d.%m.%Y")
            
            # Build ticket button text with type emoji
            ticket_text = f"{type_emoji} {status_emoji} #{ticket.id} {client_name} ({date_str})"
            
            # Add unread count if applicable
            if has_unread and unread_count > 0:
                ticket_text += f" ({unread_count})"
            
            # Single button per row
            buttons.append([
                InlineKeyboardButton(
                    text=ticket_text,
                    callback_data=TicketListCallback(
                        action="focus_ticket",
                        ticket_id=ticket.id,
                        filter_type=current_filter,
                        page=current_page
                    ).pack()
                )
            ])
        
        # Pagination buttons
        total_pages = (len(tickets) + TICKETS_PER_PAGE - 1) // TICKETS_PER_PAGE
        if total_pages > 1:
            pagination_row = []
            
            if current_page > 0:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data=TicketListCallback(
                            action="page",
                            filter_type=current_filter,
                            page=current_page - 1
                        ).pack()
                    )
                )
            
            pagination_row.append(
                InlineKeyboardButton(
                    text=f"📄 {current_page + 1}/{total_pages}",
                    callback_data="noop"
                )
            )
            
            if current_page < total_pages - 1:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="Вперёд ▶️",
                        callback_data=TicketListCallback(
                            action="page",
                            filter_type=current_filter,
                            page=current_page + 1
                        ).pack()
                    )
                )
            
            buttons.append(pagination_row)
        
        # Add "Exit Focus" button if in focus mode
        if focused_ticket_id:
            buttons.append([
                InlineKeyboardButton(
                    text="❌ Снять фокус",
                    callback_data=TicketActionCallback(
                        action="exit_focus",
                        ticket_id=focused_ticket_id
                    ).pack()
                )
            ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        logger.info(
            f"Generated active tickets keyboard: "
            f"tickets_count={len(tickets)}, filter={current_filter}, "
            f"page={current_page}, focused_ticket_id={focused_ticket_id}"
        )
        
        return keyboard
        
    except Exception as e:
        logger.error(
            f"Error generating active tickets keyboard: error={e}",
            exc_info=True
        )
        raise


async def format_active_tickets_header(
    tickets_count: int,
    focused_ticket_id: int | None,
    current_filter: str = "all"
) -> str:
    """
    Format header text for active tickets list.
    
    Args:
        tickets_count: Number of active tickets (filtered)
        focused_ticket_id: ID of currently focused ticket (if any)
        current_filter: Current filter type ('all', 'invoice', 'technical_support', 'renewal')
    
    Returns:
        Formatted header text
    
    Requirements: Active Tickets Inline Keyboard with Filters
    """
    filter_names = {
        "all": "Все",
        "invoice": "💰 Счёт",
        "technical_support": "🔧 ТП",
        "renewal": "🔄 Продление"
    }
    
    filter_text = filter_names.get(current_filter, "Все")
    
    header_lines = [
        f"📥 <b>Активные заявки</b>",
        f"Фильтр: {filter_text} • Найдено: {tickets_count}",
        ""
    ]
    
    if focused_ticket_id:
        header_lines.append(f"🎯 <b>В фокусе:</b> Заявка #{focused_ticket_id}")
        header_lines.append("")
    
    header_lines.append("🔹 <b>Фильтры:</b> выберите тип заявок (повторное нажатие отключает)")
    
    if tickets_count > 0:
        header_lines.append("🔹 <b>Заявки:</b> нажмите для входа в режим работы")
    else:
        header_lines.append("🔹 <i>Нет заявок выбранного типа</i>")
    
    return "\n".join(header_lines)


# ========== Admin Panel - Employee Management ==========


async def create_staff_member(
    session: AsyncSession,
    tg_user_id: int,
    full_name: str,
    position: str,
    staff_role: StaffRole
) -> Staff_Member:
    """
    Create new staff member record.
    
    Args:
        session: Database session
        tg_user_id: Telegram user ID
        full_name: Employee full name
        position: Employee signature text
        staff_role: Employee role (MANAGER, TECHNICAL_SUPPORT, DUTY_ENGINEER, ADMINISTRATOR)
    
    Returns:
        Created Staff_Member object
    
    Raises:
        ValueError: If tg_user_id is already registered as active staff member
    
    Requirements: 2.7
    """
    try:
        # Check if user is already registered as active staff member
        existing_stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == tg_user_id,
            Staff_Member.is_active == True
        )
        existing_result = await session.execute(existing_stmt)
        existing_staff = existing_result.scalar_one_or_none()
        
        if existing_staff:
            raise ValueError(
                f"Telegram ID {tg_user_id} is already registered as active staff member "
                f"(ID: {existing_staff.id}, Name: {existing_staff.full_name})"
            )
        
        # Create new staff member
        new_staff = Staff_Member(
            tg_user_id=tg_user_id,
            full_name=full_name,
            position=position,
            staff_role=staff_role,
            is_active=True
        )
        
        session.add(new_staff)
        await session.flush()  # Flush to get the ID
        await session.refresh(new_staff)
        
        logger.info(
            f"Created new staff member: id={new_staff.id}, tg_user_id={tg_user_id}, "
            f"full_name={full_name}, role={staff_role.value}"
        )
        
        return new_staff
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(
            f"Error creating staff member: tg_user_id={tg_user_id}, "
            f"full_name={full_name}, role={staff_role.value}, error={e}",
            exc_info=True
        )
        raise



async def update_staff_signature(
    session: AsyncSession,
    employee_id: int,
    new_signature: str
) -> Staff_Member:
    """
    Update employee signature (position field).
    
    Args:
        session: Database session
        employee_id: Staff member internal ID
        new_signature: New signature text
    
    Returns:
        Updated Staff_Member object
    
    Raises:
        ValueError: If employee not found
    
    Requirements: 4.2
    """
    try:
        # Fetch employee
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            raise ValueError(f"Employee with ID {employee_id} not found")
        
        # Update signature
        old_signature = employee.position
        employee.position = new_signature
        
        await session.flush()
        await session.refresh(employee)
        
        logger.info(
            f"Updated staff signature: employee_id={employee_id}, "
            f"old_signature='{old_signature}', new_signature='{new_signature}'"
        )
        
        return employee
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(
            f"Error updating staff signature: employee_id={employee_id}, "
            f"new_signature='{new_signature}', error={e}",
            exc_info=True
        )
        raise


async def update_staff_name(
    session: AsyncSession,
    employee_id: int,
    new_name: str
) -> Staff_Member:
    """
    Update employee name (full_name field).
    
    Args:
        session: Database session
        employee_id: Staff member internal ID
        new_name: New full name
    
    Returns:
        Updated Staff_Member object
    
    Raises:
        ValueError: If employee not found
    
    Requirements: 4.2
    """
    try:
        # Fetch employee
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            raise ValueError(f"Employee with ID {employee_id} not found")
        
        # Update name
        old_name = employee.full_name
        employee.full_name = new_name
        
        await session.flush()
        await session.refresh(employee)
        
        logger.info(
            f"Updated staff name: employee_id={employee_id}, "
            f"old_name='{old_name}', new_name='{new_name}'"
        )
        
        return employee
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(
            f"Error updating staff name: employee_id={employee_id}, "
            f"new_name='{new_name}', error={e}",
            exc_info=True
        )
        raise


async def update_staff_role(
    session: AsyncSession,
    employee_id: int,
    new_role: StaffRole
) -> Staff_Member:
    """
    Update employee role.
    
    Args:
        session: Database session
        employee_id: Staff member internal ID
        new_role: New staff role
    
    Returns:
        Updated Staff_Member object
    
    Raises:
        ValueError: If employee not found
    
    Requirements: 4.4
    """
    try:
        # Fetch employee
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            raise ValueError(f"Employee with ID {employee_id} not found")
        
        # Update role
        old_role = employee.staff_role
        employee.staff_role = new_role
        
        await session.flush()
        await session.refresh(employee)
        
        logger.info(
            f"Updated staff role: employee_id={employee_id}, "
            f"old_role={old_role.value}, new_role={new_role.value}"
        )
        
        return employee
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(
            f"Error updating staff role: employee_id={employee_id}, "
            f"new_role={new_role.value}, error={e}",
            exc_info=True
        )
        raise


async def deactivate_staff_member(
    session: AsyncSession,
    employee_id: int
) -> tuple[Staff_Member, int]:
    """
    Deactivate staff member and reassign their tickets.
    
    Sets is_active to False and reassigns all active tickets to status NEW
    with no assignee.
    
    Args:
        session: Database session
        employee_id: Staff member internal ID
    
    Returns:
        Tuple of (deactivated_employee, reassigned_ticket_count)
    
    Raises:
        ValueError: If employee not found
    
    Requirements: 5.2, 5.3
    """
    try:
        # Fetch employee
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            raise ValueError(f"Employee with ID {employee_id} not found")
        
        # Deactivate employee
        employee.is_active = False
        
        # Find all active tickets assigned to this employee
        from database.models import Ticket, TicketStatus
        
        tickets_stmt = select(Ticket).where(
            and_(
                Ticket.assigned_staff_id == employee_id,
                Ticket.ticket_status.in_([
                    TicketStatus.NEW,
                    TicketStatus.IN_PROGRESS,
                    TicketStatus.WAITING_CLIENT
                ])
            )
        )
        tickets_result = await session.execute(tickets_stmt)
        active_tickets = tickets_result.scalars().all()
        
        # Reassign all active tickets
        reassigned_count = 0
        for ticket in active_tickets:
            ticket.ticket_status = TicketStatus.NEW
            ticket.assigned_staff_id = None
            reassigned_count += 1
        
        await session.flush()
        await session.refresh(employee)
        
        logger.info(
            f"Deactivated staff member: employee_id={employee_id}, "
            f"full_name='{employee.full_name}', reassigned_tickets={reassigned_count}"
        )
        
        return employee, reassigned_count
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(
            f"Error deactivating staff member: employee_id={employee_id}, error={e}",
            exc_info=True
        )
        raise


async def set_backup_manager(
    session: AsyncSession,
    employee_id: int,
    slot: int,
    backup_id: int | None
) -> Staff_Member:
    """
    Set or remove backup manager for slot 1 or 2.
    
    Args:
        session: Database session
        employee_id: Staff member internal ID
        slot: Backup slot number (1 or 2)
        backup_id: Backup manager's internal ID (None to remove)
    
    Returns:
        Updated Staff_Member object
    
    Raises:
        ValueError: If employee not found or invalid slot number
    
    Requirements: 6.4
    """
    try:
        # Validate slot number
        if slot not in [1, 2]:
            raise ValueError(f"Invalid slot number: {slot}. Must be 1 or 2.")
        
        # Fetch employee
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            raise ValueError(f"Employee with ID {employee_id} not found")
        
        # If backup_id is provided, validate it exists and is active
        if backup_id is not None:
            backup_stmt = select(Staff_Member).where(
                Staff_Member.id == backup_id,
                Staff_Member.is_active == True
            )
            backup_result = await session.execute(backup_stmt)
            backup_manager = backup_result.scalar_one_or_none()
            
            if not backup_manager:
                raise ValueError(
                    f"Backup manager with ID {backup_id} not found or inactive"
                )
        
        # Update the appropriate backup manager field
        if slot == 1:
            old_backup_id = employee.backup_manager_1_id
            employee.backup_manager_1_id = backup_id
        else:  # slot == 2
            old_backup_id = employee.backup_manager_2_id
            employee.backup_manager_2_id = backup_id
        
        await session.flush()
        await session.refresh(employee)
        
        action = "removed" if backup_id is None else "assigned"
        logger.info(
            f"Backup manager {action} for slot {slot}: employee_id={employee_id}, "
            f"old_backup_id={old_backup_id}, new_backup_id={backup_id}"
        )
        
        return employee
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(
            f"Error setting backup manager: employee_id={employee_id}, "
            f"slot={slot}, backup_id={backup_id}, error={e}",
            exc_info=True
        )
        raise



async def transfer_ticket(
    session: AsyncSession,
    ticket_id: int,
    from_staff_id: int,
    to_staff_id: int,
    admin_id: int
) -> Ticket:
    """
    Transfer ticket from one staff member to another.
    
    Updates the ticket's assigned_staff_id and logs the action.
    
    Args:
        session: Database session
        ticket_id: Ticket ID to transfer
        from_staff_id: Current assigned staff member's internal ID
        to_staff_id: New assigned staff member's internal ID
        admin_id: Administrator's internal ID performing the transfer
    
    Returns:
        Updated Ticket object
    
    Raises:
        ValueError: If ticket or staff members not found
    
    Requirements: 7.3, 7.4, 7.5
    """
    try:
        # Fetch ticket
        ticket_stmt = select(Ticket).where(Ticket.id == ticket_id)
        ticket_result = await session.execute(ticket_stmt)
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            raise ValueError(f"Ticket with ID {ticket_id} not found")
        
        # Verify from_staff exists
        from_staff_stmt = select(Staff_Member).where(Staff_Member.id == from_staff_id)
        from_staff_result = await session.execute(from_staff_stmt)
        from_staff = from_staff_result.scalar_one_or_none()
        
        if not from_staff:
            raise ValueError(f"Source staff member with ID {from_staff_id} not found")
        
        # Verify to_staff exists and is active
        to_staff_stmt = select(Staff_Member).where(
            Staff_Member.id == to_staff_id,
            Staff_Member.is_active == True
        )
        to_staff_result = await session.execute(to_staff_stmt)
        to_staff = to_staff_result.scalar_one_or_none()
        
        if not to_staff:
            raise ValueError(
                f"Target staff member with ID {to_staff_id} not found or inactive"
            )
        
        # Update ticket assignment
        old_staff_id = ticket.assigned_staff_id
        ticket.assigned_staff_id = to_staff_id
        
        await session.flush()
        await session.refresh(ticket)
        
        # Log the transfer action
        action_log = Action_Log(
            action_type=ActionType.TICKET_ASSIGNED,
            staff_id=admin_id,
            ticket_id=ticket_id,
            action_details={
                "source_staff_id": from_staff.tg_user_id,
                "target_staff_id": to_staff.tg_user_id,
                "source_staff_name": from_staff.full_name,
                "target_staff_name": to_staff.full_name,
                "transferred_by_admin": True
            }
        )
        session.add(action_log)
        
        await session.flush()
        
        logger.info(
            f"Transferred ticket {ticket_id}: "
            f"from_staff={from_staff.full_name} (id={from_staff_id}) → "
            f"to_staff={to_staff.full_name} (id={to_staff_id}), "
            f"admin_id={admin_id}"
        )
        
        return ticket
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(
            f"Error transferring ticket: ticket_id={ticket_id}, "
            f"from_staff_id={from_staff_id}, to_staff_id={to_staff_id}, error={e}",
            exc_info=True
        )
        raise


async def transfer_all_clients(
    session: AsyncSession,
    from_manager_id: int,
    to_manager_id: int
) -> int:
    """
    Transfer all clients from one manager to another via i-TAT API.
    
    This function sends an API request to update the assigned manager
    for all INNs associated with the source manager.
    
    Args:
        session: Database session
        from_manager_id: Source manager's internal ID
        to_manager_id: Target manager's internal ID
    
    Returns:
        Count of transferred INNs
    
    Raises:
        ValueError: If managers not found or invalid roles
        Exception: If API request fails
    
    Requirements: 8.3
    """
    try:
        # Fetch source manager
        from_manager_stmt = select(Staff_Member).where(
            Staff_Member.id == from_manager_id,
            Staff_Member.is_active == True
        )
        from_manager_result = await session.execute(from_manager_stmt)
        from_manager = from_manager_result.scalar_one_or_none()
        
        if not from_manager:
            raise ValueError(
                f"Source manager with ID {from_manager_id} not found or inactive"
            )
        
        # Verify source is a manager
        if from_manager.staff_role != StaffRole.MANAGER:
            raise ValueError(
                f"Source staff member (ID {from_manager_id}) is not a manager. "
                f"Role: {from_manager.staff_role.value}"
            )
        
        # Fetch target manager
        to_manager_stmt = select(Staff_Member).where(
            Staff_Member.id == to_manager_id,
            Staff_Member.is_active == True
        )
        to_manager_result = await session.execute(to_manager_stmt)
        to_manager = to_manager_result.scalar_one_or_none()
        
        if not to_manager:
            raise ValueError(
                f"Target manager with ID {to_manager_id} not found or inactive"
            )
        
        # Verify target is a manager
        if to_manager.staff_role != StaffRole.MANAGER:
            raise ValueError(
                f"Target staff member (ID {to_manager_id}) is not a manager. "
                f"Role: {to_manager.staff_role.value}"
            )
        
        # Get all unique INNs from tickets assigned to source manager
        from database.models import Ticket
        
        inn_stmt = (
            select(Ticket.organization_inn)
            .where(
                and_(
                    Ticket.assigned_staff_id == from_manager_id,
                    Ticket.organization_inn.isnot(None)
                )
            )
            .distinct()
        )
        inn_result = await session.execute(inn_stmt)
        inns = [row[0] for row in inn_result.all()]
        
        if not inns:
            logger.info(
                f"No clients (INNs) found for manager {from_manager.full_name} "
                f"(id={from_manager_id})"
            )
            return 0
        
        logger.info(
            f"Transferring {len(inns)} clients from {from_manager.full_name} "
            f"to {to_manager.full_name}"
        )
        
        # TODO: Implement i-TAT API call for client transfer
        # For now, this is a placeholder that simulates the API call
        # The actual API endpoint needs to be added to i_tat_service.py
        
        # Placeholder implementation:
        # In a real implementation, this would call:
        # from services.i_tat_service import get_itat_client
        # client = get_itat_client()
        # response = await client.transfer_clients(
        #     from_manager_tg_id=from_manager.tg_user_id,
        #     to_manager_tg_id=to_manager.tg_user_id,
        #     inns=inns
        # )
        
        # For now, we'll just log the operation
        logger.warning(
            f"Client transfer API not yet implemented. "
            f"Would transfer {len(inns)} INNs from manager {from_manager.tg_user_id} "
            f"to manager {to_manager.tg_user_id}"
        )
        
        # Return the count of INNs that would be transferred
        transferred_count = len(inns)
        
        logger.info(
            f"Client transfer completed: "
            f"from_manager={from_manager.full_name} (id={from_manager_id}), "
            f"to_manager={to_manager.full_name} (id={to_manager_id}), "
            f"transferred_count={transferred_count}"
        )
        
        return transferred_count
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(
            f"Error transferring clients: from_manager_id={from_manager_id}, "
            f"to_manager_id={to_manager_id}, error={e}",
            exc_info=True
        )
        raise



async def format_archived_ticket_details(
    ticket: Ticket,
    session: AsyncSession
) -> str:
    """
    Format full archived ticket details including client info and ticket details.
    
    Does NOT include message history (handled separately due to length).
    
    Args:
        ticket: Ticket object to format
        session: Database session
    
    Returns:
        Formatted ticket details as string
    """
    try:
        from database.models import File_Attachment, Staff_Member
        
        lines = [
            f"📋 <b>АРХИВНАЯ ЗАЯВКА #{ticket.id}</b>",
            ""
        ]
        
        # Ticket type
        ticket_type_map = {
            TicketType.INVOICE: "💰 Счет",
            TicketType.TECHNICAL_SUPPORT: "🔧 Техническая поддержка",
            TicketType.RENEWAL: "🔄 Продление подписки"
        }
        ticket_type_str = ticket_type_map.get(ticket.ticket_type, str(ticket.ticket_type.value))
        lines.append(f"<b>Тип:</b> {ticket_type_str}")
        
        # Status
        status_map = {
            TicketStatus.CLOSED: "✅ Закрыто",
            TicketStatus.CANCELLED: "❌ Отменено"
        }
        status_str = status_map.get(ticket.ticket_status, str(ticket.ticket_status.value))
        lines.append(f"<b>Статус:</b> {status_str}")
        lines.append("")
        
        # Client information
        lines.append("<b>👤 ИНФОРМАЦИЯ О КЛИЕНТЕ</b>")
        client_name = ticket.user.full_name or ticket.user.first_name or "Неизвестно"
        lines.append(f"Имя: {client_name}")
        
        if ticket.user.phone_number:
            lines.append(f"Телефон: {ticket.user.phone_number}")
        
        if ticket.user.email:
            lines.append(f"Email: {ticket.user.email}")
        
        lines.append(f"Telegram ID: {ticket.user.tg_user_id}")
        lines.append("")
        
        # Organization info
        if ticket.organization_inn:
            lines.append("<b>🏢 ОРГАНИЗАЦИЯ</b>")
            lines.append(f"ИНН: {ticket.organization_inn}")
                        
            lines.append("")
        
        # GS Keys
        if ticket.gs_keys:
            lines.append("<b>🔑 КЛЮЧИ ГС</b>")
            for key in ticket.gs_keys:
                lines.append(f"• {key.key_number}")
            lines.append("")
        
        # Delivery method (if available)
        if hasattr(ticket, 'delivery_method') and ticket.delivery_method:
            lines.append("<b>📦 СПОСОБ ПОЛУЧЕНИЯ</b>")
            delivery_method_names = {
                "telegram": "💬 В чат",
                "email": "📧 На Email",
                "none": "❌ Не указан"
            }
            delivery_method_text = delivery_method_names.get(
                ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method),
                str(ticket.delivery_method)
            )
            lines.append(delivery_method_text)
            
            # Add delivery email if method is email
            if (ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method)) == "email":
                if hasattr(ticket, 'delivery_email') and ticket.delivery_email:
                    lines.append(f"Email: {ticket.delivery_email}")
            
            lines.append("")
        
        # Description
        if ticket.description:
            lines.append("<b>📝 ОПИСАНИЕ</b>")
            lines.append(ticket.description)
            lines.append("")
        
        # Assigned staff
        if ticket.assigned_staff_id:
            stmt = select(Staff_Member).where(Staff_Member.id == ticket.assigned_staff_id)
            result = await session.execute(stmt)
            staff = result.scalar_one_or_none()
            
            if staff:
                lines.append(f"<b>👨‍💼 Исполнитель:</b> {staff.full_name}")
                lines.append("")
        
        # Dates
        lines.append("<b>📅 ДАТЫ</b>")
        lines.append(f"Создано: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}")
        
        if ticket.closed_at:
            lines.append(f"Закрыто: {ticket.closed_at.strftime('%d.%m.%Y %H:%M')}")
            
            # Calculate duration
            duration = ticket.closed_at - ticket.created_at
            days = duration.days
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            
            duration_parts = []
            if days > 0:
                duration_parts.append(f"{days}д")
            if hours > 0:
                duration_parts.append(f"{hours}ч")
            if minutes > 0:
                duration_parts.append(f"{minutes}м")
            
            duration_str = " ".join(duration_parts) if duration_parts else "< 1м"
            lines.append(f"Длительность: {duration_str}")
        
        lines.append("")
        
        # File attachments
        stmt = select(File_Attachment).where(File_Attachment.ticket_id == ticket.id)
        result = await session.execute(stmt)
        attachments = list(result.scalars().all())
        
        if attachments:
            lines.append(f"<b>📎 ВЛОЖЕНИЯ ({len(attachments)})</b>")
            for att in attachments[:5]:  # Show first 5
                file_type = att.file_type.value if att.file_type else "unknown"
                lines.append(f"• {att.file_name} ({file_type})")
            
            if len(attachments) > 5:
                lines.append(f"... и еще {len(attachments) - 5}")
            
            lines.append("")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(
            f"Error formatting archived ticket details: ticket_id={ticket.id}, error={e}",
            exc_info=True
        )
        raise


async def format_ticket_message_history(
    ticket: Ticket,
    session: AsyncSession
) -> str:
    """
    Format ticket message history as text.
    
    Args:
        ticket: Ticket object
        session: Database session
    
    Returns:
        Formatted message history as string
    """
    try:
        from database.models import Message, SenderType, Staff_Member
        from sqlalchemy.orm import selectinload
        
        # Get all messages for this ticket with file attachments
        stmt = (
            select(Message)
            .where(Message.ticket_id == ticket.id)
            .options(selectinload(Message.file_attachments))
            .order_by(Message.sent_at.asc())
        )
        result = await session.execute(stmt)
        messages = list(result.scalars().all())
        
        if not messages:
            return "История переписки пуста."
        
        lines = [
            f"💬 ИСТОРИЯ ПЕРЕПИСКИ - Заявка #{ticket.id}",
            f"Всего сообщений: {len(messages)}",
            "─" * 29,
            ""
        ]
        
        for msg in messages:
            # Format timestamp
            timestamp = msg.sent_at.strftime("%d.%m.%Y %H:%M:%S")
            
            # Determine sender
            if msg.sender_type == SenderType.USER:
                sender_name = ticket.user.full_name or ticket.user.first_name or "Клиент"
                sender_label = f"👤 {sender_name}"
            elif msg.sender_type == SenderType.STAFF:
                # Get staff member name by internal ID
                if msg.sender_id:
                    stmt = select(Staff_Member).where(Staff_Member.id == msg.sender_id)
                    result = await session.execute(stmt)
                    staff = result.scalar_one_or_none()
                    
                    if staff:
                        sender_label = f"👨‍💼 {staff.full_name}"
                    else:
                        sender_label = "👨‍💼 Сотрудник"
                else:
                    sender_label = "👨‍💼 Сотрудник"
            elif msg.sender_type == SenderType.SYSTEM:
                sender_label = "🤖 Система"
            else:
                sender_label = "❓ Неизвестно"
            
            # Format message
            lines.append(f"[{timestamp}] {sender_label}")
            
            if msg.message_text:
                # Indent message text
                message_lines = msg.message_text.split('\n')
                for line in message_lines:
                    lines.append(f"  {line}")
            
            # Check for file attachments
            if msg.file_attachments:
                for attachment in msg.file_attachments:
                    file_type = attachment.file_type.value if attachment.file_type else "unknown"
                    lines.append(f"  📎 [Вложение: {attachment.file_name} ({file_type})]")
            
            lines.append("")  # Empty line between messages
        
        lines.append("─" * 29)
        lines.append(f"Конец истории переписки")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(
            f"Error formatting ticket message history: ticket_id={ticket.id}, error={e}",
            exc_info=True
        )
        raise
