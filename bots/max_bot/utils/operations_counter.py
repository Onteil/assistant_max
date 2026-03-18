"""
Operations Counter Utility for MAX Bot Admin Panel

Provides functions to count pending operations for admin panel display.
Used to show operation counters in admin panel menu and operations submenu.
"""

import logging
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    GS_Key, KeyConflictStatus, 
    Escalation, 
    Ticket, TicketType, TicketStatus
)

logger = logging.getLogger(__name__)


async def count_key_conflicts(session: AsyncSession) -> int:
    """
    Count pending key conflicts that need admin resolution.
    
    Args:
        session: Database session
        
    Returns:
        Number of keys with PENDING_REVIEW status
    """
    try:
        stmt = select(func.count(GS_Key.id)).where(
            GS_Key.conflict_status == KeyConflictStatus.PENDING_REVIEW
        )
        result = await session.execute(stmt)
        count = result.scalar() or 0
        logger.debug(f"Key conflicts count: {count}")
        return count
    except Exception as e:
        logger.error(f"Error counting key conflicts: {e}", exc_info=True)
        return 0


async def count_phone_changes(session: AsyncSession) -> int:
    """
    Count pending phone change requests that need admin review.
    
    Args:
        session: Database session
        
    Returns:
        Number of open phone change tickets
    """
    try:
        stmt = select(func.count(Ticket.id)).where(
            and_(
                Ticket.ticket_type == TicketType.PHONE_CHANGE,
                Ticket.ticket_status.in_([TicketStatus.NEW, TicketStatus.IN_PROGRESS])
            )
        )
        result = await session.execute(stmt)
        count = result.scalar() or 0
        logger.debug(f"Phone changes count: {count}")
        return count
    except Exception as e:
        logger.error(f"Error counting phone changes: {e}", exc_info=True)
        return 0


async def count_escalations(session: AsyncSession) -> int:
    """
    Count unresolved escalations that need admin attention.
    
    Args:
        session: Database session
        
    Returns:
        Number of unresolved escalations
    """
    try:
        stmt = select(func.count(Escalation.id)).where(
            Escalation.is_resolved == False
        )
        result = await session.execute(stmt)
        count = result.scalar() or 0
        logger.debug(f"Escalations count: {count}")
        return count
    except Exception as e:
        logger.error(f"Error counting escalations: {e}", exc_info=True)
        return 0


async def count_all_operations(session: AsyncSession) -> dict[str, int]:
    """
    Count all pending operations for admin panel display.
    
    Args:
        session: Database session
        
    Returns:
        Dictionary with operation counts:
        {
            'key_conflicts': int,
            'phone_changes': int, 
            'escalations': int,
            'total': int
        }
    """
    try:
        # Count all operations in parallel
        key_conflicts = await count_key_conflicts(session)
        phone_changes = await count_phone_changes(session)
        escalations = await count_escalations(session)
        
        total = key_conflicts + phone_changes + escalations
        
        counts = {
            'key_conflicts': key_conflicts,
            'phone_changes': phone_changes,
            'escalations': escalations,
            'total': total
        }
        
        logger.info(f"Operations counts: {counts}")
        return counts
        
    except Exception as e:
        logger.error(f"Error counting all operations: {e}", exc_info=True)
        return {
            'key_conflicts': 0,
            'phone_changes': 0,
            'escalations': 0,
            'total': 0
        }


def format_operation_counter(count: int) -> str:
    """
    Format operation counter for display in buttons.
    
    Args:
        count: Number of pending operations
        
    Returns:
        Formatted counter string (empty if 0, " (N)" if > 0)
    """
    if count > 0:
        return f" ({count})"
    return ""


def format_total_operations_indicator(total: int) -> str:
    """
    Format total operations indicator for admin panel menu text.
    
    Args:
        total: Total number of pending operations
        
    Returns:
        Formatted indicator string for menu text
    """
    if total > 0:
        return f" ⚠️ <b>{total}</b> активных операций"
    return ""