"""
Ticket List Inline Keyboards for MAX Bot

Generates inline keyboards for active tickets list.
"""

import logging

from maxapi.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.callback_datas import TicketListCallback
from database.models import Ticket
from services.employee_service import (
    get_ticket_status_emoji,
    has_unread_messages,
)

logger = logging.getLogger(__name__)


async def build_active_tickets_keyboard(
    tickets: list[Ticket],
    focused_ticket_id: int | None,
    employee_id: int,
    session: AsyncSession
) -> InlineKeyboardMarkup:
    """
    Generate inline keyboard for active tickets list.
    
    Each row contains:
    - Ticket button (left): [Emoji #ID Client (info)] - click to focus
    - Actions button (right): [📋] - click to open actions menu
    
    Args:
        tickets: List of active tickets
        focused_ticket_id: ID of currently focused ticket (if any)
        employee_id: Employee's MAX user ID
        session: Database session
    
    Returns:
        InlineKeyboardMarkup with ticket list
    
    Requirements: Active Tickets Inline Keyboard
    """
    try:
        buttons = []
        
        for ticket in tickets:
            # Check for unread messages
            has_unread, unread_count = await has_unread_messages(
                session, ticket.id, employee_id
            )
            
            # Determine if this ticket is focused
            is_focused = (focused_ticket_id == ticket.id)
            
            # Get status emoji
            emoji = get_ticket_status_emoji(ticket, has_unread, is_focused)
            
            # Get client name
            client_name = ticket.user.full_name or ticket.user.first_name or "Неизвестно"
            
            # Build ticket button text
            ticket_text = f"{emoji} #{ticket.id} {client_name}"
            
            # Add unread count if applicable
            if has_unread and unread_count > 0:
                ticket_text += f" ({unread_count} сообщ.)"
            
            # Create row with two buttons
            row = [
                InlineKeyboardButton(
                    text=ticket_text,
                    callback_data=TicketListCallback(
                        action="focus_ticket",
                        ticket_id=ticket.id
                    ).pack()
                ),
                InlineKeyboardButton(
                    text="📋",
                    callback_data=TicketListCallback(
                        action="ticket_actions",
                        ticket_id=ticket.id
                    ).pack()
                )
            ]
            
            buttons.append(row)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        logger.info(
            f"Generated active tickets keyboard: "
            f"tickets_count={len(tickets)}, focused_ticket_id={focused_ticket_id}"
        )
        
        return keyboard
        
    except Exception as e:
        logger.error(
            f"Error generating active tickets keyboard: error={e}",
            exc_info=True
        )
        raise
