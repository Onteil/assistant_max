"""
Calendar Service

Business logic for calendar rule management and work mode determination.
Handles CRUD operations for schedule rules and determines current work mode.
"""

from datetime import date, time, datetime
from typing import List, Optional

from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Calendar_Rule, WorkMode


class CalendarService:
    """
    Service for managing calendar rules and determining work modes.
    """

    def _calculate_priority(self, start_date: date, end_date: date) -> int:
        """
        Calculate priority for a rule.
        
        Priority logic:
        - Single date rules (start_date == end_date): priority = 100
        - Date range rules: priority = 50
        
        Args:
            start_date: First date of the rule
            end_date: Last date of the rule
        
        Returns:
            Priority value (100 for single date, 50 for range)
        """
        if start_date == end_date:
            return 100
        else:
            return 50

    async def create_rule(
        self,
        session: AsyncSession,
        start_date: date,
        end_date: date,
        work_mode: WorkMode,
        work_start_time: Optional[time],
        work_end_time: Optional[time]
    ) -> Calendar_Rule:
        """
        Create a new schedule rule with automatic priority calculation.
        
        Args:
            session: Database session
            start_date: First date of the rule
            end_date: Last date of the rule
            work_mode: Work mode (REGULAR, EXTENDED, NON_WORKING)
            work_start_time: Start of work hours (nullable for NON_WORKING)
            work_end_time: End of work hours (nullable for NON_WORKING)
        
        Returns:
            Created Calendar_Rule instance
        """
        # Calculate priority automatically
        priority = self._calculate_priority(start_date, end_date)
        
        # Create rule instance
        rule = Calendar_Rule(
            start_date=start_date,
            end_date=end_date,
            work_mode=work_mode,
            work_start_time=work_start_time,
            work_end_time=work_end_time,
            rule_priority=priority
        )
        
        # Add to session and commit
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        
        return rule

    async def get_rules_for_date_range(
        self,
        session: AsyncSession,
        start_date: date,
        end_date: date
    ) -> List[Calendar_Rule]:
        """
        Get all rules that overlap with the specified date range.
        
        Overlap logic: A rule overlaps if:
        - rule.start_date <= end_date AND rule.end_date >= start_date
        
        Args:
            session: Database session
            start_date: Start of query range
            end_date: End of query range
        
        Returns:
            List of Calendar_Rule ordered by priority DESC, created_at DESC
        """
        # Query for overlapping rules
        stmt = (
            select(Calendar_Rule)
            .where(
                and_(
                    Calendar_Rule.start_date <= end_date,
                    Calendar_Rule.end_date >= start_date
                )
            )
            .order_by(
                Calendar_Rule.rule_priority.desc(),
                Calendar_Rule.created_at.desc()
            )
        )
        
        result = await session.execute(stmt)
        rules = result.scalars().all()
        
        return list(rules)

    async def get_all_rules(
        self,
        session: AsyncSession
    ) -> List[Calendar_Rule]:
        """
        Get all active rules ordered by priority and creation time.
        
        Args:
            session: Database session
        
        Returns:
            List of Calendar_Rule ordered by priority DESC, created_at DESC
        """
        stmt = (
            select(Calendar_Rule)
            .order_by(
                Calendar_Rule.rule_priority.desc(),
                Calendar_Rule.created_at.desc()
            )
        )
        
        result = await session.execute(stmt)
        rules = result.scalars().all()
        
        return list(rules)

    async def delete_rule(
        self,
        session: AsyncSession,
        rule_id: int
    ) -> bool:
        """
        Delete a specific rule by ID.
        
        Args:
            session: Database session
            rule_id: ID of the rule to delete
        
        Returns:
            True if deleted, False if not found
        """
        # Query for the rule
        stmt = select(Calendar_Rule).where(Calendar_Rule.id == rule_id)
        result = await session.execute(stmt)
        rule = result.scalar_one_or_none()
        
        if rule is None:
            return False
        
        # Delete the rule
        await session.delete(rule)
        await session.commit()
        
        return True

    async def delete_rules_in_period(
        self,
        session: AsyncSession,
        start_date: date,
        end_date: date
    ) -> int:
        """
        Delete all rules that overlap with the specified period.
        
        Args:
            session: Database session
            start_date: Start of period to clear
            end_date: End of period to clear
        
        Returns:
            Count of deleted rules
        """
        # Delete overlapping rules
        stmt = (
            delete(Calendar_Rule)
            .where(
                and_(
                    Calendar_Rule.start_date <= end_date,
                    Calendar_Rule.end_date >= start_date
                )
            )
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        # Return count of deleted rows
        return result.rowcount

    def _get_base_schedule_mode(
        self,
        dt: datetime
    ) -> tuple[WorkMode, Optional[time], Optional[time]]:
        """
        Get base schedule for a datetime.
        
        Base schedule:
        - Mon-Fri: 08:00-17:00 (REGULAR), 17:00-20:00 (EXTENDED)
        - Sat: 09:00-13:00 (EXTENDED)
        - Sun: NON_WORKING
        
        Args:
            dt: Datetime to check
        
        Returns:
            Tuple of (WorkMode, start_time, end_time)
        """
        # Get day of week (0=Monday, 6=Sunday)
        day_of_week = dt.weekday()
        current_time = dt.time()
        
        # Sunday - NON_WORKING
        if day_of_week == 6:
            return (WorkMode.NON_WORKING, None, None)
        
        # Saturday - EXTENDED 09:00-13:00
        elif day_of_week == 5:
            return (WorkMode.EXTENDED, time(9, 0), time(13, 0))
        
        # Monday-Friday
        else:
            # Check if in REGULAR hours (08:00-17:00)
            if time(8, 0) <= current_time < time(17, 0):
                return (WorkMode.REGULAR, time(8, 0), time(17, 0))
            # Check if in EXTENDED hours (17:00-20:00)
            elif time(17, 0) <= current_time < time(20, 0):
                return (WorkMode.EXTENDED, time(17, 0), time(20, 0))
            # Outside work hours
            else:
                return (WorkMode.NON_WORKING, None, None)

    async def get_work_mode_for_datetime(
        self,
        session: AsyncSession,
        dt: datetime
    ) -> WorkMode:
        """
        Determine work mode for a specific datetime.
        
        Logic:
        1. Query rules for the date
        2. If rules exist, apply highest priority rule
        3. If no rules, apply base schedule
        4. Check if current time falls within work hours
        
        Args:
            session: Database session
            dt: Datetime to check
        
        Returns:
            WorkMode enum
        """
        try:
            # Query rules for the specific date
            target_date = dt.date()
            rules = await self.get_rules_for_date_range(
                session,
                target_date,
                target_date
            )
            
            # If rules exist, use the highest priority rule (first in list)
            if rules:
                rule = rules[0]
                work_mode = rule.work_mode
                work_start = rule.work_start_time
                work_end = rule.work_end_time
                
                # If work mode is NON_WORKING, return immediately
                if work_mode == WorkMode.NON_WORKING:
                    return WorkMode.NON_WORKING
                
                # Check if current time falls within rule's work hours
                current_time = dt.time()
                if work_start and work_end:
                    if work_start <= current_time < work_end:
                        # Within rule's work hours - return rule's work mode
                        return work_mode
                    else:
                        # Outside rule's work hours - fall back to base schedule
                        base_mode, base_start, base_end = self._get_base_schedule_mode(dt)
                        if base_mode == WorkMode.NON_WORKING:
                            return WorkMode.NON_WORKING
                        if base_start and base_end:
                            if base_start <= current_time < base_end:
                                return base_mode
                            else:
                                return WorkMode.NON_WORKING
                        else:
                            return base_mode
                else:
                    # No time range specified in rule, return the mode
                    return work_mode
            else:
                # No rules, use base schedule
                work_mode, work_start, work_end = self._get_base_schedule_mode(dt)
                
                # If work mode is NON_WORKING, return immediately
                if work_mode == WorkMode.NON_WORKING:
                    return WorkMode.NON_WORKING
                
                # Check if current time falls within work hours
                current_time = dt.time()
                if work_start and work_end:
                    if work_start <= current_time < work_end:
                        return work_mode
                    else:
                        return WorkMode.NON_WORKING
                else:
                    # No time range specified, return the mode
                    return work_mode
                
        except Exception as e:
            # Log error and return safe default
            import logging
            logging.error(f"Error determining work mode: {e}", exc_info=True)
            return WorkMode.NON_WORKING



# ========== Public API for Ticket Routing Integration ==========


async def get_current_work_mode(session: AsyncSession) -> WorkMode:
    """
    Get current work mode based on Moscow time and calendar rules.
    
    This is the public API function for ticket routing integration.
    It determines the current work mode by querying calendar rules
    and applying the CalendarService logic.
    
    Args:
        session: Database session
    
    Returns:
        WorkMode enum (REGULAR, EXTENDED, or NON_WORKING)
    
    Error Handling:
        Returns NON_WORKING as safe default if any error occurs
    
    Requirements: 18.1, 18.2, 18.5
    """
    try:
        # Get current time in Moscow timezone (UTC+3)
        import pytz
        MOSCOW_TZ = pytz.timezone('Europe/Moscow')
        current_moscow_time = datetime.now(MOSCOW_TZ)
        
        # Use CalendarService to determine work mode
        calendar_service = CalendarService()
        work_mode = await calendar_service.get_work_mode_for_datetime(
            session,
            current_moscow_time
        )
        
        return work_mode
        
    except Exception as e:
        # Log error and return safe default
        import logging
        logging.error(
            f"Error in get_current_work_mode: {e}",
            exc_info=True
        )
        return WorkMode.NON_WORKING
