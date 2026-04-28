#!/usr/bin/env python3
"""
Test script for manager backup chain functionality.

Tests the updated determine_assigned_manager function to ensure it properly
handles the backup manager chain when the primary manager is unavailable.
"""

import asyncio
import logging
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from constants import AsyncSessionLocal
from database.models import Staff_Member, StaffRole, User
from services.ticket_service import determine_assigned_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_manager_backup_chain():
    """Test manager backup chain logic."""
    logger.info("=== Testing Manager Backup Chain ===")
    
    async with AsyncSessionLocal() as session:
        # Find a user with a default manager
        stmt = select(User).where(User.default_manager_id.isnot(None)).limit(1)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning("No user with default manager found")
            return
        
        logger.info(f"Testing with user: {user.full_name} (ID: {user.id})")
        logger.info(f"Default manager ID: {user.default_manager_id}")
        
        # Get the default manager
        stmt = select(Staff_Member).where(Staff_Member.id == user.default_manager_id)
        result = await session.execute(stmt)
        default_manager = result.scalar_one_or_none()
        
        if not default_manager:
            logger.warning("Default manager not found")
            return
        
        logger.info(f"Default manager: {default_manager.full_name}")
        logger.info(f"  is_active: {default_manager.is_active}")
        logger.info(f"  is_working_today: {default_manager.is_working_today}")
        logger.info(f"  backup_manager_1_id: {default_manager.backup_manager_1_id}")
        logger.info(f"  backup_manager_2_id: {default_manager.backup_manager_2_id}")
        
        # Test 1: Manager available
        logger.info("\n--- Test 1: Manager available ---")
        original_working = default_manager.is_working_today
        default_manager.is_working_today = True
        await session.commit()
        
        assigned_id, has_manager = await determine_assigned_manager(
            session, user.id, assign_admin_if_no_manager=True
        )
        logger.info(f"Result: assigned_id={assigned_id}, has_manager={has_manager}")
        
        # Test 2: Manager unavailable
        logger.info("\n--- Test 2: Manager unavailable ---")
        default_manager.is_working_today = False
        await session.commit()
        
        assigned_id, has_manager = await determine_assigned_manager(
            session, user.id, assign_admin_if_no_manager=True
        )
        logger.info(f"Result: assigned_id={assigned_id}, has_manager={has_manager}")
        
        if assigned_id:
            # Get assigned staff info
            stmt = select(Staff_Member).where(Staff_Member.id == assigned_id)
            result = await session.execute(stmt)
            assigned_staff = result.scalar_one_or_none()
            if assigned_staff:
                logger.info(f"Assigned to: {assigned_staff.full_name} (role: {assigned_staff.staff_role.value})")
        
        # Restore original state
        default_manager.is_working_today = original_working
        await session.commit()
        logger.info(f"Restored manager availability to: {original_working}")


async def test_backup_manager_availability():
    """Test backup manager availability logic."""
    logger.info("\n=== Testing Backup Manager Availability ===")
    
    async with AsyncSessionLocal() as session:
        # Find a manager with backup managers
        stmt = (
            select(Staff_Member)
            .where(
                and_(
                    Staff_Member.backup_manager_1_id.isnot(None),
                    Staff_Member.is_active == True
                )
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        manager = result.scalar_one_or_none()
        
        if not manager:
            logger.warning("No manager with backup managers found")
            return
        
        logger.info(f"Testing with manager: {manager.full_name}")
        
        # Get backup managers
        backup1_id = manager.backup_manager_1_id
        backup2_id = manager.backup_manager_2_id
        
        backup1 = None
        backup2 = None
        
        if backup1_id:
            stmt = select(Staff_Member).where(Staff_Member.id == backup1_id)
            result = await session.execute(stmt)
            backup1 = result.scalar_one_or_none()
            if backup1:
                logger.info(f"Backup 1: {backup1.full_name} (working: {backup1.is_working_today})")
        
        if backup2_id:
            stmt = select(Staff_Member).where(Staff_Member.id == backup2_id)
            result = await session.execute(stmt)
            backup2 = result.scalar_one_or_none()
            if backup2:
                logger.info(f"Backup 2: {backup2.full_name} (working: {backup2.is_working_today})")
        
        # Find a user assigned to this manager
        stmt = select(User).where(User.default_manager_id == manager.id).limit(1)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning("No user assigned to this manager")
            return
        
        logger.info(f"Testing with user: {user.full_name}")
        
        # Store original states
        original_manager_working = manager.is_working_today
        original_backup1_working = backup1.is_working_today if backup1 else None
        original_backup2_working = backup2.is_working_today if backup2 else None
        
        try:
            # Test scenario: manager unavailable, backup1 available
            if backup1:
                logger.info("\n--- Scenario: Manager unavailable, Backup1 available ---")
                manager.is_working_today = False
                backup1.is_working_today = True
                if backup2:
                    backup2.is_working_today = False
                await session.commit()
                
                assigned_id, has_manager = await determine_assigned_manager(
                    session, user.id, assign_admin_if_no_manager=True
                )
                logger.info(f"Result: assigned_id={assigned_id}, has_manager={has_manager}")
                
                if assigned_id == backup1.id:
                    logger.info("✅ Correctly assigned to backup1")
                else:
                    logger.warning(f"❌ Expected backup1 ({backup1.id}), got {assigned_id}")
            
            # Test scenario: manager and backup1 unavailable, backup2 available
            if backup1 and backup2:
                logger.info("\n--- Scenario: Manager and Backup1 unavailable, Backup2 available ---")
                manager.is_working_today = False
                backup1.is_working_today = False
                backup2.is_working_today = True
                await session.commit()
                
                assigned_id, has_manager = await determine_assigned_manager(
                    session, user.id, assign_admin_if_no_manager=True
                )
                logger.info(f"Result: assigned_id={assigned_id}, has_manager={has_manager}")
                
                if assigned_id == backup2.id:
                    logger.info("✅ Correctly assigned to backup2")
                else:
                    logger.warning(f"❌ Expected backup2 ({backup2.id}), got {assigned_id}")
            
            # Test scenario: all managers unavailable, should assign admin
            logger.info("\n--- Scenario: All managers unavailable, should assign admin ---")
            manager.is_working_today = False
            if backup1:
                backup1.is_working_today = False
            if backup2:
                backup2.is_working_today = False
            await session.commit()
            
            assigned_id, has_manager = await determine_assigned_manager(
                session, user.id, assign_admin_if_no_manager=True
            )
            logger.info(f"Result: assigned_id={assigned_id}, has_manager={has_manager}")
            
            if assigned_id and not has_manager:
                # Get assigned staff info
                stmt = select(Staff_Member).where(Staff_Member.id == assigned_id)
                result = await session.execute(stmt)
                assigned_staff = result.scalar_one_or_none()
                if assigned_staff and assigned_staff.staff_role == StaffRole.ADMINISTRATOR:
                    logger.info("✅ Correctly assigned to admin")
                else:
                    logger.warning(f"❌ Expected admin, got {assigned_staff.staff_role if assigned_staff else 'None'}")
            
        finally:
            # Restore original states
            manager.is_working_today = original_manager_working
            if backup1 and original_backup1_working is not None:
                backup1.is_working_today = original_backup1_working
            if backup2 and original_backup2_working is not None:
                backup2.is_working_today = original_backup2_working
            await session.commit()
            logger.info("Restored original availability states")


async def main():
    """Run all tests."""
    logger.info("Starting manager backup chain tests")
    
    try:
        await test_manager_backup_chain()
        await test_backup_manager_availability()
        
        logger.info("\nAll tests completed!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())