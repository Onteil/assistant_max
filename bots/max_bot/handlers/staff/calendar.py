"""
Calendar Management Handler for MAX Bot

Handles calendar/schedule management for administrators.
Provides work schedule configuration, rule management, and period clearing.

Requirements: Calendar Management Interface
"""

import logging
from datetime import datetime

import pytz
from maxapi.types import MessageCallback, MessageCreated
from maxapi.context import MemoryContext
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    AdminMenuPayload,
    CalendarMenuPayload,
    CalendarRulePayload,
    CalendarClearPayload,
    CalendarPaginationPayload,
    CalendarConfirmPayload,
)
from database.models import Staff_Member, StaffRole
from services.calendar_service import CalendarService
from services.calendar_formatter import CalendarFormatter
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def is_admin(session: AsyncSession, max_user_id: int) -> Staff_Member | None:
    """
    Check if user is an administrator.
    
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
        logger.error(f"Error checking admin status: {e}", exc_info=True)
        return None


# ============================================================================
# ============================================================================
# Calendar Main Menu
# ============================================================================


def get_calendar_main_keyboard() -> Keyboard:
    """
    Build main calendar menu keyboard.
    
    Buttons:
    [📅 На неделю] [📅 На месяц]
    [📋 Добавить/Список] [🗑 Очистить период]
    [❓ Пример команд]
    [◀️ Назад в админ-панель]
    """
    buttons = [
        # Row 1: Weekly and monthly views
        [
            KeyboardButton(
                text="📅 На неделю",
                payload=CalendarMenuPayload(action="weekly").pack()
            ),
            KeyboardButton(
                text="📅 На месяц",
                payload=CalendarMenuPayload(action="monthly").pack()
            )
        ],
        # Row 2: Rule list and clear period
        [
            KeyboardButton(
                text="📋 Добавить/Список",
                payload=CalendarMenuPayload(action="rules").pack()
            ),
            KeyboardButton(
                text="🗑 Очистить период",
                payload=CalendarMenuPayload(action="clear").pack()
            )
        ],
        # Row 3: Command examples
        [
            KeyboardButton(
                text="❓ Пример команд",
                payload=CalendarMenuPayload(action="examples").pack()
            )
        ],
        # Row 4: Back button
        [
            KeyboardButton(
                text="◀️ Назад в админ-панель",
                payload=AdminMenuPayload(action="calendar_back").pack()
            )
        ]
    ]
    
    return Keyboard(buttons=buttons, inline=True)


async def handle_calendar_menu(
    event: MessageCallback,
    payload: AdminMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display the main calendar management menu.
    
    Shows current status, active rules, and action buttons.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: AdminMenuPayload with action="calendar"
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    logger.info(f"Calendar menu access: max_user_id={max_user_id}")
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению календарем.",
                parse_mode="HTML"
            )
            return
        
        # Set FSM state to enable text command handling
        from bots.max_bot.states import CalendarStates
        await context.set_state(CalendarStates.managing_calendar)
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Initialize services
        calendar_service = CalendarService()
        calendar_formatter = CalendarFormatter()
        
        # Get current Moscow time
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_dt = datetime.now(moscow_tz)
        current_date = current_dt.date()
        
        # Get current work mode
        current_mode = await calendar_service.get_work_mode_for_datetime(
            session, current_dt
        )
        
        # Get active rules
        active_rules = await calendar_service.get_all_rules(session)
        
        # Format main menu
        menu_text = calendar_formatter.format_main_menu(
            current_date, current_mode, active_rules
        )
        
        # Get calendar main keyboard
        keyboard = get_calendar_main_keyboard()
        
        # Send calendar menu
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=menu_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} accessed calendar menu")
        
    except Exception as e:
        logger.error(f"Error showing calendar menu: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке календаря.",
            parse_mode="HTML"
        )


# ============================================================================
# Calendar Menu Actions
# ============================================================================


async def handle_calendar_action(
    event: MessageCallback,
    payload: CalendarMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle calendar menu actions.
    
    Routes to different calendar functions based on action.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        payload: CalendarMenuPayload with action
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    action = payload.action
    
    logger.info(f"Calendar action: max_user_id={max_user_id}, action={action}")
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению календарем.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Route to appropriate handler
        if action == "weekly":
            await handle_weekly_view(event, session, messenger_adapter)
        
        elif action == "monthly":
            await handle_monthly_view(event, session, messenger_adapter)
        
        elif action == "rules":
            await handle_rule_list(event, session, messenger_adapter, context=context)
        
        elif action == "clear":
            await handle_clear_period_start(event, context, session, messenger_adapter)
        
        elif action == "examples":
            await handle_command_examples(event, messenger_adapter)
        
        elif action == "back_to_menu":
            # Return to calendar main menu
            await handle_back_to_menu(event, payload, context, session, messenger_adapter)
        
        elif action == "back":
            # Return to admin panel
            from bots.max_bot.handlers.staff.admin_panel import get_admin_panel_keyboard, get_admin_panel_menu_text
            
            keyboard = await get_admin_panel_keyboard(session)
            menu_text = await get_admin_panel_menu_text(session)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=menu_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        
        else:
            logger.warning(f"Unknown calendar action: {action}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестное действие.",
                parse_mode="HTML"
            )
        
        logger.info(f"Administrator {max_user_id} performed calendar action: {action}")
        
    except Exception as e:
        logger.error(f"Error handling calendar action: action={action}, error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


# ============================================================================
# Calendar Views (Stubs for now)
# ============================================================================


async def handle_weekly_view(
    event: MessageCallback,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display calendar view for the current week (7 days).
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    
    try:
        from datetime import timedelta
        
        # Initialize services
        calendar_service = CalendarService()
        calendar_formatter = CalendarFormatter()
        
        # Get current Moscow time
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_dt = datetime.now(moscow_tz)
        start_date = current_dt.date()
        end_date = start_date + timedelta(days=6)
        
        # Get rules for next 7 days
        rules = await calendar_service.get_rules_for_date_range(
            session, start_date, end_date
        )
        
        # Format weekly view
        view_text = calendar_formatter.format_weekly_view(start_date, rules)
        
        # Back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ Назад к календарю",
                        payload=CalendarMenuPayload(action="back_to_menu").pack()
                    )
                ]
            ],
            inline=True
        )
        
        # Send weekly view
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=view_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error showing weekly view: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке недельного вида.",
            parse_mode="HTML"
        )


async def handle_monthly_view(
    event: MessageCallback,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display calendar view for the current month.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    
    try:
        from calendar import monthrange
        from datetime import date
        
        # Initialize services
        calendar_service = CalendarService()
        calendar_formatter = CalendarFormatter()
        
        # Get current Moscow time
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_dt = datetime.now(moscow_tz)
        year = current_dt.year
        month = current_dt.month
        
        # Get first and last day of month
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        
        # Get rules for the month
        rules = await calendar_service.get_rules_for_date_range(
            session, first_day, last_day
        )
        
        # Format monthly view
        view_text = calendar_formatter.format_monthly_view(year, month, rules)
        
        # Back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ Назад к календарю",
                        payload=CalendarMenuPayload(action="back_to_menu").pack()
                    )
                ]
            ],
            inline=True
        )
        
        # Check if message is too long (MAX limit is ~4096)
        if len(view_text) > 4000:
            # Send in parts
            parts = []
            current_part = ""
            for line in view_text.split('\n'):
                if len(current_part) + len(line) + 1 > 3800:
                    parts.append(current_part)
                    current_part = line + '\n'
                else:
                    current_part += line + '\n'
            if current_part:
                parts.append(current_part)
            
            # Send all parts except last
            for part in parts[:-1]:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=part,
                    parse_mode="HTML"
                )
            
            # Send last part with keyboard
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=parts[-1],
                keyboard=keyboard,
                parse_mode="HTML"
            )
        else:
            # Single message
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=view_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"Error showing monthly view: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке месячного вида.",
            parse_mode="HTML"
        )


async def handle_rule_list_stub(
    event: MessageCallback,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Show list of calendar rules (stub - deprecated)."""
    chat_id = event.message.recipient.chat_id
    
    # TODO: Remove this stub function - use the main handle_rule_list instead
    keyboard = Keyboard(
        buttons=[
            [
                KeyboardButton(
                    text="◀️ Назад к календарю",
                    payload=CalendarMenuPayload(action="back_to_menu").pack()
                )
            ]
        ],
        inline=True
    )
    
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="📋 <b>Список правил</b>\n\nФункционал в разработке.",
        keyboard=keyboard,
        parse_mode="HTML"
    )


async def handle_clear_period_start(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Initiate period clearing flow, prompt for date range.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению календарем.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Set FSM state to waiting for date range input
        from bots.max_bot.states import CalendarStates
        await context.set_state(CalendarStates.entering_clear_period)
        
        logger.info(f"Set state to entering_clear_period for user {max_user_id}")
        
        # Display prompt for date range input
        prompt_text = (
            "🗑 <b>Очистка периода</b>\n\n"
            "Введите диапазон дат для очистки всех правил в этом периоде.\n\n"
            "<b>Формат:</b>\n"
            "• с [день] [месяц] по [день] [месяц]\n"
            "• с [день] по [день] [месяц]\n\n"
            "<b>Примеры:</b>\n"
            "• с 1 января по 31 января\n"
            "• с 1 по 15 февраля\n"
            "• с 20 декабря по 5 января\n\n"
            "Все правила, которые пересекаются с указанным периодом, будут удалены."
        )
        
        # Back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ Назад к календарю",
                        payload=CalendarMenuPayload(action="back_to_menu").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=prompt_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} initiated period clearing flow")
        
    except Exception as e:
        logger.error(f"Error starting period clearing: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при запуске очистки периода.",
            parse_mode="HTML"
        )


async def handle_command_examples(
    event: MessageCallback,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Show command examples."""
    chat_id = event.message.recipient.chat_id
    
    # TODO: Implement command examples
    keyboard = Keyboard(
        buttons=[
            [
                KeyboardButton(
                    text="◀️ Назад к календарю",
                    payload=CalendarMenuPayload(action="back_to_menu").pack()
                )
            ]
        ],
        inline=True
    )
    
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="❓ <b>Примеры команд</b>\n\nФункционал в разработке.",
        keyboard=keyboard,
        parse_mode="HTML"
    )



# ============================================================================
# Rule List Implementation
# ============================================================================


async def handle_rule_list(
    event: MessageCallback,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    target_year: int | None = None,
    target_month: int | None = None,
    context: MemoryContext | None = None
) -> None:
    """
    Display list of all active schedule rules with pagination by month.
    Uses replace_message pattern.
    
    Args:
        event: MessageCallback event
        session: Database session
        messenger_adapter: MAXMessengerAdapter
        target_year: Specific year to display
        target_month: Specific month to display
        context: MemoryContext for FSM state (required for initial call)
    """
    chat_id = event.message.recipient.chat_id
    
    def _get_month_name_ru(month: int) -> str:
        """Get Russian month name."""
        months = {
            1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
            5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
            9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
        }
        return months.get(month, "")
    
    try:
        # Initialize services
        calendar_service = CalendarService()
        calendar_formatter = CalendarFormatter()
        
        # Get all rules
        rules = await calendar_service.get_all_rules(session)
        
        # First message: Instructions (only on initial call)
        if target_year is None and target_month is None:
            # Set FSM state to enable text command handling
            if context:
                from bots.max_bot.states import CalendarStates
                await context.set_state(CalendarStates.managing_calendar)
            
            instructions_text = (
                "📝 <b>Как добавить правило календаря</b>\n\n"
                "Отправьте команду в одном из форматов:\n\n"
                "<b>Одна дата:</b>\n"
                "• <code>31 января рабочее время с 9 до 15</code>\n"
                "• <code>21 марта рабочее время с 8:30 до 17:00</code>\n"
                "• <code>23 февраля нерабочее время</code>\n"
                "• <code>8 марта продленное время с 17:30 до 20:15</code>\n\n"
                "<b>Период (диапазон дат):</b>\n"
                "• <code>с 1 по 5 февраля нерабочее время</code>\n"
                "• <code>с 10 по 15 марта рабочее время с 10 до 16</code>\n"
                "• <code>с 1 по 5 апреля продленное время с 18:30 до 22:00</code>\n\n"
                "<i>После отправки команды система покажет интерпретацию и попросит подтверждение.</i>"
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=instructions_text,
                parse_mode="HTML"
            )
        
        # Format rule list
        if not rules:
            list_text = (
                "📋 <b>Список правил</b>\n\n"
                "<i>Нет активных правил. Действует базовый график.</i>"
            )
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="◀️ Назад к календарю",
                            payload=CalendarMenuPayload(action="back_to_menu").pack()
                        )
                    ]
                ],
                inline=True
            )
        else:
            # Determine which month to display
            moscow_tz = pytz.timezone('Europe/Moscow')
            current_date = datetime.now(moscow_tz).date()
            
            if target_year is not None and target_month is not None:
                display_year = target_year
                display_month = target_month
            else:
                display_year = current_date.year
                display_month = current_date.month
            
            # Group rules by month
            from collections import defaultdict
            rules_by_month = defaultdict(list)
            for rule in rules:
                month_key = (rule.start_date.year, rule.start_date.month)
                rules_by_month[month_key].append(rule)
            
            # Get rules for display month
            display_month_key = (display_year, display_month)
            month_rules = rules_by_month.get(display_month_key, [])
            
            # Calculate prev/next months
            if display_month == 1:
                prev_year, prev_month = display_year - 1, 12
            else:
                prev_year, prev_month = display_year, display_month - 1
            
            if display_month == 12:
                next_year, next_month = display_year + 1, 1
            else:
                next_year, next_month = display_year, display_month + 1
            
            # Format month name
            month_name_ru = _get_month_name_ru(display_month) + f" {display_year}"
            
            lines = [
                f"📋 <b>Список правил - {month_name_ru}</b>",
                "<i>(упорядочены по приоритету)</i>\n"
            ]
            
            if not month_rules:
                lines.append("<i>Нет правил на этот месяц.</i>")
            else:
                # Calculate global rule numbers
                all_months_sorted = sorted(rules_by_month.keys())
                rule_number = 1
                
                for month_key in all_months_sorted:
                    if month_key == display_month_key:
                        for rule in rules_by_month[month_key]:
                            rule_str = calendar_formatter._format_rule_detail(rule_number, rule)
                            
                            potential_text = "\n".join(lines + [rule_str])
                            if len(potential_text) > 3800:
                                lines.append("\n<i>... (список сокращен)</i>")
                                break
                            
                            lines.append(rule_str)
                            rule_number += 1
                        break
                    else:
                        rule_number += len(rules_by_month[month_key])
            
            lines.append("\n<i>Чтобы удалить правило, отправьте:</i>")
            lines.append("<code>Удалить правило [номер]</code>")
            
            list_text = "\n".join(lines)
            
            # Build pagination keyboard
            buttons = []
            
            # Pagination row
            nav_buttons = []
            nav_buttons.append(
                KeyboardButton(
                    text="⬅️ Пред. месяц",
                    payload=CalendarPaginationPayload(
                        action="prev_month",
                        year=prev_year,
                        month=prev_month
                    ).pack()
                )
            )
            nav_buttons.append(
                KeyboardButton(
                    text="След. месяц ➡️",
                    payload=CalendarPaginationPayload(
                        action="next_month",
                        year=next_year,
                        month=next_month
                    ).pack()
                )
            )
            buttons.append(nav_buttons)
            
            # Back button
            buttons.append([
                KeyboardButton(
                    text="◀️ Назад к календарю",
                    payload=CalendarMenuPayload(action="back_to_menu").pack()
                )
            ])
            
            keyboard = Keyboard(buttons=buttons, inline=True)
        
        # Send message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=list_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error showing rule list: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке списка правил.",
            parse_mode="HTML"
        )


async def handle_rule_pagination(
    event: MessageCallback,
    payload: CalendarPaginationPayload,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle pagination for rule list.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Show rule list for target month
        await handle_rule_list(
            event=event,
            session=session,
            messenger_adapter=messenger_adapter,
            target_year=payload.year,
            target_month=payload.month
        )
        
    except Exception as e:
        logger.error(f"Error handling rule pagination: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


# ============================================================================
# Command Examples
# ============================================================================


async def handle_command_examples(
    event: MessageCallback,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Show command examples for calendar management.
    Uses replace_message pattern.
    """
    chat_id = event.message.recipient.chat_id
    
    try:
        # Initialize formatter
        calendar_formatter = CalendarFormatter()
        
        # Get examples text
        examples_text = calendar_formatter.format_command_examples()
        
        # Back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ Назад к календарю",
                        payload=CalendarMenuPayload(action="back_to_menu").pack()
                    )
                ]
            ],
            inline=True
        )
        
        # Send examples
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=examples_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error showing command examples: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


# ============================================================================
# Handle "Back to Menu" Action
# ============================================================================


async def handle_back_to_menu(
    event: MessageCallback,
    payload: CalendarMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle back to calendar menu action.
    Uses replace_message pattern.
    """
    # Reuse handle_calendar_menu with AdminMenuPayload
    admin_payload = AdminMenuPayload(action="calendar")
    await handle_calendar_menu(
        event=event,
        payload=admin_payload,
        context=context,
        session=session,
        messenger_adapter=messenger_adapter
    )



# ============================================================================
# Text Command Handlers
# ============================================================================


async def handle_calendar_text_command(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle text commands for calendar management.
    
    Supports:
    - Adding rules: "31 января рабочее время с 9 до 15"
    - Adding rules with minutes: "21 марта рабочее время с 8:30 до 17:00"
    - Deleting rules: "Удалить правило 2"
    - Period clearing: "Очистить с 1 по 5 февраля"
    
    Args:
        event: MessageCreated event
        context: MemoryContext for FSM state
        session: Database session
        messenger_adapter: MAXMessengerAdapter for sending messages
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    text = event.message.body.text
    
    logger.info(f"Calendar text command: max_user_id={max_user_id}, text='{text[:100]}'")
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению календарем.",
                parse_mode="HTML"
            )
            return
        
        # Check if it's a delete command
        if text.lower().startswith("удалить правило"):
            await handle_delete_rule_text(event, context, session, messenger_adapter)
            return
        
        # Check if it's a clear period command
        if text.lower().startswith("очистить"):
            await handle_clear_period_text(event, context, session, messenger_adapter)
            return
        
        # Otherwise, treat as add rule command
        await handle_add_rule_text(event, context, session, messenger_adapter)
        
    except Exception as e:
        logger.error(f"Error handling calendar text command: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при обработке команды.",
            parse_mode="HTML"
        )


async def handle_add_rule_text(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process text commands for adding schedule rules.
    Parses natural language input and creates rules.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    text = event.message.body.text
    
    try:
        from services.calendar_parser import CalendarCommandParser
        from services.calendar_formatter import CalendarFormatter
        from database.models import Calendar_Rule
        from datetime import datetime
        import pytz
        
        logger.info(f"Parsing add rule command: user={max_user_id}, text='{text}'")
        
        # Parse command
        parser = CalendarCommandParser()
        parsed_rule = parser.parse_add_rule_command(text)
        
        if not parsed_rule:
            # Parsing failed - display error with examples
            formatter = CalendarFormatter()
            examples_text = formatter.format_command_examples()
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "❌ Не удалось распознать команду.\n\n"
                    "Пожалуйста, используйте один из следующих форматов:\n\n"
                    f"{examples_text}"
                ),
                parse_mode="HTML"
            )
            logger.warning(f"Failed to parse add rule command: text='{text}'")
            return
        
        # Validate dates - prevent rules on past dates
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_date = datetime.now(moscow_tz).date()
        
        # Check if end_date is in the past
        if parsed_rule.end_date < current_date:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "❌ Нельзя создать правило на прошедшие даты.\n\n"
                    f"Конечная дата правила: {parsed_rule.end_date.strftime('%d.%m.%Y')}\n"
                    f"Сегодня: {current_date.strftime('%d.%m.%Y')}\n\n"
                    "Пожалуйста, укажите даты в будущем или включающие сегодняшний день."
                ),
                parse_mode="HTML"
            )
            logger.warning(
                f"Rejected rule with past end_date: end_date={parsed_rule.end_date}, "
                f"current_date={current_date}"
            )
            return
        
        # Store parsed rule data in FSM for confirmation
        await context.update_data(
            pending_rule={
                "start_date": parsed_rule.start_date.isoformat(),
                "end_date": parsed_rule.end_date.isoformat(),
                "work_mode": parsed_rule.work_mode.value,
                "work_start_time": parsed_rule.work_start_time.isoformat() if parsed_rule.work_start_time else None,
                "work_end_time": parsed_rule.work_end_time.isoformat() if parsed_rule.work_end_time else None,
                "original_text": text
            }
        )
        
        # Format confirmation message
        formatter = CalendarFormatter()
        
        # Create temporary rule object for formatting
        temp_rule = Calendar_Rule(
            start_date=parsed_rule.start_date,
            end_date=parsed_rule.end_date,
            work_mode=parsed_rule.work_mode,
            work_start_time=parsed_rule.work_start_time,
            work_end_time=parsed_rule.work_end_time,
            rule_priority=50,
            created_at=datetime.now()
        )
        
        preview_text = formatter.format_rule_preview(temp_rule)
        
        # Create confirmation keyboard
        from bots.max_bot.payloads import CalendarConfirmPayload
        
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="✅ Подтвердить",
                        payload=CalendarConfirmPayload(action="confirm_add").pack()
                    ),
                    KeyboardButton(
                        text="❌ Отменить",
                        payload=CalendarConfirmPayload(action="cancel_add").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"📝 <b>Ваша команда:</b>\n{text}\n\n"
                f"<b>Интерпретация системы:</b>\n{preview_text}\n\n"
                "Подтвердите добавление правила:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        # Set state to confirming
        from bots.max_bot.states import CalendarStates
        await context.set_state(CalendarStates.confirming_add_rule)
        
        logger.info(
            f"Showing confirmation for add rule: dates={parsed_rule.start_date} to "
            f"{parsed_rule.end_date}"
        )
        
    except Exception as e:
        logger.error(f"Error handling add rule text: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при обработке команды.\nПопробуйте позже.",
            parse_mode="HTML"
        )


async def handle_delete_rule_text(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process text commands for deleting schedule rules.
    Parses "Удалить правило [номер]" commands.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    text = event.message.body.text
    
    try:
        import re
        from services.calendar_service import CalendarService
        from services.calendar_formatter import CalendarFormatter
        
        logger.info(f"Parsing delete rule command: user={max_user_id}, text='{text}'")
        
        # Extract rule number from text
        match = re.search(r'удалить\s+правило\s+(\d+)', text.lower())
        if not match:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "❌ Не удалось распознать номер правила.\n\n"
                    "Используйте формат: <code>Удалить правило [номер]</code>\n"
                    "Например: <code>Удалить правило 2</code>"
                ),
                parse_mode="HTML"
            )
            return
        
        rule_number = int(match.group(1))
        
        # Get all rules to find the target rule
        calendar_service = CalendarService()
        all_rules = await calendar_service.get_all_rules(session)
        
        if not all_rules:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Нет активных правил для удаления.",
                parse_mode="HTML"
            )
            return
        
        # Check if rule number is valid
        if rule_number < 1 or rule_number > len(all_rules):
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    f"❌ Правило с номером {rule_number} не найдено.\n\n"
                    f"Всего правил: {len(all_rules)}\n"
                    "Используйте команду 📋 Список правил для просмотра."
                ),
                parse_mode="HTML"
            )
            return
        
        # Get target rule (rules are 1-indexed for users)
        target_rule = all_rules[rule_number - 1]
        
        # Store rule ID in FSM for confirmation
        await context.update_data(
            pending_delete_rule_id=target_rule.id,
            pending_delete_rule_number=rule_number
        )
        
        # Format confirmation message
        formatter = CalendarFormatter()
        rule_preview = formatter.format_rule_preview(target_rule)
        
        # Create confirmation keyboard
        from bots.max_bot.payloads import CalendarConfirmPayload
        
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="✅ Подтвердить удаление",
                        payload=CalendarConfirmPayload(action="confirm_delete").pack()
                    ),
                    KeyboardButton(
                        text="❌ Отменить",
                        payload=CalendarConfirmPayload(action="cancel_delete").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"🗑 <b>Удаление правила #{rule_number}</b>\n\n"
                f"{rule_preview}\n\n"
                "Подтвердите удаление правила:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        # Set state to confirming
        from bots.max_bot.states import CalendarStates
        await context.set_state(CalendarStates.confirming_delete_rule)
        
        logger.info(f"Showing confirmation for delete rule: rule_id={target_rule.id}")
        
    except Exception as e:
        logger.error(f"Error handling delete rule text: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при обработке команды.\nПопробуйте позже.",
            parse_mode="HTML"
        )


async def handle_clear_period_text(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process date range input for period clearing.
    Parses "с [дата] по [дата]" commands.
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    text = event.message.body.text
    
    try:
        from services.calendar_parser import CalendarCommandParser
        from services.calendar_service import CalendarService
        
        logger.info(f"Parsing clear period command: user={max_user_id}, text='{text}'")
        
        # Parse date range with CalendarCommandParser
        parser = CalendarCommandParser()
        date_range = parser.parse_date_range(text)
        
        if not date_range:
            # Parsing failed - display error and stay in state
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "❌ Не удалось распознать диапазон дат.\n\n"
                    "<b>Используйте формат:</b>\n"
                    "• с [день] [месяц] по [день] [месяц]\n"
                    "• с [день] по [день] [месяц]\n\n"
                    "<b>Примеры:</b>\n"
                    "• с 1 января по 31 января\n"
                    "• с 1 по 15 февраля\n\n"
                    "Попробуйте еще раз."
                ),
                parse_mode="HTML"
            )
            logger.warning(f"Failed to parse clear period command: text='{text}'")
            return
        
        start_date, end_date = date_range
        
        # Store date range in FSM data
        await context.update_data(
            clear_start_date=start_date.isoformat(),
            clear_end_date=end_date.isoformat()
        )
        
        # Get count of rules to be deleted
        calendar_service = CalendarService()
        rules_to_delete = await calendar_service.get_rules_for_date_range(
            session, start_date, end_date
        )
        count = len(rules_to_delete)
        
        # Format date range for display
        start_str = start_date.strftime("%d.%m.%Y")
        end_str = end_date.strftime("%d.%m.%Y")
        
        if count == 0:
            confirmation_text = (
                f"ℹ️ <b>Нет правил для удаления</b>\n\n"
                f"В периоде с {start_str} по {end_str} нет активных правил.\n\n"
                f"Нажмите Отмена для возврата в меню календаря."
            )
        else:
            # Format plural form for rules
            if count == 1:
                rules_word = "правило"
            elif 2 <= count <= 4:
                rules_word = "правила"
            else:
                rules_word = "правил"
            
            confirmation_text = (
                f"⚠️ <b>Подтверждение очистки периода</b>\n\n"
                f"Период: с {start_str} по {end_str}\n"
                f"Будет удалено: <b>{count} {rules_word}</b>\n\n"
                f"После удаления для этих дат будет использоваться базовое расписание.\n\n"
                f"Вы уверены, что хотите продолжить?"
            )
        
        # Create confirmation keyboard
        from bots.max_bot.payloads import CalendarClearPayload
        
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="✅ Подтвердить",
                        payload=CalendarClearPayload(action="confirm").pack()
                    ),
                    KeyboardButton(
                        text="❌ Отменить",
                        payload=CalendarClearPayload(action="cancel").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=confirmation_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Administrator {max_user_id} entered date range for clearing: "
            f"{start_date} to {end_date}, {count} rules to delete"
        )
        
    except Exception as e:
        logger.error(f"Error handling clear period input: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при обработке диапазона дат.\nПопробуйте позже.",
            parse_mode="HTML"
        )


# ============================================================================
# Confirmation Handlers
# ============================================================================


async def handle_calendar_confirmation(
    event: MessageCallback,
    payload: CalendarConfirmPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle confirmation callbacks for calendar operations.
    
    Supports:
    - confirm_add: Confirm adding a rule
    - cancel_add: Cancel adding a rule
    - confirm_delete: Confirm deleting a rule
    - cancel_delete: Cancel deleting a rule
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    action = payload.action
    
    logger.info(f"Calendar confirmation: max_user_id={max_user_id}, action={action}")
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению календарем.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Route to appropriate handler
        if action == "confirm_add":
            await handle_confirm_add_rule(event, context, session, messenger_adapter)
        
        elif action == "cancel_add":
            await handle_cancel_add_rule(event, context, session, messenger_adapter)
        
        elif action == "confirm_delete":
            await handle_confirm_delete_rule(event, context, session, messenger_adapter)
        
        elif action == "cancel_delete":
            await handle_cancel_delete_rule(event, context, session, messenger_adapter)
        
        else:
            logger.warning(f"Unknown confirmation action: {action}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестное действие.",
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"Error handling calendar confirmation: action={action}, error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


async def handle_confirm_add_rule(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Confirm and save the pending calendar rule."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    try:
        from datetime import date, time
        from database.models import WorkMode
        from services.calendar_service import CalendarService
        
        # Get pending rule data from FSM
        data = await context.get_data()
        pending_rule = data.get("pending_rule")
        
        if not pending_rule:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Данные правила не найдены. Пожалуйста, введите команду заново.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Parse stored data
        start_date = date.fromisoformat(pending_rule["start_date"])
        end_date = date.fromisoformat(pending_rule["end_date"])
        work_mode = WorkMode(pending_rule["work_mode"])
        work_start_time = time.fromisoformat(pending_rule["work_start_time"]) if pending_rule["work_start_time"] else None
        work_end_time = time.fromisoformat(pending_rule["work_end_time"]) if pending_rule["work_end_time"] else None
        
        # Create rule
        calendar_service = CalendarService()
        rule = await calendar_service.create_rule(
            session=session,
            start_date=start_date,
            end_date=end_date,
            work_mode=work_mode,
            work_start_time=work_start_time,
            work_end_time=work_end_time
        )
        
        # Return to calendar menu with success message
        from bots.max_bot.states import CalendarStates
        await context.set_state(CalendarStates.managing_calendar)
        
        # Format confirmation message
        formatter = CalendarFormatter()
        confirmation_text = formatter.format_rule_confirmation(rule)
        
        # Get calendar menu keyboard
        keyboard = get_calendar_main_keyboard()
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"✅ <b>Правило успешно добавлено!</b>\n\n{confirmation_text}\n\nВы можете продолжить управление календарем:",
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Rule added successfully: rule_id={rule.id}, user={max_user_id}")
        
    except Exception as e:
        logger.error(f"Error confirming add rule: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при добавлении правила.\nПопробуйте позже.",
            parse_mode="HTML"
        )


async def handle_cancel_add_rule(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Cancel adding a rule and return to calendar menu."""
    chat_id = event.message.recipient.chat_id
    
    try:
        # Return to calendar menu
        from bots.max_bot.states import CalendarStates
        await context.set_state(CalendarStates.managing_calendar)
        
        # Get calendar menu keyboard
        keyboard = get_calendar_main_keyboard()
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "❌ <b>Добавление правила отменено.</b>\n\n"
                "Вы можете продолжить управление календарем:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error canceling add rule: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_confirm_delete_rule(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Confirm and delete the pending calendar rule."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    try:
        from services.calendar_service import CalendarService
        
        # Get pending rule ID from FSM
        data = await context.get_data()
        rule_id = data.get("pending_delete_rule_id")
        rule_number = data.get("pending_delete_rule_number")
        
        if not rule_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Данные правила не найдены. Пожалуйста, введите команду заново.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Delete rule
        calendar_service = CalendarService()
        await calendar_service.delete_rule(session, rule_id)
        
        # Return to calendar menu with success message
        from bots.max_bot.states import CalendarStates
        await context.set_state(CalendarStates.managing_calendar)
        
        # Get calendar menu keyboard
        keyboard = get_calendar_main_keyboard()
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ <b>Правило #{rule_number} успешно удалено!</b>\n\n"
                "Вы можете продолжить управление календарем:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Rule deleted successfully: rule_id={rule_id}, user={max_user_id}")
        
    except Exception as e:
        logger.error(f"Error confirming delete rule: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при удалении правила.\nПопробуйте позже.",
            parse_mode="HTML"
        )


async def handle_cancel_delete_rule(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Cancel deleting a rule and return to calendar menu."""
    chat_id = event.message.recipient.chat_id
    
    try:
        # Return to calendar menu
        from bots.max_bot.states import CalendarStates
        await context.set_state(CalendarStates.managing_calendar)
        
        # Get calendar menu keyboard
        keyboard = get_calendar_main_keyboard()
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "❌ <b>Удаление правила отменено.</b>\n\n"
                "Вы можете продолжить управление календарем:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error canceling delete rule: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )



# ============================================================================
# Period Clearing Handlers
# ============================================================================


async def handle_clear_period_confirmation(
    event: MessageCallback,
    payload: CalendarClearPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle confirmation callbacks for period clearing.
    
    Supports:
    - confirm: Confirm clearing the period
    - cancel: Cancel clearing and return to menu
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    action = payload.action
    
    logger.info(f"Clear period confirmation: max_user_id={max_user_id}, action={action}")
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к управлению календарем.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Route to appropriate handler
        if action == "confirm":
            await handle_confirm_clear_period(event, context, session, messenger_adapter)
        
        elif action == "cancel":
            await handle_cancel_clear_period(event, context, session, messenger_adapter)
        
        else:
            logger.warning(f"Unknown clear period action: {action}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неизвестное действие.",
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"Error handling clear period confirmation: action={action}, error={e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка. Попробуйте позже.",
            parse_mode="HTML"
        )


async def handle_confirm_clear_period(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Execute period clearing after confirmation."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    try:
        from datetime import date
        from services.calendar_service import CalendarService
        from database.models import Action_Log, ActionType
        
        # Get date range from FSM data
        data = await context.get_data()
        start_date_str = data.get('clear_start_date')
        end_date_str = data.get('clear_end_date')
        
        if not start_date_str or not end_date_str:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка: диапазон дат не найден.\nПожалуйста, начните процесс заново.",
                parse_mode="HTML"
            )
            await context.clear()
            logger.error(f"Missing date range in FSM data for user {max_user_id}")
            return
        
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        
        # Delete rules in period with CalendarService
        calendar_service = CalendarService()
        deleted_count = await calendar_service.delete_rules_in_period(
            session, start_date, end_date
        )
        
        # Format date range for display
        start_str = start_date.strftime("%d.%m.%Y")
        end_str = end_date.strftime("%d.%m.%Y")
        
        # Display confirmation with count deleted
        if deleted_count == 0:
            confirmation_text = (
                f"ℹ️ <b>Период очищен</b>\n\n"
                f"В периоде с {start_str} по {end_str} не было активных правил.\n\n"
                f"Используйте меню календаря для управления расписанием."
            )
        else:
            # Format plural form for rules
            if deleted_count == 1:
                rules_word = "правило"
                deleted_word = "удалено"
            elif 2 <= deleted_count <= 4:
                rules_word = "правила"
                deleted_word = "удалено"
            else:
                rules_word = "правил"
                deleted_word = "удалено"
            
            confirmation_text = (
                f"✅ <b>Период успешно очищен!</b>\n\n"
                f"Период: с {start_str} по {end_str}\n"
                f"Удалено: <b>{deleted_count} {rules_word}</b>\n\n"
                f"Для этих дат теперь будет использоваться базовое расписание."
            )
        
        # Get back to calendar keyboard
        from bots.max_bot.states import CalendarStates
        await context.set_state(CalendarStates.managing_calendar)
        
        keyboard = get_calendar_main_keyboard()
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=confirmation_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        # Log period clearing with admin ID
        admin = await is_admin(session, max_user_id)
        if admin:
            action_log = Action_Log(
                action_type=ActionType.CALENDAR_PERIOD_CLEARED,
                staff_id=admin.id,
                action_details={
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "deleted_count": deleted_count
                }
            )
            session.add(action_log)
            await session.commit()
        
        logger.info(
            f"Administrator {max_user_id} cleared calendar period: "
            f"{start_date} to {end_date}, deleted {deleted_count} rules"
        )
        
    except Exception as e:
        logger.error(f"Error confirming clear period: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при очистке периода.\nПопробуйте позже.",
            parse_mode="HTML"
        )


async def handle_cancel_clear_period(
    event: MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Cancel period clearing and return to calendar menu."""
    chat_id = event.message.recipient.chat_id
    
    try:
        # Return to calendar menu
        from bots.max_bot.states import CalendarStates
        await context.set_state(CalendarStates.managing_calendar)
        
        # Get calendar menu keyboard
        keyboard = get_calendar_main_keyboard()
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "❌ <b>Очистка периода отменена.</b>\n\n"
                "Вы можете продолжить управление календарем:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error canceling clear period: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )
