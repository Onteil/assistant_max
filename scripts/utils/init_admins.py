#!/usr/bin/env python3
"""
Initialize System Administrators

This script adds initial administrators to the database from environment configuration.
Run this script once during initial system setup to create admin accounts.

Creates both User and Staff_Member records for each administrator.

Usage:
    python init_admins.py

Environment Variable:
    INITIAL_ADMINS - JSON array of admin objects with fields:
        - max_user_id (int, required): MAX messenger user ID
        - tg_user_id (int, optional): Telegram user ID (can be null)
        - full_name (str, required): Full name of the administrator
        - position (str, required): Job position/title
        - phone_number (str, required): Phone number for User record

Example .env configuration:
    INITIAL_ADMINS = '[{"max_user_id": 123456789, "tg_user_id": null, "full_name": "Иван Иванов", "position": "Системный администратор", "phone_number": "+79991234567"}]'
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import json
import logging
import os
import sys
from typing import List, Dict, Any

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import async_session_maker
from database.models import Staff_Member, StaffRole, User, RegistrationStatus, SubscriptionStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_initial_admins() -> List[Dict[str, Any]]:
    """
    Load initial admin configuration from environment variable.
    
    Returns:
        List of admin configuration dictionaries
    
    Raises:
        ValueError: If INITIAL_ADMINS is not valid JSON or has invalid format
    """
    admins_json = os.getenv("INITIAL_ADMINS", "[]")
    
    if not admins_json.strip():
        logger.warning("INITIAL_ADMINS environment variable is empty")
        return []
    
    try:
        admins = json.loads(admins_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in INITIAL_ADMINS: {e}")
    
    if not isinstance(admins, list):
        raise ValueError("INITIAL_ADMINS must be a JSON array")
    
    # Validate each admin configuration
    for i, admin in enumerate(admins):
        if not isinstance(admin, dict):
            raise ValueError(f"Admin #{i+1} must be a JSON object")
        
        # Check required fields
        if "max_user_id" not in admin:
            raise ValueError(f"Admin #{i+1} missing required field: max_user_id")
        if "full_name" not in admin:
            raise ValueError(f"Admin #{i+1} missing required field: full_name")
        if "position" not in admin:
            raise ValueError(f"Admin #{i+1} missing required field: position")
        if "phone_number" not in admin:
            raise ValueError(f"Admin #{i+1} missing required field: phone_number")
        
        # Validate types
        if not isinstance(admin["max_user_id"], int):
            raise ValueError(f"Admin #{i+1} max_user_id must be an integer")
        if admin.get("tg_user_id") is not None and not isinstance(admin["tg_user_id"], int):
            raise ValueError(f"Admin #{i+1} tg_user_id must be an integer or null")
        if not isinstance(admin["full_name"], str) or not admin["full_name"].strip():
            raise ValueError(f"Admin #{i+1} full_name must be a non-empty string")
        if not isinstance(admin["position"], str) or not admin["position"].strip():
            raise ValueError(f"Admin #{i+1} position must be a non-empty string")
        if not isinstance(admin["phone_number"], str) or not admin["phone_number"].strip():
            raise ValueError(f"Admin #{i+1} phone_number must be a non-empty string")
    
    return admins


async def check_existing_user(session: AsyncSession, max_user_id: int, tg_user_id: int | None, phone_number: str) -> User | None:
    """
    Check if user already exists in database.
    
    Args:
        session: Database session
        max_user_id: MAX messenger user ID
        tg_user_id: Telegram user ID (optional)
        phone_number: Phone number
    
    Returns:
        Existing User record or None
    """
    # Check by MAX user ID
    if max_user_id:
        stmt = select(User).where(User.max_user_id == max_user_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing
    
    # Check by Telegram user ID
    if tg_user_id:
        stmt = select(User).where(User.tg_user_id == tg_user_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing
    
    # Check by phone number
    if phone_number:
        stmt = select(User).where(User.phone_number == phone_number)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing
    
    return None


async def check_existing_admin(session: AsyncSession, max_user_id: int, tg_user_id: int | None) -> Staff_Member | None:
    """
    Check if admin already exists in database.
    
    Args:
        session: Database session
        max_user_id: MAX messenger user ID
        tg_user_id: Telegram user ID (optional)
    
    Returns:
        Existing Staff_Member record or None
    """
    # Check by MAX user ID
    if max_user_id:
        stmt = select(Staff_Member).where(Staff_Member.max_user_id == max_user_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing
    
    # Check by Telegram user ID
    if tg_user_id:
        stmt = select(Staff_Member).where(Staff_Member.tg_user_id == tg_user_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing
    
    return None


async def create_user(
    session: AsyncSession,
    max_user_id: int,
    tg_user_id: int | None,
    full_name: str,
    phone_number: str
) -> User:
    """
    Create new user in database.
    
    Args:
        session: Database session
        max_user_id: MAX messenger user ID
        tg_user_id: Telegram user ID (optional)
        full_name: Full name
        phone_number: Phone number
    
    Returns:
        Created User record
    """
    # Parse full name into components
    name_parts = full_name.strip().split()
    first_name = name_parts[0] if len(name_parts) > 0 else full_name
    last_name = name_parts[1] if len(name_parts) > 1 else None
    middle_name = name_parts[2] if len(name_parts) > 2 else None
    
    user = User(
        max_user_id=max_user_id,
        tg_user_id=tg_user_id,
        phone_number=phone_number,
        first_name=first_name,
        last_name=last_name,
        middle_name=middle_name,
        full_name=full_name,
        registration_status=RegistrationStatus.ACTIVE,
        subscription_status=SubscriptionStatus.NONE,
        notification_preferences=True
    )
    
    session.add(user)
    await session.flush()  # Flush to get the ID
    
    return user


async def create_admin(
    session: AsyncSession,
    max_user_id: int,
    tg_user_id: int | None,
    full_name: str,
    position: str
) -> Staff_Member:
    """
    Create new administrator in database.
    
    Args:
        session: Database session
        max_user_id: MAX messenger user ID
        tg_user_id: Telegram user ID (optional)
        full_name: Full name
        position: Job position
    
    Returns:
        Created Staff_Member record
    """
    admin = Staff_Member(
        max_user_id=max_user_id,
        tg_user_id=tg_user_id,
        full_name=full_name,
        position=position,
        staff_role=StaffRole.ADMINISTRATOR,
        is_active=True
    )
    
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    
    return admin


async def initialize_admins() -> None:
    """
    Initialize administrators from environment configuration.
    """
    logger.info("Starting admin initialization...")
    
    # Load configuration
    try:
        admins_config = load_initial_admins()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    if not admins_config:
        logger.warning("No admins configured in INITIAL_ADMINS")
        logger.info("To add admins, set INITIAL_ADMINS environment variable")
        return
    
    logger.info(f"Found {len(admins_config)} admin(s) in configuration")
    
    # Process each admin
    created_count = 0
    skipped_count = 0
    
    async with async_session_maker() as session:
        for i, admin_data in enumerate(admins_config, 1):
            max_user_id = admin_data["max_user_id"]
            tg_user_id = admin_data.get("tg_user_id")
            full_name = admin_data["full_name"]
            position = admin_data["position"]
            phone_number = admin_data["phone_number"]
            
            logger.info(f"Processing admin #{i}: {full_name} (MAX ID: {max_user_id})")
            
            # Check if user already exists
            existing_user = await check_existing_user(session, max_user_id, tg_user_id, phone_number)
            
            if existing_user:
                logger.info(f"  ⏭️️  User record already exists (ID: {existing_user.id})")
                user = existing_user
            else:
                # Create user record
                try:
                    user = await create_user(
                        session=session,
                        max_user_id=max_user_id,
                        tg_user_id=tg_user_id,
                        full_name=full_name,
                        phone_number=phone_number
                    )
                    logger.info(f"  ✅ User record created (ID: {user.id})")
                except Exception as e:
                    logger.error(f"  ❌ Failed to create user: {e}", exc_info=True)
                    await session.rollback()
                    continue
            
            # Check if staff member already exists
            existing_staff = await check_existing_admin(session, max_user_id, tg_user_id)
            
            if existing_staff:
                logger.info(f"  ⏭️️  Staff member already exists (ID: {existing_staff.id}, Role: {existing_staff.staff_role.value})")
                
                # Update if needed
                updated = False
                if existing_staff.staff_role != StaffRole.ADMINISTRATOR:
                    logger.info(f"  ⚠️  Updating role from {existing_staff.staff_role.value} to administrator")
                    existing_staff.staff_role = StaffRole.ADMINISTRATOR
                    updated = True
                
                if not existing_staff.is_active:
                    logger.info(f"  ⚠️  Reactivating staff member account")
                    existing_staff.is_active = True
                    updated = True
                
                if updated:
                    await session.commit()
                    logger.info(f"  ✅ Staff member updated")
                
                skipped_count += 1
                continue
            
            # Create new staff member
            try:
                admin = await create_admin(
                    session=session,
                    max_user_id=max_user_id,
                    tg_user_id=tg_user_id,
                    full_name=full_name,
                    position=position
                )
                await session.commit()
                logger.info(f"  ✅ Staff member created (ID: {admin.id})")
                created_count += 1
            except Exception as e:
                logger.error(f"  ❌ Failed to create staff member: {e}", exc_info=True)
                await session.rollback()
    
    # Summary
    logger.info("─" * 5)
    logger.info("Admin initialization complete!")
    logger.info(f"  Created: {created_count}")
    logger.info(f"  Already existed: {skipped_count}")
    logger.info(f"  Total: {len(admins_config)}")
    logger.info("─" * 5)


def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()
    
    # Run initialization
    try:
        asyncio.run(initialize_admins())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
