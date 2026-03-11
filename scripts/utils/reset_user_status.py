"""
Reset user status back to PENDING for testing
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from sqlalchemy import select
from constants import AsyncSessionLocal
from database.models import User, RegistrationStatus


async def reset_user():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == 28))
        user = result.scalar_one_or_none()
        
        if user:
            print(f"Current status: {user.registration_status}")
            user.registration_status = RegistrationStatus.PENDING
            await session.commit()
            print(f"✅ Status reset to PENDING")
        else:
            print("User not found")


if __name__ == "__main__":
    asyncio.run(reset_user())
