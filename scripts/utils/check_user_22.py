import asyncio
    asyncio.run(check_user())
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from sqlalchemy import select
from constants import AsyncSessionLocal
from database.models import User


async def check_user():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == 22))
        user = result.scalar_one_or_none()
        
        if user:
            print(f"User ID: {user.id}")
            print(f"Phone: {user.phone_number}")
            print(f"TG User ID: {user.tg_user_id}")
            print(f"Full Name: {user.full_name}")
            print(f"Registration Status: {user.registration_status}")
        else:
            print("User not found")


if __name__ == "__main__":
    asyncio.run(check_user())
