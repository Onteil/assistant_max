"""
Admin Panel Handler for MAX Bot

Handles admin panel entry point and main menu navigation.
Provides access to employees, operations, calendar, settings, and analytics sections.

Requirements: Admin Panel Interface
"""

import logging

from maxapi.types import MessageCallback
from maxapi.context import MemoryContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import ManagerMenuActionPayload, AdminMenuPayload
from database.models import Staff_Member, StaffRole

logger = logging.getLogger(__name__)


async def is_admin(session: AsyncSession, max_user_id: int) -> Staff_Member | None:
    """
    Check if user is an administrator and return their record.
    
    Args:
        session: Database session
        max_user_id: MAX user ID
    
    Returns:
        Staff_Member object if user is admin, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == max_user_id,
            Staff_Member.is_active == True,
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking admin status for MAX user {max_user_id}: {e}", exc_info=True)
        return None


def get_admin_panel_keyboard() -> Keyboard:
    """
    Create admin panel main menu keyboard.
    
    Returns:
        Keyboard with admin panel menu buttons
    
    Layout:
    [👥 Сотрудники] [📋 Операции]
    [📅 График работы] [⚙️ Настройки]
    [📊 Статистика]
    [🏠 В меню]
    """
    buttons = [
        # Row 1: Employees and Operations
        [
            KeyboardButton(
                text="👥 Сотрудники",
                payload=AdminMenuPayload(action="employees").pack()
            ),
            KeyboardButton(
                text="📋 Операции",
                payload=AdminMenuPayload(action="operations").pack()
            )
        ],
        # Row 2: Calendar and Settings
        [
            KeyboardButton(
                text="📅 График работы",
                payload=AdminMenuPayload(action="calendar").pack()
            ),
            KeyboardButton(
                text="⚙️ Настройки",
                payload=AdminMenuPayload(action="settings").pack()
            )
        ],
        # Row 3: Analytics
        [
            KeyboardButton(
                text="📊 Статистика",
                payload=AdminMenuPayload(action="analytics").pack()
            )
        ],
        # Row 4: Back to Manager Menu
        [
            KeyboardButton(
                text="🏠 В меню",
                payload=AdminMenuPayload(action="back_to_manager").pack()
            )
        ]
    ]
    
    return Keyboard(buttons=buttons, inline=True)


# ========== Admin Panel Entry Point ==========


async def handle_admin_panel_action(
    event: MessageCallback,
    payload: ManagerMenuActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle admin panel button press from manager menu.
    
    Entry point to the administrative panel. Displays main menu with navigation
    to all admin sections: employees, operations, calendar, settings, analytics.
    
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: ManagerMenuActionPayload with action="admin_panel"
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: Admin Panel Interface
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Admin panel access attempt: max_user_id={max_user_id}")
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к административной панели.\n"
                     "Эта функция доступна только администраторам.",
                parse_mode="HTML"
            )
            logger.warning(f"Non-admin user {max_user_id} attempted to access admin panel")
            return
        
        # Clear any existing FSM state to start fresh
        await context.clear()
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get admin panel main menu keyboard
        keyboard = get_admin_panel_keyboard()
        
        # Send admin panel main menu
        from bots.max_bot.texts import ADMIN_PANEL_MENU
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ADMIN_PANEL_MENU,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} ({admin.full_name}) accessed admin panel")
        
    except Exception as e:
        logger.error(f"Error showing admin panel for user {max_user_id}: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке административной панели. Попробуйте позже.",
            parse_mode="HTML"
        )


# ========== Admin Panel Main Menu Navigation ==========


async def handle_admin_menu_action(
    event: MessageCallback,
    payload: AdminMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle admin panel menu navigation.
    
    Routes to different admin sections based on action.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: AdminMenuPayload with action
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    action = payload.action
    
    logger.info(f"Admin menu action: max_user_id={max_user_id}, action={action}")
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к административной панели.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Route to appropriate section
        if action == "employees":
            # Show employees menu
            from bots.max_bot.handlers.staff.employees import handle_employees_menu
            
            # Call employees menu handler
            await handle_employees_menu(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        
        elif action == "employees_back":
            # Return to admin panel from employees section
            from bots.max_bot.texts import ADMIN_PANEL_MENU
            
            keyboard = get_admin_panel_keyboard()
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ADMIN_PANEL_MENU,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        
        elif action == "operations":
            # Show operations menu
            from bots.max_bot.handlers.staff.operations import handle_operations_menu
            
            # Call operations menu handler
            await handle_operations_menu(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        
        elif action == "calendar":
            # Show calendar menu
            from bots.max_bot.handlers.staff.calendar import handle_calendar_menu
            
            # Create a pseudo-payload for calendar menu
            calendar_payload = AdminMenuPayload(action="calendar")
            
            # Call calendar menu handler
            await handle_calendar_menu(
                event=event,
                payload=calendar_payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        
        elif action == "calendar_back":
            # Return to admin panel from calendar section
            from bots.max_bot.texts import ADMIN_PANEL_MENU
            
            keyboard = get_admin_panel_keyboard()
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ADMIN_PANEL_MENU,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        
        elif action == "settings":
            # Show settings menu
            from bots.max_bot.handlers.staff.settings import handle_settings_menu
            
            # Call settings menu handler
            await handle_settings_menu(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        
        elif action == "analytics":
            # Show analytics dashboard
            from bots.max_bot.handlers.staff.analytics import handle_analytics_dashboard
            
            # Call analytics dashboard handler
            await handle_analytics_dashboard(
                event=event,
                payload=payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
        
        elif action == "back":
            # Return to admin panel main menu
            from bots.max_bot.texts import ADMIN_PANEL_MENU
            
            keyboard = get_admin_panel_keyboard()
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ADMIN_PANEL_MENU,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        
        elif action == "back_to_manager":
            # Return to manager menu from admin panel
            is_admin_role = admin.staff_role == StaffRole.ADMINISTRATOR
            
            # Import manager keyboard
            from bots.max_bot.keyboards.staff.manager_kb import get_manager_menu_keyboard
            from bots.max_bot.handlers.staff.manager import get_employee_menu_text
            
            keyboard = get_manager_menu_keyboard(is_admin=is_admin_role)
            
            # Get current work mode
            from services.calendar_service import get_current_work_mode
            work_mode = await get_current_work_mode(session)
            
            menu_text = get_employee_menu_text(
                role=admin.staff_role.value,
                full_name=admin.full_name,
                position=admin.position,
                work_mode=work_mode.value if work_mode else None
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=menu_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Administrator {max_user_id} returned to manager menu from admin panel")
        
        else:
            logger.warning(f"Unknown admin menu action: {action}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестное действие.",
                parse_mode="HTML"
            )
        
        logger.info(f"Administrator {max_user_id} navigated to {action}")
        
    except Exception as e:
        logger.error(f"Error handling admin menu action: action={action}, error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )
