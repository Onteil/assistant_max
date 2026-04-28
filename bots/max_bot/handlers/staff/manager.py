"""
Manager Interface Handler for MAX Bot

Handles /manager command and manager menu navigation.
Provides access to active tickets, archive, and admin panel.

Requirements: Manager Interface
"""

import logging

from maxapi.types import MessageCallback, MessageCreated
from maxapi.context import MemoryContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.keyboards.staff.manager_kb import get_manager_menu_keyboard
from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    ManagerMenuActionPayload,
    ManagerTicketSelectPayload,
    ManagerTicketsFilterPayload,
    ManagerTicketsPaginationPayload,
    ManagerTicketsBackPayload,
    ManagerArchiveFilterPayload,
    ManagerArchivePaginationPayload,
    ManagerArchiveTicketPayload,
    ManagerArchiveBackPayload,
    ManagerTicketActionPayload,
    ManagerViewTicketPayload,
    ManagerToggleFocusPayload,
    ManagerEmployeeSelectPayload,
    ManagerTicketHistoryPayload,
    ManagerTicketHistoryBackPayload,
)
from database.models import Staff_Member, StaffRole, Ticket, TicketStatus, TicketType
from services.employee_service import (
    get_employee_active_tickets,
    format_ticket_card,
)

logger = logging.getLogger(__name__)


# ========== Helper Functions ==========


def format_ticket_card_detailed(ticket: Ticket) -> str:
    """
    Format detailed ticket card with all client information.
    
    Args:
        ticket: Ticket object with loaded relationships
    
    Returns:
        Formatted ticket card text
    """
    lines = [f"✅ <b>Работа с заявкой #{ticket.id}</b>", ""]
    
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
        TicketStatus.WAITING_CLIENT: "Ожидание клиента",
        TicketStatus.CLOSED: "Закрыто",
        TicketStatus.CANCELLED: "Отменено"
    }
    emoji = status_emoji.get(ticket.ticket_status, "")
    status = status_text.get(ticket.ticket_status, str(ticket.ticket_status.value))
    lines.append(f"{emoji} <b>Статус:</b> {status}")
    lines.append("")
    
    # Assigned staff
    if ticket.assigned_staff:
        staff_name = ticket.assigned_staff.full_name or "Неизвестно"
        staff_position = ticket.assigned_staff.position or ""
        staff_info = staff_name
        if staff_position:
            staff_info += f", {staff_position}"
        lines.append(f"<b>👨‍💼 Сотрудник:</b> {staff_info}")
    else:
        lines.append("<b>👨‍💼 Сотрудник:</b> Не назначен")
    lines.append("")
    
    # Client information (detailed)
    lines.append("<b>👤 Информация о клиенте:</b>")
    
    # Full name
    if ticket.user.full_name:
        lines.append(f"ФИО: {ticket.user.full_name}")
    elif ticket.user.first_name:
        name_parts = [ticket.user.first_name]
        if ticket.user.last_name:
            name_parts.insert(0, ticket.user.last_name)
        lines.append(f"Имя: {' '.join(name_parts)}")
    
    # Phone
    if ticket.user.phone_number:
        lines.append(f"Телефон: {ticket.user.phone_number}")
    
    # Email
    if ticket.user.email:
        lines.append(f"Email: {ticket.user.email}")
    
    lines.append("")
    
    # Ticket type
    type_names = {
        TicketType.INVOICE: "💰 Счет",
        TicketType.TECHNICAL_SUPPORT: "🆘 Техподдержка",
        TicketType.CONSULTATION: "💬 Консультация",
        TicketType.RENEWAL: "🔄 Продление"
    }
    type_name = type_names.get(ticket.ticket_type, "📋 Заявка")
    lines.append(f"<b>Тип:</b> {type_name}")
    
    # INN (if available)
    if ticket.organization_inn:
        if ticket.organization and ticket.organization.organization_name:
            lines.append(f"<b>Организация:</b> {ticket.organization.organization_name} ({ticket.organization_inn})")
        else:
            lines.append(f"<b>ИНН:</b> {ticket.organization_inn}")
    
    # GS Keys (if available)
    if ticket.gs_keys:
        key_numbers = [key.key_number for key in ticket.gs_keys]
        lines.append(f"<b>🔑 Ключи ГС:</b> {', '.join(key_numbers)}")
    
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
        lines.append(f"<b>📦 Способ получения:</b> {delivery_method_text}")
        
        # Add delivery email if method is email
        if (ticket.delivery_method.value if hasattr(ticket.delivery_method, 'value') else str(ticket.delivery_method)) == "email":
            if hasattr(ticket, 'delivery_email') and ticket.delivery_email:
                lines.append(f"<b>📧 Email для доставки:</b> {ticket.delivery_email}")
    
    lines.append("")
    
    # Description (if available)
    if ticket.description:
        lines.append(f"<b>📝 Описание:</b>")
        lines.append(ticket.description)
        lines.append("")
    
    # Created date
    if ticket.created_at:
        created_str = ticket.created_at.strftime("%d.%m.%Y %H:%M")
        lines.append(f"<b>📅 Создано:</b> {created_str}")
    
    return "\n".join(lines)


def get_ticket_action_keyboard(ticket: Ticket, is_focus_enabled: bool = False) -> Keyboard:
    """
    Generate action keyboard for ticket based on status and focus mode.
    
    Buttons depend on ticket status:
    - NEW: [Взять в работу] [🔄 Передать] [📁 История] [🔙 Назад]
    - IN_PROGRESS: [💬 Общение с клиентом ✅/❌] [✅ Закрыть] [🔄 Передать] [📁 История] [🔙 Назад]
    - WAITING_CLIENT: [💬 Общение с клиентом ✅/❌] [✅ Закрыть] [🔄 Передать] [📁 История] [🔙 Назад]
    
    Args:
        ticket: Ticket object
        is_focus_enabled: Whether focus mode is currently enabled
    
    Returns:
        Keyboard with action buttons
    """
    buttons = []
    
    if ticket.ticket_status == TicketStatus.NEW:
        # NEW status: Take into work button
        buttons.append([
            KeyboardButton(
                text="Взять в работу",
                payload=ManagerTicketActionPayload(action="take", ticket_id=ticket.id).pack()
            )
        ])
        buttons.append([
            KeyboardButton(
                text="🔄 Передать",
                payload=ManagerTicketActionPayload(action="transfer", ticket_id=ticket.id).pack()
            ),
            KeyboardButton(
                text="📁 История",
                payload=ManagerTicketActionPayload(action="history", ticket_id=ticket.id).pack()
            )
        ])
    
    elif ticket.ticket_status in [TicketStatus.IN_PROGRESS, TicketStatus.WAITING_CLIENT]:
        # IN_PROGRESS/WAITING_CLIENT: Add focus toggle button
        focus_text = "💬 Общение с клиентом ✅" if is_focus_enabled else "💬 Общение с клиентом"
        buttons.append([
            KeyboardButton(
                text=focus_text,
                payload=ManagerToggleFocusPayload(
                    ticket_id=ticket.id,
                    enable=not is_focus_enabled  # Toggle: if enabled, next click disables
                ).pack()
            )
        ])
        
        # Close and transfer buttons
        buttons.append([
            KeyboardButton(
                text="✅ Закрыть",
                payload=ManagerTicketActionPayload(action="close", ticket_id=ticket.id).pack()
            )
        ])
        buttons.append([
            KeyboardButton(
                text="🔄 Передать",
                payload=ManagerTicketActionPayload(action="transfer", ticket_id=ticket.id).pack()
            ),
            KeyboardButton(
                text="📁 История",
                payload=ManagerTicketActionPayload(action="history", ticket_id=ticket.id).pack()
            )
        ])
    
    # Back button (always present)
    buttons.append([
        KeyboardButton(
            text="🔙 Назад к списку",
            payload=ManagerTicketActionPayload(action="back_to_list", ticket_id=ticket.id).pack()
        )
    ])
    
    return Keyboard(buttons=buttons, inline=True)


async def is_staff_member(session: AsyncSession, max_user_id: int) -> Staff_Member | None:
    """
    Check if user is a staff member and return their record.
    
    Args:
        session: Database session
        max_user_id: MAX user ID
    
    Returns:
        Staff_Member object if user is staff, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == max_user_id,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking staff member status for MAX user {max_user_id}: {e}", exc_info=True)
        return None


def get_employee_menu_text(
    role: str, 
    full_name: str, 
    position: str, 
    work_mode: str | None = None,
    active_tickets_count: int = 0,
    new_tickets_count: int = 0
) -> str:
    """
    Generate role-specific menu text.
    
    Args:
        role: Staff role value (lowercase: "manager", "administrator", etc.)
        full_name: Employee full name
        position: Employee position/title
        work_mode: Current work mode (optional)
        active_tickets_count: Total number of active tickets (optional)
        new_tickets_count: Number of new (not taken into work) tickets (optional)
    
    Returns:
        Formatted menu text
    """
    role_display = {
        "manager": "Менеджер",
        "technical_support": "Техподдержка",
        "duty_engineer": "Дежурный инженер",
        "administrator": "Администратор"
    }
    
    work_mode_display = {
        "regular": "🟢 Рабочее время",
        "reduced": "🟡 Сокращенный режим",
        "extended": "🟡 Продленное время",
        "non_working": "🔴 Нерабочее время"
    }
    
    role_text = role_display.get(role, role)
    
    text = (
        f"👨‍💼 <b>Рабочее место сотрудника</b>\n\n"
        f"<b>Сотрудник:</b> {full_name}\n"
        f"<b>Должность:</b> {position}\n"
        f"<b>Роль:</b> {role_text}\n"
    )
    
    if work_mode:
        work_mode_text = work_mode_display.get(work_mode, work_mode)
        text += f"<b>Режим работы:</b> {work_mode_text}\n"
    
    text += f"\n<b>Доступные функции:</b>\n"
    
    # Show active tickets count with new tickets count
    if active_tickets_count > 0 or new_tickets_count > 0:
        if new_tickets_count > 0:
            text += f"📥 <b>Активные заявки ({active_tickets_count})</b> — просмотр и обработка текущих обращений\n"
        else:
            text += f"📥 <b>Активные заявки ({active_tickets_count})</b> — просмотр и обработка текущих обращений\n"
    else:
        text += f"📥 <b>Активные заявки</b> — просмотр и обработка текущих обращений\n"
    
    text += (
        f"🗃️ <b>Архив обращений</b> — поиск по завершенным заявкам\n"
        f"⚙️ <b>Настройки</b> — управление профилем и подписью\n"
    )
    
    if role == "manager":
        text += f"👥 <b>Передача клиентов</b> — передать своих клиентов другому менеджеру\n"
    
    if role == "administrator":
        text += f"🔐 <b>Админ-панель</b> — управление сотрудниками и системой\n"
    
    text += f"\nВыберите действие 👇"
    
    return text


def format_active_tickets_header(
    tickets_count: int,
    current_filter: str = "all",
    staff_role: StaffRole | None = None
) -> str:
    """
    Format header text for active tickets list.
    
    Args:
        tickets_count: Number of tickets
        current_filter: Current filter type
        staff_role: Staff role (TECHNICAL_SUPPORT and DUTY_ENGINEER skip filter line)
    
    Returns:
        Formatted header text
    """
    tech_only_roles = {StaffRole.TECHNICAL_SUPPORT, StaffRole.DUTY_ENGINEER}
    show_filter = staff_role not in tech_only_roles

    filter_names = {
        "all": "Все заявки",
        "invoice": "Счёт",
        "technical_support": "ТП",
        "consultation": "Консультация",
        "renewal": "Продление",
    }
    filter_text = filter_names.get(current_filter, "Все заявки")

    if tickets_count == 0:
        base = f"📥 <b>Активные заявки</b>\n\n"
        if show_filter:
            base += f"<b>Фильтр:</b> {filter_text}\n\n"
        return base + "<i>Нет активных заявок</i>"

    base = f"📥 <b>Активные заявки</b>\n\n"
    if show_filter:
        base += f"<b>Фильтр:</b> {filter_text}\n"
    return base + f"<b>Всего:</b> {tickets_count}\n\nВыберите заявку:"


def get_active_tickets_keyboard(
    tickets: list[Ticket],
    current_filter: str = "all",
    current_page: int = 0,
    items_per_page: int = 5,
    staff_role: StaffRole | None = None,
    all_tickets: list[Ticket] | None = None
) -> Keyboard:
    """
    Build keyboard for active tickets list with filters and pagination.

    Args:
        tickets: Filtered list of Ticket objects (for current page display)
        current_filter: Current filter type
        current_page: Current page number (0-indexed)
        items_per_page: Number of tickets per page
        staff_role: Staff role (TECHNICAL_SUPPORT and DUTY_ENGINEER skip filter buttons)
        all_tickets: Full unfiltered list — used to determine which filter buttons to show.
                     If None, falls back to tickets.

    Returns:
        Keyboard with ticket buttons, filters (if applicable), pagination, and navigation
    """
    buttons = []
    tech_only_roles = {StaffRole.TECHNICAL_SUPPORT, StaffRole.DUTY_ENGINEER}

    # Filter buttons row — hidden for tech-only roles
    if staff_role not in tech_only_roles:
        # Determine which ticket types are present across ALL tickets
        source = all_tickets if all_tickets is not None else tickets
        present_types: set[str] = set()
        _type_map = {
            TicketType.INVOICE: "invoice",
            TicketType.TECHNICAL_SUPPORT: "technical_support",
            TicketType.CONSULTATION: "consultation",
            TicketType.RENEWAL: "renewal",
        }
        for t in source:
            fkey = _type_map.get(t.ticket_type)
            if fkey:
                present_types.add(fkey)

        def _make_filter_btn(text: str, filter_type: str) -> KeyboardButton:
            label = f"[{text}]" if filter_type == current_filter else text
            return KeyboardButton(
                text=label,
                payload=ManagerTicketsFilterPayload(filter_type=filter_type).pack()
            )

        # Row 1: Все (always), Счёт (if present), ТП (if present)
        row1 = [_make_filter_btn("Все", "all")]
        if "invoice" in present_types:
            row1.append(_make_filter_btn("💰 Счёт", "invoice"))
        if "technical_support" in present_types:
            row1.append(_make_filter_btn("🆘 ТП", "technical_support"))
        buttons.append(row1)

        # Row 2: Консультация (if present), Продление (if present)
        row2 = []
        if "consultation" in present_types:
            row2.append(_make_filter_btn("💬 Консультация", "consultation"))
        if "renewal" in present_types:
            row2.append(_make_filter_btn("🔄 Продление", "renewal"))
        if row2:
            buttons.append(row2)
    
    # Ticket buttons (paginated)
    total_count = len(tickets)
    total_pages = (total_count + items_per_page - 1) // items_per_page if total_count > 0 else 1
    current_page = max(0, min(current_page, total_pages - 1))
    
    start_idx = current_page * items_per_page
    end_idx = start_idx + items_per_page
    page_tickets = tickets[start_idx:end_idx]
    
    for ticket in page_tickets:
        # Format ticket button text
        type_emoji = {
            TicketType.INVOICE: "💰",
            TicketType.TECHNICAL_SUPPORT: "🆘",
            TicketType.CONSULTATION: "💬",
            TicketType.RENEWAL: "🔄"
        }.get(ticket.ticket_type, "📋")
        
        type_name = {
            TicketType.INVOICE: "Счет",
            TicketType.TECHNICAL_SUPPORT: "ТП",
            TicketType.CONSULTATION: "Консультация",
            TicketType.RENEWAL: "Продление"
        }.get(ticket.ticket_type, "Заявка")
        
        status_emoji = {
            TicketStatus.NEW: "🆕",
            TicketStatus.IN_PROGRESS: "⏳",
            TicketStatus.WAITING_CLIENT: "⏸"
        }.get(ticket.ticket_status, "")
        
        # Format created date and time
        created_datetime = ""
        if ticket.created_at:
            created_datetime = ticket.created_at.strftime("%d.%m %H:%M")
        
        button_text = f"{status_emoji} {type_emoji} {type_name} #{ticket.id} ({created_datetime})"
        
        buttons.append([
            KeyboardButton(
                text=button_text,
                payload=ManagerTicketSelectPayload(ticket_id=ticket.id).pack()
            )
        ])
    
    # Pagination row (if needed)
    if total_count > items_per_page:
        pagination_row = []

        # First page
        if current_page > 1:
            pagination_row.append(
                KeyboardButton(
                    text="⏮️",
                    payload=ManagerTicketsPaginationPayload(page=0).pack()
                )
            )

        if current_page > 0:
            pagination_row.append(
                KeyboardButton(
                    text="⬅️",
                    payload=ManagerTicketsPaginationPayload(page=current_page - 1).pack()
                )
            )

        pagination_row.append(
            KeyboardButton(
                text=f"{current_page + 1}/{total_pages}",
                payload=ManagerTicketsBackPayload(action="noop").pack()
            )
        )

        if current_page < total_pages - 1:
            pagination_row.append(
                KeyboardButton(
                    text="➡️",
                    payload=ManagerTicketsPaginationPayload(page=current_page + 1).pack()
                )
            )

        # Last page
        if current_page < total_pages - 2:
            pagination_row.append(
                KeyboardButton(
                    text="⏭️",
                    payload=ManagerTicketsPaginationPayload(page=total_pages - 1).pack()
                )
            )

        buttons.append(pagination_row)
    
    # Navigation row
    buttons.append([
        KeyboardButton(
            text="🏠 В меню",
            payload=ManagerTicketsBackPayload(action="menu").pack()
        )
    ])
    
    return Keyboard(buttons=buttons, inline=True)


# ========== Command Handler ==========


async def cmd_manager(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle /manager command - display manager main menu.
    
    Shows inline menu with:
    - Active tickets button (with new tickets count)
    - Archive search button
    - Admin panel button (if administrator role)
    
    maxapi Pattern Notes:
    - Uses event.message.sender.user_id for user identification
    - Includes commands_info marker for automatic command registration
    
    Args:
        event: MessageCreated event from maxapi
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    commands_info: Открыть меню менеджера
    
    Requirements: Manager Interface
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    logger.info(f"cmd_manager called: max_user_id={max_user_id}, chat_id={chat_id}")
    
    try:
        # Check if user is staff member
        employee = await is_staff_member(session, max_user_id)
        
        if not employee:
            logger.warning(f"Non-staff user attempted to access manager menu: max_user_id={max_user_id}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Get current work mode
        from services.calendar_service import get_current_work_mode
        work_mode = await get_current_work_mode(session)
        
        # Get active and new tickets counts
        from services.employee_service import get_employee_active_tickets, get_employee_new_tickets_count
        
        # Get all active tickets (no filter)
        active_tickets = await get_employee_active_tickets(session, employee.max_user_id, ticket_type_filter=None)
        active_tickets_count = len(active_tickets)
        
        # Get new tickets count (status = NEW)
        new_tickets_count = await get_employee_new_tickets_count(session, employee.max_user_id, ticket_type_filter=None)
        
        # Generate menu keyboard based on employee role with new tickets count
        is_admin = employee.staff_role == StaffRole.ADMINISTRATOR
        is_manager = employee.staff_role == StaffRole.MANAGER
        show_employee_menu = not is_admin and not is_manager
        keyboard = get_manager_menu_keyboard(
            is_admin=is_admin,
            is_manager=is_manager,
            active_tickets_count=active_tickets_count,
            show_employee_menu=show_employee_menu,
        )
        
        # Generate role-specific menu text with tickets counts
        menu_text = get_employee_menu_text(
            role=employee.staff_role.value,
            full_name=employee.full_name,
            position=employee.position,
            work_mode=work_mode.value if work_mode else None,
            active_tickets_count=active_tickets_count,
            new_tickets_count=new_tickets_count
        )
        
        logger.info(f"Sending manager menu to MAX user {max_user_id} (active={active_tickets_count}, new={new_tickets_count})")
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=menu_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Employee {max_user_id} ({employee.full_name}) accessed manager menu")
        
    except Exception as e:
        logger.error(
            f"Error showing manager menu: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке меню.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )


# ========== Menu Action Handlers ==========


async def handle_manager_menu_action(
    event: MessageCallback,
    payload: ManagerMenuActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle manager menu action callbacks.
    
    Routes to different handlers based on action:
    - active_tickets: Show active tickets list
    - archive: Show archive search
    - admin_panel: Show admin panel
    
    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification in callbacks
    - Uses ManagerMenuActionPayload for type-safe callback parsing
    - Answers callback to acknowledge button press
    - Uses replace_message pattern (delete old + send new)
    
    Args:
        event: MessageCallback event from maxapi
        payload: Parsed manager menu action payload
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    
    Requirements: Manager Interface
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    action = payload.action
    
    logger.info(f"Manager menu action: max_user_id={max_user_id}, action={action}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        if action == "active_tickets":
            # Show active tickets list
            await show_active_tickets(chat_id, max_user_id, session, messenger_adapter, context)
        
        elif action == "archive":
            # Show archive view
            await show_archive(chat_id, max_user_id, session, messenger_adapter, context)
            logger.info(f"Employee {max_user_id} accessed archive")
        
        elif action == "transfer_clients":
            # Transfer clients - only for managers
            if employee.staff_role != StaffRole.MANAGER:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Передача клиентов доступна только для менеджеров.",
                    parse_mode="HTML"
                )
                return
            
            from bots.max_bot.handlers.staff.employees import handle_transfer_clients_start
            from bots.max_bot.payloads import TransferClientsPayload
            
            fake_payload = TransferClientsPayload(action="start", source_manager_id=employee.id)
            await handle_transfer_clients_start(
                event=event,
                payload=fake_payload,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter,
                initiated_by_manager=True,
                message_already_deleted=True
            )
        
        elif action == "employee_menu":
            # Show employee self-service menu (for non-admin, non-manager roles)
            if employee.staff_role == StaffRole.ADMINISTRATOR:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Меню сотрудника недоступно для администраторов.",
                    parse_mode="HTML"
                )
                return
            await show_employee_self_service_menu(
                chat_id=chat_id,
                employee=employee,
                session=session,
                messenger_adapter=messenger_adapter,
            )

        elif action == "back_to_menu":
            # Return to manager main menu (used after transfer_clients)
            is_admin_role = employee.staff_role == StaffRole.ADMINISTRATOR
            is_manager_role = employee.staff_role == StaffRole.MANAGER
            
            from services.employee_service import get_employee_active_tickets, get_employee_new_tickets_count
            active_tickets = await get_employee_active_tickets(session, employee.max_user_id, ticket_type_filter=None)
            new_tickets_count = await get_employee_new_tickets_count(session, employee.max_user_id, ticket_type_filter=None)
            
            keyboard = get_manager_menu_keyboard(
                is_admin=is_admin_role,
                is_manager=is_manager_role,
                active_tickets_count=len(active_tickets),
                show_employee_menu=not is_admin_role and not is_manager_role,
            )
            menu_text = get_employee_menu_text(
                role=employee.staff_role.value,
                full_name=employee.full_name,
                position=employee.position,
                active_tickets_count=len(active_tickets),
                new_tickets_count=new_tickets_count
            )
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=menu_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        
        elif action == "admin_panel":
            # Delegate to admin panel handler
            from bots.max_bot.handlers.staff.admin_panel import handle_admin_panel_action
            
            # Re-create event without deleting message (admin handler will do it)
            # We already deleted the message above, so we need to handle this differently
            # Actually, we should NOT delete the message here, let admin handler do it
            # But we already deleted it... Let's call admin handler directly
            
            # Check if user is admin
            if employee.staff_role != StaffRole.ADMINISTRATOR:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ У вас нет доступа к админ-панели.",
                    parse_mode="HTML"
                )
                return
            
            # Cache scalar attributes before further DB calls to avoid lazy-load issues
            employee_full_name = employee.full_name
            
            # Call admin panel handler (message already deleted above)
            from bots.max_bot.handlers.staff.admin_panel import get_admin_panel_keyboard, get_admin_panel_menu_text
            
            # Clear any existing FSM state
            await context.clear()
            
            # Get admin panel main menu keyboard and text
            keyboard = await get_admin_panel_keyboard(session)
            menu_text = await get_admin_panel_menu_text(session)
            
            # Send admin panel main menu
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=menu_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Administrator {max_user_id} ({employee_full_name}) accessed admin panel")
        
        else:
            logger.warning(f"Unknown manager menu action: {action}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестное действие.",
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(
            f"Error handling manager menu action: action={action}, max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )


# ========== Active Tickets Handlers ==========


async def show_active_tickets(
    chat_id: int,
    max_user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    context: MemoryContext,
    current_filter: str = "all",
    current_page: int = 0
) -> None:
    """
    Show active tickets list with filters and pagination.
    
    For TECHNICAL_SUPPORT and DUTY_ENGINEER roles, filters are hidden and
    only technical_support tickets are shown regardless of current_filter.
    
    Args:
        chat_id: Chat ID for sending messages
        max_user_id: MAX user ID of the employee
        session: Database session
        messenger_adapter: Messenger adapter for sending messages
        context: FSM context
        current_filter: Current filter type
        current_page: Current page number
    """
    logger.info(f"Showing active tickets: max_user_id={max_user_id}, filter={current_filter}, page={current_page}")
    
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == max_user_id,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee or not employee.max_user_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Не удалось загрузить заявки. ID сотрудника не найден.",
                parse_mode="HTML"
            )
            return
        
        staff_role = employee.staff_role
        tech_only_roles = {StaffRole.TECHNICAL_SUPPORT, StaffRole.DUTY_ENGINEER}

        # Force technical_support filter for tech-only roles
        if staff_role in tech_only_roles:
            current_filter = "technical_support"

        # Get all tickets (for filter visibility) and filtered tickets (for display)
        all_tickets = await get_employee_active_tickets(session, employee.max_user_id, None)
        ticket_type_filter = None if current_filter == "all" else current_filter
        tickets = all_tickets if ticket_type_filter is None else await get_employee_active_tickets(session, employee.max_user_id, ticket_type_filter)

        # Save filter to context
        await context.update_data(
            manager_active_filter=current_filter,
            manager_active_page=current_page
        )

        # Format header text
        header_text = format_active_tickets_header(
            tickets_count=len(tickets),
            current_filter=current_filter,
            staff_role=staff_role
        )

        # Generate keyboard
        keyboard = get_active_tickets_keyboard(
            tickets=tickets,
            current_filter=current_filter,
            current_page=current_page,
            staff_role=staff_role,
            all_tickets=all_tickets,
        )
        
        # Send message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=header_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Employee {max_user_id} viewed {len(tickets)} active tickets "
            f"(filter={current_filter}, page={current_page})"
        )
    
    except Exception as e:
        logger.error(
            f"Error showing active tickets: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке активных заявок.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )



async def handle_tickets_filter(
    event: MessageCallback,
    payload: ManagerTicketsFilterPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle ticket filter selection.
    
    Updates the ticket list to show only tickets of the selected type.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: Filter payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    new_filter = payload.filter_type
    
    logger.info(f"Tickets filter: max_user_id={max_user_id}, filter={new_filter}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Show tickets with new filter
        await show_active_tickets(chat_id, max_user_id, session, messenger_adapter, context, new_filter, 0)
    
    except Exception as e:
        logger.error(f"Error handling tickets filter: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при фильтрации заявок.",
            parse_mode="HTML"
        )


async def handle_tickets_pagination(
    event: MessageCallback,
    payload: ManagerTicketsPaginationPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle ticket list pagination.
    
    Updates the ticket list to show the requested page.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: Pagination payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    page = payload.page
    
    logger.info(f"Tickets pagination: max_user_id={max_user_id}, page={page}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Get current filter from context
        data = await context.get_data()
        current_filter = data.get("manager_active_filter", "all")
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Show tickets with new page
        await show_active_tickets(chat_id, max_user_id, session, messenger_adapter, context, current_filter, page)
    
    except Exception as e:
        logger.error(f"Error handling tickets pagination: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при навигации.",
            parse_mode="HTML"
        )


async def handle_ticket_select(
    event: MessageCallback,
    payload: ManagerTicketSelectPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle ticket selection - show detailed ticket card with action buttons.
    
    Uses replace_message pattern.
    Shows detailed client information and action buttons based on ticket status.
    
    Args:
        event: MessageCallback event
        payload: Ticket select payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    ticket_id = payload.ticket_id
    
    logger.info(f"Ticket select: max_user_id={max_user_id}, ticket_id={ticket_id}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Get ticket from database with all relationships
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys),
            selectinload(Ticket.assigned_staff)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Check if focus mode is enabled
        current_state = await context.get_state()
        from bots.max_bot.states import EmployeeStates
        is_focus_enabled = (current_state == EmployeeStates.in_focus)
        
        # Format detailed ticket card
        ticket_card = format_ticket_card_detailed(ticket)
        
        # Build action keyboard based on ticket status and focus state
        keyboard = get_ticket_action_keyboard(ticket, is_focus_enabled)
        
        # Send ticket details with action buttons
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ticket_card,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Employee {max_user_id} viewed ticket {ticket_id} with action buttons")
    
    except Exception as e:
        logger.error(f"Error handling ticket select: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке заявки.",
            parse_mode="HTML"
        )


async def handle_view_ticket_from_notification(
    event: MessageCallback,
    payload: ManagerViewTicketPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "К заявке" button click from ticket notification.
    
    Shows detailed ticket card with action buttons WITHOUT automatically taking it into work.
    This allows staff to view ticket details before deciding to take it.
    
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: ManagerViewTicketPayload with ticket_id
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    ticket_id = payload.ticket_id
    
    logger.info(f"View ticket from notification: max_user_id={max_user_id}, ticket_id={ticket_id}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Get ticket from database with all relationships
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys),
            selectinload(Ticket.assigned_staff)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Delete old notification message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old notification message: {e}")
        
        # Check if focus mode is enabled
        current_state = await context.get_state()
        from bots.max_bot.states import EmployeeStates
        is_focus_enabled = (current_state == EmployeeStates.in_focus)
        
        # Format detailed ticket card
        ticket_card = format_ticket_card_detailed(ticket)
        
        # Build action keyboard based on ticket status and focus state
        keyboard = get_ticket_action_keyboard(ticket, is_focus_enabled)
        
        # Send ticket details with action buttons
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ticket_card,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Employee {max_user_id} viewed ticket {ticket_id} from notification")
    
    except Exception as e:
        logger.error(f"Error handling view ticket from notification: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке заявки.",
            parse_mode="HTML"
        )


async def handle_tickets_back(
    event: MessageCallback,
    payload: ManagerTicketsBackPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle back navigation from tickets.
    
    Routes based on action:
    - menu: Return to manager menu
    - list: Return to tickets list
    - noop: Do nothing (for pagination page number button)
    
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: Back navigation payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    action = payload.action
    
    logger.info(f"Tickets back: max_user_id={max_user_id}, action={action}")
    
    try:
        # Check for noop first
        if action == "noop":
            await event.answer()
            return
        
        # Answer callback
        await event.answer()
        
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        if action == "menu":
            # Return to manager menu
            is_admin = employee.staff_role == StaffRole.ADMINISTRATOR
            
            # Get active and new tickets counts
            from services.employee_service import get_employee_active_tickets, get_employee_new_tickets_count
            active_tickets = await get_employee_active_tickets(session, employee.max_user_id, ticket_type_filter=None)
            active_tickets_count = len(active_tickets)
            new_tickets_count = await get_employee_new_tickets_count(session, employee.max_user_id, ticket_type_filter=None)
            
            keyboard = get_manager_menu_keyboard(is_admin=is_admin, active_tickets_count=active_tickets_count)
            
            # Get current work mode
            from services.calendar_service import get_current_work_mode
            work_mode = await get_current_work_mode(session)
            
            menu_text = get_employee_menu_text(
                role=employee.staff_role.value,
                full_name=employee.full_name,
                position=employee.position,
                work_mode=work_mode.value if work_mode else None,
                active_tickets_count=active_tickets_count,
                new_tickets_count=new_tickets_count
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=menu_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Employee {max_user_id} returned to manager menu")
        
        elif action == "list":
            # Return to tickets list
            data = await context.get_data()
            current_filter = data.get("manager_active_filter", "all")
            current_page = data.get("manager_active_page", 0)
            
            await show_active_tickets(chat_id, max_user_id, session, messenger_adapter, context, current_filter, current_page)
            
            logger.info(f"Employee {max_user_id} returned to tickets list")
        
        else:
            logger.warning(f"Unknown back action: {action}")
    
    except Exception as e:
        logger.error(f"Error handling tickets back: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при навигации.",
            parse_mode="HTML"
        )


# ========== Archive Handlers ==========


def format_archive_header(
    tickets_count: int,
    current_filter: str = "day",
    current_type_filter: str = "all"
) -> str:
    """Format header text for archive list."""
    filter_names = {
        "day": "День",
        "week": "Неделя",
        "month": "Месяц",
        "custom": "Произвольный",
    }
    type_names = {
        "all": "Все типы",
        "invoice": "Счёт",
        "technical_support": "ТП",
        "consultation": "Консультация",
        "renewal": "Продление",
    }

    filter_text = filter_names.get(current_filter, "День")
    type_text = type_names.get(current_type_filter, "Все типы")

    if tickets_count == 0:
        return (
            f"🗃️ <b>Архив обращений</b>\n\n"
            f"<b>Период:</b> {filter_text} | <b>Тип:</b> {type_text}\n\n"
            f"<i>Нет закрытых заявок</i>"
        )

    return (
        f"🗃️ <b>Архив обращений</b>\n\n"
        f"<b>Период:</b> {filter_text} | <b>Тип:</b> {type_text}\n"
        f"<b>Найдено:</b> {tickets_count}\n\n"
        f"Выберите заявку:"
    )


def get_archive_keyboard(
    tickets: list[Ticket],
    current_filter: str = "day",
    current_page: int = 0,
    items_per_page: int = 5,
    all_tickets: list[Ticket] | None = None,
    current_type_filter: str = "all",
) -> Keyboard:
    """
    Build keyboard for archive list with period filters, type filters, and pagination.

    Args:
        tickets: Already-filtered list for display
        current_filter: Current time period filter
        current_page: Current page number (0-indexed)
        items_per_page: Number of tickets per page
        all_tickets: Full unfiltered list — used to determine which type filter buttons to show
        current_type_filter: Current ticket-type filter
    """
    from bots.max_bot.payloads import ManagerArchiveTypeFilterPayload

    buttons = []

    # --- Row 1: Period filters (День / Неделя / Месяц / 🔍) ---
    period_row = []
    for text, filter_type in [("День", "day"), ("Неделя", "week"), ("Месяц", "month"), ("🔍", "custom")]:
        label = f"[{text}]" if filter_type == current_filter and filter_type != "custom" else text
        period_row.append(KeyboardButton(
            text=label,
            payload=ManagerArchiveFilterPayload(filter_type=filter_type).pack()
        ))
    buttons.append(period_row)

    # --- Rows 2-3: Type filters (only types present in all_tickets) ---
    source = all_tickets if all_tickets is not None else tickets
    present_types: set[str] = set()
    _type_map = {
        TicketType.INVOICE: "invoice",
        TicketType.TECHNICAL_SUPPORT: "technical_support",
        TicketType.CONSULTATION: "consultation",
        TicketType.RENEWAL: "renewal",
    }
    for t in source:
        fkey = _type_map.get(t.ticket_type)
        if fkey:
            present_types.add(fkey)

    def _type_btn(label: str, ttype: str) -> KeyboardButton:
        text = f"[{label}]" if ttype == current_type_filter else label
        return KeyboardButton(
            text=text,
            payload=ManagerArchiveTypeFilterPayload(ticket_type=ttype).pack()
        )

    # Row 2: Все (always) + Счёт + ТП
    row2 = [_type_btn("Все", "all")]
    if "invoice" in present_types:
        row2.append(_type_btn("💰 Счёт", "invoice"))
    if "technical_support" in present_types:
        row2.append(_type_btn("🆘 ТП", "technical_support"))
    buttons.append(row2)

    # Row 3: Консультация + Продление (only if present)
    row3 = []
    if "consultation" in present_types:
        row3.append(_type_btn("💬 Консультация", "consultation"))
    if "renewal" in present_types:
        row3.append(_type_btn("🔄 Продление", "renewal"))
    if row3:
        buttons.append(row3)

    # --- Ticket buttons (paginated) ---
    total_count = len(tickets)
    total_pages = (total_count + items_per_page - 1) // items_per_page if total_count > 0 else 1
    current_page = max(0, min(current_page, total_pages - 1))

    start_idx = current_page * items_per_page
    end_idx = start_idx + items_per_page

    for ticket in tickets[start_idx:end_idx]:
        type_emoji = {
            TicketType.INVOICE: "💰",
            TicketType.TECHNICAL_SUPPORT: "🆘",
            TicketType.CONSULTATION: "💬",
            TicketType.RENEWAL: "🔄",
        }.get(ticket.ticket_type, "📋")

        type_name = {
            TicketType.INVOICE: "Счет",
            TicketType.TECHNICAL_SUPPORT: "ТП",
            TicketType.CONSULTATION: "Консультация",
            TicketType.RENEWAL: "Продление",
        }.get(ticket.ticket_type, "Заявка")

        status_emoji = {
            TicketStatus.CLOSED: "✅",
            TicketStatus.CANCELLED: "❌",
        }.get(ticket.ticket_status, "")

        created_datetime = ticket.created_at.strftime("%d.%m %H:%M") if ticket.created_at else ""
        button_text = f"{status_emoji} {type_emoji} {type_name} #{ticket.id} ({created_datetime})"

        buttons.append([KeyboardButton(
            text=button_text,
            payload=ManagerArchiveTicketPayload(ticket_id=ticket.id).pack()
        )])

    # --- Pagination ---
    if total_count > items_per_page:
        pagination_row = []

        if current_page > 1:
            pagination_row.append(KeyboardButton(
                text="⏮️",
                payload=ManagerArchivePaginationPayload(page=0).pack()
            ))
        if current_page > 0:
            pagination_row.append(KeyboardButton(
                text="⬅️",
                payload=ManagerArchivePaginationPayload(page=current_page - 1).pack()
            ))

        pagination_row.append(KeyboardButton(
            text=f"{current_page + 1}/{total_pages}",
            payload=ManagerArchiveBackPayload(action="noop").pack()
        ))

        if current_page < total_pages - 1:
            pagination_row.append(KeyboardButton(
                text="➡️",
                payload=ManagerArchivePaginationPayload(page=current_page + 1).pack()
            ))
        if current_page < total_pages - 2:
            pagination_row.append(KeyboardButton(
                text="⏭️",
                payload=ManagerArchivePaginationPayload(page=total_pages - 1).pack()
            ))

        buttons.append(pagination_row)

    # --- Navigation ---
    buttons.append([KeyboardButton(
        text="🏠 В меню",
        payload=ManagerArchiveBackPayload(action="menu").pack()
    )])

    return Keyboard(buttons=buttons, inline=True)


async def show_archive(
    chat_id: int,
    max_user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    context: MemoryContext,
    current_filter: str = "day",
    current_page: int = 0,
    search_criteria: str | None = None,
    current_type_filter: str = "all",
) -> None:
    """Show archive list with period filters, type filters, and pagination."""
    from services.employee_service import get_closed_tickets_by_filter, search_closed_tickets

    logger.info(f"Showing archive: max_user_id={max_user_id}, filter={current_filter}, type={current_type_filter}, page={current_page}")

    try:
        # Get all tickets for the period (for type filter visibility)
        if current_filter == "custom" and search_criteria:
            all_period_tickets = await search_closed_tickets(session, search_criteria)
        else:
            all_period_tickets = await get_closed_tickets_by_filter(session, current_filter)

        # Apply type filter
        if current_type_filter != "all":
            _tmap = {
                "invoice": TicketType.INVOICE,
                "technical_support": TicketType.TECHNICAL_SUPPORT,
                "consultation": TicketType.CONSULTATION,
                "renewal": TicketType.RENEWAL,
            }
            ttype = _tmap.get(current_type_filter)
            tickets = [t for t in all_period_tickets if t.ticket_type == ttype] if ttype else all_period_tickets
        else:
            tickets = all_period_tickets

        # Save state to context
        await context.update_data(
            manager_archive_filter=current_filter,
            manager_archive_page=current_page,
            manager_archive_search=search_criteria,
            manager_archive_type_filter=current_type_filter,
        )

        # Format header
        header_text = format_archive_header(
            tickets_count=len(tickets),
            current_filter=current_filter,
            current_type_filter=current_type_filter,
        )
        if current_filter == "custom" and search_criteria:
            header_text += f"\n<b>Запрос:</b> <code>{search_criteria}</code>\n"

        # Generate keyboard
        keyboard = get_archive_keyboard(
            tickets=tickets,
            current_filter=current_filter,
            current_page=current_page,
            all_tickets=all_period_tickets,
            current_type_filter=current_type_filter,
        )

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=header_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )

        logger.info(f"Employee {max_user_id} viewed {len(tickets)} archived tickets (filter={current_filter}, type={current_type_filter}, page={current_page})")

    except Exception as e:
        logger.error(f"Error showing archive: max_user_id={max_user_id}, error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке архива.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )


async def handle_archive_filter(
    event: MessageCallback,
    payload: ManagerArchiveFilterPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle archive filter selection.
    
    For "custom" filter, shows search instructions and sets FSM state.
    For other filters, updates the archive list.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: Filter payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    from bots.max_bot.states import EmployeeStates
    
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    new_filter = payload.filter_type
    
    logger.info(f"Archive filter: max_user_id={max_user_id}, filter={new_filter}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        if new_filter == "custom":
            # Show custom search instructions
            from bots.max_bot.payloads import ManagerArchiveBackPayload
            
            # Set FSM state for custom search
            await context.set_state(EmployeeStates.archive_custom_search)
            
            text = (
                "🔍 <b>Произвольный поиск в архиве</b>\n\n"
                "<b>Примеры поисковых запросов:</b>\n\n"
                "• <code>123</code> или <code>#123</code> — поиск по номеру заявки\n"
                "• <code>Иван</code> — поиск по имени клиента\n"
                "• <code>2024-01-01 to 2024-01-31</code> — поиск по диапазону дат\n"
                "• <code>01.01.2024 по 31.01.2024</code> — поиск по диапазону дат (русский формат)\n\n"
                "Введите поисковый запрос:"
            )
            
            # Create keyboard with back button
            buttons = [[
                KeyboardButton(
                    text="⬅️ Назад к архиву",
                    payload=ManagerArchiveBackPayload(action="list").pack()
                )
            ]]
            keyboard = Keyboard(buttons=buttons, inline=True)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Employee {max_user_id} opened custom search in archive")
        else:
            # Show archive with new filter
            await show_archive(chat_id, max_user_id, session, messenger_adapter, context, new_filter, 0)
    
    except Exception as e:
        logger.error(f"Error handling archive filter: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при фильтрации архива.",
            parse_mode="HTML"
        )


async def handle_archive_type_filter(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Handle ticket-type filter selection in archive. Uses replace_message pattern."""
    from bots.max_bot.payloads import ManagerArchiveTypeFilterPayload

    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    # Parse payload manually since it's injected via filter
    raw_payload = event.callback.payload
    try:
        parsed = ManagerArchiveTypeFilterPayload.unpack(raw_payload)
        new_type_filter = parsed.ticket_type
    except Exception:
        new_type_filter = "all"

    logger.info(f"Archive type filter: max_user_id={max_user_id}, type={new_type_filter}")

    try:
        await event.answer()

        data = await context.get_data()
        current_filter = data.get("manager_archive_filter", "day")
        search_criteria = data.get("manager_archive_search")

        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")

        await show_archive(chat_id, max_user_id, session, messenger_adapter, context, current_filter, 0, search_criteria, new_type_filter)

    except Exception as e:
        logger.error(f"Error handling archive type filter: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при фильтрации архива.",
            parse_mode="HTML"
        )


async def handle_archive_pagination(
    event: MessageCallback,
    payload: ManagerArchivePaginationPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle archive list pagination.
    
    Updates the archive list to show the requested page.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: Pagination payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    page = payload.page
    
    logger.info(f"Archive pagination: max_user_id={max_user_id}, page={page}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Get current filter from context
        data = await context.get_data()
        current_filter = data.get("manager_archive_filter", "day")
        search_criteria = data.get("manager_archive_search")
        current_type_filter = data.get("manager_archive_type_filter", "all")

        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")

        # Show archive with new page
        await show_archive(chat_id, max_user_id, session, messenger_adapter, context, current_filter, page, search_criteria, current_type_filter)
    
    except Exception as e:
        logger.error(f"Error handling archive pagination: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при навигации.",
            parse_mode="HTML"
        )


async def handle_archive_ticket_select(
    event: MessageCallback,
    payload: ManagerArchiveTicketPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle archived ticket selection - show ticket details and message history.

    If message history exceeds 4090 characters, it's sent as a .txt file.
    Uses replace_message pattern.

    Args:
        event: MessageCallback event
        payload: Ticket select payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    ticket_id = payload.ticket_id

    logger.info(f"Archive ticket select: max_user_id={max_user_id}, ticket_id={ticket_id}")

    try:
        # Answer callback
        await event.answer()

        # Get ticket from database
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys),
            selectinload(Ticket.assigned_staff)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()

        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return

        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")

        # Format ticket card
        ticket_card = await format_ticket_card(ticket, session)

        # Get message history
        from services.employee_service import format_ticket_message_history
        message_history = await format_ticket_message_history(ticket, session)

        # Build navigation keyboard
        buttons = [
            [
                KeyboardButton(
                    text="⬅️ Назад к архиву",
                    payload=ManagerArchiveBackPayload(action="list").pack()
                )
            ],
            [
                KeyboardButton(
                    text="🏠 В меню",
                    payload=ManagerArchiveBackPayload(action="menu").pack()
                )
            ]
        ]

        keyboard = Keyboard(buttons=buttons, inline=True)

        # Combine ticket details and history
        combined_text = f"{ticket_card}\n\n{message_history}"

        # Check if combined text exceeds MAX limit (4090 chars to be safe)
        if len(combined_text) <= 4090:
            # Send as single message
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=combined_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            # Send ticket details as message
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ticket_card,
                keyboard=keyboard,
                parse_mode="HTML"
            )

            # Send message history as .txt file
            import tempfile
            import os

            try:
                # Create temporary file
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    encoding='utf-8',
                    suffix='.txt',
                    delete=False
                ) as tmp_file:
                    tmp_file.write(message_history)
                    tmp_file_path = tmp_file.name

                # Send file
                await messenger_adapter.send_document(
                    chat_id=chat_id,
                    document_path=tmp_file_path,
                    caption=f"📎 История переписки по заявке #{ticket_id}",
                    parse_mode="HTML"
                )

                # Clean up temporary file
                os.unlink(tmp_file_path)

            except Exception as e:
                logger.error(f"Failed to send history as file: {e}", exc_info=True)
                # Fallback: send truncated history as text
                truncated_history = message_history[:3000] + "\n\n... (история обрезана)"
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=f"📎 История переписки (обрезана):\n\n{truncated_history}",
                    parse_mode="HTML"
                )

        logger.info(
            f"Employee {max_user_id} viewed archived ticket {ticket_id} "
            f"(history_length={len(message_history)}, sent_as_file={len(combined_text) > 4090})"
        )

    except Exception as e:
        logger.error(f"Error handling archive ticket select: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке заявки.",
            parse_mode="HTML"
        )




async def handle_archive_back(
    event: MessageCallback,
    payload: ManagerArchiveBackPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle back navigation from archive.
    
    Routes based on action:
    - menu: Return to manager menu
    - list: Return to archive list
    - noop: Do nothing (for pagination page number button)
    
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: Back navigation payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    from bots.max_bot.states import EmployeeStates
    
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    action = payload.action
    
    logger.info(f"Archive back: max_user_id={max_user_id}, action={action}")
    
    try:
        # Check for noop first
        if action == "noop":
            await event.answer()
            return
        
        # Answer callback
        await event.answer()
        
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        if action == "menu":
            # Clear custom search state if active
            current_state = await context.get_state()
            if current_state == EmployeeStates.archive_custom_search:
                await context.clear()
            
            # Return to manager menu
            is_admin = employee.staff_role == StaffRole.ADMINISTRATOR
            
            # Get active and new tickets counts
            from services.employee_service import get_employee_active_tickets, get_employee_new_tickets_count
            active_tickets = await get_employee_active_tickets(session, employee.max_user_id, ticket_type_filter=None)
            active_tickets_count = len(active_tickets)
            new_tickets_count = await get_employee_new_tickets_count(session, employee.max_user_id, ticket_type_filter=None)
            
            keyboard = get_manager_menu_keyboard(is_admin=is_admin, active_tickets_count=active_tickets_count)
            
            # Get current work mode
            from services.calendar_service import get_current_work_mode
            work_mode = await get_current_work_mode(session)
            
            menu_text = get_employee_menu_text(
                role=employee.staff_role.value,
                full_name=employee.full_name,
                position=employee.position,
                work_mode=work_mode.value if work_mode else None,
                active_tickets_count=active_tickets_count,
                new_tickets_count=new_tickets_count
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=menu_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Employee {max_user_id} returned to manager menu from archive")
        
        elif action == "list":
            # Clear custom search state if active
            current_state = await context.get_state()
            if current_state == EmployeeStates.archive_custom_search:
                await context.clear()
            
            # Return to archive list
            data = await context.get_data()
            current_filter = data.get("manager_archive_filter", "day")
            current_page = data.get("manager_archive_page", 0)
            search_criteria = data.get("manager_archive_search")
            
            await show_archive(chat_id, max_user_id, session, messenger_adapter, context, current_filter, current_page, search_criteria)
            
            logger.info(f"Employee {max_user_id} returned to archive list")
        
        else:
            logger.warning(f"Unknown archive back action: {action}")
    
    except Exception as e:
        logger.error(f"Error handling archive back: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при навигации.",
            parse_mode="HTML"
        )


async def handle_archive_custom_search_input(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle custom search input in archive.
    
    Executes search with provided criteria and shows results.
    
    Args:
        event: MessageCreated event
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    from services.employee_service import search_closed_tickets
    
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    search_criteria = event.message.body.text.strip()
    
    logger.info(f"Archive custom search: max_user_id={max_user_id}, criteria={search_criteria}")
    
    try:
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Clear FSM state
        await context.clear()
        
        # Show archive with custom search results
        await show_archive(chat_id, max_user_id, session, messenger_adapter, context, "custom", 0, search_criteria)
        
        logger.info(f"Employee {max_user_id} executed custom search: {search_criteria}")
    
    except Exception as e:
        logger.error(
            f"Error handling custom search: max_user_id={max_user_id}, criteria={search_criteria}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при выполнении поиска.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )


# ========== Ticket Action Handlers ==========


async def handle_ticket_action(
    event: MessageCallback,
    payload: ManagerTicketActionPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle ticket action callbacks.
    
    Routes to different handlers based on action:
    - take: Take ticket into work
    - close: Close ticket
    - transfer: Transfer ticket to another employee
    - history: View ticket history
    - back_to_list: Return to tickets list
    
    Args:
        event: MessageCallback event
        payload: Ticket action payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    action = payload.action
    ticket_id = payload.ticket_id
    
    logger.info(f"Ticket action: max_user_id={max_user_id}, action={action}, ticket_id={ticket_id}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        if action == "take":
            # Take ticket into work
            from services.ticket_service import take_ticket_into_work as take_ticket_service
            from bots.max_bot.states import EmployeeStates
            
            # Take ticket into work using MAX user ID
            ticket = await take_ticket_service(session, ticket_id, max_user_id, messenger="max")
            
            # Get ticket with relationships loaded BEFORE setting context
            from sqlalchemy.orm import selectinload
            stmt = select(Ticket).where(Ticket.id == ticket_id).options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.assigned_staff)
            )
            result = await session.execute(stmt)
            ticket = result.scalar_one_or_none()
            
            if not ticket:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Заявка не найдена.",
                    parse_mode="HTML"
                )
                return
            
            # Get client ID (prefer MAX, fallback to Telegram)
            focused_client_id = ticket.user.max_user_id if ticket.user.max_user_id else ticket.user.tg_user_id
            
            # Enter focus mode
            await context.set_state(EmployeeStates.in_focus)
            await context.update_data(
                focused_ticket_id=ticket_id,
                focused_client_id=focused_client_id
            )
            
            logger.info(
                f"Employee {max_user_id} entered focus mode: "
                f"ticket_id={ticket_id}, client_id={focused_client_id}, "
                f"state={EmployeeStates.in_focus}"
            )
            
            # Format ticket card
            ticket_card = format_ticket_card_detailed(ticket)
            keyboard = get_ticket_action_keyboard(ticket)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"✅ Заявка взята в работу. Вы в режиме фокуса.\n\n{ticket_card}",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Employee {max_user_id} took ticket {ticket_id} into work")
        
        elif action == "close":
            # Initiate ticket closing flow - prompt for final comment
            from bots.max_bot.states import EmployeeStates
            
            # Set FSM state
            await context.set_state(EmployeeStates.manager_closing_ticket)
            await context.update_data(ticket_id=ticket_id)
            
            # Create cancel button
            buttons = [[
                KeyboardButton(
                    text="❌ Отменить закрытие",
                    payload=ManagerTicketActionPayload(action="cancel_close", ticket_id=ticket_id).pack()
                )
            ]]
            keyboard = Keyboard(buttons=buttons, inline=True)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="✅ <b>Закрытие заявки</b>\n\nПожалуйста, введите финальный комментарий для закрытия заявки.\n\n💡 Вы можете отправить текст, изображение или файл.",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Employee {max_user_id} initiated closing for ticket {ticket_id}")
        
        elif action == "transfer":
            # Initiate ticket transfer flow - show employee selection
            from services.employee_service import get_available_employees_for_transfer
            from bots.max_bot.states import EmployeeStates

            # Get ticket with relationships
            from sqlalchemy.orm import selectinload
            stmt = select(Ticket).where(Ticket.id == ticket_id).options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.assigned_staff)
            )
            result = await session.execute(stmt)
            ticket = result.scalar_one_or_none()

            if not ticket:
                await messenger_adapter.send_message(
                    chat_id=chat_id, text="❌ Заявка не найдена.", parse_mode="HTML"
                )
                return

            # Get current employee record
            stmt = select(Staff_Member).where(
                Staff_Member.max_user_id == max_user_id,
                Staff_Member.is_active == True
            )
            result = await session.execute(stmt)
            emp = result.scalar_one_or_none()

            if not emp:
                await messenger_adapter.send_message(
                    chat_id=chat_id, text="❌ Не удалось получить данные сотрудника.", parse_mode="HTML"
                )
                return

            # Get ALL available employees (no filtering by role or ticket type)
            available_employees = await get_available_employees_for_transfer(
                session, ticket, emp.id, use_internal_id=True
            )

            await context.set_state(EmployeeStates.manager_transferring_ticket)
            await context.update_data(ticket_id=ticket_id)

            role_display = {
                "manager": ("💼", "Менеджер"),
                "technical_support": ("🔧", "ТП"),
                "duty_engineer": ("👷", "Дежурный инженер"),
                "administrator": ("👑", "Администратор"),
            }

            buttons = []
            for emp_item in available_employees:
                if emp_item.is_estimate_tech_specialist:
                    label = f"📋 {emp_item.full_name} (Сметный)"
                else:
                    emoji, role_text = role_display.get(emp_item.staff_role.value, ("👤", emp_item.staff_role.value))
                    label = f"{emoji} {emp_item.full_name} ({role_text})"
                buttons.append([
                    KeyboardButton(
                        text=label,
                        payload=ManagerEmployeeSelectPayload(
                            action="select",
                            employee_id=emp_item.id
                        ).pack()
                    )
                ])

            buttons.append([
                KeyboardButton(
                    text="❌ Отмена",
                    payload=ManagerEmployeeSelectPayload(action="cancel", employee_id=None).pack()
                )
            ])

            keyboard = Keyboard(buttons=buttons, inline=True)

            if available_employees:
                text = "🔄 <b>Передача заявки</b>\n\nВыберите сотрудника для передачи заявки:"
            else:
                text = (
                    "🔄 <b>Передача заявки</b>\n\n"
                    "❌ Нет доступных сотрудников для передачи заявки."
                )

            await messenger_adapter.send_message(
                chat_id=chat_id, text=text, keyboard=keyboard, parse_mode="HTML"
            )

            logger.info(
                f"Employee {max_user_id} initiated transfer for ticket {ticket_id}, "
                f"available_employees={len(available_employees)}"
            )

        
        elif action == "view_card":
            # Show ticket card (used from notification buttons)
            from sqlalchemy.orm import selectinload
            stmt = select(Ticket).where(Ticket.id == ticket_id).options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.assigned_staff)
            )
            result = await session.execute(stmt)
            ticket = result.scalar_one_or_none()

            if not ticket:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Заявка не найдена.",
                    parse_mode="HTML"
                )
                return

            ticket_card = format_ticket_card_detailed(ticket)
            keyboard = get_ticket_action_keyboard(ticket)

            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=ticket_card,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            logger.info(f"Employee {max_user_id} viewing card of ticket {ticket_id}")

        elif action == "history":
            # Show ticket message history with pagination
            from bots.max_bot.payloads import ManagerTicketHistoryPayload
            
            # Delete old message
            if message_id:
                try:
                    await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception as e:
                    logger.warning(f"Failed to delete old message: {e}")
            
            # Redirect to history handler with page 0
            await handle_manager_ticket_history(
                event=event,
                payload=ManagerTicketHistoryPayload(ticket_id=ticket_id, page=0),
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
            logger.info(f"Employee {max_user_id} viewing history of ticket {ticket_id}")
        
        elif action == "cancel_close":
            # Cancel closing flow - return to ticket details
            from bots.max_bot.states import EmployeeStates
            
            # Clear FSM state
            await context.clear()
            
            # Get ticket and show details
            from sqlalchemy.orm import selectinload
            stmt = select(Ticket).where(Ticket.id == ticket_id).options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.assigned_staff)
            )
            result = await session.execute(stmt)
            ticket = result.scalar_one_or_none()
            
            if ticket:
                ticket_card = format_ticket_card_detailed(ticket)
                keyboard = get_ticket_action_keyboard(ticket)
                
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=ticket_card,
                    keyboard=keyboard,
                    parse_mode="HTML"
                )
            
            logger.info(f"Employee {max_user_id} cancelled closing ticket {ticket_id}")
        
        elif action == "back_to_list":
            # Return to tickets list
            # Clear focus mode if active
            current_state = await context.get_state()
            from bots.max_bot.states import EmployeeStates
            if current_state == EmployeeStates.in_focus:
                logger.info(f"Employee {max_user_id} exiting focus mode (back to list)")
            
            # Get current filter and page before clearing
            data = await context.get_data()
            current_filter = data.get("manager_active_filter", "all")
            current_page = data.get("manager_active_page", 0)
            
            # Clear FSM state (including focus mode)
            await context.clear()
            
            await show_active_tickets(chat_id, max_user_id, session, messenger_adapter, context, current_filter, current_page)
            
            logger.info(f"Employee {max_user_id} returned to tickets list from ticket {ticket_id}")
        
        else:
            logger.warning(f"Unknown ticket action: {action}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестное действие.",
                parse_mode="HTML"
            )
    
    except Exception as e:
        logger.error(
            f"Error handling ticket action: action={action}, ticket_id={ticket_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )


# ========== Ticket Closing Flow ==========


async def handle_closing_comment_input(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle final comment input for closing ticket.
    
    Supports text messages and file attachments (images, documents, voice, video, audio).
    Sends final comment to client and closes the ticket.
    
    Args:
        event: MessageCreated event
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    from services.ticket_service import close_ticket_with_notification
    from services.validation_service import classify_file_type
    from database.models import FileType
    
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    logger.info(f"Closing comment input: max_user_id={max_user_id}")
    
    try:
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Get ticket_id from context
        data = await context.get_data()
        ticket_id = data.get("ticket_id")
        
        if not ticket_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка: ID заявки не найден.",
                parse_mode="HTML"
            )
            return
        
        # Get employee's MAX ID
        if not employee.max_user_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Не удалось закрыть заявку. MAX ID не найден.",
                parse_mode="HTML"
            )
            return
        
        # Get final comment text
        final_comment = event.message.body.text.strip() if event.message.body.text else ""
        
        # Check if message has attachments
        has_attachments = (
            event.message.body.attachments and 
            len(event.message.body.attachments) > 0
        )
        
        # Prepare file data if attachments exist
        file_id = None
        file_type = None
        max_media_type = None
        
        if has_attachments:
            # Process first attachment (for simplicity, handle one file per closing comment)
            attachment = event.message.body.attachments[0]
            max_media_type = attachment.type
            
            # Determine file type based on attachment type
            if attachment.type == "image":
                file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                file_type = FileType.IMAGE
                if not final_comment:
                    final_comment = "📷 Изображение"
            
            elif attachment.type == "file":
                file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                raw_name = attachment.payload.name if hasattr(attachment.payload, 'name') else None
                from services.validation_service import resolve_file_name
                file_name = resolve_file_name(raw_name, file_id, fallback="document.bin")
                file_type = classify_file_type(file_name)
                if not final_comment:
                    final_comment = f"📎 {file_name}"
            
            elif attachment.type in ("voice", "audio"):
                file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                file_type = FileType.OTHER
                if not final_comment:
                    final_comment = "🎤 Голосовое сообщение"
            
            elif attachment.type == "video":
                file_id = attachment.payload.url if hasattr(attachment.payload, 'url') else None
                file_type = FileType.OTHER
                raw_video_name = attachment.payload.name if hasattr(attachment.payload, 'name') else None
                from services.validation_service import resolve_file_name
                file_name = resolve_file_name(raw_video_name, file_id, fallback="video.mp4")
                if not final_comment:
                    final_comment = f"🎥 {file_name}"
            
            else:
                logger.warning(f"Unknown attachment type: {attachment.type}")
                file_id = None
                file_type = None
                max_media_type = None
        
        # Ensure we have some content
        if not final_comment and not file_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Финальный комментарий не может быть пустым.",
                parse_mode="HTML"
            )
            return
        
        # Close ticket with notification to client
        ticket = await close_ticket_with_notification(
            session=session,
            ticket_id=ticket_id,
            employee_id=employee.max_user_id,
            final_comment=final_comment,
            messenger_adapter=messenger_adapter,
            file_id=file_id,
            file_type=file_type,
            max_media_type=max_media_type,
            messenger="max"
        )
        
        # Clear FSM state
        await context.clear()
        
        # Show success message and return to tickets list
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"✅ Заявка #{ticket_id} успешно закрыта.",
            parse_mode="HTML"
        )
        
        # Return to active tickets list
        await show_active_tickets(chat_id, max_user_id, session, messenger_adapter, context)
        
        logger.info(f"Employee {max_user_id} closed ticket {ticket_id} with final comment")
    
    except Exception as e:
        logger.error(
            f"Error handling closing comment: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при закрытии заявки.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )


# ========== Focus Mode Toggle ==========


async def handle_toggle_focus(
    event: MessageCallback,
    payload: ManagerToggleFocusPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle focus mode toggle - enable/disable communication with client.
    
    When enabled:
    - Employee enters EmployeeStates.in_focus
    - All messages sent to client automatically
    - Button shows "💬 Общение с клиентом ✅"
    
    When disabled:
    - Employee exits focus mode
    - Messages not sent to client
    - Button shows "💬 Общение с клиентом"
    
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: Toggle focus payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    ticket_id = payload.ticket_id
    enable = payload.enable
    
    logger.info(f"Toggle focus: max_user_id={max_user_id}, ticket_id={ticket_id}, enable={enable}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Get ticket
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys),
            selectinload(Ticket.assigned_staff)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Toggle focus mode
        from bots.max_bot.states import EmployeeStates
        
        if enable:
            # Enable focus mode
            focused_client_id = ticket.user.max_user_id if ticket.user.max_user_id else ticket.user.tg_user_id
            
            await context.set_state(EmployeeStates.in_focus)
            await context.update_data(
                focused_ticket_id=ticket_id,
                focused_client_id=focused_client_id
            )
            
            status_text = "💬 <b>Общение с клиентом включено</b> ✅\n\nВаши сообщения будут автоматически отправляться клиенту."
            logger.info(f"Employee {max_user_id} enabled focus mode for ticket {ticket_id}")
        else:
            # Disable focus mode
            await context.clear()
            
            status_text = "💬 <b>Общение с клиентом выключено</b> ❌\n\nВаши сообщения не будут отправляться клиенту."
            logger.info(f"Employee {max_user_id} disabled focus mode for ticket {ticket_id}")
        
        # Format ticket card with status
        ticket_card = format_ticket_card_detailed(ticket)
        full_text = f"{status_text}\n\n{ticket_card}"
        
        # Build keyboard with updated focus state
        keyboard = get_ticket_action_keyboard(ticket, enable)
        
        # Send updated message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=full_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(f"Error toggling focus: error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при переключении режима общения.",
            parse_mode="HTML"
        )


# ========== Ticket Transfer Flow ==========


async def handle_employee_selection(
    event: MessageCallback,
    payload: ManagerEmployeeSelectPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle employee selection for ticket transfer.
    
    Args:
        event: MessageCallback event
        payload: Employee selection payload
        context: FSM context
        session: Database session
        messenger_adapter: Messenger adapter
    """
    from services.ticket_service import transfer_ticket as transfer_ticket_service
    
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    action = payload.action
    
    logger.info(f"Employee selection: max_user_id={max_user_id}, action={action}, employee_id={payload.employee_id}")
    
    try:
        # Answer callback
        await event.answer()
        
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        if action == "cancel":
            # Cancel transfer - return to ticket details
            data = await context.get_data()
            ticket_id = data.get("ticket_id")
            
            # Clear FSM state
            await context.clear()
            
            if ticket_id:
                # Get ticket and show details
                from sqlalchemy.orm import selectinload
                stmt = select(Ticket).where(Ticket.id == ticket_id).options(
                    selectinload(Ticket.user),
                    selectinload(Ticket.organization),
                    selectinload(Ticket.gs_keys),
                    selectinload(Ticket.assigned_staff)
                )
                result = await session.execute(stmt)
                ticket = result.scalar_one_or_none()
                
                if ticket:
                    ticket_card = format_ticket_card_detailed(ticket)
                    keyboard = get_ticket_action_keyboard(ticket)
                    
                    await messenger_adapter.send_message(
                        chat_id=chat_id,
                        text=ticket_card,
                        keyboard=keyboard,
                        parse_mode="HTML"
                    )
            
            logger.info(f"Employee {max_user_id} cancelled ticket transfer")
        
        elif action == "select":
            # Transfer ticket to selected employee
            data = await context.get_data()
            ticket_id = data.get("ticket_id")
            target_employee_id = payload.employee_id

            if not ticket_id or not target_employee_id:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Ошибка: недостаточно данных для передачи.",
                    parse_mode="HTML"
                )
                return
            
            # Get employee's MAX ID
            if not employee.max_user_id:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Не удалось передать заявку. MAX ID не найден.",
                    parse_mode="HTML"
                )
                return
            
            # Get target employee
            stmt = select(Staff_Member).where(Staff_Member.id == target_employee_id)
            result = await session.execute(stmt)
            target_employee = result.scalar_one_or_none()
            
            if not target_employee:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Целевой сотрудник не найден.",
                    parse_mode="HTML"
                )
                return
            
            # Verify target employee has MAX ID
            if not target_employee.max_user_id:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=f"❌ Не удалось передать заявку. У сотрудника {target_employee.full_name} не найден MAX ID.",
                    parse_mode="HTML"
                )
                return
            
            # Transfer ticket using MAX user IDs (ticket type remains unchanged)
            ticket = await transfer_ticket_service(
                session, ticket_id, employee.max_user_id, target_employee.max_user_id,
                messenger="max", new_ticket_type=None
            )
            
            # Clear FSM state
            await context.clear()

            # Notify target employee about the transfer
            try:
                from services.ticket_service import send_staff_notification
                from sqlalchemy.orm import selectinload as _selectinload
                # Reload ticket with relationships for notification
                stmt_notif = (
                    select(Ticket)
                    .where(Ticket.id == ticket_id)
                    .options(
                        _selectinload(Ticket.user),
                        _selectinload(Ticket.gs_keys),
                    )
                )
                result_notif = await session.execute(stmt_notif)
                ticket_for_notif = result_notif.scalar_one_or_none()
                if ticket_for_notif:
                    await send_staff_notification(
                        bot=messenger_adapter.bot,
                        staff_id=target_employee.id,
                        ticket=ticket_for_notif,
                        routing_info={
                            "is_transfer": True,
                            "source_employee_name": employee.full_name,
                        },
                        session=session,
                    )
            except Exception as notif_err:
                logger.warning(
                    f"Failed to send transfer notification to employee {target_employee.id}: {notif_err}"
                )

            # Show success message
            success_text = f"✅ Заявка #{ticket_id} успешно передана сотруднику {target_employee.full_name}."
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=success_text,
                parse_mode="HTML"
            )
            
            # Return to active tickets list
            await show_active_tickets(chat_id, max_user_id, session, messenger_adapter, context)
            
            logger.info(
                f"Employee {max_user_id} transferred ticket {ticket_id} to employee {target_employee_id}"
            )
        
        else:
            logger.warning(f"Unknown employee selection action: {action}")
    
    except Exception as e:
        logger.error(
            f"Error handling employee selection: action={action}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при передаче заявки.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )



# ============================================================================
# Manager Ticket History Handlers
# ============================================================================

# Message history pagination constants
MANAGER_MESSAGES_PER_PAGE = 5
MAX_MESSAGE_TEXT_LENGTH = 4000  # MAX API message length limit


async def handle_manager_ticket_history(
    event: MessageCallback,
    payload: ManagerTicketHistoryPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show ticket message history with pagination for manager.
    
    Displays messages in chronological order with navigation buttons.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: Payload with ticket_id and page (or just ticket_id)
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    # Extract ticket_id and page from payload
    ticket_id = payload.ticket_id
    page = getattr(payload, 'page', 0)  # Default to page 0 if not present
    
    logger.info(f"Manager viewing ticket history: max_user_id={max_user_id}, ticket_id={ticket_id}, page={page}")
    
    try:
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Get ticket
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys),
            selectinload(Ticket.assigned_staff)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Get all messages for this ticket
        from database.models import Message
        
        stmt = (
            select(Message)
            .where(Message.ticket_id == ticket_id)
            .options(selectinload(Message.file_attachments))
            .order_by(Message.sent_at.asc())
        )
        result = await session.execute(stmt)
        all_messages = list(result.scalars().all())
        
        if not all_messages:
            # Delete old message
            if message_id:
                try:
                    await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception as e:
                    logger.warning(f"Failed to delete old message: {e}")
            
            # Show empty history message with back button
            from bots.max_bot.payloads import ManagerTicketHistoryBackPayload
            
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="🔙 К заявке",
                            payload=ManagerTicketHistoryBackPayload(ticket_id=ticket_id).pack()
                        )
                    ]
                ],
                inline=True
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="📭 История переписки пуста",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        # Calculate pagination
        total_messages = len(all_messages)
        total_pages = (total_messages + MANAGER_MESSAGES_PER_PAGE - 1) // MANAGER_MESSAGES_PER_PAGE
        
        # Validate page number
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1
        
        # Get messages for current page
        start_idx = page * MANAGER_MESSAGES_PER_PAGE
        end_idx = min(start_idx + MANAGER_MESSAGES_PER_PAGE, total_messages)
        page_messages = all_messages[start_idx:end_idx]
        
        # Format messages
        from database.models import SenderType, Staff_Member
        
        lines = [
            f"📁 <b>История переписки - Заявка #{ticket_id}</b>",
            f"Страница {page + 1} из {total_pages} (сообщений {start_idx + 1}-{end_idx} из {total_messages})",
            "─" * 5,
            ""
        ]
        
        for msg in page_messages:
            # Format timestamp
            timestamp = msg.sent_at.strftime("%d.%m %H:%M")
            
            # Determine sender
            if msg.sender_type == SenderType.USER:
                sender_name = ticket.user.full_name or ticket.user.first_name or "Клиент"
                sender_label = f"👤 {sender_name}"
            elif msg.sender_type == SenderType.STAFF:
                # Get staff member name by internal ID
                if msg.sender_id:
                    stmt = select(Staff_Member).where(Staff_Member.id == msg.sender_id)
                    result = await session.execute(stmt)
                    staff = result.scalar_one_or_none()
                    
                    if staff:
                        sender_label = f"👨‍💼 {staff.full_name}"
                    else:
                        sender_label = "👨‍💼 Сотрудник"
                else:
                    sender_label = "👨‍💼 Сотрудник"
            elif msg.sender_type == SenderType.SYSTEM:
                sender_label = "🤖 Система"
            else:
                sender_label = "❓ Неизвестно"
            
            # Format message
            lines.append(f"<b>[{timestamp}] {sender_label}</b>")
            
            if msg.message_text:
                # Truncate long messages
                text = msg.message_text
                if len(text) > 200:
                    text = text[:200] + "..."
                lines.append(text)
            
            # Check for file attachments
            if msg.file_attachments:
                for attachment in msg.file_attachments:
                    from database.models import FileType as FT
                    ft = attachment.file_type
                    if ft == FT.IMAGE:
                        label = "Изображение"
                        emoji = "🖼"
                    elif ft in (FT.DOCUMENT, FT.PDF):
                        label = "Документ"
                        emoji = "📄"
                    elif ft == FT.OTHER:
                        label = "Голосовое сообщение"
                        emoji = "🎤"
                    else:
                        label = "Файл"
                        emoji = "📎"
                    file_url = attachment.max_file_url or (
                        attachment.telegram_file_id
                        if attachment.telegram_file_id and attachment.telegram_file_id.startswith("http")
                        else None
                    )
                    if file_url:
                        lines.append(f'{emoji} <a href="{file_url}">{label}</a>')
                    else:
                        lines.append(f"{emoji} {label}")
            
            lines.append("")  # Empty line between messages
        
        lines.append("─" * 5)
        
        history_text = "\n".join(lines)
        
        # Build navigation keyboard
        from bots.max_bot.payloads import ManagerTicketHistoryPayload, ManagerTicketHistoryBackPayload
        
        buttons = []
        
        # Pagination buttons
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(
                    KeyboardButton(
                        text="⬅️ Назад",
                        payload=ManagerTicketHistoryPayload(ticket_id=ticket_id, page=page - 1).pack()
                    )
                )
            if page < total_pages - 1:
                nav_buttons.append(
                    KeyboardButton(
                        text="Вперёд ➡️",
                        payload=ManagerTicketHistoryPayload(ticket_id=ticket_id, page=page + 1).pack()
                    )
                )
            if nav_buttons:
                buttons.append(nav_buttons)
        
        # Back button
        buttons.append([
            KeyboardButton(
                text="🔙 К заявке",
                payload=ManagerTicketHistoryBackPayload(ticket_id=ticket_id).pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        # Truncate if exceeds MAX API limit
        if len(history_text) > MAX_MESSAGE_TEXT_LENGTH:
            history_text = history_text[:MAX_MESSAGE_TEXT_LENGTH - 50] + "\n\n<i>... (текст обрезан)</i>"
        
        # Delete old message and send new one (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=history_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Manager viewed ticket history: max_user_id={max_user_id}, ticket_id={ticket_id}, "
            f"page={page + 1}/{total_pages}"
        )
        
    except Exception as e:
        logger.error(
            f"Error viewing manager ticket history: max_user_id={max_user_id}, ticket_id={ticket_id}, "
            f"page={page}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке истории.",
            parse_mode="HTML"
        )


async def handle_manager_ticket_history_back(
    event: MessageCallback,
    payload: ManagerTicketHistoryBackPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Return from ticket history to ticket card for manager.
    
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: ManagerTicketHistoryBackPayload with ticket_id
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    ticket_id = payload.ticket_id
    
    logger.info(f"Manager returning from history to ticket: max_user_id={max_user_id}, ticket_id={ticket_id}")
    
    try:
        # Verify user is staff member
        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML"
            )
            return
        
        # Get ticket
        from sqlalchemy.orm import selectinload
        stmt = select(Ticket).where(Ticket.id == ticket_id).options(
            selectinload(Ticket.user),
            selectinload(Ticket.organization),
            selectinload(Ticket.gs_keys),
            selectinload(Ticket.assigned_staff)
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Show ticket card
        ticket_card = format_ticket_card_detailed(ticket)
        
        # Check if focus mode is enabled for this ticket
        data = await context.get_data()
        focus_ticket_id = data.get("focus_ticket_id")
        is_focus_enabled = (focus_ticket_id == ticket_id)
        
        keyboard = get_ticket_action_keyboard(ticket, is_focus_enabled)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=ticket_card,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Manager returned to ticket card: max_user_id={max_user_id}, ticket_id={ticket_id}")
        
    except Exception as e:
        logger.error(
            f"Error returning to ticket card: max_user_id={max_user_id}, ticket_id={ticket_id}, "
            f"error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


# ========== Client Message Notification Action Handlers ==========


async def handle_take_from_message_notification(
    event: MessageCallback,
    payload: "ManagerTakeFromMessagePayload",
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Handle "Взять в работу" button click from a client message notification.

    Takes the ticket into work and enters focus mode so the manager can
    reply directly by typing in chat — no extra menus needed.

    Uses replace_message pattern.
    """
    from bots.max_bot.payloads import ManagerTakeFromMessagePayload
    from bots.max_bot.states import EmployeeStates
    from services.ticket_service import take_ticket_into_work as take_ticket_service
    from sqlalchemy.orm import selectinload

    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None
    ticket_id = payload.ticket_id

    logger.info(
        f"Take ticket from message notification: max_user_id={max_user_id}, ticket_id={ticket_id}"
    )

    try:
        await event.answer()

        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML",
            )
            return

        # Delete notification message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete notification message: {e}")

        # Take ticket into work
        await take_ticket_service(session, ticket_id, max_user_id, messenger="max")

        # Reload ticket with relationships
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.assigned_staff),
            )
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()

        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML",
            )
            return

        # Enter focus mode
        focused_client_id = (
            ticket.user.max_user_id if ticket.user.max_user_id else ticket.user.tg_user_id
        )
        await context.set_state(EmployeeStates.in_focus)
        await context.update_data(
            focused_ticket_id=ticket_id,
            focused_client_id=focused_client_id,
        )

        ticket_card = format_ticket_card_detailed(ticket)
        keyboard = get_ticket_action_keyboard(ticket, is_focus_enabled=True)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ <b>Заявка взята в работу. Режим общения включён.</b>\n\n"
                f"Просто пишите сообщения — они будут автоматически отправляться клиенту.\n\n"
                f"{ticket_card}"
            ),
            keyboard=keyboard,
            parse_mode="HTML",
        )

        logger.info(
            f"Employee {max_user_id} took ticket {ticket_id} into work from message notification"
        )

    except Exception as e:
        logger.error(
            f"Error taking ticket from message notification: ticket_id={ticket_id}, error={e}",
            exc_info=True,
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при взятии заявки в работу.",
            parse_mode="HTML",
        )


async def handle_focus_from_message_notification(
    event: MessageCallback,
    payload: "ManagerFocusFromMessagePayload",
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Handle "Общение с клиентом" button click from a client message notification.

    Enters focus mode for an already in-progress ticket so the manager can
    reply directly by typing in chat — no extra menus needed.

    Uses replace_message pattern.
    """
    from bots.max_bot.payloads import ManagerFocusFromMessagePayload
    from bots.max_bot.states import EmployeeStates
    from sqlalchemy.orm import selectinload

    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, "mid") else None
    ticket_id = payload.ticket_id

    logger.info(
        f"Focus from message notification: max_user_id={max_user_id}, ticket_id={ticket_id}"
    )

    try:
        await event.answer()

        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML",
            )
            return

        # Delete notification message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete notification message: {e}")

        # Load ticket with relationships
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.organization),
                selectinload(Ticket.gs_keys),
                selectinload(Ticket.assigned_staff),
            )
        )
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()

        if not ticket:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Заявка не найдена.",
                parse_mode="HTML",
            )
            return

        # Enter focus mode
        focused_client_id = (
            ticket.user.max_user_id if ticket.user.max_user_id else ticket.user.tg_user_id
        )
        await context.set_state(EmployeeStates.in_focus)
        await context.update_data(
            focused_ticket_id=ticket_id,
            focused_client_id=focused_client_id,
        )

        ticket_card = format_ticket_card_detailed(ticket)
        keyboard = get_ticket_action_keyboard(ticket, is_focus_enabled=True)

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"💬 <b>Режим общения включён.</b>\n\n"
                f"Просто пишите сообщения — они будут автоматически отправляться клиенту.\n\n"
                f"{ticket_card}"
            ),
            keyboard=keyboard,
            parse_mode="HTML",
        )

        logger.info(
            f"Employee {max_user_id} entered focus mode for ticket {ticket_id} from message notification"
        )

    except Exception as e:
        logger.error(
            f"Error entering focus from message notification: ticket_id={ticket_id}, error={e}",
            exc_info=True,
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при включении режима общения.",
            parse_mode="HTML",
        )


# ========== Employee Self-Service Menu ==========


async def show_employee_self_service_menu(
    chat_id: int,
    employee: "Staff_Member",
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Show employee self-service menu with duty and availability controls.

    Determines which buttons to show based on employee role:
    - TECHNICAL_SUPPORT (is_estimate_tech_specialist=False): duty TP button
    - Any role with is_estimate_tech_specialist=True: duty estimate button
    - All non-admin, non-manager roles: toggle working availability button

    Args:
        chat_id: MAX chat ID
        employee: Staff_Member object
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    from bots.max_bot.keyboards.staff.manager_kb import get_employee_self_service_keyboard
    from services.settings_service import get_setting

    # Determine which duty buttons to show
    can_set_duty_tp = (
        employee.staff_role == StaffRole.TECHNICAL_SUPPORT
        and not employee.is_estimate_tech_specialist
    )
    can_set_duty_estimate = employee.is_estimate_tech_specialist

    # Check if employee is currently the duty specialist
    is_current_duty_tp = False
    is_current_duty_estimate = False

    if can_set_duty_tp:
        duty_tp_id = await get_setting(session, "duty_support_account")
        is_current_duty_tp = duty_tp_id is not None and int(duty_tp_id) == employee.id

    if can_set_duty_estimate:
        duty_est_id = await get_setting(session, "duty_estimate_specialist_account")
        is_current_duty_estimate = duty_est_id is not None and int(duty_est_id) == employee.id

    keyboard = get_employee_self_service_keyboard(
        can_set_duty_tp=can_set_duty_tp,
        can_set_duty_estimate=can_set_duty_estimate,
        is_working_today=employee.is_working_today,
        is_current_duty_tp=is_current_duty_tp,
        is_current_duty_estimate=is_current_duty_estimate,
    )

    # Build status text
    working_status = "🟢 Доступен" if employee.is_working_today else "🔴 Недоступен"
    duty_lines = []
    if is_current_duty_tp:
        duty_lines.append("⚡ Вы назначены дежурным ТП")
    if is_current_duty_estimate:
        duty_lines.append("📊 Вы назначены дежурным по сметной консультации")

    text = (
        f"👤 <b>Меню сотрудника</b>\n\n"
        f"<b>Сотрудник:</b> {employee.full_name}\n"
        f"<b>Статус доступности:</b> {working_status}\n"
    )
    if duty_lines:
        text += "\n" + "\n".join(duty_lines) + "\n"

    text += "\nВыберите действие 👇"

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=text,
        keyboard=keyboard,
        parse_mode="HTML",
    )


async def handle_employee_menu_action(
    event: MessageCallback,
    payload: "StaffSelfServicePayload",
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Handle employee self-service menu action callbacks.

    Routes to:
    - set_duty_tp: Show confirmation for setting self as duty TP
    - set_duty_estimate: Show confirmation for setting self as duty estimate specialist
    - toggle_working: Show confirmation for toggling working availability
    - back_to_manager: Return to main manager menu

    maxapi Pattern Notes:
    - Uses event.callback.user.user_id for user identification
    - Uses replace_message pattern (delete old + send new)

    Args:
        event: MessageCallback event from maxapi
        payload: Parsed StaffSelfServicePayload
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    from bots.max_bot.keyboards.staff.manager_kb import (
        get_employee_duty_confirm_keyboard,
        get_employee_toggle_working_confirm_keyboard,
    )

    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    action = payload.action

    logger.info(f"Employee menu action: max_user_id={max_user_id}, action={action}")

    try:
        await event.answer()

        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML",
            )
            return

        # Delete old message (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")

        if action == "set_duty_tp":
            # Only TECHNICAL_SUPPORT (non-estimate) can set themselves as duty TP
            if not (employee.staff_role == StaffRole.TECHNICAL_SUPPORT and not employee.is_estimate_tech_specialist):
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Эта функция доступна только для специалистов техподдержки.",
                    parse_mode="HTML",
                )
                return

            keyboard = get_employee_duty_confirm_keyboard(duty_type="tp")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "⚡ <b>Назначить себя дежурным ТП</b>\n\n"
                    "Вы будете назначены дежурным специалистом техподдержки.\n"
                    "В продлённое рабочее время заявки типа «Техподдержка» будут направляться вам.\n\n"
                    "Подтвердить?"
                ),
                keyboard=keyboard,
                parse_mode="HTML",
            )

        elif action == "set_duty_estimate":
            # Only estimate specialists can set themselves as duty estimate
            if not employee.is_estimate_tech_specialist:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Эта функция доступна только для сметных специалистов.",
                    parse_mode="HTML",
                )
                return

            keyboard = get_employee_duty_confirm_keyboard(duty_type="estimate")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "📊 <b>Назначить себя дежурным по сметной консультации</b>\n\n"
                    "Вы будете назначены дежурным специалистом по сметной консультации.\n"
                    "В продлённое рабочее время заявки типа «Консультация» будут направляться вам.\n\n"
                    "Подтвердить?"
                ),
                keyboard=keyboard,
                parse_mode="HTML",
            )

        elif action == "toggle_working":
            if employee.is_working_today:
                confirm_text = (
                    "🔴 <b>Сделать себя недоступным</b>\n\n"
                    "Вы не будете получать новые заявки, пока не вернёте статус «Доступен».\n"
                    "Уже назначенные заявки остаются у вас.\n\n"
                    "Подтвердить?"
                )
            else:
                confirm_text = (
                    "🟢 <b>Сделать себя доступным</b>\n\n"
                    "Вы снова будете получать новые заявки.\n\n"
                    "Подтвердить?"
                )
            keyboard = get_employee_toggle_working_confirm_keyboard()
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=confirm_text,
                keyboard=keyboard,
                parse_mode="HTML",
            )

        elif action == "back_to_manager":
            # Return to main manager menu
            is_admin = employee.staff_role == StaffRole.ADMINISTRATOR
            is_manager = employee.staff_role == StaffRole.MANAGER
            from services.employee_service import get_employee_active_tickets, get_employee_new_tickets_count
            active_tickets = await get_employee_active_tickets(session, employee.max_user_id, ticket_type_filter=None)
            new_tickets_count = await get_employee_new_tickets_count(session, employee.max_user_id, ticket_type_filter=None)
            keyboard = get_manager_menu_keyboard(
                is_admin=is_admin,
                is_manager=is_manager,
                active_tickets_count=len(active_tickets),
                show_employee_menu=not is_admin and not is_manager,
            )
            menu_text = get_employee_menu_text(
                role=employee.staff_role.value,
                full_name=employee.full_name,
                position=employee.position,
                active_tickets_count=len(active_tickets),
                new_tickets_count=new_tickets_count,
            )
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=menu_text,
                keyboard=keyboard,
                parse_mode="HTML",
            )

        else:
            logger.warning(f"Unknown employee menu action: {action}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестное действие.",
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(
            f"Error handling employee menu action: action={action}, max_user_id={max_user_id}, error={e}",
            exc_info=True,
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML",
        )


async def handle_employee_set_duty(
    event: MessageCallback,
    payload: "StaffSetDutyPayload",
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Handle confirmation of setting employee as duty specialist.

    On confirm=True: updates the system setting (duty_support_account or
    duty_estimate_specialist_account) to this employee's staff ID.
    On confirm=False: returns to employee self-service menu.

    Args:
        event: MessageCallback event from maxapi
        payload: Parsed StaffSetDutyPayload
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    from services.settings_service import set_setting

    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    logger.info(
        f"Employee set duty: max_user_id={max_user_id}, duty_type={payload.duty_type}, confirm={payload.confirm}"
    )

    try:
        await event.answer()

        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML",
            )
            return

        # Delete old message (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")

        if not payload.confirm:
            # User cancelled — return to employee menu
            await show_employee_self_service_menu(
                chat_id=chat_id,
                employee=employee,
                session=session,
                messenger_adapter=messenger_adapter,
            )
            return

        # Validate permissions
        if payload.duty_type == "tp":
            if not (employee.staff_role == StaffRole.TECHNICAL_SUPPORT and not employee.is_estimate_tech_specialist):
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Эта функция доступна только для специалистов техподдержки.",
                    parse_mode="HTML",
                )
                return
            setting_key = "duty_support_account"
            success_text = (
                "✅ <b>Вы назначены дежурным специалистом ТП</b>\n\n"
                "В продлённое рабочее время заявки типа «Техподдержка» будут направляться вам."
            )

        elif payload.duty_type == "estimate":
            if not employee.is_estimate_tech_specialist:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ Эта функция доступна только для сметных специалистов.",
                    parse_mode="HTML",
                )
                return
            setting_key = "duty_estimate_specialist_account"
            success_text = (
                "✅ <b>Вы назначены дежурным по сметной консультации</b>\n\n"
                "В продлённое рабочее время заявки типа «Консультация» будут направляться вам."
            )

        else:
            logger.warning(f"Unknown duty_type: {payload.duty_type}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестный тип дежурства.",
                parse_mode="HTML",
            )
            return

        # Save setting: store staff internal ID as string
        await set_setting(session, setting_key, str(employee.id))
        await session.commit()

        logger.info(
            f"Employee {max_user_id} (staff_id={employee.id}) set as duty {payload.duty_type}"
        )

        # Show success and return to employee menu
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=success_text,
            parse_mode="HTML",
        )

        # Re-fetch employee to get fresh state
        employee = await is_staff_member(session, max_user_id)
        if employee:
            await show_employee_self_service_menu(
                chat_id=chat_id,
                employee=employee,
                session=session,
                messenger_adapter=messenger_adapter,
            )

    except Exception as e:
        logger.error(
            f"Error setting duty specialist: max_user_id={max_user_id}, error={e}",
            exc_info=True,
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при назначении дежурного.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML",
        )


async def handle_employee_toggle_working(
    event: MessageCallback,
    payload: "StaffToggleWorkingPayload",
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """
    Handle confirmation of toggling employee working availability.

    On confirm=True: flips employee.is_working_today in the database.
    On confirm=False: returns to employee self-service menu.

    When is_working_today becomes False, the employee is excluded from
    round-robin assignment and duty routing.

    Args:
        event: MessageCallback event from maxapi
        payload: Parsed StaffToggleWorkingPayload
        context: MemoryContext for FSM state management
        session: AsyncSession for database operations
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    from sqlalchemy import select as sa_select

    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None

    logger.info(
        f"Employee toggle working: max_user_id={max_user_id}, confirm={payload.confirm}"
    )

    try:
        await event.answer()

        employee = await is_staff_member(session, max_user_id)
        if not employee:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к интерфейсу сотрудника.",
                parse_mode="HTML",
            )
            return

        # Delete old message (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")

        if not payload.confirm:
            # User cancelled — return to employee menu
            await show_employee_self_service_menu(
                chat_id=chat_id,
                employee=employee,
                session=session,
                messenger_adapter=messenger_adapter,
            )
            return

        # Toggle the flag
        new_status = not employee.is_working_today
        employee.is_working_today = new_status
        await session.commit()

        logger.info(
            f"Employee {max_user_id} (staff_id={employee.id}) toggled is_working_today to {new_status}"
        )

        if new_status:
            status_text = (
                "🟢 <b>Статус изменён: Доступен</b>\n\n"
                "Вы снова будете получать новые заявки."
            )
        else:
            status_text = (
                "🔴 <b>Статус изменён: Недоступен</b>\n\n"
                "Вы не будете получать новые заявки.\n"
                "Уже назначенные заявки остаются у вас.\n"
                "Не забудьте вернуть статус «Доступен», когда будете готовы к работе."
            )

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=status_text,
            parse_mode="HTML",
        )

        # Re-fetch employee to get fresh state and show updated menu
        employee = await is_staff_member(session, max_user_id)
        if employee:
            await show_employee_self_service_menu(
                chat_id=chat_id,
                employee=employee,
                session=session,
                messenger_adapter=messenger_adapter,
            )

    except Exception as e:
        logger.error(
            f"Error toggling working status: max_user_id={max_user_id}, error={e}",
            exc_info=True,
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при изменении статуса.\nПожалуйста, попробуйте позже.",
            parse_mode="HTML",
        )
