"""
Client service layer for managing client interface operations.

Provides async functions for client ticket management, ticket list formatting,
and keyboard generation.
"""

import logging
from math import ceil

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import File_Attachment, Ticket, TicketStatus, User

logger = logging.getLogger(__name__)

# Pagination settings
TICKETS_PER_PAGE = 5


async def get_client_active_tickets(
    session: AsyncSession,
    tg_user_id: int
) -> list[Ticket]:
    """
    Get all active tickets for a client.
    
    Returns tickets with status NEW, IN_PROGRESS, or WAITING_CLIENT,
    ordered by updated_at descending (most recent first).
    
    Args:
        session: Database session
        tg_user_id: Client's Telegram user ID
    
    Returns:
        List of active Ticket objects ordered by updated_at desc
    """
    try:
        stmt = (
            select(Ticket)
            .join(User, Ticket.user_id == User.id)
            .where(
                User.tg_user_id == tg_user_id,
                Ticket.ticket_status.in_([
                    TicketStatus.NEW,
                    TicketStatus.IN_PROGRESS,
                    TicketStatus.WAITING_CLIENT
                ])
            )
            .order_by(Ticket.updated_at.desc())
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.assigned_staff)
            )
        )
        
        result = await session.execute(stmt)
        tickets = list(result.scalars().all())
        
        logger.info(f"Found {len(tickets)} active tickets for client {tg_user_id}")
        return tickets
        
    except Exception as e:
        logger.error(
            f"Error getting active tickets for client {tg_user_id}: {e}",
            exc_info=True
        )
        return []


async def get_client_active_tickets_keyboard(
    tickets: list[Ticket],
    current_page: int = 0
) -> InlineKeyboardMarkup:
    """
    Generate inline keyboard for client's active tickets list with pagination.
    
    Each row contains a ticket button with ticket info.
    Bottom row contains pagination buttons if needed.
    
    Args:
        tickets: List of active tickets
        current_page: Current page number (0-indexed)
    
    Returns:
        InlineKeyboardMarkup with ticket list and pagination
    """
    try:
        from bots.tg_bot.callback_datas import ClientTicketListCallback
        
        buttons = []
        
        # Calculate pagination
        total_tickets = len(tickets)
        total_pages = ceil(total_tickets / TICKETS_PER_PAGE) if total_tickets > 0 else 1
        current_page = max(0, min(current_page, total_pages - 1))
        
        start_idx = current_page * TICKETS_PER_PAGE
        end_idx = min(start_idx + TICKETS_PER_PAGE, total_tickets)
        
        page_tickets = tickets[start_idx:end_idx]
        
        # Add ticket buttons
        for ticket in page_tickets:
            # Get ticket type emoji
            if ticket.ticket_type == "INVOICE":
                emoji = "💰"
            elif ticket.ticket_type == "TECHNICAL_SUPPORT":
                emoji = "🔧"
            else:
                emoji = "📋"
            
            # Get status text
            status_text = ""
            if ticket.ticket_status == TicketStatus.NEW:
                status_text = "Новая"
            elif ticket.ticket_status == TicketStatus.IN_PROGRESS:
                status_text = "В работе"
            elif ticket.ticket_status == TicketStatus.WAITING_CLIENT:
                status_text = "Ожидает ответа"
            
            # Format date
            date_str = ticket.created_at.strftime("%d.%m.%Y")
            
            # Build button text
            button_text = f"{emoji} #{ticket.id} - {status_text} ({date_str})"
            
            buttons.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=ClientTicketListCallback(
                        action="select_ticket",
                        ticket_id=ticket.id,
                        page=current_page
                    ).pack()
                )
            ])
        
        # Add pagination buttons if needed
        if total_pages > 1:
            pagination_row = []
            
            # Previous page button
            if current_page > 0:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data=ClientTicketListCallback(
                            action="page",
                            page=current_page - 1
                        ).pack()
                    )
                )
            
            # Page indicator
            pagination_row.append(
                InlineKeyboardButton(
                    text=f"{current_page + 1}/{total_pages}",
                    callback_data="noop"
                )
            )
            
            # Next page button
            if current_page < total_pages - 1:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="Вперёд ▶️",
                        callback_data=ClientTicketListCallback(
                            action="page",
                            page=current_page + 1
                        ).pack()
                    )
                )
            
            buttons.append(pagination_row)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        logger.info(
            f"Generated client tickets keyboard: "
            f"total={total_tickets}, page={current_page + 1}/{total_pages}"
        )
        
        return keyboard
        
    except Exception as e:
        logger.error(
            f"Error generating client tickets keyboard: error={e}",
            exc_info=True
        )
        raise


async def format_client_active_tickets_header(
    tickets_count: int,
    current_page: int = 0
) -> str:
    """
    Format header text for client's active tickets list.
    
    Args:
        tickets_count: Total number of active tickets
        current_page: Current page number (0-indexed)
    
    Returns:
        Formatted header text
    """
    total_pages = ceil(tickets_count / TICKETS_PER_PAGE) if tickets_count > 0 else 1
    
    header_lines = [
        "📥 Активные обращения",
        "",
        "Используйте это меню для возврата к диалогу с менеджером конкретной заявки.",
        "",
        f"Всего обращений: {tickets_count}"
    ]
    
    if total_pages > 1:
        header_lines.append(f"Страница: {current_page + 1}/{total_pages}")
    
    header_lines.append("")
    header_lines.append("Выберите обращение для продолжения диалога:")
    
    return "\n".join(header_lines)


async def format_ticket_card_for_client(
    ticket: Ticket,
    session: AsyncSession
) -> str:
    """
    Format ticket information as text card for client view.
    
    Shows client's own data instead of "Client" label.
    
    Args:
        ticket: Ticket object to format
        session: Database session
    
    Returns:
        Formatted ticket card as string
    """
    try:
        from services.employee_service import calculate_ticket_elapsed_time
        
        # Ticket header
        lines = [
            f"✅ Работа с заявкой #{ticket.id}",
        ]
        
        # Status
        status_emoji = {
            TicketStatus.NEW: "🆕",
            TicketStatus.IN_PROGRESS: "⚙️",
            TicketStatus.WAITING_CLIENT: "⏳",
            TicketStatus.CLOSED: "✅",
            TicketStatus.CANCELLED: "❌"
        }
        status_text = {
            TicketStatus.NEW: "Новое",
            TicketStatus.IN_PROGRESS: "В работе",
            TicketStatus.WAITING_CLIENT: "Ожидание ответа",
            TicketStatus.CLOSED: "Закрыто",
            TicketStatus.CANCELLED: "Отменено"
        }
        emoji = status_emoji.get(ticket.ticket_status, "")
        status = status_text.get(ticket.ticket_status, str(ticket.ticket_status.value))
        lines.append(f"{emoji} Статус: {status}")
        lines.append("")
        
        # Client's own data
        lines.append("👤 Ваши данные:")
        
        # Full name
        client_name = ticket.user.full_name or ticket.user.first_name or "Не указано"
        lines.append(f"  • ФИО: {client_name}")
        
        # Phone
        if ticket.user.phone_number:
            lines.append(f"  • Телефон: {ticket.user.phone_number}")
        
        # Email
        if ticket.user.email:
            lines.append(f"  • Email: {ticket.user.email}")
        
        # Username
        if ticket.user.username:
            lines.append(f"  • Username: @{ticket.user.username}")
        
        lines.append("")
        
        # INN (if available)
        if ticket.organization_inn:
            lines.append(f"📋 ИНН: {ticket.organization_inn}")
        
        # GS Keys (if available)
        if ticket.gs_keys:
            key_numbers = [key.key_number for key in ticket.gs_keys]
            lines.append(f"🔑 Ключи ГС: {', '.join(key_numbers)}")
        
        # Add blank line after INN/Keys if they exist
        if ticket.organization_inn or ticket.gs_keys:
            lines.append("")
        
        # Delivery method (if available)
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
            lines.append(f"📦 Способ получения: {delivery_method_text}")
            
            # Add delivery email if method is email
            if (ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method)) == "email":
                if hasattr(ticket, 'delivery_email') and ticket.delivery_email:
                    lines.append(f"📧 Email для доставки: {ticket.delivery_email}")
            
            lines.append("")
        
        # Description (if available)
        if ticket.description:
            lines.append(f"📝 Описание: {ticket.description}")
        
        # Elapsed time
        elapsed = await calculate_ticket_elapsed_time(ticket)
        lines.append(f"⏱ Время: {elapsed}")
        lines.append("")
        
        # File attachment count (if any)
        stmt = select(File_Attachment).where(File_Attachment.ticket_id == ticket.id)
        result = await session.execute(stmt)
        attachments = result.scalars().all()
        if attachments:
            lines.append(f"📎 Вложений: {len(attachments)}")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error formatting ticket card for client: ticket {ticket.id}, error={e}", exc_info=True)
        raise



# ========== Client Archive Functions ==========


async def get_client_closed_tickets_by_filter(
    session: AsyncSession,
    tg_user_id: int = None,
    user_id: int = None,
    filter_type: str = "all"
) -> list[Ticket]:
    """
    Get closed tickets for a client by filter type.
    
    Args:
        session: Database session
        tg_user_id: Client's Telegram user ID (optional)
        user_id: Client's internal user ID (optional)
        filter_type: Filter type ('all', 'invoice', 'technical_support', 'renewal')
    
    Returns:
        List of closed tickets matching the filter
    
    Note: Either tg_user_id or user_id must be provided
    """
    from database.models import TicketType
    
    try:
        # Get user
        if user_id:
            stmt = select(User).where(User.id == user_id)
        elif tg_user_id:
            stmt = select(User).where(User.tg_user_id == tg_user_id)
        else:
            logger.error("Neither tg_user_id nor user_id provided")
            return []
        
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return []
        
        # Base query for closed tickets
        query = (
            select(Ticket)
            .where(
                Ticket.user_id == user.id,
                Ticket.ticket_status.in_([TicketStatus.CLOSED, TicketStatus.CANCELLED])
            )
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys)
            )
        )
        
        # Apply filter
        if filter_type == "invoice":
            query = query.where(Ticket.ticket_type == TicketType.INVOICE)
        elif filter_type == "technical_support":
            query = query.where(Ticket.ticket_type == TicketType.TECHNICAL_SUPPORT)
        elif filter_type == "consultation":
            query = query.where(Ticket.ticket_type == TicketType.CONSULTATION)
        elif filter_type == "renewal":
            query = query.where(Ticket.ticket_type == TicketType.RENEWAL)
        # 'all' - no additional filter
        
        # Order by closed_at descending
        query = query.order_by(Ticket.closed_at.desc())
        
        result = await session.execute(query)
        tickets = list(result.scalars().all())
        
        logger.info(
            f"Found {len(tickets)} closed tickets for client (user_id={user.id}) "
            f"with filter: {filter_type}"
        )
        
        return tickets
        
    except Exception as e:
        logger.error(
            f"Error getting closed tickets by filter: tg_user_id={tg_user_id}, "
            f"user_id={user_id}, filter_type={filter_type}, error={e}",
            exc_info=True
        )
        raise


async def format_client_archive_header(
    tickets_count: int,
    current_filter: str = "all"
) -> str:
    """
    Format header text for client archive list.
    
    Args:
        tickets_count: Total number of tickets
        current_filter: Current filter type
    
    Returns:
        Formatted header text
    """
    filter_text_map = {
        "all": "Все типы",
        "invoice": "💰 Счёт",
        "technical_support": "🆘 ТП",
        "consultation": "💬 Консультация",
        "renewal": "🔄 Активация подписки",
    }
    
    filter_text = filter_text_map.get(current_filter, "Все типы")
    
    header_lines = [
        f"📋 <b>Архив обращений</b>",
        "",
        f"Здесь вы можете просмотреть историю всех закрытых обращений.",
        f"Используйте фильтры для поиска нужного типа заявки.",
        "",
        f"<b>Текущий фильтр:</b> {filter_text}",
        f"<b>Найдено обращений:</b> {tickets_count}",
        ""
    ]
    
    return "\n".join(header_lines)


async def get_client_archive_keyboard(
    tickets: list[Ticket],
    current_filter: str = "all",
    current_page: int = 0
) -> InlineKeyboardMarkup:
    """
    Generate inline keyboard for client archive list with filters and pagination.
    
    Args:
        tickets: List of closed tickets (already filtered)
        current_filter: Current filter type ('all', 'invoice', 'technical_support', 'renewal')
        current_page: Current page number (0-indexed)
    
    Returns:
        InlineKeyboardMarkup with filters, ticket list, and pagination
    """
    try:
        from bots.tg_bot.callback_datas import ClientArchiveCallback
        from database.models import TicketType
        
        buttons = []
        
        # Filter buttons row (3 buttons without "All")
        filter_buttons = []
        
        # Invoice filter
        invoice_text = "🟢 💰 Счёт" if current_filter == "invoice" else "💰 Счёт"
        filter_buttons.append(
            InlineKeyboardButton(
                text=invoice_text,
                callback_data=ClientArchiveCallback(
                    action="filter",
                    filter_type="invoice",
                    page=0
                ).pack()
            )
        )
        
        # Technical Support filter
        ts_text = "🟢 🔧 ТП" if current_filter == "technical_support" else "🔧 ТП"
        filter_buttons.append(
            InlineKeyboardButton(
                text=ts_text,
                callback_data=ClientArchiveCallback(
                    action="filter",
                    filter_type="technical_support",
                    page=0
                ).pack()
            )
        )
        
        # Renewal filter
        renewal_text = "🟢 🔄 Активация подписки" if current_filter == "renewal" else "🔄 Активация подписки"
        filter_buttons.append(
            InlineKeyboardButton(
                text=renewal_text,
                callback_data=ClientArchiveCallback(
                    action="filter",
                    filter_type="renewal",
                    page=0
                ).pack()
            )
        )
        
        buttons.append(filter_buttons)
        
        # Pagination: 5 tickets per page
        TICKETS_PER_PAGE = 5
        start_idx = current_page * TICKETS_PER_PAGE
        end_idx = start_idx + TICKETS_PER_PAGE
        page_tickets = tickets[start_idx:end_idx]
        
        # Ticket type emoji mapping
        ticket_type_emoji = {
            TicketType.INVOICE: "💰",
            TicketType.TECHNICAL_SUPPORT: "🔧",
            TicketType.RENEWAL: "🔄"
        }
        
        # Ticket buttons (5 rows)
        for ticket in page_tickets:
            # Get ticket type emoji
            type_emoji = ticket_type_emoji.get(ticket.ticket_type, "📋")
            
            # Format date
            date_str = ticket.closed_at.strftime("%d.%m") if ticket.closed_at else "Не указано"
            
            # Build ticket button text
            ticket_text = f"{type_emoji} #{ticket.id} ({date_str})"
            
            # Single button per row
            buttons.append([
                InlineKeyboardButton(
                    text=ticket_text,
                    callback_data=ClientArchiveCallback(
                        action="view_ticket",
                        ticket_id=ticket.id,
                        filter_type=current_filter,
                        page=current_page
                    ).pack()
                )
            ])
        
        # Pagination buttons
        total_pages = (len(tickets) + TICKETS_PER_PAGE - 1) // TICKETS_PER_PAGE if tickets else 1
        if total_pages > 1:
            pagination_row = []
            
            if current_page > 0:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="◀️",
                        callback_data=ClientArchiveCallback(
                            action="page",
                            filter_type=current_filter,
                            page=current_page - 1
                        ).pack()
                    )
                )
            
            if current_page < total_pages - 1:
                pagination_row.append(
                    InlineKeyboardButton(
                        text="▶️",
                        callback_data=ClientArchiveCallback(
                            action="page",
                            filter_type=current_filter,
                            page=current_page + 1
                        ).pack()
                    )
                )
            
            if pagination_row:
                buttons.append(pagination_row)
        
        # Close button
        buttons.append([
            InlineKeyboardButton(
                text="❌ Закрыть",
                callback_data=ClientArchiveCallback(action="close").pack()
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        logger.info(
            f"Generated client archive keyboard: "
            f"tickets_count={len(tickets)}, filter={current_filter}, "
            f"page={current_page}"
        )
        
        return keyboard
        
    except Exception as e:
        logger.error(
            f"Error generating client archive keyboard: error={e}",
            exc_info=True
        )
        raise


async def format_client_archived_ticket_details(
    ticket: Ticket,
    session: AsyncSession
) -> str:
    """
    Format full archived ticket details for client view.
    
    Args:
        ticket: Ticket object to format
        session: Database session
    
    Returns:
        Formatted ticket details as string
    """
    try:
        from database.models import File_Attachment, Staff_Member
        
        lines = [
            f"📋 <b>ОБРАЩЕНИЕ #{ticket.id}</b>",
            ""
        ]
        
        # Ticket type
        ticket_type_map = {
            "invoice": "💰 Счет",
            "technical_support": "🔧 Техническая поддержка",
            "consultation": "💬 Консультация",
            "renewal": "🔄 Активация подписки"
        }
        ticket_type_str = ticket_type_map.get(ticket.ticket_type.value, str(ticket.ticket_type.value))
        lines.append(f"<b>Тип:</b> {ticket_type_str}")
        
        # Status
        status_map = {
            TicketStatus.CLOSED: "✅ Закрыто",
            TicketStatus.CANCELLED: "❌ Отменено"
        }
        status_str = status_map.get(ticket.ticket_status, str(ticket.ticket_status.value))
        lines.append(f"<b>Статус:</b> {status_str}")
        lines.append("")
        
        # Organization info
        if ticket.organization_inn:
            lines.append("<b>🏢 ОРГАНИЗАЦИЯ</b>")
            lines.append(f"ИНН: {ticket.organization_inn}")
            lines.append("")
        
        # GS Keys
        if ticket.gs_keys:
            lines.append("<b>🔑 КЛЮЧИ ГС</b>")
            for key in ticket.gs_keys:
                lines.append(f"• {key.key_number}")
            lines.append("")
        
        # Delivery method (if available)
        if hasattr(ticket, 'delivery_method') and ticket.delivery_method:
            lines.append("<b>📦 СПОСОБ ПОЛУЧЕНИЯ</b>")
            delivery_method_names = {
                "telegram": "💬 В чат",
                "email": "📧 На Email",
                "none": "❌ Не указан"
            }
            delivery_method_text = delivery_method_names.get(
                ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method),
                str(ticket.delivery_method)
            )
            lines.append(delivery_method_text)
            
            # Add delivery email if method is email
            if (ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method)) == "email":
                if hasattr(ticket, 'delivery_email') and ticket.delivery_email:
                    lines.append(f"Email: {ticket.delivery_email}")
            
            lines.append("")
        
        # Description
        if ticket.description:
            lines.append("<b>📝 ОПИСАНИЕ</b>")
            lines.append(ticket.description)
            lines.append("")
        
        # Assigned staff
        if ticket.assigned_staff_id:
            stmt = select(Staff_Member).where(Staff_Member.id == ticket.assigned_staff_id)
            result = await session.execute(stmt)
            staff = result.scalar_one_or_none()
            
            if staff:
                lines.append(f"<b>👨‍💼 Исполнитель:</b> {staff.full_name}")
                lines.append("")
        
        # Dates
        lines.append("<b>📅 ДАТЫ</b>")
        lines.append(f"Создано: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}")
        
        if ticket.closed_at:
            lines.append(f"Закрыто: {ticket.closed_at.strftime('%d.%m.%Y %H:%M')}")
            
            # Calculate duration
            duration = ticket.closed_at - ticket.created_at
            days = duration.days
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            
            duration_parts = []
            if days > 0:
                duration_parts.append(f"{days}д")
            if hours > 0:
                duration_parts.append(f"{hours}ч")
            if minutes > 0:
                duration_parts.append(f"{minutes}м")
            
            duration_str = " ".join(duration_parts) if duration_parts else "< 1м"
            lines.append(f"Длительность: {duration_str}")
        
        lines.append("")
        
        # File attachments
        stmt = select(File_Attachment).where(File_Attachment.ticket_id == ticket.id)
        result = await session.execute(stmt)
        attachments = list(result.scalars().all())
        
        if attachments:
            lines.append(f"<b>📎 ВЛОЖЕНИЯ ({len(attachments)})</b>")
            for att in attachments[:5]:  # Show first 5
                file_type = att.file_type.value if att.file_type else "unknown"
                lines.append(f"• {att.file_name} ({file_type})")
            
            if len(attachments) > 5:
                lines.append(f"... и еще {len(attachments) - 5}")
            
            lines.append("")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(
            f"Error formatting client archived ticket details: ticket_id={ticket.id}, error={e}",
            exc_info=True
        )
        raise



async def get_client_archive_keyboard_max(
    tickets: list[Ticket],
    current_filter: str = "all",
    current_page: int = 0,
    all_tickets: list[Ticket] | None = None,
):
    """
    Generate inline keyboard for client archive list (MAX messenger version).

    Args:
        tickets: List of closed tickets (already filtered by type)
        current_filter: Current filter type
        current_page: Current page number (0-indexed)
        all_tickets: Full unfiltered list — used to determine which filter buttons to show
    """
    try:
        from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton
        from bots.max_bot.payloads import (
            ArchiveFilterPayload,
            ArchivePaginationPayload,
            ViewArchivedTicketPayload,
            ArchiveClosePayload
        )
        from database.models import TicketType

        buttons = []

        # Determine which types are present in all tickets
        source = all_tickets if all_tickets is not None else tickets
        _type_map = {
            TicketType.INVOICE: "invoice",
            TicketType.TECHNICAL_SUPPORT: "technical_support",
            TicketType.CONSULTATION: "consultation",
            TicketType.RENEWAL: "renewal",
        }
        present_types: set[str] = set()
        for t in source:
            fkey = _type_map.get(t.ticket_type)
            if fkey:
                present_types.add(fkey)

        def _filter_btn(label: str, ftype: str) -> KeyboardButton:
            text = f"[{label}]" if ftype == current_filter else label
            return KeyboardButton(text=text, payload=ArchiveFilterPayload(filter_type=ftype).pack())

        # Row 1: Все (always) + Счёт + ТП
        row1 = [_filter_btn("Все", "all")]
        if "invoice" in present_types:
            row1.append(_filter_btn("💰 Счёт", "invoice"))
        if "technical_support" in present_types:
            row1.append(_filter_btn("🆘 ТП", "technical_support"))
        buttons.append(row1)

        # Row 2: Консультация + Активация подписки (only if present)
        row2 = []
        if "consultation" in present_types:
            row2.append(_filter_btn("💬 Консультация", "consultation"))
        if "renewal" in present_types:
            row2.append(_filter_btn("🔄 Активация подписки", "renewal"))
        if row2:
            buttons.append(row2)

        # Pagination
        TICKETS_PER_PAGE = 5
        total_pages = max(1, (len(tickets) + TICKETS_PER_PAGE - 1) // TICKETS_PER_PAGE)
        current_page = max(0, min(current_page, total_pages - 1))
        start_idx = current_page * TICKETS_PER_PAGE
        end_idx = start_idx + TICKETS_PER_PAGE

        # Ticket type emoji and name mapping
        ticket_type_info = {
            TicketType.INVOICE: ("💰", "Счёт"),
            TicketType.TECHNICAL_SUPPORT: ("🆘", "ТП"),
            TicketType.CONSULTATION: ("💬", "Консультация"),
            TicketType.RENEWAL: ("🔄", "Активация подписки"),
        }

        for ticket in tickets[start_idx:end_idx]:
            type_emoji, type_name = ticket_type_info.get(ticket.ticket_type, ("📋", "Обращение"))
            date_str = ticket.closed_at.strftime("%d.%m") if ticket.closed_at else "—"
            ticket_text = f"{type_emoji} {type_name} #{ticket.id} ({date_str})"
            buttons.append([KeyboardButton(
                text=ticket_text,
                payload=ViewArchivedTicketPayload(ticket_id=ticket.id).pack()
            )])

        # Pagination buttons
        if total_pages > 1:
            pagination_row = []

            if current_page > 1:
                pagination_row.append(KeyboardButton(
                    text="⏮️",
                    payload=ArchivePaginationPayload(page=0, filter_type=current_filter).pack()
                ))
            if current_page > 0:
                pagination_row.append(KeyboardButton(
                    text="◀️",
                    payload=ArchivePaginationPayload(page=current_page - 1, filter_type=current_filter).pack()
                ))

            pagination_row.append(KeyboardButton(
                text=f"{current_page + 1}/{total_pages}",
                payload=ArchivePaginationPayload(page=current_page, filter_type=current_filter).pack()
            ))

            if current_page < total_pages - 1:
                pagination_row.append(KeyboardButton(
                    text="▶️",
                    payload=ArchivePaginationPayload(page=current_page + 1, filter_type=current_filter).pack()
                ))
            if current_page < total_pages - 2:
                pagination_row.append(KeyboardButton(
                    text="⏭️",
                    payload=ArchivePaginationPayload(page=total_pages - 1, filter_type=current_filter).pack()
                ))

            buttons.append(pagination_row)

        # Back to main menu
        buttons.append([KeyboardButton(
            text="🏠 В меню",
            payload=ArchiveClosePayload().pack()
        )])

        return Keyboard(buttons=buttons, inline=True)

    except Exception as e:
        logger.error(f"Error generating client archive keyboard (MAX): filter={current_filter}, page={current_page}, error={e}", exc_info=True)
        raise
