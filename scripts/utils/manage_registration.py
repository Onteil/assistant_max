#!/usr/bin/env python
"""
Console command to approve or reject user registrations

Usage:
    python manage_registration.py list                    # List pending registrations
    python manage_registration.py approve <user_id>       # Approve registration
    python manage_registration.py reject <user_id> [reason]  # Reject registration
    python manage_registration.py info <user_id>          # Show user details
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import sys
from datetime import datetime

from aiogram import Bot
from aiogram.enums import ParseMode
from sqlalchemy import select

from bots.tg_bot.texts import REGISTRATION_APPROVED, REGISTRATION_REJECTED
from constants import AsyncSessionLocal, TG_BOT_TOKEN
from database.models import Action_Log, ActionType, RegistrationStatus, User


async def list_pending_users():
    """List all users with pending registration status"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User)
            .where(User.registration_status == RegistrationStatus.PENDING)
            .order_by(User.created_at.desc())
        )
        users = result.scalars().all()
        
        if not users:
            print("\n✅ No pending registrations found.\n")
            return
        
        print(f"\n📋 Pending Registrations ({len(users)}):")
        print("─" * 5)
        
        for user in users:
            print(f"\nUser ID: {user.id}")
            print(f"  Name: {user.full_name or 'N/A'}")
            print(f"  Phone: {user.phone_number}")
            print(f"  Telegram ID: {user.tg_user_id or 'N/A'}")
            print(f"  Username: @{user.username}" if user.username else "  Username: N/A")
            print(f"  Created: {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\n" + "─" * 5)
        print(f"\nTotal: {len(users)} pending registration(s)\n")


async def show_user_info(user_id: int):
    """Show detailed information about a user"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"\n❌ User with ID {user_id} not found.\n")
            return
        
        print(f"\n👤 User Information:")
        print("─" * 5)
        print(f"ID: {user.id}")
        print(f"Full Name: {user.full_name or 'N/A'}")
        print(f"First Name: {user.first_name or 'N/A'}")
        print(f"Last Name: {user.last_name or 'N/A'}")
        print(f"Phone: {user.phone_number}")
        print(f"Email: {user.email or 'N/A'}")
        print(f"Telegram ID: {user.tg_user_id or 'N/A'}")
        print(f"Username: @{user.username}" if user.username else "Username: N/A")
        print(f"Registration Status: {user.registration_status.value}")
        print(f"Subscription Status: {user.subscription_status.value}")
        print(f"Created: {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if user.updated_at:
            print(f"Updated: {user.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print("─" * 5 + "\n")


async def approve_registration(user_id: int):
    """Approve user registration"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"\n❌ User with ID {user_id} not found.\n")
            return
        
        if user.registration_status == RegistrationStatus.ACTIVE:
            print(f"\n⚠️ User {user_id} is already approved (status: ACTIVE).\n")
            return
        
        print(f"\n📝 Approving registration for user {user_id}...")
        print(f"   Name: {user.full_name}")
        print(f"   Phone: {user.phone_number}")
        
        # Update status
        user.registration_status = RegistrationStatus.ACTIVE
        await session.commit()
        
        print(f"✅ Status updated to ACTIVE")
        
        # Send notification to user
        if user.tg_user_id:
            bot = Bot(token=TG_BOT_TOKEN)
            try:
                await bot.send_message(
                    chat_id=user.tg_user_id,
                    text=REGISTRATION_APPROVED,
                    parse_mode=ParseMode.HTML
                )
                print(f"✅ Notification sent to Telegram user {user.tg_user_id}")
            except Exception as e:
                print(f"⚠️ Failed to send notification: {e}")
            finally:
                await bot.session.close()
        else:
            print("⚠️ No Telegram ID - notification not sent")
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.USER_REGISTERED,
            user_id=user.id,
            action_details={
                "action": "registration_approved_via_console",
                "approval_method": "console",
                "status": "approved",
                "phone": user.phone_number,
                "user_name": user.full_name
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        print(f"✅ Action logged\n")


async def reject_registration(user_id: int, reason: str = None):
    """Reject user registration"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"\n❌ User with ID {user_id} not found.\n")
            return
        
        if user.registration_status == RegistrationStatus.REJECTED:
            print(f"\n⚠️ User {user_id} is already rejected.\n")
            return
        
        if not reason:
            reason = "Не указано"
        
        print(f"\n📝 Rejecting registration for user {user_id}...")
        print(f"   Name: {user.full_name}")
        print(f"   Phone: {user.phone_number}")
        print(f"   Reason: {reason}")
        
        # Update status
        user.registration_status = RegistrationStatus.REJECTED
        await session.commit()
        
        print(f"✅ Status updated to REJECTED")
        
        # Send notification to user
        if user.tg_user_id:
            notification_text = REGISTRATION_REJECTED.format(reason=reason)
            bot = Bot(token=TG_BOT_TOKEN)
            try:
                await bot.send_message(
                    chat_id=user.tg_user_id,
                    text=notification_text,
                    parse_mode=ParseMode.HTML
                )
                print(f"✅ Notification sent to Telegram user {user.tg_user_id}")
            except Exception as e:
                print(f"⚠️ Failed to send notification: {e}")
            finally:
                await bot.session.close()
        else:
            print("⚠️ No Telegram ID - notification not sent")
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.USER_REGISTERED,
            user_id=user.id,
            action_details={
                "action": "registration_rejected_via_console",
                "approval_method": "console",
                "status": "rejected",
                "rejection_reason": reason,
                "phone": user.phone_number,
                "user_name": user.full_name
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        print(f"✅ Action logged\n")


def print_usage():
    """Print usage instructions"""
    print("""
Usage:
    python manage_registration.py list                           # List pending registrations
    python manage_registration.py approve <user_id>              # Approve registration
    python manage_registration.py reject <user_id> [reason]      # Reject registration
    python manage_registration.py info <user_id>                 # Show user details

Examples:
    python manage_registration.py list
    python manage_registration.py info 28
    python manage_registration.py approve 28
    python manage_registration.py reject 28 "Недостаточно данных"
    """)


async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print_usage()
        return
    
    command = sys.argv[1].lower()
    
    try:
        if command == "list":
            await list_pending_users()
        
        elif command == "info":
            if len(sys.argv) < 3:
                print("\n❌ Error: User ID required\n")
                print("Usage: python manage_registration.py info <user_id>\n")
                return
            
            user_id = int(sys.argv[2])
            await show_user_info(user_id)
        
        elif command == "approve":
            if len(sys.argv) < 3:
                print("\n❌ Error: User ID required\n")
                print("Usage: python manage_registration.py approve <user_id>\n")
                return
            
            user_id = int(sys.argv[2])
            await approve_registration(user_id)
        
        elif command == "reject":
            if len(sys.argv) < 3:
                print("\n❌ Error: User ID required\n")
                print("Usage: python manage_registration.py reject <user_id> [reason]\n")
                return
            
            user_id = int(sys.argv[2])
            reason = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else None
            await reject_registration(user_id, reason)
        
        else:
            print(f"\n❌ Unknown command: {command}\n")
            print_usage()
    
    except ValueError:
        print("\n❌ Error: Invalid user ID (must be a number)\n")
    except Exception as e:
        print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
