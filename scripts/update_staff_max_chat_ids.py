"""
Update max_chat_id for existing staff members.

This script populates max_chat_id field for staff members who have max_user_id
by looking up the chat_id from max_messenger_data table.
"""

import asyncio
import logging

from sqlalchemy import select

from constants import DB_URL
from database.models import Staff_Member, MAX_Messenger_Data
from database.session import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def update_staff_chat_ids():
    """Update max_chat_id for all staff members with max_user_id."""
    # Initialize database
    db_manager = init_db(DB_URL)
    
    async with db_manager.session() as session:
        # Get all staff members with max_user_id but no max_chat_id
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id.isnot(None),
            Staff_Member.max_chat_id.is_(None)
        )
        result = await session.execute(stmt)
        staff_members = result.scalars().all()
        
        logger.info(f"Found {len(staff_members)} staff members to update")
        
        updated_count = 0
        not_found_count = 0
        
        for staff in staff_members:
            # Look up chat_id from max_messenger_data
            stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                MAX_Messenger_Data.max_user_id == staff.max_user_id
            )
            result_chat = await session.execute(stmt_chat)
            chat_id = result_chat.scalar_one_or_none()
            
            if chat_id:
                staff.max_chat_id = chat_id
                updated_count += 1
                logger.info(
                    f"Updated staff {staff.id} ({staff.full_name}): "
                    f"max_user_id={staff.max_user_id}, max_chat_id={chat_id}"
                )
            else:
                not_found_count += 1
                logger.warning(
                    f"No chat_id found for staff {staff.id} ({staff.full_name}): "
                    f"max_user_id={staff.max_user_id}"
                )
        
        logger.info(
            f"Update complete: {updated_count} updated, {not_found_count} not found"
        )
    
    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(update_staff_chat_ids())
