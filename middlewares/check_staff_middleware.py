"""
Staff Member Check Middleware

This middleware restricts access to employee interface handlers to staff members only.
It checks if the user is an active staff member in the database and provides
the staff member record to handlers.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Staff_Member


class StaffMemberCheckMiddleware(BaseMiddleware):
    """
    Middleware to verify user is an active staff member.
    
    This middleware:
    - Checks if the user exists in Staff_Member table
    - Verifies the staff member is active (is_active = True)
    - Provides the staff member record to handlers via data["employee"]
    - Blocks access for non-staff users with a friendly message
    
    Usage:
        Apply this middleware to employee interface routers to restrict access.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Get user from event
        user = data.get("event_from_user")
        
        if user is None:
            # No user in event, skip middleware
            return await handler(event, data)
        
        # Get database session
        session: AsyncSession = data.get("session")
        if session is None:
            # No session available, skip middleware
            return await handler(event, data)
        
        # Check if user is an active staff member
        try:
            # Get telegram_id from user
            telegram_id = user.id
            
            stmt = select(Staff_Member).where(
                Staff_Member.tg_user_id == telegram_id,
                Staff_Member.is_active == True
            )
            result = await session.execute(stmt)
            employee = result.scalar_one_or_none()
            
            if employee:
                # User is a staff member, provide employee record to handlers
                data["employee"] = employee
                return await handler(event, data)
            else:
                # User is not a staff member, deny access
                rejection_text = (
                    "❌ *Доступ запрещен*\n\n"
                    "Эта функция доступна только сотрудникам.\n\n"
                    "Если вы являетесь сотрудником и видите это сообщение, "
                    "обратитесь к администратору."
                )
                
                # Send rejection message based on event type
                if isinstance(event, Message):
                    await event.answer(rejection_text, parse_mode="Markdown")
                elif isinstance(event, CallbackQuery):
                    await event.message.answer(rejection_text, parse_mode="Markdown")
                    await event.answer("Доступ запрещен.", show_alert=True)
                
                # Stop further processing
                return
                
        except Exception as e:
            # Log error and allow handler to proceed (fail open for safety)
            import logging
            logging.error(f"Error in StaffMemberCheckMiddleware: {e}", exc_info=True)
            return await handler(event, data)
