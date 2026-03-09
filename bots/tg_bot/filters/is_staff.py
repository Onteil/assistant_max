"""
Staff Member Filter

Filter to check if user is an active staff member.
Used to restrict access to staff-only handlers.
"""

import logging

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Staff_Member

logger = logging.getLogger(__name__)


class IsStaffFilter(BaseFilter):
    """
    Filter to verify user is an active staff member.
    
    This filter checks if the user exists in Staff_Member table
    and is active (is_active = True).
    
    Usage:
        @router.message(Command("manager"), IsStaffFilter())
        async def show_employee_menu(message: Message, session: AsyncSession):
            # Handler code here
            pass
    """
    
    async def __call__(
        self,
        message: Message | CallbackQuery,
        session: AsyncSession,
    ) -> bool:
        """
        Check if user is an active staff member.
        
        Args:
            message: Message or CallbackQuery event
            session: Database session (injected by middleware)
        
        Returns:
            True if user is active staff member, False otherwise
        """
        user_id = message.from_user.id
        
        logger.info(f"IsStaffFilter: Checking user {user_id}")
        
        try:
            stmt = select(Staff_Member).where(
                Staff_Member.tg_user_id == user_id,
                Staff_Member.is_active == True
            )
            result = await session.execute(stmt)
            staff_member = result.scalar_one_or_none()
            
            is_staff = staff_member is not None
            logger.info(f"IsStaffFilter: User {user_id} is staff: {is_staff}")
            
            return is_staff
            
        except Exception as e:
            # On error, deny access (fail closed)
            logger.error(f"IsStaffFilter: Error checking user {user_id}: {e}", exc_info=True)
            return False
