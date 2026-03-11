"""
Find a test user with tg_user_id
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from sqlalchemy import select
from constants import AsyncSessionLocal
from database.models import User


async def find_user():
    async with AsyncSessionLocal() as session:
        # Find user with id = 28
        result = await session.execute(
            select(User).where(User.id == 28)
        )
        user = result.scalar_one_or_none()
        
        if user:
            print(f"User ID: {user.id}")
            print(f"Phone: {user.phone_number}")
            print(f"TG User ID: {user.tg_user_id}")
            print(f"Full Name: {user.full_name}")
            print(f"Registration Status: {user.registration_status}")
        else:
            print("User not found, looking for any PENDING user...")
            result = await session.execute(
                select(User).where(User.registration_status == "pending").limit(1)
            )
            user = result.scalar_one_or_none()
            if user:
                print(f"\nFound PENDING user:")
                print(f"User ID: {user.id}")
                print(f"Phone: {user.phone_number}")
                print(f"TG User ID: {user.tg_user_id}")
                print(f"Full Name: {user.full_name}")
            else:
                print("No PENDING users found")


if __name__ == "__main__":
    asyncio.run(find_user())
