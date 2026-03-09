"""
Cancel Command Handler

Provides global /cancel command that works in all FSM states.
Cleans up state and returns user to main menu.

Requirements: 27.1-27.5, 28.1-28.5
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.keyboards.main_menu_kb import get_main_menu_keyboard
from bots.tg_bot.texts import FLOW_CANCELLED, MAIN_MENU
from database.models import RegistrationStatus
from services.user_service import get_user_by_tg_id

logger = logging.getLogger(__name__)

router = Router(name="cancel")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, session: AsyncSession):
    """
    Global cancel command handler.
    
    Works in all FSM states:
    - Clears FSM state
    - Returns user to main menu (if registered and active)
    - Ensures no partial data is persisted
    
    Requirements: 27.1, 27.2, 27.3, 27.4, 27.5, 28.1, 28.2, 28.3, 28.4, 28.5
    """
    tg_user_id = message.from_user.id
    
    # Get current state
    current_state = await state.get_state()
    
    # Clear FSM state
    await state.clear()
    
    logger.info(
        f"User {tg_user_id} cancelled operation, "
        f"previous state: {current_state or 'None'}"
    )
    
    # Check if user is registered and active
    try:
        user = await get_user_by_tg_id(session, tg_user_id)
        
        if user and user.registration_status == RegistrationStatus.ACTIVE:
            # Show main menu for active users
            # Check for active tickets count
            from services.client_service import get_client_active_tickets
            
            active_tickets = await get_client_active_tickets(session, tg_user_id)
            active_tickets_count = len(active_tickets)
            
            main_menu_keyboard = await get_main_menu_keyboard(active_tickets_count=active_tickets_count)
            await message.answer(
                FLOW_CANCELLED + "\n\n" + MAIN_MENU,
                reply_markup=main_menu_keyboard
            )
        else:
            # Just show cancellation message for non-active users
            await message.answer(
                FLOW_CANCELLED + "\n\nИспользуйте /start для начала работы.",
                reply_markup=ReplyKeyboardRemove()
            )
    
    except Exception as e:
        logger.error(
            f"Error in cancel handler for user {tg_user_id}: {e}",
            exc_info=True
        )
        # Fallback - just clear state and show cancellation
        await message.answer(
            FLOW_CANCELLED,
            reply_markup=ReplyKeyboardRemove()
        )


@router.message(F.text == "❌ Отмена")
async def handle_cancel_button(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle cancel button press (text-based).
    
    Delegates to cmd_cancel for consistent behavior.
    
    Requirements: 28.2, 28.4
    """
    await cmd_cancel(message, state, session)
