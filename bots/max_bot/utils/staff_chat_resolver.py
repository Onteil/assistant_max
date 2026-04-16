"""
Staff Chat ID Resolver

Utility for resolving MAX chat_id for staff members with automatic fallback
from Staff_Member table to MAX_Messenger_Data table.

This ensures notifications can be sent to staff members even if their max_chat_id
is not stored in the Staff_Member table but exists in MAX_Messenger_Data.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Staff_Member, MAX_Messenger_Data

logger = logging.getLogger(__name__)


async def get_staff_chat_id(
    session: AsyncSession,
    staff_id: int
) -> Optional[int]:
    """
    Get MAX chat_id for a staff member with automatic fallback.
    
    Resolution order:
    1. Check Staff_Member.max_chat_id (direct field)
    2. If not found, check MAX_Messenger_Data by Staff_Member.max_user_id (fallback)
    
    Args:
        session: Database session
        staff_id: Internal staff member ID
    
    Returns:
        MAX chat_id if found, None otherwise
    
    Example:
        >>> chat_id = await get_staff_chat_id(session, staff_id=42)
        >>> if chat_id:
        >>>     await messenger_adapter.send_message(
        >>>         chat_id=chat_id,
        >>>         text="Notification"
        >>>     )
    """
    try:
        # Get staff member
        stmt = select(Staff_Member).where(Staff_Member.id == staff_id)
        result = await session.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if not staff:
            logger.warning(f"Staff member not found: staff_id={staff_id}")
            return None
        
        # Try direct max_chat_id first
        if staff.max_chat_id:
            logger.debug(
                f"Found chat_id in Staff_Member: staff_id={staff_id}, "
                f"chat_id={staff.max_chat_id}"
            )
            return staff.max_chat_id
        
        # Fallback: try MAX_Messenger_Data by max_user_id
        if staff.max_user_id:
            stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                MAX_Messenger_Data.max_user_id == staff.max_user_id
            )
            result_chat = await session.execute(stmt_chat)
            chat_id = result_chat.scalar_one_or_none()
            
            if chat_id:
                logger.info(
                    f"Found chat_id in MAX_Messenger_Data (fallback): "
                    f"staff_id={staff_id}, max_user_id={staff.max_user_id}, "
                    f"chat_id={chat_id}"
                )
                return chat_id
        
        # No chat_id found
        logger.warning(
            f"No MAX chat_id found for staff member: staff_id={staff_id}, "
            f"max_user_id={staff.max_user_id}, checked both Staff_Member "
            f"and MAX_Messenger_Data tables"
        )
        return None
        
    except Exception as e:
        logger.error(
            f"Error resolving chat_id for staff member: staff_id={staff_id}, "
            f"error={e}",
            exc_info=True
        )
        return None


async def get_staff_chat_id_by_max_user_id(
    session: AsyncSession,
    max_user_id: int
) -> Optional[int]:
    """
    Get MAX chat_id by max_user_id with automatic fallback.
    
    Resolution order:
    1. Check Staff_Member.max_chat_id where max_user_id matches
    2. If not found, check MAX_Messenger_Data by max_user_id (fallback)
    
    Args:
        session: Database session
        max_user_id: MAX user ID
    
    Returns:
        MAX chat_id if found, None otherwise
    
    Example:
        >>> chat_id = await get_staff_chat_id_by_max_user_id(session, max_user_id=123456)
        >>> if chat_id:
        >>>     await messenger_adapter.send_message(
        >>>         chat_id=chat_id,
        >>>         text="Notification"
        >>>     )
    """
    try:
        # Try Staff_Member first
        stmt = select(Staff_Member).where(Staff_Member.max_user_id == max_user_id)
        result = await session.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if staff and staff.max_chat_id:
            logger.debug(
                f"Found chat_id in Staff_Member: max_user_id={max_user_id}, "
                f"chat_id={staff.max_chat_id}"
            )
            return staff.max_chat_id
        
        # Fallback: try MAX_Messenger_Data
        stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
            MAX_Messenger_Data.max_user_id == max_user_id
        )
        result_chat = await session.execute(stmt_chat)
        chat_id = result_chat.scalar_one_or_none()
        
        if chat_id:
            logger.info(
                f"Found chat_id in MAX_Messenger_Data (fallback): "
                f"max_user_id={max_user_id}, chat_id={chat_id}"
            )
            return chat_id
        
        # No chat_id found
        logger.warning(
            f"No MAX chat_id found for max_user_id={max_user_id}, "
            f"checked both Staff_Member and MAX_Messenger_Data tables"
        )
        return None
        
    except Exception as e:
        logger.error(
            f"Error resolving chat_id by max_user_id: max_user_id={max_user_id}, "
            f"error={e}",
            exc_info=True
        )
        return None


async def resolve_staff_chat_ids(
    session: AsyncSession,
    staff_ids: list[int]
) -> dict[int, int]:
    """
    Resolve MAX chat_ids for multiple staff members at once.
    
    Args:
        session: Database session
        staff_ids: List of internal staff member IDs
    
    Returns:
        Dictionary mapping staff_id to chat_id (only includes staff with found chat_ids)
    
    Example:
        >>> chat_ids = await resolve_staff_chat_ids(session, [1, 2, 3])
        >>> for staff_id, chat_id in chat_ids.items():
        >>>     await messenger_adapter.send_message(
        >>>         chat_id=chat_id,
        >>>         text=f"Notification for staff {staff_id}"
        >>>     )
    """
    result_map = {}
    
    for staff_id in staff_ids:
        chat_id = await get_staff_chat_id(session, staff_id)
        if chat_id:
            result_map[staff_id] = chat_id
    
    logger.info(
        f"Resolved chat_ids for {len(result_map)}/{len(staff_ids)} staff members"
    )
    
    return result_map
