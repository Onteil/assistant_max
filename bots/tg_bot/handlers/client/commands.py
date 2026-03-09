"""
Command Handlers

Паттерн: Обработка команд бота
- Используйте Command фильтр для команд
- Всегда очищайте state при старте нового флоу
- Используйте FSMContext для управления состояниями
- Логируйте важные действия
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.texts import HELP_TEXT, MENU_ARCHIVE, MENU_INVOICE, MENU_PROFILE, MENU_SUPPORT

logger = logging.getLogger(__name__)

router = Router(name="commands")


@router.message(Command("help"))
async def help_command(message: Message):
    """
    Обработчик команды /help.
    
    Показывает справку по использованию бота.
    """
    await message.answer(HELP_TEXT)
    logger.info(f"User {message.from_user.id} requested help")


# Main menu button handlers - delegate to specific handlers

@router.message(F.text == MENU_INVOICE)
async def handle_invoice_button(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle "Get Invoice" button from main menu.
    
    Delegates to invoice handler's start_invoice_request.
    """
    from .invoice import start_invoice_request
    await start_invoice_request(message, state, session)


@router.message(F.text == MENU_SUPPORT)
async def handle_support_button(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle "Technical Support" button from main menu.
    
    Delegates to support handler's start_support_request.
    """
    from .support import start_support_request
    await start_support_request(message, state, session)


@router.message(F.text == MENU_PROFILE)
async def handle_profile_button(message: Message, session: AsyncSession):
    """
    Handle "My Profile" button from main menu.
    
    Delegates to profile handler's show_profile.
    """
    from .profile import show_profile
    await show_profile(message, session)


# Archive button is handled in archive.py



@router.message(F.text.startswith("📥 Активные обращения"))
async def handle_return_to_ticket_button(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle "Active Tickets" button from main menu.
    
    Shows inline list of all active tickets with pagination.
    Client can select a ticket to continue communication.
    
    Requirements: AC-1.3, TR-2
    """
    from services.client_service import (
        get_client_active_tickets,
        get_client_active_tickets_keyboard,
        format_client_active_tickets_header
    )
    
    user_id = message.from_user.id
    
    # Get all active tickets for this client
    tickets = await get_client_active_tickets(session, user_id)
    
    if not tickets:
        await message.answer("❌ У вас нет активных обращений")
        logger.info(f"Client {user_id} has no active tickets")
        return
    
    # Generate header text
    header_text = await format_client_active_tickets_header(
        tickets_count=len(tickets),
        current_page=0
    )
    
    # Generate inline keyboard with pagination
    keyboard = await get_client_active_tickets_keyboard(
        tickets=tickets,
        current_page=0
    )
    
    # Send message with ticket list
    await message.answer(
        header_text,
        reply_markup=keyboard
    )
    
    logger.info(f"Client {user_id} viewed {len(tickets)} active tickets")

