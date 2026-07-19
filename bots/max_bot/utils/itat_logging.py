"""
I-TAT API logging utilities for MAX bot.

This module provides helper functions to log ticket operations to I-TAT API
for audit trail and CRM integration.
"""

import logging
from typing import Optional

from database.models import Ticket, TicketType, TicketStatus, User
from services.itat_retry_helper import call_itat_with_managed_retry
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


async def log_ticket_to_itat(
    session: AsyncSession,
    ticket: Ticket,
    status: str,
    comment: Optional[str] = None,
    staff_id: Optional[int] = None
) -> bool:
    """
    Log ticket operation to I-TAT API.
    
    Args:
        session: Database session
        ticket: Ticket object
        status: Ticket status in Russian (e.g., "Новое", "В работе", "Закрыто")
        comment: Optional comment for the operation
        staff_id: Optional staff member ID (internal ID, not messenger ID)
    
    Returns:
        bool: True if logging was successful, False otherwise
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 7.1
    """
    try:
        # Get user with MAX messenger data (eager load to avoid lazy-load in async context)
        result = await session.execute(
            select(User)
            .options(selectinload(User.max_messenger_data))
            .where(User.id == ticket.user_id)
        )
        user = result.scalar_one_or_none()
        if not user or not user.max_messenger_data:
            logger.warning(
                f"Cannot log ticket to I-TAT: user has no MAX messenger data. "
                f"ticket_id={ticket.id}, user_id={ticket.user_id}"
            )
            return False
        
        # Map ticket type to API format
        # NOTE: i-TAT API only accepts: "Счет", "Техподдержка", "Продление", "Конфликт ключа", "Перенос номера"
        # CONSULTATION is mapped to "Техподдержка" since it's not a separate type in i-TAT API
        ticket_type_map = {
            TicketType.INVOICE: "Счет",
            TicketType.TECHNICAL_SUPPORT: "Техподдержка",
            TicketType.CONSULTATION: "Техподдержка",  # Mapped to Техподдержка (i-TAT doesn't have separate Consultation type)
            TicketType.RENEWAL: "Продление",
            TicketType.PHONE_CHANGE: "Перенос номера",
            TicketType.KEY_CONFLICT: "Конфликт ключа"
        }
        
        # Prepare API call parameters
        api_params = {
            "ticket_id": f"TKT_{ticket.id}",
            "messenger": "max",
            "user_id": user.max_messenger_data.max_user_id,
            "ticket_type": ticket_type_map.get(ticket.ticket_type, "Прочее"),
            "status": status,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "updated_at": (ticket.updated_at or ticket.created_at).isoformat() if (ticket.updated_at or ticket.created_at) else None
        }
        
        # Add optional parameters
        if comment:
            api_params["comment"] = comment
        
        # staff_id is now required by i-TAT API (as of 2026-03-24)
        # Use 0 for user/system actions when no staff member is involved
        if staff_id is not None:
            api_params["staff_id"] = staff_id
        else:
            api_params["staff_id"] = 0
        
        # Keep a transient API failure even if the ticket transaction rolls back later.
        api_result = await call_itat_with_managed_retry(
            operation="log_ticket",
            payload=api_params,
            user_id=user.id,
        )

        if api_result is None:
            logger.warning(
                f"Ticket log queued for i-TAT retry: ticket_id={ticket.id}, "
                f"status={status}, messenger=max"
            )
        else:
            logger.info(
                f"Ticket logged to I-TAT API: ticket_id={ticket.id}, "
                f"status={status}, messenger=max"
            )
        return True
        
    except Exception as e:
        # Log error but don't fail the operation
        logger.error(
            f"Failed to log ticket to I-TAT API: ticket_id={ticket.id}, "
            f"status={status}, error={e}",
            exc_info=True
        )
        return False


async def log_ticket_creation_to_itat(
    session: AsyncSession,
    ticket: Ticket
) -> bool:
    """
    Log ticket creation to I-TAT API.
    
    Args:
        session: Database session
        ticket: Created ticket object
    
    Returns:
        bool: True if logging was successful, False otherwise
    """
    description_preview = ""
    if ticket.description:
        description_preview = ticket.description[:100]
        if len(ticket.description) > 100:
            description_preview += "..."
    
    comment = f"Заявка создана через MAX бот. Описание: {description_preview or 'Не указано'}"
    
    # Use staff_id=0 for user-created tickets (i-TAT API requires this parameter)
    # 0 indicates "no staff member" or "system/user action"
    return await log_ticket_to_itat(
        session=session,
        ticket=ticket,
        status="Новое",
        comment=comment,
        staff_id=0
    )


async def log_ticket_status_change_to_itat(
    session: AsyncSession,
    ticket: Ticket,
    old_status: TicketStatus,
    new_status: TicketStatus,
    staff_id: Optional[int] = None,
    comment: Optional[str] = None
) -> bool:
    """
    Log ticket status change to I-TAT API.
    
    Args:
        session: Database session
        ticket: Ticket object
        old_status: Previous ticket status
        new_status: New ticket status
        staff_id: Staff member ID who performed the action
        comment: Optional comment for the status change
    
    Returns:
        bool: True if logging was successful, False otherwise
    """
    # Map status to Russian
    status_map = {
        TicketStatus.NEW: "Новое",
        TicketStatus.IN_PROGRESS: "В работе",
        TicketStatus.WAITING_CLIENT: "Ожидание клиента",
        TicketStatus.CLOSED: "Закрыто",
        TicketStatus.CANCELLED: "Отменено"
    }
    
    status_text = status_map.get(new_status, new_status.value)
    
    # Generate comment if not provided
    if not comment:
        old_status_text = status_map.get(old_status, old_status.value)
        comment = f"Статус изменен с '{old_status_text}' на '{status_text}'"
    
    return await log_ticket_to_itat(
        session=session,
        ticket=ticket,
        status=status_text,
        comment=comment,
        staff_id=staff_id
    )


async def log_ticket_assignment_to_itat(
    session: AsyncSession,
    ticket: Ticket,
    staff_id: int,
    action: str = "assigned"
) -> bool:
    """
    Log ticket assignment to I-TAT API.
    
    Args:
        session: Database session
        ticket: Ticket object
        staff_id: Staff member ID who was assigned or performed assignment
        action: Type of assignment action ("assigned", "transferred", "taken")
    
    Returns:
        bool: True if logging was successful, False otherwise
    """
    # Map status to Russian
    status_map = {
        TicketStatus.NEW: "Новое",
        TicketStatus.IN_PROGRESS: "В работе",
        TicketStatus.WAITING_CLIENT: "Ожидание клиента",
        TicketStatus.CLOSED: "Закрыто",
        TicketStatus.CANCELLED: "Отменено"
    }
    
    status_text = status_map.get(ticket.ticket_status, ticket.ticket_status.value)
    
    # Generate comment based on action
    action_comments = {
        "assigned": "Заявка назначена сотруднику",
        "transferred": "Заявка передана другому сотруднику", 
        "taken": "Заявка взята в работу"
    }
    
    comment = action_comments.get(action, f"Действие с заявкой: {action}")
    
    return await log_ticket_to_itat(
        session=session,
        ticket=ticket,
        status=status_text,
        comment=comment,
        staff_id=staff_id
    )
