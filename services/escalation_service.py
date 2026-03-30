"""
Escalation service layer for managing ticket escalation operations.

Provides async functions for escalation CRUD operations, active escalation retrieval,
resolution tracking, and escalation statistics.

Requirements: 2.1, 2.2, 2.3, 3.2
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    Escalation,
    EscalationType,
    ResolutionAction,
    Staff_Member,
    StaffRole,
    Ticket,
    TicketStatus,
)

logger = logging.getLogger(__name__)


# ========== Escalation CRUD Operations ==========


async def create_escalation(
    session: AsyncSession,
    ticket_id: int,
    escalation_type: EscalationType
) -> Escalation:
    """
    Create new escalation record for a ticket.
    
    Preconditions:
    - session is an active database session
    - ticket_id exists in tickets table
    - escalation_type is a valid EscalationType value
    
    Postconditions:
    - New record created in escalations table
    - escalation.is_resolved = False
    - escalation.created_at set automatically
    - Returns Escalation object with populated id
    - Changes committed to database
    
    Args:
        session: Database session
        ticket_id: ID of the ticket to escalate
        escalation_type: Type of escalation (REMINDER_10MIN or ESCALATION_20MIN)
    
    Returns:
        Created Escalation object
    
    Raises:
        ValueError: If ticket not found or invalid escalation_type
        SQLAlchemyError: If database operation fails
    
    Requirements: 2.1, 2.2
    """
    try:
        # Validate ticket exists
        result = await session.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            error_msg = f"Ticket not found for escalation: ticket_id={ticket_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Create escalation
        escalation = Escalation(
            ticket_id=ticket_id,
            escalation_type=escalation_type,
            is_resolved=False
        )
        
        session.add(escalation)
        await session.flush()  # Get escalation.id
        
        logger.info(
            f"Escalation created: id={escalation.id}, ticket_id={ticket_id}, "
            f"type={escalation_type.value}"
        )
        
        return escalation
    
    except ValueError as e:
        logger.error(f"Validation error creating escalation: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error creating escalation: ticket_id={ticket_id}, "
            f"type={escalation_type.value}, error={e}",
            exc_info=True
        )
        raise


async def get_active_escalations(
    session: AsyncSession,
    limit: int = 50
) -> list[Escalation]:
    """
    Get list of active (unresolved) escalations.
    
    Preconditions:
    - session is an active database session
    - limit > 0 and limit <= 100
    
    Postconditions:
    - Returns list of Escalation objects
    - All objects have is_resolved = False
    - List sorted by created_at DESC (newest first)
    - Number of objects <= limit
    - Related objects loaded (ticket, ticket.user, ticket.assigned_staff)
    
    Args:
        session: Database session
        limit: Maximum number of escalations to return (default: 50)
    
    Returns:
        List of active Escalation objects with eager-loaded relationships
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 2.1, 2.2, 3.2
    """
    try:
        # Validate limit
        if limit <= 0 or limit > 100:
            logger.warning(f"Invalid limit value: {limit}, using default 50")
            limit = 50
        
        # Query active escalations with eager loading
        stmt = (
            select(Escalation)
            .where(Escalation.is_resolved == False)
            .order_by(desc(Escalation.created_at))
            .limit(limit)
            .options(
                selectinload(Escalation.ticket).selectinload(Ticket.user),
                selectinload(Escalation.ticket).selectinload(Ticket.assigned_staff),
                selectinload(Escalation.ticket).selectinload(Ticket.organization)
            )
        )
        
        result = await session.execute(stmt)
        escalations = result.scalars().all()
        
        logger.debug(
            f"Retrieved {len(escalations)} active escalations (limit={limit})"
        )
        
        return list(escalations)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error getting active escalations: limit={limit}, error={e}",
            exc_info=True
        )
        raise


async def get_escalation_by_ticket(
    session: AsyncSession,
    ticket_id: int
) -> Escalation | None:
    """
    Get active escalation for a specific ticket.
    
    Args:
        session: Database session
        ticket_id: Ticket ID to search for
    
    Returns:
        Active Escalation object or None if not found
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 2.1, 2.2
    """
    try:
        stmt = (
            select(Escalation)
            .where(
                and_(
                    Escalation.ticket_id == ticket_id,
                    Escalation.is_resolved == False
                )
            )
            .options(
                selectinload(Escalation.ticket).selectinload(Ticket.user),
                selectinload(Escalation.ticket).selectinload(Ticket.assigned_staff)
            )
        )
        
        result = await session.execute(stmt)
        escalation = result.scalar_one_or_none()
        
        if escalation:
            logger.debug(
                f"Found active escalation for ticket: ticket_id={ticket_id}, "
                f"escalation_id={escalation.id}"
            )
        else:
            logger.debug(f"No active escalation found for ticket: ticket_id={ticket_id}")
        
        return escalation
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error getting escalation by ticket: ticket_id={ticket_id}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def resolve_escalation(
    session: AsyncSession,
    escalation_id: int,
    resolved_by_staff_id: int,
    resolution_action: ResolutionAction
) -> Escalation:
    """
    Resolve an active escalation.
    
    Preconditions:
    - session is an active database session
    - escalation_id exists in escalations table
    - escalation.is_resolved = False (escalation is active)
    - resolved_by_staff_id exists in staff_members table
    - resolution_action is a valid ResolutionAction value
    
    Postconditions:
    - escalation.is_resolved = True
    - escalation.resolved_at set to current time
    - escalation.resolved_by_staff_id = resolved_by_staff_id
    - escalation.resolution_action = resolution_action
    - Returns updated Escalation object
    - Changes committed to database
    
    Args:
        session: Database session
        escalation_id: ID of the escalation to resolve
        resolved_by_staff_id: Internal staff ID of the admin resolving the escalation
        resolution_action: Action taken to resolve (REASSIGNED, TAKEN_OVER, etc.)
    
    Returns:
        Updated Escalation object
    
    Raises:
        ValueError: If escalation not found, already resolved, or staff not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 2.1, 2.3
    """
    try:
        # Get escalation
        result = await session.execute(
            select(Escalation).where(Escalation.id == escalation_id)
        )
        escalation = result.scalar_one_or_none()
        
        if not escalation:
            error_msg = f"Escalation not found: escalation_id={escalation_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Check if already resolved
        if escalation.is_resolved:
            error_msg = (
                f"Escalation already resolved: escalation_id={escalation_id}, "
                f"resolved_at={escalation.resolved_at}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Verify staff member exists
        staff_result = await session.execute(
            select(Staff_Member).where(Staff_Member.id == resolved_by_staff_id)
        )
        staff = staff_result.scalar_one_or_none()
        
        if not staff:
            error_msg = f"Staff member not found: staff_id={resolved_by_staff_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Resolve escalation
        escalation.is_resolved = True
        escalation.resolved_at = datetime.utcnow()
        escalation.resolved_by_staff_id = resolved_by_staff_id
        escalation.resolution_action = resolution_action
        escalation.updated_at = datetime.utcnow()
        
        await session.flush()
        
        logger.info(
            f"Escalation resolved: id={escalation_id}, ticket_id={escalation.ticket_id}, "
            f"resolved_by={resolved_by_staff_id}, action={resolution_action.value}"
        )
        
        return escalation
    
    except ValueError as e:
        logger.error(f"Validation error resolving escalation: {e}")
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error resolving escalation: escalation_id={escalation_id}, "
            f"resolved_by={resolved_by_staff_id}, error={e}",
            exc_info=True
        )
        raise



async def get_escalation_stats(
    session: AsyncSession,
    days: int = 7
) -> dict[str, Any]:
    """
    Get escalation statistics for a time period.
    
    Args:
        session: Database session
        days: Number of days to look back (default: 7)
    
    Returns:
        Dictionary with escalation statistics:
            - total_escalations: Total number of escalations created
            - active_escalations: Number of unresolved escalations
            - resolved_escalations: Number of resolved escalations
            - resolution_by_action: Count by resolution action type
            - avg_resolution_time_minutes: Average time to resolve (in minutes)
            - escalations_by_type: Count by escalation type
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 2.1, 2.2, 2.3
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Total escalations in period
        total_result = await session.execute(
            select(func.count(Escalation.id))
            .where(Escalation.created_at >= start_date)
        )
        total_escalations = total_result.scalar() or 0
        
        # Active escalations
        active_result = await session.execute(
            select(func.count(Escalation.id))
            .where(
                and_(
                    Escalation.created_at >= start_date,
                    Escalation.is_resolved == False
                )
            )
        )
        active_escalations = active_result.scalar() or 0
        
        # Resolved escalations
        resolved_escalations = total_escalations - active_escalations
        
        # Resolution by action type
        resolution_by_action_result = await session.execute(
            select(
                Escalation.resolution_action,
                func.count(Escalation.id)
            )
            .where(
                and_(
                    Escalation.created_at >= start_date,
                    Escalation.is_resolved == True
                )
            )
            .group_by(Escalation.resolution_action)
        )
        resolution_by_action = {
            action.value if action else "unknown": count
            for action, count in resolution_by_action_result.all()
        }
        
        # Average resolution time
        avg_time_result = await session.execute(
            select(
                func.avg(
                    func.extract(
                        'epoch',
                        Escalation.resolved_at - Escalation.created_at
                    )
                )
            )
            .where(
                and_(
                    Escalation.created_at >= start_date,
                    Escalation.is_resolved == True,
                    Escalation.resolved_at.isnot(None)
                )
            )
        )
        avg_seconds = avg_time_result.scalar()
        avg_resolution_time_minutes = round(avg_seconds / 60, 2) if avg_seconds else 0
        
        # Escalations by type
        by_type_result = await session.execute(
            select(
                Escalation.escalation_type,
                func.count(Escalation.id)
            )
            .where(Escalation.created_at >= start_date)
            .group_by(Escalation.escalation_type)
        )
        escalations_by_type = {
            esc_type.value: count
            for esc_type, count in by_type_result.all()
        }
        
        stats = {
            "period_days": days,
            "start_date": start_date.isoformat(),
            "total_escalations": total_escalations,
            "active_escalations": active_escalations,
            "resolved_escalations": resolved_escalations,
            "resolution_by_action": resolution_by_action,
            "avg_resolution_time_minutes": avg_resolution_time_minutes,
            "escalations_by_type": escalations_by_type
        }
        
        logger.info(
            f"Escalation stats calculated: period={days} days, "
            f"total={total_escalations}, active={active_escalations}"
        )
        
        return stats
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error getting escalation stats: days={days}, error={e}",
            exc_info=True
        )
        raise


# ========== Helper Functions ==========


async def get_staff_by_telegram_id(
    session: AsyncSession,
    telegram_id: int
) -> Staff_Member | None:
    """
    Get staff member by Telegram user ID.
    
    Helper function to retrieve staff member from Telegram ID.
    
    Args:
        session: Database session
        telegram_id: Telegram user ID
    
    Returns:
        Staff_Member object or None if not found
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        result = await session.execute(
            select(Staff_Member).where(Staff_Member.tg_user_id == telegram_id)
        )
        staff = result.scalar_one_or_none()
        
        if not staff:
            logger.warning(f"Staff member not found: telegram_id={telegram_id}")
        
        return staff
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error getting staff by telegram_id: telegram_id={telegram_id}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def get_active_admins(
    session: AsyncSession
) -> list[Staff_Member]:
    """
    Get all active administrators with messenger IDs (Telegram or MAX).
    
    Helper function to retrieve administrators for escalation notifications.
    Supports both Telegram and MAX messengers.
    
    Args:
        session: Database session
    
    Returns:
        List of active Staff_Member objects with ADMIN role and at least one messenger ID
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        stmt = select(Staff_Member).where(
            and_(
                Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
                Staff_Member.is_active == True,
                or_(
                    Staff_Member.tg_user_id.isnot(None),
                    Staff_Member.max_user_id.isnot(None),
                    Staff_Member.max_chat_id.isnot(None)
                )
            )
        )
        
        result = await session.execute(stmt)
        admins = result.scalars().all()
        
        logger.debug(f"Retrieved {len(admins)} active administrators")
        
        return list(admins)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error getting active admins: error={e}",
            exc_info=True
        )
        raise
