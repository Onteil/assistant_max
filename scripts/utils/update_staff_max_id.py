"""
Script to update staff member's MAX user ID.

Usage:
    python update_staff_max_id.py <staff_id> <max_user_id>

Example:
    python update_staff_max_id.py 3 187660968
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from database.models import Staff_Member
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


async def update_staff_max_id(staff_id: int, max_user_id: int):
    """Update staff member's MAX user ID."""
    
    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            # Get staff member
            stmt = select(Staff_Member).where(Staff_Member.id == staff_id)
            result = await session.execute(stmt)
            staff = result.scalar_one_or_none()
            
            if not staff:
                print(f"❌ Staff member not found: id={staff_id}")
                return
            
            print(f"Found staff member: {staff.full_name} (id={staff.id})")
            print(f"Current MAX user ID: {staff.max_user_id}")
            
            # Update MAX user ID
            staff.max_user_id = max_user_id
            await session.commit()
            
            print(f"✅ Updated MAX user ID to: {max_user_id}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            await session.rollback()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python update_staff_max_id.py <staff_id> <max_user_id>")
        print("Example: python update_staff_max_id.py 3 187660968")
        sys.exit(1)
    
    try:
        staff_id = int(sys.argv[1])
        max_user_id = int(sys.argv[2])
    except ValueError:
        print("❌ Error: staff_id and max_user_id must be integers")
        sys.exit(1)
    
    asyncio.run(update_staff_max_id(staff_id, max_user_id))
