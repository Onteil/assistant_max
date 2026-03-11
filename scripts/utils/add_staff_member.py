"""
Script to add a user as a staff member.
Usage: python add_staff_member.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from sqlalchemy import select
from database.models import Staff_Member, StaffRole, User
from constants import get_session


async def add_staff_member(
    tg_user_id: int = None,
    max_user_id: int = None,
    full_name: str = None,
    position: str = None,
    staff_role: StaffRole = StaffRole.MANAGER
):
    """Add a user as a staff member."""
    
    if not tg_user_id and not max_user_id:
        print("❌ Необходимо указать хотя бы один ID (Telegram или MAX)")
        return
    
    async with get_session() as session:
        # Check if user exists in users table
        user = None
        if tg_user_id:
            user_result = await session.execute(
                select(User).where(User.tg_user_id == tg_user_id)
            )
            user = user_result.scalar_one_or_none()
        elif max_user_id:
            user_result = await session.execute(
                select(User).where(User.max_user_id == max_user_id)
            )
            user = user_result.scalar_one_or_none()
        
        if not user:
            print(f"⚠️  User not found in users table")
            print("   The user needs to register first via /start command")
            print("   Continuing anyway to add staff member record...")
        
        # Check if already a staff member
        staff_result = await session.execute(
            select(Staff_Member).where(
                (Staff_Member.tg_user_id == tg_user_id) if tg_user_id else (Staff_Member.max_user_id == max_user_id)
            )
        )
        existing_staff = staff_result.scalar_one_or_none()
        
        if existing_staff:
            print(f"✓ User is already a staff member")
            print(f"  Name: {existing_staff.full_name}")
            print(f"  Position: {existing_staff.position}")
            print(f"  Role: {existing_staff.staff_role.value}")
            print(f"  Active: {existing_staff.is_active}")
            print(f"  Telegram ID: {existing_staff.tg_user_id}")
            print(f"  MAX ID: {existing_staff.max_user_id}")
            
            # Update missing IDs if provided
            updated = False
            if tg_user_id and not existing_staff.tg_user_id:
                existing_staff.tg_user_id = tg_user_id
                updated = True
            if max_user_id and not existing_staff.max_user_id:
                existing_staff.max_user_id = max_user_id
                updated = True
            
            # Reactivate if inactive
            if not existing_staff.is_active:
                existing_staff.is_active = True
                updated = True
                print("  → Reactivated staff member")
            
            if updated:
                await session.commit()
                print("  → Updated staff member record")
            return
        
        # Create new staff member
        staff_member = Staff_Member(
            tg_user_id=tg_user_id,
            max_user_id=max_user_id,
            full_name=full_name,
            position=position,
            staff_role=staff_role,
            is_active=True
        )
        
        session.add(staff_member)
        await session.commit()
        await session.refresh(staff_member)
        
        print(f"✓ Successfully added staff member:")
        print(f"  ID: {staff_member.id}")
        print(f"  Telegram User ID: {staff_member.tg_user_id}")
        print(f"  MAX User ID: {staff_member.max_user_id}")
        print(f"  Name: {staff_member.full_name}")
        print(f"  Position: {staff_member.position}")
        print(f"  Role: {staff_member.staff_role.value}")


async def main():
    """Main function to add the specific user as staff."""
    print("=== Добавление пользователя в staff members ===")
    print()
    
    # Ask which messenger
    print("Выберите мессенджер:")
    print("1. Telegram")
    print("2. MAX")
    print("3. Оба")
    messenger_choice = input("Выбор (1-3): ").strip()
    
    tg_user_id = None
    max_user_id = None
    
    if messenger_choice in ["1", "3"]:
        tg_input = input("Введите Telegram User ID: ").strip()
        if tg_input:
            tg_user_id = int(tg_input)
    
    if messenger_choice in ["2", "3"]:
        max_input = input("Введите MAX User ID (по умолчанию 268948175): ").strip()
        if max_input:
            max_user_id = int(max_input)
        else:
            max_user_id = 268948175
    
    if not tg_user_id and not max_user_id:
        print("❌ Необходимо указать хотя бы один ID")
        return
    
    full_name = input("Введите полное имя сотрудника: ").strip()
    if not full_name:
        full_name = "Staff Member"
    
    position = input("Введите должность (по умолчанию 'Manager'): ").strip()
    if not position:
        position = "Manager"
    
    print("\nДоступные роли:")
    print("1. MANAGER")
    print("2. TECHNICAL_SUPPORT")
    print("3. RENEWAL")
    role_choice = input("Выберите роль (1-3, по умолчанию 1): ").strip()
    
    role_map = {
        "1": StaffRole.MANAGER,
        "2": StaffRole.TECHNICAL_SUPPORT,
        "3": StaffRole.RENEWAL,
    }
    staff_role = role_map.get(role_choice, StaffRole.MANAGER)
    
    print(f"\nДобавление пользователя:")
    if tg_user_id:
        print(f"  Telegram ID: {tg_user_id}")
    if max_user_id:
        print(f"  MAX ID: {max_user_id}")
    print(f"  Имя: {full_name}")
    print(f"  Должность: {position}")
    print(f"  Роль: {staff_role.value}")
    print()
    
    await add_staff_member(
        tg_user_id=tg_user_id,
        max_user_id=max_user_id,
        full_name=full_name,
        position=position,
        staff_role=staff_role
    )


if __name__ == "__main__":
    asyncio.run(main())
