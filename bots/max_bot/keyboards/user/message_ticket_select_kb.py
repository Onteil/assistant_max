"""
Keyboard for selecting a ticket when routing a free-text message.

Shown when user sends a message without active FSM state and has multiple
active tickets. No filters — just paginated ticket list with cancel button.
"""

import logging
from typing import List

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
from database.models import Ticket

logger = logging.getLogger(__name__)

TICKETS_PER_PAGE = 5

# Ticket type display info
TICKET_TYPE_INFO = {
    "invoice": ("💰", "Счёт"),
    "support": ("🆘", "ТП"),
    "technical_support": ("🆘", "ТП"),
    "consultation": ("💬", "Консультация"),
    "renewal": ("🔄", "Активация подписки"),
}

STATUS_EMOJI = {
    "new": "🆕",
    "in_progress": "⏳",
    "waiting_client": "⏸",
}


async def get_message_ticket_select_keyboard(
    tickets: List[Ticket],
    page: int = 0,
) -> Keyboard:
    """
    Create inline keyboard for selecting a ticket to route a message to.

    Layout:
      ...ticket buttons (paginated)...
      Pagination: [◀️] X/N [▶️]
      [❌ Отмена]

    Args:
        tickets: List of active tickets
        page: Current page number (0-indexed)

    Returns:
        Inline keyboard with ticket buttons, pagination, and cancel button
    """
    from bots.max_bot.payloads import (
        MessageTicketSelectPayload,
        MessageTicketPaginationPayload,
        MessageTicketCancelPayload,
    )

    total = len(tickets)
    total_pages = max(1, (total + TICKETS_PER_PAGE - 1) // TICKETS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * TICKETS_PER_PAGE
    end = min(start + TICKETS_PER_PAGE, total)

    buttons = []

    for ticket in tickets[start:end]:
        raw_type = ticket.ticket_type.value if hasattr(ticket.ticket_type, 'value') else ticket.ticket_type
        emoji, type_name = TICKET_TYPE_INFO.get(raw_type, ("📋", "Заявка"))

        raw_status = ticket.ticket_status.value if hasattr(ticket.ticket_status, 'value') else ticket.ticket_status
        status_emoji = STATUS_EMOJI.get(raw_status, "📋")

        date_str = ticket.created_at.strftime("%d.%m") if ticket.created_at else "—"
        text = f"{status_emoji} {emoji} {type_name} #{ticket.id} ({date_str})"

        buttons.append([KeyboardButton(
            text=text,
            payload=MessageTicketSelectPayload(ticket_id=ticket.id).pack()
        )])

    # Pagination row
    if total_pages > 1:
        pagination_row = []
        if page > 0:
            pagination_row.append(KeyboardButton(
                text="◀️",
                payload=MessageTicketPaginationPayload(page=page - 1).pack()
            ))
        pagination_row.append(KeyboardButton(
            text=f"{page + 1}/{total_pages}",
            payload=MessageTicketPaginationPayload(page=page).pack()
        ))
        if page < total_pages - 1:
            pagination_row.append(KeyboardButton(
                text="▶️",
                payload=MessageTicketPaginationPayload(page=page + 1).pack()
            ))
        buttons.append(pagination_row)

    buttons.append([KeyboardButton(
        text="❌ Отмена",
        payload=MessageTicketCancelPayload().pack()
    )])

    return Keyboard(buttons=buttons, inline=True)
