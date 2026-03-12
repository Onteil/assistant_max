"""
Active Tickets Keyboard for MAX Bot

Provides inline keyboard for displaying and selecting active tickets.

Requirements: AC-1.3, TR-2
"""

import logging
from typing import List

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from database.models import Ticket

logger = logging.getLogger(__name__)

# Pagination settings
TICKETS_PER_PAGE = 5


async def get_active_tickets_keyboard(
    tickets: List[Ticket],
    page: int = 0
) -> Keyboard:
    """
    Create inline keyboard with active tickets list and pagination.
    
    Uses CallbackPayload classes for type-safe payload handling.
    
    Shows up to TICKETS_PER_PAGE tickets per page with:
    - Ticket number and type
    - Status indicator
    - Pagination buttons if needed
    - Back to main menu button
    
    Args:
        tickets: List of active tickets
        page: Current page number (0-indexed)
    
    Returns:
        Inline keyboard with ticket buttons and pagination
    
    Requirements: AC-1.3, TR-2
    """
    from bots.max_bot.payloads import (
        TicketSelectPayload,
        TicketsPaginationPayload,
        ActiveTicketsClosePayload
    )
    
    buttons = []
    
    # Calculate pagination
    total_tickets = len(tickets)
    total_pages = (total_tickets + TICKETS_PER_PAGE - 1) // TICKETS_PER_PAGE
    start_idx = page * TICKETS_PER_PAGE
    end_idx = min(start_idx + TICKETS_PER_PAGE, total_tickets)
    
    # Add ticket buttons for current page
    for ticket in tickets[start_idx:end_idx]:
        # Get ticket type emoji and name
        ticket_type_info = {
            "invoice": ("💰", "Счёт"),
            "support": ("🆘", "ТП"),
            "renewal": ("🔄", "Продление")
        }
        ticket_type_emoji, ticket_type_name = ticket_type_info.get(
            ticket.ticket_type,
            ("📋", "Заявка")
        )
        
        # Get status emoji
        status_emoji = {
            "new": "🆕",
            "in_progress": "⏳",
            "waiting_client": "⏸"
        }.get(ticket.ticket_status.value, "📋")
        
        # Format creation date
        date_str = ticket.created_at.strftime("%d.%m") if ticket.created_at else "Не указано"
        
        # Build button text: emoji Type name #ID status (date)
        button_text = f"{ticket_type_emoji} {ticket_type_name} #{ticket.id} {status_emoji} ({date_str})"
        
        buttons.append([
            KeyboardButton(
                text=button_text,
                payload=TicketSelectPayload(ticket_id=ticket.id).pack()
            )
        ])
    
    # Add pagination buttons if needed
    if total_pages > 1:
        pagination_row = []
        
        # Previous page button
        if page > 0:
            pagination_row.append(
                KeyboardButton(
                    text="◀️",
                    payload=TicketsPaginationPayload(page=page - 1).pack()
                )
            )
        
        # Next page button
        if page < total_pages - 1:
            pagination_row.append(
                KeyboardButton(
                    text="▶️",
                    payload=TicketsPaginationPayload(page=page + 1).pack()
                )
            )
        
        if pagination_row:
            buttons.append(pagination_row)
    
    # Add back to main menu button
    buttons.append([
        KeyboardButton(
            text="🏠 В меню",
            payload=ActiveTicketsClosePayload().pack()
        )
    ])
    
    return Keyboard(buttons=buttons, inline=True)


async def format_ticket_card_for_client(ticket: Ticket) -> str:
    """
    Format ticket information for client display.
    
    Args:
        ticket: Ticket object
    
    Returns:
        Formatted ticket card text
    """
    ticket_type_name = {
        "invoice": "Запрос счета",
        "support": "Техподдержка",
        "renewal": "Продление"
    }.get(ticket.ticket_type, "Обращение")
    
    status_name = {
        "new": "Новое",
        "in_progress": "В работе",
        "waiting_client": "Ожидает ответа"
    }.get(ticket.ticket_status.value, ticket.ticket_status.value)
    
    card = f"📋 <b>Обращение #{ticket.id}</b>\n\n"
    card += f"<b>Тип:</b> {ticket_type_name}\n"
    card += f"<b>Статус:</b> {status_name}\n"
    
    if ticket.created_at:
        card += f"<b>Создано:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    
    if ticket.assigned_staff:
        card += f"<b>Менеджер:</b> {ticket.assigned_staff.full_name}\n"
    
    # Add delivery method information
    if hasattr(ticket, 'delivery_method') and ticket.delivery_method:
        delivery_method_names = {
            "telegram": "💬 В чат",
            "email": "📧 На Email",
            "none": "❌ Не указан"
        }
        delivery_method_text = delivery_method_names.get(
            ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method),
            str(ticket.delivery_method)
        )
        card += f"<b>Способ получения:</b> {delivery_method_text}\n"
        
        # Add delivery email if method is email
        if (ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method)) == "email":
            if hasattr(ticket, 'delivery_email') and ticket.delivery_email:
                card += f"<b>Email для доставки:</b> {ticket.delivery_email}\n"
    
    return card
