"""
Query helper functions for common database operations.

Provides utilities for get_or_create, bulk inserts, eager loading,
and query performance logging.

Requirements: Query Optimization section
"""

import logging
import time
from typing import Any, Dict, List, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from database.models import (
    Base,
    User,
    Organization,
    GS_Key,
    Staff_Member,
    Ticket,
    Message,
    File_Attachment,
    Manager_Assignment
)

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=Base)


async def get_or_create(
    session: AsyncSession,
    model: Type[T],
    defaults: Dict[str, Any] | None = None,
    **kwargs
) -> tuple[T, bool]:
    """
    Get an existing record or create a new one if it doesn't exist.
    
    Args:
        session: Database session
        model: SQLAlchemy model class
        defaults: Default values for creation (if not found)
        **kwargs: Filter criteria for lookup
    
    Returns:
        Tuple of (instance, created) where created is True if new record was created
    
    Example:
        user, created = await get_or_create(
            session,
            User,
            defaults={'full_name': 'John Doe'},
            tg_user_id=123456,
            phone_number='+79991234567'
        )
    """
    # Try to find existing record
    stmt = select(model).filter_by(**kwargs)
    result = await session.execute(stmt)
    instance = result.scalar_one_or_none()
    
    if instance:
        return instance, False
    
    # Create new record
    params = kwargs.copy()
    if defaults:
        params.update(defaults)
    
    instance = model(**params)
    session.add(instance)
    await session.flush()
    
    logger.debug(f"Created new {model.__name__} with {kwargs}")
    return instance, True


async def bulk_insert(
    session: AsyncSession,
    model: Type[T],
    records: List[Dict[str, Any]],
    return_instances: bool = False
) -> List[T] | None:
    """
    Bulk insert multiple records efficiently.
    
    Args:
        session: Database session
        model: SQLAlchemy model class
        records: List of dictionaries with record data
        return_instances: Whether to return created instances (slower)
    
    Returns:
        List of created instances if return_instances=True, else None
    
    Example:
        users_data = [
            {'tg_user_id': 1, 'phone_number': '+79991111111'},
            {'tg_user_id': 2, 'phone_number': '+79992222222'},
        ]
        users = await bulk_insert(session, User, users_data, return_instances=True)
    """
    if not records:
        return [] if return_instances else None
    
    start_time = time.time()
    
    if return_instances:
        instances = [model(**record) for record in records]
        session.add_all(instances)
        await session.flush()
        
        elapsed = time.time() - start_time
        logger.info(
            f"Bulk inserted {len(records)} {model.__name__} records "
            f"with instances in {elapsed:.3f}s"
        )
        return instances
    else:
        # Use bulk_insert_mappings for better performance
        await session.run_sync(
            lambda sync_session: sync_session.bulk_insert_mappings(model, records)
        )
        
        elapsed = time.time() - start_time
        logger.info(
            f"Bulk inserted {len(records)} {model.__name__} records "
            f"in {elapsed:.3f}s"
        )
        return None


class EagerLoadHelper:
    """
    Helper class for common eager loading patterns.
    
    Provides pre-configured eager loading strategies for frequently
    accessed relationships to avoid N+1 query problems.
    """
    
    @staticmethod
    def load_user_with_organizations(stmt):
        """
        Eager load user with organizations.
        
        Args:
            stmt: SQLAlchemy select statement
        
        Returns:
            Modified statement with eager loading
        """
        return stmt.options(
            selectinload(User.organizations)
        )
    
    @staticmethod
    def load_user_with_keys(stmt):
        """
        Eager load user with GS keys.
        
        Args:
            stmt: SQLAlchemy select statement
        
        Returns:
            Modified statement with eager loading
        """
        return stmt.options(
            selectinload(User.gs_keys)
        )
    
    @staticmethod
    def load_user_full(stmt):
        """
        Eager load user with all common relationships.
        
        Args:
            stmt: SQLAlchemy select statement
        
        Returns:
            Modified statement with eager loading
        """
        return stmt.options(
            selectinload(User.organizations),
            selectinload(User.gs_keys),
            selectinload(User.manager_assignments)
        )
    
    @staticmethod
    def load_ticket_with_user(stmt):
        """
        Eager load ticket with user.
        
        Args:
            stmt: SQLAlchemy select statement
        
        Returns:
            Modified statement with eager loading
        """
        return stmt.options(
            joinedload(Ticket.user)
        )
    
    @staticmethod
    def load_ticket_with_staff(stmt):
        """
        Eager load ticket with assigned staff.
        
        Args:
            stmt: SQLAlchemy select statement
        
        Returns:
            Modified statement with eager loading
        """
        return stmt.options(
            joinedload(Ticket.assigned_staff)
        )
    
    @staticmethod
    def load_ticket_with_messages(stmt):
        """
        Eager load ticket with messages.
        
        Args:
            stmt: SQLAlchemy select statement
        
        Returns:
            Modified statement with eager loading
        """
        return stmt.options(
            selectinload(Ticket.messages)
        )
    
    @staticmethod
    def load_ticket_with_keys(stmt):
        """
        Eager load ticket with GS keys.
        
        Args:
            stmt: SQLAlchemy select statement
        
        Returns:
            Modified statement with eager loading
        """
        return stmt.options(
            selectinload(Ticket.gs_keys)
        )
    
    @staticmethod
    def load_ticket_full(stmt):
        """
        Eager load ticket with all common relationships.
        
        Args:
            stmt: SQLAlchemy select statement
        
        Returns:
            Modified statement with eager loading
        """
        return stmt.options(
            joinedload(Ticket.user),
            joinedload(Ticket.assigned_staff),
            joinedload(Ticket.organization),
            selectinload(Ticket.gs_keys),
            selectinload(Ticket.messages),
            selectinload(Ticket.file_attachments)
        )
    
    @staticmethod
    def load_staff_with_assignments(stmt):
        """
        Eager load staff member with manager assignments.
        
        Args:
            stmt: SQLAlchemy select statement
        
        Returns:
            Modified statement with eager loading
        """
        return stmt.options(
            selectinload(Staff_Member.manager_assignments)
        )
    
    @staticmethod
    def load_staff_with_tickets(stmt):
        """
        Eager load staff member with assigned tickets.
        
        Args:
            stmt: SQLAlchemy select statement
        
        Returns:
            Modified statement with eager loading
        """
        return stmt.options(
            selectinload(Staff_Member.tickets_assigned)
        )


class QueryPerformanceLogger:
    """
    Context manager for logging query performance.
    
    Logs query execution time and can warn about slow queries.
    """
    
    def __init__(
        self,
        query_name: str,
        slow_query_threshold: float = 1.0
    ):
        """
        Initialize query performance logger.
        
        Args:
            query_name: Descriptive name for the query
            slow_query_threshold: Threshold in seconds for slow query warning
        """
        self.query_name = query_name
        self.slow_query_threshold = slow_query_threshold
        self.start_time = None
    
    def __enter__(self):
        """Start timing the query."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Log query execution time."""
        elapsed = time.time() - self.start_time
        
        if elapsed >= self.slow_query_threshold:
            logger.warning(
                f"SLOW QUERY: {self.query_name} took {elapsed:.3f}s "
                f"(threshold: {self.slow_query_threshold}s)"
            )
        else:
            logger.debug(f"Query {self.query_name} took {elapsed:.3f}s")


async def get_user_with_full_context(
    session: AsyncSession,
    user_id: int
) -> User | None:
    """
    Get user with all commonly needed relationships loaded.
    
    Optimized query that loads user with organizations, keys, and manager
    assignments in a single database round-trip.
    
    Args:
        session: Database session
        user_id: Telegram user ID
    
    Returns:
        User instance with relationships loaded, or None if not found
    """
    with QueryPerformanceLogger("get_user_with_full_context"):
        stmt = select(User).where(User.tg_user_id == user_id)
        stmt = EagerLoadHelper.load_user_full(stmt)
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_ticket_with_full_context(
    session: AsyncSession,
    ticket_id: int
) -> Ticket | None:
    """
    Get ticket with all commonly needed relationships loaded.
    
    Optimized query that loads ticket with user, staff, organization,
    keys, messages, and attachments in minimal database round-trips.
    
    Args:
        session: Database session
        ticket_id: Ticket ID
    
    Returns:
        Ticket instance with relationships loaded, or None if not found
    """
    with QueryPerformanceLogger("get_ticket_with_full_context"):
        stmt = select(Ticket).where(Ticket.id == ticket_id)
        stmt = EagerLoadHelper.load_ticket_full(stmt)
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_active_tickets_for_user(
    session: AsyncSession,
    user_id: int,
    limit: int = 50
) -> List[Ticket]:
    """
    Get active tickets for a user with optimized loading.
    
    Args:
        session: Database session
        user_id: Telegram user ID
        limit: Maximum number of tickets to return
    
    Returns:
        List of active tickets with relationships loaded
    """
    with QueryPerformanceLogger("get_active_tickets_for_user"):
        from database.models import TicketStatus
        
        stmt = (
            select(Ticket)
            .where(Ticket.tg_user_id == user_id)
            .where(Ticket.ticket_status.in_([
                TicketStatus.NEW,
                TicketStatus.IN_PROGRESS,
                TicketStatus.WAITING_CLIENT
            ]))
            .order_by(Ticket.created_at.desc())
            .limit(limit)
        )
        
        stmt = EagerLoadHelper.load_ticket_with_staff(stmt)
        stmt = EagerLoadHelper.load_ticket_with_keys(stmt)
        
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_staff_assigned_tickets(
    session: AsyncSession,
    staff_id: int,
    limit: int = 50
) -> List[Ticket]:
    """
    Get tickets assigned to a staff member with optimized loading.
    
    Args:
        session: Database session
        staff_id: Staff member Telegram user ID
        limit: Maximum number of tickets to return
    
    Returns:
        List of assigned tickets with relationships loaded
    """
    with QueryPerformanceLogger("get_staff_assigned_tickets"):
        from database.models import TicketStatus
        
        stmt = (
            select(Ticket)
            .where(Ticket.assigned_staff_id == staff_id)
            .where(Ticket.ticket_status.in_([
                TicketStatus.NEW,
                TicketStatus.IN_PROGRESS,
                TicketStatus.WAITING_CLIENT
            ]))
            .order_by(Ticket.created_at.desc())
            .limit(limit)
        )
        
        stmt = EagerLoadHelper.load_ticket_with_user(stmt)
        stmt = EagerLoadHelper.load_ticket_with_keys(stmt)
        
        result = await session.execute(stmt)
        return list(result.scalars().all())
