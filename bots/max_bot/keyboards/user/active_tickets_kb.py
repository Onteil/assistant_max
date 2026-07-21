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

# Filter labels
FILTER_LABELS = {
    "all": "✅ Все",
    "invoice": "💰 Счёт",
    "support": "🆘 ТП",
    "consultation": "💬 Консультация",
    "renewal": "🔄 Продление",
}

# Ticket type → filter key mapping
TICKET_TYPE_TO_FILTER = {
    "invoice": "invoice",
    "support": "support",
    "technical_support": "support",
    "consultation": "consultation",
    "renewal": "renewal",
}


def filter_tickets(tickets: List[Ticket], filter_key: str) -> List[Ticket]:
    """Filter tickets by type key."""
    if filter_key == "all":
        return tickets
    return [
        t for t in tickets
        if TICKET_TYPE_TO_FILTER.get(
            t.ticket_type.value if hasattr(t.ticket_type, 'value') else t.ticket_type,
            ""
        ) == filter_key
    ]


async def get_active_tickets_keyboard(
    tickets: List[Ticket],
    page: int = 0,
    active_filter: str = "all",
) -> Keyboard:
    """
    Create inline keyboard with active tickets list, filter buttons, and pagination.

    Layout:
      Row 1: [✅ Все] [💰 Счёт] [🆘 ТП]
      Row 2: [💬 Консультация] [🔄 Продление]
      ...ticket buttons...
      Pagination: [⏮️] [◀️] X/N [▶️] [⏭️]
      [🏠 В меню]

    Args:
        tickets: Full list of active tickets (unfiltered)
        page: Current page number (0-indexed)
        active_filter: Active filter key

    Returns:
        Inline keyboard with filter, ticket buttons, pagination, and back button
    """
    from bots.max_bot.payloads import (
        MainMenuActionPayload,
        TicketSelectPayload,
        TicketsFilterPayload,
        TicketsPaginationPayload,
    )

    buttons = []

    # --- Determine which ticket types are present ---
    present_types: set[str] = set()
    for t in tickets:
        raw = t.ticket_type.value if hasattr(t.ticket_type, 'value') else t.ticket_type
        fkey = TICKET_TYPE_TO_FILTER.get(raw, "")
        if fkey:
            present_types.add(fkey)

    # --- Filter rows (only show filters for types that exist) ---
    # Row 1: Все, Счёт (if any), ТП (if any)
    row1 = []
    for key in ("all", "invoice", "support"):
        if key != "all" and key not in present_types:
            continue
        label = FILTER_LABELS[key]
        if key == active_filter:
            label = f"[{label}]"
        row1.append(KeyboardButton(
            text=label,
            payload=TicketsFilterPayload(filter=key).pack()
        ))
    if row1:
        buttons.append(row1)

    # Row 2: Консультация (if any), Продление (if any)
    row2 = []
    for key in ("consultation", "renewal"):
        if key not in present_types:
            continue
        label = FILTER_LABELS[key]
        if key == active_filter:
            label = f"[{label}]"
        row2.append(KeyboardButton(
            text=label,
            payload=TicketsFilterPayload(filter=key).pack()
        ))
    if row2:
        buttons.append(row2)

    # --- Apply filter ---
    filtered = filter_tickets(tickets, active_filter)

    # Calculate pagination
    total_tickets = len(filtered)
    total_pages = max(1, (total_tickets + TICKETS_PER_PAGE - 1) // TICKETS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start_idx = page * TICKETS_PER_PAGE
    end_idx = min(start_idx + TICKETS_PER_PAGE, total_tickets)

    # --- Ticket buttons ---
    for ticket in filtered[start_idx:end_idx]:
        ticket_type_info = {
            "invoice": ("💰", "Счёт"),
            "support": ("🆘", "ТП"),
            "technical_support": ("🆘", "ТП"),
            "consultation": ("💬", "Консультация"),
            "renewal": ("🔄", "Продление"),
        }
        ticket_type_emoji, ticket_type_name = ticket_type_info.get(
            ticket.ticket_type.value if hasattr(ticket.ticket_type, 'value') else ticket.ticket_type,
            ("📋", "Заявка")
        )

        status_emoji = {
            "new": "🆕",
            "in_progress": "⏳",
            "waiting_client": "⏸",
        }.get(ticket.ticket_status.value, "📋")

        date_str = ticket.created_at.strftime("%d.%m") if ticket.created_at else "—"
        button_text = f"{status_emoji} {ticket_type_emoji} {ticket_type_name} #{ticket.id} ({date_str})"

        buttons.append([
            KeyboardButton(
                text=button_text,
                payload=TicketSelectPayload(ticket_id=ticket.id).pack()
            )
        ])

    # --- Pagination ---
    if total_pages > 1:
        pagination_row = []

        # First page button (skip if already on first page)
        if page > 1:
            pagination_row.append(KeyboardButton(
                text="⏮️",
                payload=TicketsPaginationPayload(page=0, filter=active_filter).pack()
            ))

        # Previous page
        if page > 0:
            pagination_row.append(KeyboardButton(
                text="◀️",
                payload=TicketsPaginationPayload(page=page - 1, filter=active_filter).pack()
            ))

        # Page indicator (non-clickable — reuse current page payload)
        pagination_row.append(KeyboardButton(
            text=f"{page + 1}/{total_pages}",
            payload=TicketsPaginationPayload(page=page, filter=active_filter).pack()
        ))

        # Next page
        if page < total_pages - 1:
            pagination_row.append(KeyboardButton(
                text="▶️",
                payload=TicketsPaginationPayload(page=page + 1, filter=active_filter).pack()
            ))

        # Last page button (skip if already on last page)
        if page < total_pages - 2:
            pagination_row.append(KeyboardButton(
                text="⏭️",
                payload=TicketsPaginationPayload(page=total_pages - 1, filter=active_filter).pack()
            ))

        if pagination_row:
            buttons.append(pagination_row)

    # --- Back to main menu ---
    buttons.append([
        KeyboardButton(
            text="🏠 В меню",
            payload=MainMenuActionPayload(action="main_menu").pack()
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
        "technical_support": "Техподдержка",
        "consultation": "Консультация",
        "renewal": "Продление",
    }.get(
        ticket.ticket_type.value if hasattr(ticket.ticket_type, 'value') else ticket.ticket_type,
        "Обращение"
    )

    status_name = {
        "new": "Новое",
        "in_progress": "В работе",
        "waiting_client": "Ожидает ответа",
    }.get(ticket.ticket_status.value, ticket.ticket_status.value)

    card = f"📋 <b>Обращение #{ticket.id}</b>\n\n"
    card += f"<b>Тип:</b> {ticket_type_name}\n"
    card += f"<b>Статус:</b> {status_name}\n"

    if ticket.created_at:
        card += f"<b>Создано:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"

    if ticket.assigned_staff:
        card += f"<b>Менеджер:</b> {ticket.assigned_staff.full_name}\n"

    if hasattr(ticket, 'delivery_method') and ticket.delivery_method:
        delivery_method_names = {
            "telegram": "💬 В чат",
            "email": "📧 На Email",
            "none": "❌ Не указан",
        }
        delivery_method_text = delivery_method_names.get(
            ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method),
            str(ticket.delivery_method)
        )
        card += f"<b>Способ получения:</b> {delivery_method_text}\n"

        if (ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method)) == "email":
            if hasattr(ticket, 'delivery_email') and ticket.delivery_email:
                card += f"<b>Email для доставки:</b> {ticket.delivery_email}\n"

    return card
