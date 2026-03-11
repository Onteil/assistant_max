"""
Admin Panel - Analytics/Statistics Handlers for MAX Bot

Provides statistics dashboard with key metrics:
- Ticket statistics by type (invoice, technical support, renewal)
- SLA metrics (average response times by role)
- Stuck tickets identification
- NPS survey metrics

Supports period selection (today, week, month) and real-time refresh.

Migrated from Telegram bot to MAX messenger.
Uses replace_message pattern for all callback handlers.

Requirements: 17.1-17.9, 18.1-18.4
"""

import asyncio
import logging
from datetime import datetime

from maxapi.types import MessageCallback
from maxapi.context import MemoryContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import AdminMenuPayload, AnalyticsPayload
from database.models import Staff_Member, StaffRole
from services.analytics_service import (
    calculate_period_dates,
    get_dashboard_data,
)

logger = logging.getLogger(__name__)


# ========== Helper Functions ==========


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
        from sqlalchemy import select
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


def format_analytics_dashboard(
    period_name: str,
    dashboard_data: dict
) -> str:
    """
    Format dashboard data into display text.
    
    Args:
        period_name: Display name for period ("Сегодня", "Неделя", "Месяц")
        dashboard_data: Aggregated metrics from analytics_service
    
    Returns:
        Formatted HTML text for dashboard display
    
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.10
    """
    # Extract metrics from dashboard data
    ticket_stats = dashboard_data.get("ticket_stats", {})
    sla_metrics = dashboard_data.get("sla_metrics", {})
    stuck_tickets = dashboard_data.get("stuck_tickets", [])
    nps_metrics = dashboard_data.get("nps_metrics", {})
    
    # Check if all metrics are empty
    total_tickets = ticket_stats.get("total", 0)
    has_sla_data = any(
        sla_metrics.get(role) is not None
        for role in ["manager", "technical_support", "duty_engineer"]
    )
    has_stuck_tickets = len(stuck_tickets) > 0
    nps_responses = nps_metrics.get("response_count", 0)
    
    # If no data at all, return no data message
    if total_tickets == 0 and not has_sla_data and not has_stuck_tickets and nps_responses == 0:
        return (
            f"📊 <b>Статистика: {period_name}</b>\n\n"
            "📭 <b>Нет данных за выбранный период</b>\n\n"
            "Выберите другой период или дождитесь поступления заявок."
        )
    
    # Format SLA times
    def format_sla(minutes: float | None) -> str:
        if minutes is None:
            return "—"
        return f"{minutes:.2f} мин"
    
    manager_sla = format_sla(sla_metrics.get("manager"))
    support_sla = format_sla(sla_metrics.get("technical_support"))
    duty_sla = format_sla(sla_metrics.get("duty_engineer"))
    
    # Format stuck tickets list
    if not stuck_tickets:
        stuck_tickets_text = "Нет застрявших заявок ✅"
    else:
        # Limit to 10 tickets for display
        display_tickets = stuck_tickets[:10]
        stuck_lines = []
        
        for ticket in display_tickets:
            line = format_stuck_ticket_line(ticket)
            stuck_lines.append(line)
        
        stuck_tickets_text = "\n".join(stuck_lines)
        
        # Show overflow count if more than 10
        if len(stuck_tickets) > 10:
            overflow_count = len(stuck_tickets) - 10
            stuck_tickets_text += f"\n\n...и еще {overflow_count}"
    
    # Format NPS score
    nps_score = nps_metrics.get("average_score", 0.0)
    nps_score_text = f"{nps_score:.1f}" if nps_responses > 0 else "Нет данных"
    
    # Build formatted dashboard
    return (
        f"📊 <b>Статистика: {period_name}</b>\n\n"
        
        f"📋 <b>Заявки</b>\n"
        f"• Всего: {ticket_stats.get('total', 0)}\n"
        f"• Счета: {ticket_stats.get('invoice', 0)}\n"
        f"• Техподдержка: {ticket_stats.get('technical_support', 0)}\n"
        f"• Продления: {ticket_stats.get('renewal', 0)}\n\n"
        
        f"⏱ <b>Среднее время реакции</b>\n"
        f"• Менеджеры: {manager_sla}\n"
        f"• Техподдержка: {support_sla}\n"
        f"• Дежурная: {duty_sla}\n\n"
        
        f"⚠️ <b>Застрявшие заявки: {len(stuck_tickets)}</b>\n"
        f"{stuck_tickets_text}\n\n"
        
        f"📊 <b>NPS</b>\n"
        f"• Средний балл: {nps_score_text}\n"
        f"• Ответов: {nps_responses}"
    )


def format_stuck_ticket_line(ticket_data: dict) -> str:
    """
    Format a single stuck ticket for display.
    
    Args:
        ticket_data: Stuck ticket details from analytics_service
    
    Returns:
        Formatted line: "#{ticket_id} - {client_name} - {type} - {elapsed_time}"
    
    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
    """
    ticket_id = ticket_data.get("ticket_id")
    user_name = ticket_data.get("user_name", "Unknown")
    ticket_type = ticket_data.get("ticket_type", "unknown")
    elapsed_minutes = ticket_data.get("elapsed_minutes", 0)
    
    # Truncate client name to 20 characters
    if len(user_name) > 20:
        user_name = user_name[:20] + "..."
    
    # Translate ticket type to Russian
    type_translation = {
        "invoice": "Счет",
        "technical_support": "ТП",
        "renewal": "Продление"
    }
    type_text = type_translation.get(ticket_type, ticket_type)
    
    # Format elapsed time
    if elapsed_minutes < 60:
        elapsed_text = f"{elapsed_minutes} мин"
    else:
        hours = elapsed_minutes // 60
        minutes = elapsed_minutes % 60
        elapsed_text = f"{hours} ч {minutes} мин"
    
    # Build formatted line
    return f"#{ticket_id} - {user_name} - {type_text} - {elapsed_text}"


# ========== Analytics Dashboard Handlers ==========


async def handle_analytics_dashboard(
    event: MessageCallback,
    payload: AdminMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display statistics dashboard with default "today" period.
    
    Verifies admin authorization, calculates date range in Moscow timezone,
    executes analytics queries in parallel, formats dashboard, and sends message.
    
    Uses replace_message pattern.
    
    Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9, 18.1, 18.2, 18.3, 18.4
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator (Requirement 17.2)
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к административной панели.",
                parse_mode="HTML"
            )
            logger.warning(f"Non-admin user {max_user_id} attempted to access analytics")
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Calculate today's date range in Moscow timezone (Requirements 18.1, 18.4)
        # Default period is "today" (Requirement 17.6)
        start_date, end_date = calculate_period_dates("today")
        
        # Store current period in context for refresh functionality (Requirement 18.7)
        await context.update_data(analytics_period="today")
        
        # Execute analytics queries in parallel with asyncio.gather() (Requirement 17.5)
        dashboard_data = await get_dashboard_data(session, start_date, end_date)
        
        # Format dashboard using format_analytics_dashboard() (Requirement 17.6)
        formatted_text = format_analytics_dashboard("Сегодня", dashboard_data)
        
        # Build keyboard with period selection and refresh buttons
        buttons = [
            [
                KeyboardButton(
                    text="📅 Сегодня ✓",
                    payload=AnalyticsPayload(action="period", period="today").pack()
                ),
                KeyboardButton(
                    text="📅 Неделя",
                    payload=AnalyticsPayload(action="period", period="week").pack()
                ),
                KeyboardButton(
                    text="📅 Месяц",
                    payload=AnalyticsPayload(action="period", period="month").pack()
                )
            ],
            [
                KeyboardButton(
                    text="🔄 Обновить",
                    payload=AnalyticsPayload(action="refresh").pack()
                )
            ],
            [
                KeyboardButton(
                    text="◀️ Назад в главное меню",
                    payload=AdminMenuPayload(action="back").pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        # Send message with analytics keyboard (Requirement 17.7)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=formatted_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Administrator {max_user_id} ({admin.full_name}) accessed analytics dashboard: period=today"
        )
        
    except SQLAlchemyError as e:
        # Handle database errors gracefully (Requirement 17.8, 17.9)
        logger.error(
            f"Database error loading analytics: user={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Ошибка подключения к базе данных. Попробуйте позже.",
            parse_mode="HTML"
        )
    except asyncio.TimeoutError as e:
        # Handle query timeout (Requirement 17.8)
        logger.error(
            f"Timeout loading analytics: user={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Превышено время ожидания. Попробуйте позже.",
            parse_mode="HTML"
        )
    except Exception as e:
        # Handle all other errors gracefully (Requirement 17.8, 17.9)
        logger.error(
            f"Error showing analytics dashboard: user={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке статистики.",
            parse_mode="HTML"
        )


async def handle_analytics_period_selection(
    event: MessageCallback,
    payload: AnalyticsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle period selection button press.
    
    Recalculates statistics for selected period and updates dashboard.
    Uses replace_message pattern.
    
    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
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
        
        # Extract period from callback data
        period = payload.period
        
        # Validate period
        if period not in ["today", "week", "month"]:
            logger.error(f"Invalid period selected: {period}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Неверный период.",
                parse_mode="HTML"
            )
            return
        
        # Calculate date range for selected period
        start_date, end_date = calculate_period_dates(period)
        
        # Store current period in context for refresh functionality
        await context.update_data(analytics_period=period)
        
        # Fetch dashboard data
        dashboard_data = await get_dashboard_data(session, start_date, end_date)
        
        # Map period to display name
        period_display = {
            "today": "Сегодня",
            "week": "Неделя",
            "month": "Месяц"
        }
        
        # Format dashboard
        formatted_text = format_analytics_dashboard(
            period_display[period],
            dashboard_data
        )
        
        # Build keyboard with selected period highlighted
        buttons = [
            [
                KeyboardButton(
                    text="📅 Сегодня" + (" ✓" if period == "today" else ""),
                    payload=AnalyticsPayload(action="period", period="today").pack()
                ),
                KeyboardButton(
                    text="📅 Неделя" + (" ✓" if period == "week" else ""),
                    payload=AnalyticsPayload(action="period", period="week").pack()
                ),
                KeyboardButton(
                    text="📅 Месяц" + (" ✓" if period == "month" else ""),
                    payload=AnalyticsPayload(action="period", period="month").pack()
                )
            ],
            [
                KeyboardButton(
                    text="🔄 Обновить",
                    payload=AnalyticsPayload(action="refresh").pack()
                )
            ],
            [
                KeyboardButton(
                    text="◀️ Назад в главное меню",
                    payload=AdminMenuPayload(action="back").pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        # Send updated message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=formatted_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Administrator {max_user_id} changed analytics period: period={period}"
        )
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error changing analytics period: user={max_user_id}, "
            f"period={payload.period}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Ошибка подключения к базе данных. Попробуйте позже.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(
            f"Error changing analytics period: user={max_user_id}, "
            f"period={payload.period}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке статистики.",
            parse_mode="HTML"
        )


async def handle_analytics_refresh(
    event: MessageCallback,
    payload: AnalyticsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle refresh button press.
    
    Reloads statistics for currently selected period.
    Uses replace_message pattern.
    
    Requirements: 10.4
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
        
        # Retrieve current period from context (default to "today")
        data = await context.get_data()
        period = data.get("analytics_period", "today")
        
        # Calculate date range for current period
        start_date, end_date = calculate_period_dates(period)
        
        # Fetch dashboard data
        dashboard_data = await get_dashboard_data(session, start_date, end_date)
        
        # Map period to display name
        period_display = {
            "today": "Сегодня",
            "week": "Неделя",
            "month": "Месяц"
        }
        
        # Format dashboard
        formatted_text = format_analytics_dashboard(
            period_display[period],
            dashboard_data
        )
        
        # Build keyboard with current period highlighted
        buttons = [
            [
                KeyboardButton(
                    text="📅 Сегодня" + (" ✓" if period == "today" else ""),
                    payload=AnalyticsPayload(action="period", period="today").pack()
                ),
                KeyboardButton(
                    text="📅 Неделя" + (" ✓" if period == "week" else ""),
                    payload=AnalyticsPayload(action="period", period="week").pack()
                ),
                KeyboardButton(
                    text="📅 Месяц" + (" ✓" if period == "month" else ""),
                    payload=AnalyticsPayload(action="period", period="month").pack()
                )
            ],
            [
                KeyboardButton(
                    text="🔄 Обновить",
                    payload=AnalyticsPayload(action="refresh").pack()
                )
            ],
            [
                KeyboardButton(
                    text="◀️ Назад в главное меню",
                    payload=AdminMenuPayload(action="back").pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        # Send updated message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=formatted_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Administrator {max_user_id} refreshed analytics: period={period}"
        )
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error refreshing analytics: user={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Ошибка подключения к базе данных. Попробуйте позже.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(
            f"Error refreshing analytics: user={max_user_id}, error={e}",
            exc_info=True
        )
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при обновлении статистики.",
            parse_mode="HTML"
        )
