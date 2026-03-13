"""
Test script to verify support staff assignment logic.

This script tests the logic for assigning staff to technical support tickets
when no TECHNICAL_SUPPORT staff members are available.

Expected behavior:
- If no TECHNICAL_SUPPORT staff available, assign first active admin
- Admin should receive notification about missing support staff
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_
from database.session import init_db
from database.models import Staff_Member, StaffRole
from constants import DB_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def get_active_admins(session):
    """Get active admin staff members."""
    stmt = select(Staff_Member).where(
        and_(
            Staff_Member.staff_role == StaffRole.ADMIN,
            Staff_Member.is_active == True
        )
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def check_support_staff_assignment():
    """Check support staff assignment logic."""
    db = init_db(DB_URL)
    async with db.session() as session:
        try:
            # Check for TECHNICAL_SUPPORT staff
            stmt = select(Staff_Member).where(
                and_(
                    Staff_Member.staff_role == StaffRole.TECHNICAL_SUPPORT,
                    Staff_Member.is_active == True
                )
            )
            result = await session.execute(stmt)
            support_staff = result.scalars().all()
            
            logger.info(f"Found {len(support_staff)} active TECHNICAL_SUPPORT staff members:")
            for staff in support_staff:
                logger.info(
                    f"  - ID: {staff.id}, Name: {staff.full_name}, "
                    f"MAX ID: {staff.max_user_id}, TG ID: {staff.tg_user_id}"
                )
            
            # Check for admins
            admins = await get_active_admins(session)
            logger.info(f"\nFound {len(admins)} active admin staff members:")
            for admin in admins:
                logger.info(
                    f"  - ID: {admin.id}, Name: {admin.full_name}, "
                    f"Role: {admin.staff_role.value}, "
                    f"MAX ID: {admin.max_user_id}, TG ID: {admin.tg_user_id}"
                )
            
            # Simulate assignment logic
            logger.info("\n--- Simulating assignment logic ---")
            
            has_support_staff = len(support_staff) > 0
            logger.info(f"Has support staff: {has_support_staff}")
            
            if not has_support_staff:
                if admins:
                    assigned_admin_id = admins[0].id
                    logger.info(
                        f"✅ Would assign to admin: ID={assigned_admin_id}, "
                        f"Name={admins[0].full_name}"
                    )
                    logger.info(
                        "✅ Would send notification to admin about missing support staff"
                    )
                else:
                    logger.error("❌ No support staff and no admins available!")
            else:
                logger.info("✅ Would send notifications to all support staff members")
            
        except Exception as e:
            logger.error(f"Error checking staff assignment: {e}", exc_info=True)
    
    await db.close()


if __name__ == "__main__":
    asyncio.run(check_support_staff_assignment())
