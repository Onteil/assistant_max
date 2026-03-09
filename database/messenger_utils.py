"""
Utility functions for multi-messenger support.

Provides helpers for managing users across Telegram and MAX messengers.
"""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, Staff_Member

MessengerType = Literal["telegram", "max"]


async def get_or_create_user_by_messenger(
    session: AsyncSession,
    messenger_type: MessengerType,
    messenger_user_id: int,
    phone_number: str | None = None,
    **user_data
) -> User:
    """
    Get or create user by messenger type and ID.
    
    Args:
        session: Database session
        messenger_type: "telegram" or "max"
        messenger_user_id: User ID from the messenger
        phone_number: Phone number (required for new users)
        **user_data: Additional user data (first_name, last_name, etc.)
    
    Returns:
        User instance
    
    Raises:
        ValueError: If phone_number is not provided for new users
    """
    # Try to find existing user
    if messenger_type == "telegram":
        stmt = select(User).where(User.tg_user_id == messenger_user_id)
    else:  # max
        stmt = select(User).where(User.max_user_id == messenger_user_id)
    
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user:
        # Update user_id to current messenger
        user.user_id = messenger_user_id
        user.messenger_type = messenger_type
        await session.commit()
        return user
    
    # Create new user
    if not phone_number:
        raise ValueError("phone_number is required for new users")
    
    if messenger_type == "telegram":
        user = User(
            tg_user_id=messenger_user_id,
            user_id=messenger_user_id,
            messenger_type=messenger_type,
            phone_number=phone_number,
            **user_data
        )
    else:  # max
        # For MAX users, we need to generate a unique tg_user_id
        # Use negative values to avoid conflicts with real Telegram IDs
        # This is a temporary solution until we refactor to use a separate primary key
        user = User(
            tg_user_id=-messenger_user_id,  # Negative to distinguish from Telegram
            max_user_id=messenger_user_id,
            user_id=messenger_user_id,
            messenger_type=messenger_type,
            phone_number=phone_number,
            **user_data
        )
    
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    return user


async def link_messenger_to_user(
    session: AsyncSession,
    user: User,
    messenger_type: MessengerType,
    messenger_user_id: int
) -> User:
    """
    Link a new messenger account to an existing user.
    
    Args:
        session: Database session
        user: Existing user instance
        messenger_type: "telegram" or "max"
        messenger_user_id: User ID from the new messenger
    
    Returns:
        Updated user instance
    
    Raises:
        ValueError: If messenger is already linked
    """
    if messenger_type == "telegram":
        if user.tg_user_id and user.tg_user_id > 0:
            raise ValueError("Telegram account already linked")
        user.tg_user_id = messenger_user_id
    else:  # max
        if user.max_user_id:
            raise ValueError("MAX account already linked")
        user.max_user_id = messenger_user_id
    
    await session.commit()
    await session.refresh(user)
    
    return user


async def get_user_by_phone(
    session: AsyncSession,
    phone_number: str
) -> User | None:
    """
    Get user by phone number (messenger-agnostic).
    
    Args:
        session: Database session
        phone_number: Phone number to search
    
    Returns:
        User instance or None
    """
    stmt = select(User).where(User.phone_number == phone_number)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_staff_by_messenger(
    session: AsyncSession,
    messenger_type: MessengerType,
    messenger_user_id: int
) -> Staff_Member | None:
    """
    Get staff member by messenger type and ID.
    
    Args:
        session: Database session
        messenger_type: "telegram" or "max"
        messenger_user_id: User ID from the messenger
    
    Returns:
        Staff_Member instance or None
    """
    if messenger_type == "telegram":
        stmt = select(Staff_Member).where(Staff_Member.tg_user_id == messenger_user_id)
    else:  # max
        stmt = select(Staff_Member).where(Staff_Member.max_user_id == messenger_user_id)
    
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def get_active_messenger_id(user: User) -> int:
    """
    Get the active messenger user ID for API calls.
    
    Args:
        user: User instance
    
    Returns:
        Active messenger user ID
    """
    return user.user_id or user.tg_user_id
