"""
Analytics service layer for admin panel statistics and metrics.

Provides async functions for ticket statistics aggregation, SLA metrics calculation,
stuck ticket identification, NPS metrics, and dashboard data aggregation.

Requirements: 1.1, 1.6, 1.10, 7.4, 13.1
"""

import logging
from datetime import datetime, timedelta
from typing import Any, TypedDict

import pytz
from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    Message,
    NPS_Response,
    Organization,
    Staff_Member,
    StaffRole,
    Ticket,
    TicketStatus,
    TicketType,
    User,
)

logger = logging.getLogger(__name__)


# ========== TypedDict Definitions ==========


class TicketStatistics(TypedDict):
    """Ticket counts by type for a period."""
    invoice: int
    technical_support: int
    renewal: int
    total: int


class SLAMetrics(TypedDict):
    """Average response times by department in minutes."""
    manager: float | None
    technical_support: float | None
    duty_engineer: float | None


class StuckTicketData(TypedDict):
    """Data for a single stuck ticket."""
    ticket_id: int
    user_name: str
    ticket_type: str
    elapsed_minutes: int
    organization_name: str | None


class NPSMetrics(TypedDict):
    """NPS survey metrics for a period."""
    average_score: float
    response_count: int


# ========== Helper Functions ==========


def calculate_period_dates(period: str) -> tuple[datetime, datetime]:
    """
    Calculate start and end dates for a period in Moscow timezone.
    
    Preconditions:
    - period is one of: "today", "week", "month"
    
    Postconditions:
    - Returns tuple of (start_date, end_date) as timezone-aware datetimes
    - Both dates use Europe/Moscow timezone
    - For "today": start is 00:00:00, end is 23:59:59 of current day
    - For "week": start is 7 days before current time, end is current time
    - For "month": start is 30 days before current time, end is current time
    
    Args:
        period: Period identifier ("today", "week", "month")
    
    Returns:
        Tuple of (start_date, end_date) as timezone-aware datetime objects
    
    Raises:
        ValueError: If period is not one of the valid values
    
    Requirements: 7.1, 7.2, 7.3, 7.4
    """
    moscow_tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(moscow_tz)
    
    if period == "today":
        # Start of day (00:00:00) to end of day (23:59:59)
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == "week":
        # Last 7 days
        start_date = now - timedelta(days=7)
        end_date = now
    elif period == "month":
        # Last 30 days
        start_date = now - timedelta(days=30)
        end_date = now
    else:
        error_msg = f"Invalid period: {period}. Must be 'today', 'week', or 'month'"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.debug(
        f"Period dates calculated: period={period}, "
        f"start={start_date.isoformat()}, end={end_date.isoformat()}"
    )
    
    return start_date, end_date


# ========== Ticket Statistics ==========


async def get_ticket_statistics(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime
) -> dict[str, int]:
    """
    Get ticket counts grouped by type for a period.
    
    Preconditions:
    - session is an active database session
    - start_date <= end_date
    - Both dates are timezone-aware (Moscow timezone)
    
    Postconditions:
    - Returns dict with keys: "invoice", "technical_support", "renewal", "total"
    - All values are non-negative integers
    - Returns zero for types with no tickets
    - Includes tickets in all statuses
    
    Args:
        session: Database session
        start_date: Period start (inclusive)
        end_date: Period end (inclusive)
    
    Returns:
        Dictionary with ticket counts by type:
        {
            "invoice": int,
            "technical_support": int,
            "renewal": int,
            "total": int
        }
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
    """
    try:
        logger.debug(
            f"Fetching ticket statistics: start={start_date.isoformat()}, "
            f"end={end_date.isoformat()}"
        )
        
        # Convert timezone-aware datetime to naive datetime for PostgreSQL
        # Database stores timestamps as TIMESTAMP WITHOUT TIME ZONE
        start_date_naive = start_date.replace(tzinfo=None)
        end_date_naive = end_date.replace(tzinfo=None)
        
        # Build query with CASE statements for grouping by ticket type
        stmt = select(
            func.count().label('total'),
            func.sum(
                case((Ticket.ticket_type == TicketType.INVOICE, 1), else_=0)
            ).label('invoice'),
            func.sum(
                case((Ticket.ticket_type == TicketType.TECHNICAL_SUPPORT, 1), else_=0)
            ).label('technical_support'),
            func.sum(
                case((Ticket.ticket_type == TicketType.RENEWAL, 1), else_=0)
            ).label('renewal')
        ).where(
            and_(
                Ticket.created_at >= start_date_naive,
                Ticket.created_at <= end_date_naive
            )
        )
        
        result = await session.execute(stmt)
        row = result.one()
        
        # Handle empty results by returning zeros
        stats = {
            "invoice": int(row.invoice or 0),
            "technical_support": int(row.technical_support or 0),
            "renewal": int(row.renewal or 0),
            "total": int(row.total or 0)
        }
        
        logger.info(
            f"Ticket statistics retrieved: total={stats['total']}, "
            f"invoice={stats['invoice']}, technical_support={stats['technical_support']}, "
            f"renewal={stats['renewal']}"
        )
        
        return stats
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in get_ticket_statistics: start={start_date.isoformat()}, "
            f"end={end_date.isoformat()}, error={e}",
            exc_info=True
        )
        raise


# ========== SLA Metrics ==========


async def get_sla_metrics(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime
) -> dict[str, float | None]:
    """
    Calculate average response time by staff role.
    
    Response time is measured from ticket creation to first staff message.
    
    Preconditions:
    - session is an active database session
    - start_date <= end_date
    - Both dates are timezone-aware (Moscow timezone)
    
    Postconditions:
    - Returns dict with keys: "manager", "technical_support", "duty_engineer"
    - Values are floats rounded to 2 decimal places (minutes)
    - Returns None for roles with no data
    - Excludes tickets with no staff messages
    
    Args:
        session: Database session
        start_date: Period start (inclusive)
        end_date: Period end (inclusive)
    
    Returns:
        Dictionary with average response times in minutes:
        {
            "manager": float | None,
            "technical_support": float | None,
            "duty_engineer": float | None
        }
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 1.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8
    """
    try:
        logger.debug(
            f"Fetching SLA metrics: start={start_date.isoformat()}, "
            f"end={end_date.isoformat()}"
        )
        
        # Convert timezone-aware datetime to naive datetime for PostgreSQL
        # Database stores timestamps as TIMESTAMP WITHOUT TIME ZONE
        start_date_naive = start_date.replace(tzinfo=None)
        end_date_naive = end_date.replace(tzinfo=None)
        
        # Subquery to get first staff message per ticket
        first_message_subq = (
            select(
                Message.ticket_id,
                func.min(Message.sent_at).label('first_response_at')
            )
            .where(Message.sender_type == 'STAFF')
            .group_by(Message.ticket_id)
            .subquery()
        )
        
        # Main query: calculate response time and group by staff role
        stmt = (
            select(
                Staff_Member.staff_role,
                func.avg(
                    func.extract('epoch', first_message_subq.c.first_response_at - Ticket.created_at) / 60
                ).label('avg_response_minutes')
            )
            .select_from(Ticket)
            .join(first_message_subq, Ticket.id == first_message_subq.c.ticket_id)
            .join(Staff_Member, Ticket.assigned_staff_id == Staff_Member.id)
            .where(
                and_(
                    Ticket.created_at >= start_date_naive,
                    Ticket.created_at <= end_date_naive
                )
            )
            .group_by(Staff_Member.staff_role)
        )
        
        result = await session.execute(stmt)
        rows = result.all()
        
        # Initialize all roles with None
        sla_metrics = {
            "manager": None,
            "technical_support": None,
            "duty_engineer": None
        }
        
        # Map StaffRole enum values to dictionary keys
        role_mapping = {
            StaffRole.MANAGER: "manager",
            StaffRole.TECHNICAL_SUPPORT: "technical_support",
            StaffRole.DUTY_ENGINEER: "duty_engineer"
        }
        
        # Populate metrics from query results, rounded to 2 decimal places
        for row in rows:
            role_key = role_mapping.get(row.staff_role)
            if role_key and row.avg_response_minutes is not None:
                sla_metrics[role_key] = round(float(row.avg_response_minutes), 2)
        
        logger.info(
            f"SLA metrics retrieved: manager={sla_metrics['manager']}, "
            f"technical_support={sla_metrics['technical_support']}, "
            f"duty_engineer={sla_metrics['duty_engineer']}"
        )
        
        return sla_metrics
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in get_sla_metrics: start={start_date.isoformat()}, "
            f"end={end_date.isoformat()}, error={e}",
            exc_info=True
        )
        raise


# ========== Stuck Tickets ==========


async def get_stuck_tickets(
    session: AsyncSession,
    threshold_minutes: int = 15
) -> list[dict[str, Any]]:
    """
    Identify tickets stuck in NEW status beyond threshold.
    
    Preconditions:
    - session is an active database session
    - threshold_minutes > 0
    
    Postconditions:
    - Returns list of dicts with ticket details
    - Only includes tickets with status NEW
    - Only includes tickets older than threshold_minutes
    - Ordered by created_at ascending (oldest first)
    - Limited to 20 results maximum
    - Returns empty list if no stuck tickets
    
    Args:
        session: Database session
        threshold_minutes: Age threshold in minutes (default: 15)
    
    Returns:
        List of dictionaries with stuck ticket details:
        [
            {
                "ticket_id": int,
                "user_name": str,
                "ticket_type": str,  # "invoice", "technical_support", "renewal"
                "elapsed_minutes": int,
                "organization_name": str | None
            },
            ...
        ]
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 1.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
    """
    try:
        logger.debug(f"Fetching stuck tickets: threshold={threshold_minutes} minutes")
        
        # Calculate threshold timestamp
        threshold_time = datetime.utcnow() - timedelta(minutes=threshold_minutes)
        
        # Build query with filters and eager loading
        stmt = (
            select(Ticket)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization)
            )
            .where(
                and_(
                    Ticket.ticket_status == TicketStatus.NEW,
                    Ticket.created_at < threshold_time
                )
            )
            .order_by(Ticket.created_at.asc())
            .limit(20)
        )
        
        result = await session.execute(stmt)
        tickets = result.scalars().all()
        
        # Convert to list of dicts with calculated elapsed time
        stuck_tickets = []
        current_time = datetime.utcnow()
        
        # Map TicketType enum to string keys
        type_mapping = {
            TicketType.INVOICE: "invoice",
            TicketType.TECHNICAL_SUPPORT: "technical_support",
            TicketType.RENEWAL: "renewal"
        }
        
        for ticket in tickets:
            # Calculate elapsed time in minutes
            elapsed_seconds = (current_time - ticket.created_at).total_seconds()
            elapsed_minutes = int(elapsed_seconds / 60)
            
            stuck_tickets.append({
                "ticket_id": ticket.id,
                "user_name": ticket.user.full_name if ticket.user else "Unknown",
                "ticket_type": type_mapping.get(ticket.ticket_type, "unknown"),
                "elapsed_minutes": elapsed_minutes,
                "organization_name": ticket.organization.organization_name if ticket.organization else None
            })
        
        logger.info(f"Stuck tickets retrieved: count={len(stuck_tickets)}")
        
        return stuck_tickets
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in get_stuck_tickets: threshold={threshold_minutes}, error={e}",
            exc_info=True
        )
        raise


# ========== NPS Metrics ==========


async def get_nps_metrics(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime
) -> dict[str, float]:
    """
    Calculate NPS metrics for a period.
    
    Queries the nps_responses table to calculate average NPS score and count
    of responses within the specified date range.
    
    Preconditions:
    - session is an active database session
    - start_date <= end_date
    - Both dates are timezone-aware (Moscow timezone)
    
    Postconditions:
    - Returns dict with keys: "average_score", "response_count"
    - average_score rounded to 1 decimal place
    - Returns zeros when no NPS data exists
    - Logs warning if NPS table doesn't exist
    
    Args:
        session: Database session
        start_date: Period start (inclusive)
        end_date: Period end (inclusive)
    
    Returns:
        Dictionary with NPS metrics:
        {
            "average_score": float,  # 0.0-10.0, rounded to 1 decimal
            "response_count": int
        }
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8
    """
    try:
        logger.debug(
            f"Fetching NPS metrics: start={start_date.isoformat()}, "
            f"end={end_date.isoformat()}"
        )
        
        # Check if NPS response table exists
        try:
            from sqlalchemy import inspect
            inspector = inspect(session.bind)
            tables = await session.run_sync(lambda sync_session: inspector.get_table_names())
            
            has_nps_table = 'nps_responses' in tables
            
        except Exception as e:
            logger.debug(f"Could not check for NPS table: {e}")
            has_nps_table = False
        
        if not has_nps_table:
            # No NPS response table exists - return placeholder values
            logger.warning(
                "NPS data requested but no NPS response table exists. "
                "Returning placeholder values (0.0, 0). "
                f"Period: {start_date.isoformat()} to {end_date.isoformat()}"
            )
            
            return {
                "average_score": 0.0,
                "response_count": 0
            }
        
        # Convert timezone-aware datetime to naive datetime for PostgreSQL
        # Database stores timestamps as TIMESTAMP WITHOUT TIME ZONE
        start_date_naive = start_date.replace(tzinfo=None)
        end_date_naive = end_date.replace(tzinfo=None)
        
        # Query NPS responses for the period
        stmt = (
            select(
                func.avg(NPS_Response.rating).label('avg_score'),
                func.count(NPS_Response.id).label('response_count')
            )
            .where(
                and_(
                    NPS_Response.responded_at >= start_date_naive,
                    NPS_Response.responded_at <= end_date_naive
                )
            )
        )
        
        result = await session.execute(stmt)
        row = result.one()
        
        # Handle empty results by returning zeros
        average_score = round(float(row.avg_score or 0.0), 1)
        response_count = int(row.response_count or 0)
        
        logger.info(
            f"NPS metrics retrieved: average_score={average_score}, "
            f"response_count={response_count}"
        )
        
        return {
            "average_score": average_score,
            "response_count": response_count
        }
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error in get_nps_metrics: start={start_date.isoformat()}, "
            f"end={end_date.isoformat()}, error={e}",
            exc_info=True
        )
        raise


# ========== Dashboard Aggregation ==========


async def get_dashboard_data(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime
) -> dict[str, Any]:
    """
    Aggregate all dashboard metrics in parallel.
    
    Executes all metric queries concurrently for optimal performance.
    
    Preconditions:
    - session is an active database session
    - start_date <= end_date
    - Both dates are timezone-aware (Moscow timezone)
    
    Postconditions:
    - Returns dict with all dashboard metrics
    - Completes within 3 seconds for typical datasets
    - Returns partial data if individual queries fail
    
    Args:
        session: Database session
        start_date: Period start (inclusive)
        end_date: Period end (inclusive)
    
    Returns:
        Dictionary with all metrics:
        {
            "ticket_stats": dict,
            "sla_metrics": dict,
            "stuck_tickets": list,
            "nps_metrics": dict
        }
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 12.6, 12.7
    """
    import asyncio
    
    try:
        logger.info(
            f"Aggregating dashboard data: start={start_date.isoformat()}, "
            f"end={end_date.isoformat()}"
        )
        
        # Execute all metric queries in parallel using asyncio.gather
        # return_exceptions=True allows partial results if individual queries fail
        results = await asyncio.gather(
            get_ticket_statistics(session, start_date, end_date),
            get_sla_metrics(session, start_date, end_date),
            get_stuck_tickets(session),
            get_nps_metrics(session, start_date, end_date),
            return_exceptions=True
        )
        
        # Unpack results
        ticket_stats, sla_metrics, stuck_tickets, nps_metrics = results
        
        # Handle individual query failures gracefully
        # If a query failed, use default empty values and log the error
        
        if isinstance(ticket_stats, Exception):
            logger.error(
                f"Failed to fetch ticket statistics: {ticket_stats}",
                exc_info=ticket_stats
            )
            ticket_stats = {
                "invoice": 0,
                "technical_support": 0,
                "renewal": 0,
                "total": 0
            }
        
        if isinstance(sla_metrics, Exception):
            logger.error(
                f"Failed to fetch SLA metrics: {sla_metrics}",
                exc_info=sla_metrics
            )
            sla_metrics = {
                "manager": None,
                "technical_support": None,
                "duty_engineer": None
            }
        
        if isinstance(stuck_tickets, Exception):
            logger.error(
                f"Failed to fetch stuck tickets: {stuck_tickets}",
                exc_info=stuck_tickets
            )
            stuck_tickets = []
        
        if isinstance(nps_metrics, Exception):
            logger.error(
                f"Failed to fetch NPS metrics: {nps_metrics}",
                exc_info=nps_metrics
            )
            nps_metrics = {
                "average_score": 0.0,
                "response_count": 0
            }
        
        # Construct dashboard data dictionary
        dashboard_data = {
            "ticket_stats": ticket_stats,
            "sla_metrics": sla_metrics,
            "stuck_tickets": stuck_tickets,
            "nps_metrics": nps_metrics
        }
        
        logger.info(
            f"Dashboard data aggregated successfully: "
            f"ticket_count={ticket_stats.get('total', 0)}, "
            f"stuck_count={len(stuck_tickets)}, "
            f"nps_responses={nps_metrics.get('response_count', 0)}"
        )
        
        return dashboard_data
        
    except Exception as e:
        # Catch any unexpected errors during aggregation
        logger.error(
            f"Unexpected error in get_dashboard_data: start={start_date.isoformat()}, "
            f"end={end_date.isoformat()}, error={e}",
            exc_info=True
        )
        raise
