"""
Admin Panel - Employee Management Handlers

Handles administrative functions for employee management:
- Admin panel entry point and main menu
- Employee CRUD operations (add, list, view, edit, deactivate)
- Backup manager configuration
- Ticket and client transfers

Requirements: 1.1, 1.2, 1.3, 2.x, 3.x, 4.x, 5.x, 6.x, 7.x, 8.x
"""

import asyncio
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import (
    AdminMenuCallback,
    AnalyticsCallback,
    BackupManagerCallback,
    EmployeeCallback,
    EmployeeRoleCallback,
)
from bots.tg_bot.keyboards.admin_kb import get_admin_panel_keyboard, get_cancel_keyboard
from bots.tg_bot.texts import BTN_ADMIN_PANEL
from bots.tg_bot.states import AdminStates
from database.models import Staff_Member, StaffRole
from services.analytics_service import get_dashboard_data, calculate_period_dates

logger = logging.getLogger(__name__)

router = Router(name="admin_employee_management")

# Include calendar router inside admin router for proper routing
from .calendar import router as calendar_router
from .key_conflicts import router as key_conflicts_router

router.include_router(key_conflicts_router)
router.include_router(calendar_router)

# Include settings routers
from .settings import router as settings_router
from .settings_timeout import router as settings_timeout_router
from .settings_escalation import router as settings_escalation_router
from .settings_duty import router as settings_duty_router
from .settings_nps import router as settings_nps_router
from .settings_renewal import router as settings_renewal_router
from .settings_utility import router as settings_utility_router

router.include_router(settings_router)
router.include_router(settings_timeout_router)
router.include_router(settings_escalation_router)
router.include_router(settings_duty_router)
router.include_router(settings_nps_router)
router.include_router(settings_renewal_router)
router.include_router(settings_utility_router)


# ========== Helper Functions ==========


async def is_admin(session: AsyncSession, user_id: int) -> Staff_Member | None:
    """
    Check if user is an administrator and return their record.
    
    Args:
        session: Database session
        user_id: Telegram user ID
    
    Returns:
        Staff_Member object if user is admin, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == user_id,
            Staff_Member.is_active == True,
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}", exc_info=True)
        return None


# ========== Admin Panel Entry Point ==========


@router.message(F.text == BTN_ADMIN_PANEL)
async def handle_admin_panel_button(
    message: Message,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Admin Panel" reply button press.
    
    Entry point to the administrative panel. Displays main menu with navigation
    to all admin sections: employees, operations, calendar, settings, analytics.
    
    Requirements: 1.1, 1.2, 1.3
    """
    
    try:
        user_id = message.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await message.answer(
                "❌ У вас нет доступа к административной панели.\n"
                "Эта функция доступна только администраторам."
            )
            logger.warning(f"Non-admin user {user_id} attempted to access admin panel")
            return
        
        # Clear any existing FSM state to start fresh
        await state.clear()
        
        # Get admin panel main menu keyboard
        keyboard = await get_admin_panel_keyboard()
        
        # Send admin panel main menu
        admin_panel_text = (
            "🔐 Административная панель\n\n"
            "Выберите раздел для управления:\n\n"
            "👥 Сотрудники - управление персоналом\n"
            "📋 Операции - регистрации, рассылки, конфликты\n"
            "📅 График работы - настройка расписания\n"
            "⚙️ Настройки - системные параметры\n"
            "📊 Статистика - аналитика и отчеты"
        )
        
        await message.answer(
            admin_panel_text,
            reply_markup=keyboard
        )
        
        logger.info(f"Administrator {user_id} ({admin.full_name}) accessed admin panel")
        
    except SQLAlchemyError as e:
        logger.error(f"Database error showing admin panel for user {message.from_user.id}: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при загрузке административной панели. Попробуйте позже."
        )
    except Exception as e:
        logger.error(f"Error showing admin panel for user {message.from_user.id}: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при загрузке административной панели. Попробуйте позже."
        )


# ========== Admin Panel Main Menu Navigation ==========


@router.callback_query(AdminMenuCallback.filter(F.action == "employees"))
async def handle_employees_menu(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Employees" menu button in admin panel.
    
    Shows employee management submenu with options to add or list employees.
    Also serves as the "back" button to cancel ongoing employee operations.
    
    Requirements: 1.3, 2.1
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Clear any existing FSM state (cancels ongoing operations like add employee)
        await state.clear()
        
        # Build employee management menu keyboard
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from bots.tg_bot.callback_datas import EmployeeCallback
        
        builder = InlineKeyboardBuilder()
        
        builder.button(
            text="➕ Добавить сотрудника",
            callback_data=EmployeeCallback(action="add")
        )
        
        builder.button(
            text="📋 Список сотрудников",
            callback_data=EmployeeCallback(action="list")
        )
        
        builder.button(
            text="🔙 Назад",
            callback_data=AdminMenuCallback(action="back_to_main")
        )
        
        builder.adjust(1)
        
        await callback.message.edit_text(
            "👥 Управление сотрудниками\n\n"
            "В этом разделе вы можете:\n"
            "• Просматривать список всех сотрудников\n"
            "• Добавлять новых сотрудников в систему\n"
            "• Редактировать данные и роли сотрудников\n"
            "• Удалять сотрудников из системы\n\n"
            "Выберите действие:",
            reply_markup=builder.as_markup()
        )
        
        logger.info(f"Administrator {user_id} accessed employees menu")
        
    except SQLAlchemyError as e:
        logger.error(f"Database error showing employees menu: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке меню.",
            show_alert=True
        )
    except Exception as e:
        logger.error(f"Error showing employees menu: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке меню.",
            show_alert=True
        )


@router.callback_query(AdminMenuCallback.filter(F.action == "operations"))
async def handle_operations_menu(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Handle "Operations" menu button in admin panel.
    
    Shows operations submenu with broadcast, registrations, key conflicts, and escalations.
    
    Requirements: 1.3, 10.1, 24.3, 24.6
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Import callback data classes for operations menu
        from bots.tg_bot.callback_datas import (
            BroadcastCallback,
            RegistrationCallback,
            KeyConflictCallback
        )
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        # Build operations menu keyboard
        builder = InlineKeyboardBuilder()
        
        # Registrations button (first in order per requirements)
        # builder.button(
        #     text="📋 Регистрации",
        #     callback_data=RegistrationCallback(action="list", page=0)
        # )
        
        # Key conflicts button (second in order)
        builder.button(
            text="🔑 Конфликты ключей",
            callback_data=KeyConflictCallback(action="list", page=0)
        )
        
        # Broadcast button (third in order)
        builder.button(
            text="📢 Рассылка",
            callback_data=BroadcastCallback(action="create")
        )
        
        # Escalations button (fourth in order)
        builder.button(
            text="⚠️ Эскалации",
            callback_data=AdminMenuCallback(action="escalations")
        )
        
        # Back button
        builder.button(
            text="🔙 Назад в главное меню",
            callback_data=AdminMenuCallback(action="back_to_main")
        )
        
        # Layout: 1 button per row
        builder.adjust(1)
        
        operations_text = (
            "📋 <b>Операции</b>\n\n"
            "Раздел для управления операционными процессами и мониторинга системы.\n\n"
            "<b>Доступные функции:</b>\n\n"
            "📋 <b>Регистрации</b>\n"
            "Просмотр и одобрение новых регистраций пользователей в системе. "
            "Подтверждение, отклонение или отметка на проверку.\n\n"
            "🔑 <b>Конфликты ключей</b>\n"
            "Разрешение конфликтов при дублировании ключей GS_Key между пользователями. "
            "Передача ключа новому владельцу или отклонение претензии.\n\n"
            "📢 <b>Рассылка</b>\n"
            "Создание и отправка массовых уведомлений пользователям. "
            "Выбор целевой аудитории, предпросмотр и отправка сообщений.\n\n"
            "⚠️ <b>Эскалации</b>\n"
            "Мониторинг и управление эскалированными заявками. "
            "Просмотр заявок, требующих внимания администратора, переназначение и контроль."
        )
        
        await callback.message.edit_text(
            operations_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} accessed operations menu")
        
    except Exception as e:
        logger.error(f"Error showing operations menu: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке меню.",
            show_alert=True
        )


@router.callback_query(AdminMenuCallback.filter(F.action == "calendar"))
async def handle_calendar_menu(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Calendar" menu button in admin panel.
    
    Shows calendar management menu with current status and action buttons.
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        logger.info(f"[ADMIN_PANEL ROUTER] handle_calendar_menu called by user {user_id}")
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Set FSM state to managing_calendar
        from bots.tg_bot.states import CalendarStates
        await state.set_state(CalendarStates.managing_calendar)
        logger.info(f"[ADMIN_PANEL ROUTER] Set state to CalendarStates.managing_calendar for user {user_id}")
        
        # Import calendar services
        from services.calendar_service import CalendarService
        from services.calendar_formatter import CalendarFormatter
        from bots.tg_bot.keyboards.calendar_kb import get_calendar_main_keyboard
        from datetime import datetime
        import pytz
        
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
        
        # Display calendar menu
        await callback.message.edit_text(
            menu_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} accessed calendar menu")
        
    except Exception as e:
        logger.error(f"Error showing calendar menu: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке календаря.",
            show_alert=True
        )
        await callback.answer(
            "❌ Произошла ошибка при загрузке меню.",
            show_alert=True
        )


@router.callback_query(AdminMenuCallback.filter(F.action == "settings"))
async def handle_settings_menu(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Handle "Settings" menu button in admin panel.
    
    Redirects to the settings menu handler.
    
    Requirements: 1.3
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Import here to avoid circular imports
        from services.settings_service import verify_admin_access
        from bots.tg_bot.keyboards.admin_kb import get_settings_menu_keyboard
        
        # Verify user is administrator
        if not await verify_admin_access(session, user_id):
            await callback.answer(
                "❌ У вас нет доступа к настройкам системы.",
                show_alert=True
            )
            return
        
        # Get settings menu keyboard
        keyboard = await get_settings_menu_keyboard()
        
        # Display settings menu
        settings_text = (
            "⚙️ <b>Настройки системы</b>\n\n"
            "Выберите категорию для настройки:\n\n"
            "⏱ <b>Таймауты</b> - время ожидания ответа и эскалации\n"
            "📢 <b>Эскалация</b> - каналы уведомлений об эскалации\n"
            "🌙 <b>Дежурная поддержка</b> - аккаунт для внерабочих часов\n"
            "📊 <b>NPS настройки</b> - частота и триггеры опросов\n"
            "🔔 <b>Напоминания</b> - расписание напоминаний о продлении\n"
            # "👥 <b>Резервы менеджеров</b> - просмотр назначений резервов\n"
            "📜 <b>История</b> - журнал изменений настроек"
        )
        
        await callback.message.edit_text(
            text=settings_text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error displaying settings menu: {e}", exc_info=True)
        await callback.answer(
            "❌ Ошибка при отображении настроек",
            show_alert=True
        )


@router.callback_query(AdminMenuCallback.filter(F.action == "analytics"))
async def handle_analytics_dashboard(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Analytics" menu button in admin panel.
    
    Displays statistics dashboard with default "today" period.
    Verifies admin authorization, calculates date range in Moscow timezone,
    executes analytics queries in parallel, formats dashboard, and sends message.
    
    Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9, 18.1, 18.2, 18.3, 18.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator (Requirement 17.2)
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            logger.warning(f"Non-admin user {user_id} attempted to access analytics")
            return
        
        # Import analytics keyboard
        from bots.tg_bot.keyboards.admin_kb import get_analytics_dashboard_keyboard
        
        # Calculate today's date range in Moscow timezone (Requirements 18.1, 18.4)
        # Default period is "today" (Requirement 17.6)
        start_date, end_date = calculate_period_dates("today")
        
        # Store current period in FSM state for refresh functionality (Requirement 18.7)
        await state.update_data(analytics_period="today")
        
        # Execute analytics queries in parallel with asyncio.gather() (Requirement 17.5)
        dashboard_data = await get_dashboard_data(session, start_date, end_date)
        
        # Format dashboard using format_analytics_dashboard() (Requirement 17.6)
        formatted_text = format_analytics_dashboard("Сегодня", dashboard_data)
        
        # Get keyboard with "today" selected (Requirement 17.5)
        keyboard = await get_analytics_dashboard_keyboard(selected_period="today")
        
        # Send message with analytics keyboard (Requirement 17.7)
        await callback.message.edit_text(
            formatted_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Administrator {user_id} ({admin.full_name}) accessed analytics dashboard: period=today"
        )
        
    except SQLAlchemyError as e:
        # Handle database errors gracefully (Requirement 17.8, 17.9)
        logger.error(
            f"Database error loading analytics: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Ошибка подключения к базе данных. Попробуйте позже.",
            show_alert=True
        )
    except asyncio.TimeoutError as e:
        # Handle query timeout (Requirement 17.8)
        logger.error(
            f"Timeout loading analytics: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Превышено время ожидания. Попробуйте позже.",
            show_alert=True
        )
    except Exception as e:
        # Handle all other errors gracefully (Requirement 17.8, 17.9)
        logger.error(
            f"Error showing analytics dashboard: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Произошла ошибка при загрузке статистики.",
            show_alert=True
        )


@router.callback_query(AnalyticsCallback.filter(F.action == "period"))
async def handle_analytics_period_selection(
    callback: CallbackQuery,
    callback_data: AnalyticsCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle period selection button press.
    
    Recalculates statistics for selected period and updates dashboard.
    
    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Import analytics keyboard
        from bots.tg_bot.keyboards.admin_kb import get_analytics_dashboard_keyboard
        
        # Extract period from callback data
        period = callback_data.period
        
        # Validate period
        if period not in ["today", "week", "month"]:
            logger.error(f"Invalid period selected: {period}")
            await callback.answer("❌ Неверный период.", show_alert=True)
            return
        
        # Calculate date range for selected period
        start_date, end_date = calculate_period_dates(period)
        
        # Store current period in FSM state for refresh functionality
        await state.update_data(analytics_period=period)
        
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
        
        # Get keyboard with selected period highlighted
        keyboard = await get_analytics_dashboard_keyboard(selected_period=period)
        
        # Update message
        await callback.message.edit_text(
            formatted_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Administrator {user_id} changed analytics period: period={period}"
        )
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error changing analytics period: user={callback.from_user.id}, "
            f"period={callback_data.period}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Ошибка подключения к базе данных. Попробуйте позже.",
            show_alert=True
        )
    except Exception as e:
        logger.error(
            f"Error changing analytics period: user={callback.from_user.id}, "
            f"period={callback_data.period}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Произошла ошибка при загрузке статистики.",
            show_alert=True
        )


@router.callback_query(AnalyticsCallback.filter(F.action == "refresh"))
async def handle_analytics_refresh(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle refresh button press.
    
    Reloads statistics for currently selected period.
    
    Requirements: 10.4
    """
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Import analytics keyboard
        from bots.tg_bot.keyboards.admin_kb import get_analytics_dashboard_keyboard
        
        # Retrieve current period from FSM state (default to "today")
        data = await state.get_data()
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
        
        # Get keyboard with current period highlighted
        keyboard = await get_analytics_dashboard_keyboard(selected_period=period)
        
        # Update message
        await callback.message.edit_text(
            formatted_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        # Show brief confirmation
        await callback.answer("Обновлено ✅")
        
        logger.info(
            f"Administrator {user_id} refreshed analytics: period={period}"
        )
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error refreshing analytics: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Ошибка подключения к базе данных. Попробуйте позже.",
            show_alert=True
        )
    except Exception as e:
        logger.error(
            f"Error refreshing analytics: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Произошла ошибка при обновлении статистики.",
            show_alert=True
        )


# ========== Analytics Formatter Functions ==========


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
    from bots.tg_bot.texts import ADMIN_ANALYTICS_DASHBOARD, ADMIN_ANALYTICS_NO_DATA
    
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
        return ADMIN_ANALYTICS_NO_DATA.format(period=period_name)
    
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
    return ADMIN_ANALYTICS_DASHBOARD.format(
        period=period_name,
        total_count=ticket_stats.get("total", 0),
        invoice_count=ticket_stats.get("invoice", 0),
        technical_support_count=ticket_stats.get("technical_support", 0),
        renewal_count=ticket_stats.get("renewal", 0),
        manager_avg_minutes=manager_sla,
        technical_support_avg_minutes=support_sla,
        duty_engineer_avg_minutes=duty_sla,
        stuck_count=len(stuck_tickets),
        stuck_tickets_list=stuck_tickets_text,
        nps_average_score=nps_score_text,
        nps_response_count=nps_responses
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


# ========== Add Employee Flow ==========


@router.callback_query(EmployeeCallback.filter(F.action == "add"))
async def handle_add_employee_start(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Add Employee" button press.
    
    Prompts administrator to provide Telegram ID or forward a message.
    
    Requirements: 2.1
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Set FSM state to wait for employee ID
        from bots.tg_bot.states import AdminStates
        await state.set_state(AdminStates.adding_employee_id)
        
        # Get cancel keyboard
        from bots.tg_bot.keyboards.admin_kb import get_cancel_keyboard
        keyboard = await get_cancel_keyboard(action="employees")
        
        # Prompt for Telegram ID or forwarded message
        await callback.message.edit_text(
            "➕ <b>Добавление сотрудника</b>\n\n"
            "Отправьте Telegram ID нового сотрудника или перешлите любое сообщение от него.\n\n"
            "<b>Пример ID:</b> 123456789\n\n"
            "💡 <i>Как узнать Telegram ID:</i>\n"
            "• Используйте бота @userinfobot\n"
            "• Перешлите боту любое сообщение пользователя\n"
            "• Бот покажет его Telegram ID",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} started add employee flow")
        
    except SQLAlchemyError as e:
        logger.error(f"Database error starting add employee flow: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке формы.",
            show_alert=True
        )
    except Exception as e:
        logger.error(f"Error starting add employee flow: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка.",
            show_alert=True
        )


@router.message(AdminStates.adding_employee_id)
async def handle_employee_id_forwarded(
    message: Message,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle forwarded message to extract Telegram ID or text input.
    
    Extracts the sender's ID from the forwarded message or parses text as ID.
    
    Requirements: 2.2, 2.3, 2.4
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await message.answer("❌ У вас нет доступа к административной панели.")
            await state.clear()
            return
        
        tg_user_id = None
        user_info = None
        
        # Check if this is a forwarded message
        if message.forward_origin:
            # Handle different forward origin types
            if message.forward_origin.type == "user":
                # Direct forward from user
                tg_user_id = message.forward_origin.sender_user.id
                user_info = f"{message.forward_origin.sender_user.first_name}"
                if message.forward_origin.sender_user.last_name:
                    user_info += f" {message.forward_origin.sender_user.last_name}"
                if message.forward_origin.sender_user.username:
                    user_info += f" (@{message.forward_origin.sender_user.username})"
            elif message.forward_origin.type == "hidden_user":
                # User has privacy settings enabled
                from bots.tg_bot.keyboards.admin_kb import get_cancel_keyboard
                await message.answer(
                    "⚠️ Не удалось получить Telegram ID из пересланного сообщения.\n\n"
                    "Данный пользователь не взаимодействовал с ботом или скрыл свой профиль в настройках приватности.\n"
                    "Попросите пользователя написать боту команду /start, после чего отправить вам его ID или используйте бота @userinfobot.",
                    reply_markup=await get_cancel_keyboard(action="employees")
                )
                return
            elif message.forward_origin.type in ["channel", "chat"]:
                await message.answer(
                    "❌ Пересланное сообщение из канала или чата.\n\n"
                    "Перешлите сообщение от конкретного пользователя.",
                    reply_markup=await get_cancel_keyboard(action="employees")
                )
                return
        elif message.text:
            # Try to parse as text ID
            try:
                tg_user_id = int(message.text.strip())
            except ValueError:
                from bots.tg_bot.keyboards.admin_kb import get_cancel_keyboard
                keyboard = await get_cancel_keyboard(action="employees")
                
                await message.answer(
                    "❌ Неверный формат Telegram ID. ID должен быть числом.",
                    reply_markup=keyboard
                )
                return
        else:
            await message.answer(
                "❌ Отправьте Telegram ID числом или перешлите сообщение от пользователя.",
                reply_markup=await get_cancel_keyboard(action="employees")
            )
            return
        
        # Check if already registered
        existing_stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == tg_user_id,
            Staff_Member.is_active == True
        )
        existing_result = await session.execute(existing_stmt)
        existing_staff = existing_result.scalar_one_or_none()
        
        if existing_staff:
            from bots.tg_bot.keyboards.admin_kb import get_cancel_keyboard
            keyboard = await get_cancel_keyboard(action="employees")
            
            await message.answer(
                f"❌ Этот пользователь уже зарегистрирован как сотрудник.\n\n"
                f"ID: {existing_staff.id}\n"
                f"Имя: {existing_staff.full_name}\n"
                f"Роль: {existing_staff.staff_role.value}",
                reply_markup=keyboard
            )
            return
        
        # Store the Telegram ID in FSM data
        await state.update_data(tg_user_id=tg_user_id)
        
        # Move to role selection
        await state.set_state(AdminStates.adding_employee_role)
        
        # Show role selection keyboard
        from bots.tg_bot.keyboards.admin_kb import get_role_selection_keyboard
        keyboard = await get_role_selection_keyboard()
        
        # Build response message
        response_text = f"✅ Telegram ID: {tg_user_id}\n"
        if user_info:
            response_text = f"✅ Пользователь: {user_info}\n" + response_text
        response_text += "\nВыберите роль для нового сотрудника:"
        
        await message.answer(
            response_text,
            reply_markup=keyboard
        )
        
        logger.info(f"Administrator {user_id} provided employee ID: {tg_user_id}")
        
    except SQLAlchemyError as e:
        logger.error(f"Database error handling employee ID: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при проверке пользователя в базе данных.")
        await state.clear()
    except Exception as e:
        logger.error(f"Error handling employee ID: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обработке данных.")
        await state.clear()


@router.callback_query(EmployeeRoleCallback.filter(), AdminStates.adding_employee_role)
async def handle_role_selection(
    callback: CallbackQuery,
    callback_data: EmployeeRoleCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle role selection for new employee.
    
    Stores the role and prompts for signature text.
    
    Requirements: 2.5, 2.6
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            await state.clear()
            return
        
        # Map role string to StaffRole enum
        role_map = {
            "manager": StaffRole.MANAGER,
            "technical_support": StaffRole.TECHNICAL_SUPPORT,
            "duty_engineer": StaffRole.DUTY_ENGINEER,
            "administrator": StaffRole.ADMINISTRATOR
        }
        
        staff_role = role_map.get(callback_data.role)
        if not staff_role:
            await callback.answer("❌ Неверная роль.", show_alert=True)
            return
        
        # Store role in FSM data
        await state.update_data(staff_role=staff_role)
        
        # Move to signature input
        await state.set_state(AdminStates.adding_employee_signature)
        
        # Role display names
        role_display = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        # Get cancel keyboard
        from bots.tg_bot.keyboards.admin_kb import get_cancel_keyboard
        
        await callback.message.edit_text(
            f"✅ Роль: {role_display[staff_role]}\n\n"
            "Теперь введите подпись сотрудника.\n\n"
            "Подпись будет использоваться в сообщениях клиентам.\n"
            "Например: \"Иван Петров, менеджер отдела продаж\"",
            reply_markup=await get_cancel_keyboard(action="employees")
        )
        
        logger.info(f"Administrator {user_id} selected role: {staff_role.value}")
        
    except SQLAlchemyError as e:
        logger.error(f"Database error handling role selection: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при сохранении роли.", show_alert=True)
        await state.clear()
    except Exception as e:
        logger.error(f"Error handling role selection: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка.", show_alert=True)
        await state.clear()


@router.message(F.text, AdminStates.adding_employee_signature)
async def handle_signature_input(
    message: Message,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle signature text input for new employee.
    
    Creates the staff member record and sends notifications.
    
    Requirements: 2.6, 2.7, 2.8, 2.9
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await message.answer("❌ У вас нет доступа к административной панели.")
            await state.clear()
            return
        
        # Get signature text
        signature = message.text.strip()
        
        if len(signature) < 3:
            # Get cancel keyboard
            from bots.tg_bot.keyboards.admin_kb import get_cancel_keyboard
            keyboard = await get_cancel_keyboard(action="employees")
            
            await message.answer(
                "❌ Подпись слишком короткая. Минимум 3 символа.",
                reply_markup=keyboard
            )
            return
        
        if len(signature) > 128:
            # Get cancel keyboard
            from bots.tg_bot.keyboards.admin_kb import get_cancel_keyboard
            keyboard = await get_cancel_keyboard(action="employees")
            
            await message.answer(
                "❌ Подпись слишком длинная. Максимум 128 символов.",
                reply_markup=keyboard
            )
            return
        
        # Get data from FSM
        data = await state.get_data()
        tg_user_id = data.get("tg_user_id")
        staff_role = data.get("staff_role")
        
        if not tg_user_id or not staff_role:
            await message.answer("❌ Ошибка: данные не найдены. Начните заново.")
            await state.clear()
            return
        
        # Extract full name from signature (first part before comma)
        # If no comma, use the whole signature
        if "," in signature:
            full_name = signature.split(",")[0].strip()
        else:
            full_name = signature
        
        # Create staff member
        from services.employee_service import create_staff_member
        
        try:
            new_staff = await create_staff_member(
                session=session,
                tg_user_id=tg_user_id,
                full_name=full_name,
                position=signature,
                staff_role=staff_role
            )
            
            await session.commit()
            
            # Role display names
            role_display = {
                StaffRole.MANAGER: "Менеджер",
                StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
                StaffRole.DUTY_ENGINEER: "Дежурный инженер",
                StaffRole.ADMINISTRATOR: "Администратор"
            }
            
            # Send confirmation to administrator
            await message.answer(
                f"✅ Сотрудник успешно добавлен!\n\n"
                f"ID: {new_staff.id}\n"
                f"Telegram ID: {tg_user_id}\n"
                f"Имя: {full_name}\n"
                f"Роль: {role_display[staff_role]}\n"
                f"Подпись: {signature}"
            )
            
            # Send notification to new employee
            try:
                from aiogram import Bot
                bot = message.bot
                
                await bot.send_message(
                    chat_id=tg_user_id,
                    text=(
                        f"🎉 Поздравляем!\n\n"
                        f"Вам предоставлен доступ к системе в качестве сотрудника.\n\n"
                        f"Роль: {role_display[staff_role]}\n"
                        f"Подпись: {signature}\n\n"
                        f"Используйте команду /manager для начала работы."
                    )
                )
                
                logger.info(f"Sent notification to new employee: {tg_user_id}")
                
            except Exception as notify_error:
                logger.warning(
                    f"Failed to send notification to new employee {tg_user_id}: {notify_error}"
                )
                await message.answer(
                    "⚠️ Не удалось отправить уведомление новому сотруднику. "
                    "Возможно, он еще не начал диалог с ботом."
                )
            
            # Log action
            from database.models import Action_Log, ActionType
            action_log = Action_Log(
                action_type=ActionType.STAFF_ADDED,
                staff_id=admin.id,
                action_details={
                    "new_staff_id": new_staff.id,
                    "tg_user_id": tg_user_id,
                    "full_name": full_name,
                    "role": staff_role.value,
                    "signature": signature
                }
            )
            session.add(action_log)
            await session.commit()
            
            logger.info(
                f"Administrator {user_id} added new staff member: "
                f"id={new_staff.id}, tg_user_id={tg_user_id}, role={staff_role.value}"
            )
            
        except ValueError as ve:
            # Duplicate staff member or validation error
            await message.answer(f"❌ {str(ve)}")
            logger.warning(f"Staff member creation validation error: {ve}")
        
        # Clear FSM state
        await state.clear()
        
    except SQLAlchemyError as e:
        logger.error(f"Database error handling signature input: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при создании сотрудника в базе данных.")
        await state.clear()
    except Exception as e:
        logger.error(f"Error handling signature input: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при создании сотрудника.")
        await state.clear()


# ========== Employee List and View ==========


@router.callback_query(EmployeeCallback.filter(F.action == "list"))
async def handle_employee_list(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Employees List" button press.
    
    Displays paginated list of all active staff members except current user.
    Current user is excluded to prevent self-modification.
    
    Requirements: 3.1, 3.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Clear any FSM state
        await state.clear()
        
        # Get page number from callback data
        page = callback_data.page if callback_data.page is not None else 0
        
        # Fetch all staff members except current user (including deactivated)
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id != user_id  # Exclude current user
        ).order_by(Staff_Member.full_name)
        
        result = await session.execute(stmt)
        employees = result.scalars().all()
        
        if not employees:
            await callback.message.edit_text(
                "📋 <b>Список сотрудников</b>\n\n"
                "Список сотрудников пуст.\n\n"
                "Добавьте сотрудников через меню или используйте команду добавления.",
                reply_markup=None,
                parse_mode="HTML"
            )
            return
        
        # Build employee list keyboard
        from bots.tg_bot.keyboards.admin_kb import get_employee_list_keyboard
        keyboard = await get_employee_list_keyboard(
            employees=list(employees),
            page=page,
            page_size=5
        )
        
        # Calculate pagination info
        total_employees = len(employees)
        active_employees = sum(1 for emp in employees if emp.is_active)
        page_size = 5
        total_pages = (total_employees + page_size - 1) // page_size
        start_idx = page * page_size
        end_idx = min(start_idx + page_size, total_employees)
        
        await callback.message.edit_text(
            "📋 <b>Список сотрудников</b>\n\n"
            "В этом разделе вы можете просматривать информацию о сотрудниках, "
            "изменять их роли, подписи и управлять доступом.\n\n"
            f"<b>Всего сотрудников:</b> {total_employees} (активных: {active_employees})\n"
            f"<b>Показаны:</b> {start_idx + 1}-{end_idx}\n\n"
            "🚫 — деактивированный сотрудник\n\n"
            "Выберите сотрудника для просмотра деталей:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} viewed employee list (page {page + 1}/{total_pages})")
        
    except SQLAlchemyError as e:
        logger.error(f"Database error showing employee list: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке списка из базы данных.",
            show_alert=True
        )
    except Exception as e:
        logger.error(f"Error showing employee list: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке списка.",
            show_alert=True
        )


@router.callback_query(EmployeeCallback.filter(F.action == "view"))
async def handle_employee_view(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle employee selection from list.
    
    Displays detailed employee card with all information and action buttons.
    
    Requirements: 3.2, 3.3, 3.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Clear any FSM state
        await state.clear()
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee details
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer(
                "❌ Сотрудник не найден.",
                show_alert=True
            )
            return
        
        # Role display names
        role_display = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        # Check if this employee is designated for duty accounts
        from services.settings_service import get_setting
        duty_support_id = await get_setting(session, "duty_support_account")
        duty_manager_id = await get_setting(session, "duty_manager_account")
        is_duty_support = duty_support_id and int(duty_support_id) == employee.id
        is_duty_manager = duty_manager_id and int(duty_manager_id) == employee.id
        
        # Build employee card text
        card_text = (
            f"👤 Карточка сотрудника\n\n"
            f"ID: {employee.id}\n"
            f"Имя: {employee.full_name}\n"
            f"Роль: {role_display.get(employee.staff_role, employee.staff_role.value)}\n"
            f"Подпись: {employee.position}\n"
            f"Telegram ID: {employee.tg_user_id or 'не указан'}\n"
            f"Статус: {'✅ Активен' if employee.is_active else '❌ Деактивирован'}\n"
        )
        
        # Add duty flags
        card_text += "\n"
        card_text += f"⚙️ Дежурный аккаунт ТП: {'✅ Да' if is_duty_support else '❌ Нет'}\n"
        card_text += f"⚙️ Дежурный аккаунт менеджеров: {'✅ Да' if is_duty_manager else '❌ Нет'}\n"
        
        # Add backup manager info if configured
        if employee.backup_manager_1_id or employee.backup_manager_2_id:
            card_text += "\n🛡 Резервные менеджеры:\n"
            
            if employee.backup_manager_1_id:
                backup1_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_1_id
                )
                backup1_result = await session.execute(backup1_stmt)
                backup1 = backup1_result.scalar_one_or_none()
                if backup1:
                    card_text += f"Резерв 1: {backup1.full_name}\n"
            
            if employee.backup_manager_2_id:
                backup2_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_2_id
                )
                backup2_result = await session.execute(backup2_stmt)
                backup2 = backup2_result.scalar_one_or_none()
                if backup2:
                    card_text += f"Резерв 2: {backup2.full_name}\n"
        
        # Build employee card keyboard
        from bots.tg_bot.keyboards.admin_kb import get_employee_card_keyboard
        keyboard = await get_employee_card_keyboard(
            employee, 
            is_duty_support=is_duty_support,
            is_duty_manager=is_duty_manager
        )
        
        await callback.message.edit_text(
            card_text,
            reply_markup=keyboard
        )
        
        logger.info(f"Administrator {user_id} viewed employee card: employee_id={employee_id}")
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error showing employee card: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Произошла ошибка при загрузке карточки из базы данных.",
            show_alert=True
        )
    except Exception as e:
        logger.error(
            f"Error showing employee card: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer(
            "❌ Произошла ошибка при загрузке карточки.",
            show_alert=True
        )


# ========== Back to Main Menu ==========


@router.callback_query(AdminMenuCallback.filter(F.action == "back_to_main"))
async def handle_back_to_main(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """
    Handle "Back" button to return to admin panel main menu.
    """
    await callback.answer()
    
    try:
        # Clear any FSM state
        await state.clear()
        
        # Get admin panel main menu keyboard
        keyboard = await get_admin_panel_keyboard()
        
        # Send admin panel main menu
        admin_panel_text = (
            "🔐 Административная панель\n\n"
            "Выберите раздел для управления:\n\n"
            "👥 Сотрудники - управление персоналом\n"
            "📋 Операции - регистрации, рассылки, конфликты\n"
            "📅 График работы - настройка расписания\n"
            "⚙️ Настройки - системные параметры\n"
            "📊 Статистика - аналитика и отчеты"
        )
        
        await callback.message.edit_text(
            admin_panel_text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error returning to main menu: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка.", show_alert=True)



# ========== Edit Employee Signature ==========


@router.callback_query(EmployeeCallback.filter(F.action == "edit_signature"))
async def handle_edit_signature_start(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Edit Signature" button press.
    
    Prompts administrator to enter new signature text.
    
    Requirements: 4.1, 4.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee details
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        # Store employee ID in FSM data
        await state.update_data(editing_employee_id=employee_id)
        
        # Set FSM state to wait for new signature
        await state.set_state(AdminStates.editing_employee_signature)
        
        # Get cancel keyboard
        from bots.tg_bot.keyboards.admin_kb import get_cancel_keyboard
        keyboard = await get_cancel_keyboard(action="view_employee", employee_id=employee_id)
        
        await callback.message.edit_text(
            f"✏️ Изменение подписи\n\n"
            f"Сотрудник: {employee.full_name}\n"
            f"Текущая подпись: {employee.position}\n\n"
            f"Введите новую подпись:",
            reply_markup=keyboard
        )
        
        logger.info(f"Administrator {user_id} started editing signature for employee {employee_id}")
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error starting signature edit: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при загрузке данных сотрудника.", show_alert=True)
    except Exception as e:
        logger.error(
            f"Error starting signature edit: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.message(F.text, AdminStates.editing_employee_signature)
async def handle_signature_edit_input(
    message: Message,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle new signature text input.
    
    Updates the employee signature and displays confirmation.
    
    Requirements: 4.2, 4.3, 4.5
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await message.answer("❌ У вас нет доступа к административной панели.")
            await state.clear()
            return
        
        # Get new signature text
        new_signature = message.text.strip()
        
        if len(new_signature) < 3:
            await message.answer(
                "❌ Подпись слишком короткая. Минимум 3 символа."
            )
            return
        
        if len(new_signature) > 128:
            await message.answer(
                "❌ Подпись слишком длинная. Максимум 128 символов."
            )
            return
        
        # Get employee ID from FSM data
        data = await state.get_data()
        employee_id = data.get("editing_employee_id")
        
        if not employee_id:
            await message.answer("❌ Ошибка: данные не найдены. Начните заново.")
            await state.clear()
            return
        
        # Update signature
        from services.employee_service import update_staff_signature
        
        try:
            updated_employee = await update_staff_signature(
                session=session,
                employee_id=employee_id,
                new_signature=new_signature
            )
            
            await session.commit()
            
            # Log action
            from database.models import Action_Log, ActionType
            action_log = Action_Log(
                action_type=ActionType.STAFF_UPDATED,
                staff_id=admin.id,
                action_details={
                    "employee_id": employee_id,
                    "field": "signature",
                    "old_value": data.get("old_signature"),
                    "new_value": new_signature
                }
            )
            session.add(action_log)
            await session.commit()
            
            # Role display names
            role_display = {
                StaffRole.MANAGER: "Менеджер",
                StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
                StaffRole.DUTY_ENGINEER: "Дежурный инженер",
                StaffRole.ADMINISTRATOR: "Администратор"
            }
            
            # Build employee card text with confirmation
            card_text = (
                f"✅ Подпись успешно обновлена!\n\n"
                f"Сотрудник: {updated_employee.full_name}\n"
                f"Новая подпись: {new_signature}\n\n"
                f"👤 Карточка сотрудника\n\n"
                f"ID: {updated_employee.id}\n"
                f"Имя: {updated_employee.full_name}\n"
                f"Роль: {role_display.get(updated_employee.staff_role, updated_employee.staff_role.value)}\n"
                f"Подпись: {updated_employee.position}\n"
                f"Telegram ID: {updated_employee.tg_user_id or 'не указан'}\n"
                f"Статус: {'✅ Активен' if updated_employee.is_active else '❌ Деактивирован'}\n"
            )
            
            # Add backup manager info if configured
            if updated_employee.backup_manager_1_id or updated_employee.backup_manager_2_id:
                card_text += "\n🛡 Резервные менеджеры:\n"
                
                if updated_employee.backup_manager_1_id:
                    backup1_stmt = select(Staff_Member).where(
                        Staff_Member.id == updated_employee.backup_manager_1_id
                    )
                    backup1_result = await session.execute(backup1_stmt)
                    backup1 = backup1_result.scalar_one_or_none()
                    if backup1:
                        card_text += f"Резерв 1: {backup1.full_name}\n"
                
                if updated_employee.backup_manager_2_id:
                    backup2_stmt = select(Staff_Member).where(
                        Staff_Member.id == updated_employee.backup_manager_2_id
                    )
                    backup2_result = await session.execute(backup2_stmt)
                    backup2 = backup2_result.scalar_one_or_none()
                    if backup2:
                        card_text += f"Резерв 2: {backup2.full_name}\n"
            
            # Build employee card keyboard
            from bots.tg_bot.keyboards.admin_kb import get_employee_card_keyboard
            keyboard = await get_employee_card_keyboard(updated_employee)
            
            await message.answer(
                card_text,
                reply_markup=keyboard
            )
            
            logger.info(
                f"Administrator {user_id} updated signature for employee {employee_id}: "
                f"new_signature='{new_signature}'"
            )
            
        except ValueError as ve:
            await message.answer(f"❌ {str(ve)}")
            logger.warning(f"Signature update validation error: {ve}")
        
        # Clear FSM state
        await state.clear()
        
    except SQLAlchemyError as e:
        logger.error(f"Database error handling signature edit: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обновлении подписи в базе данных.")
        await state.clear()
    except Exception as e:
        logger.error(f"Error handling signature edit: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обновлении подписи.")
        await state.clear()


# ========== Edit Employee Name ==========


@router.callback_query(EmployeeCallback.filter(F.action == "edit_name"))
async def handle_edit_name_start(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Edit Name" button press.
    
    Prompts administrator to enter new name.
    
    Requirements: 4.1, 4.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee details
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        # Store employee ID in FSM data
        await state.update_data(editing_employee_id=employee_id)
        
        # Set FSM state to wait for new name
        await state.set_state(AdminStates.editing_employee_name)
        
        # Get cancel keyboard
        from bots.tg_bot.keyboards.admin_kb import get_cancel_keyboard
        keyboard = await get_cancel_keyboard(action="view_employee", employee_id=employee_id)
        
        await callback.message.edit_text(
            f"✏️ Изменение имени\n\n"
            f"Сотрудник: {employee.full_name}\n"
            f"Текущее имя: {employee.full_name}\n\n"
            f"Введите новое имя:",
            reply_markup=keyboard
        )
        
        logger.info(f"Administrator {user_id} started editing name for employee {employee_id}")
        
    except SQLAlchemyError as e:
        logger.error(
            f"Database error starting name edit: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при загрузке данных сотрудника.", show_alert=True)
    except Exception as e:
        logger.error(
            f"Error starting name edit: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.message(F.text, AdminStates.editing_employee_name)
async def handle_name_edit_input(
    message: Message,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle new name text input.
    
    Updates the employee name and displays confirmation with employee card.
    
    Requirements: 4.2, 4.3, 4.5
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await message.answer("❌ У вас нет доступа к административной панели.")
            await state.clear()
            return
        
        # Get new name text
        new_name = message.text.strip()
        
        if len(new_name) < 2:
            await message.answer(
                "❌ Имя слишком короткое. Минимум 2 символа."
            )
            return
        
        if len(new_name) > 100:
            await message.answer(
                "❌ Имя слишком длинное. Максимум 100 символов."
            )
            return
        
        # Get employee ID from FSM data
        data = await state.get_data()
        employee_id = data.get("editing_employee_id")
        
        if not employee_id:
            await message.answer("❌ Ошибка: данные не найдены. Начните заново.")
            await state.clear()
            return
        
        # Update name
        from services.employee_service import update_staff_name
        
        try:
            updated_employee = await update_staff_name(
                session=session,
                employee_id=employee_id,
                new_name=new_name
            )
            
            await session.commit()
            
            # Log action
            from database.models import Action_Log, ActionType
            action_log = Action_Log(
                action_type=ActionType.STAFF_UPDATED,
                staff_id=admin.id,
                action_details={
                    "employee_id": employee_id,
                    "field": "name",
                    "old_value": data.get("old_name"),
                    "new_value": new_name
                }
            )
            session.add(action_log)
            await session.commit()
            
            # Role display names
            role_display = {
                StaffRole.MANAGER: "Менеджер",
                StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
                StaffRole.DUTY_ENGINEER: "Дежурный инженер",
                StaffRole.ADMINISTRATOR: "Администратор"
            }
            
            # Build employee card text with confirmation
            card_text = (
                f"✅ Имя успешно обновлено!\n\n"
                f"Сотрудник: {updated_employee.full_name}\n"
                f"Новое имя: {new_name}\n\n"
                f"👤 Карточка сотрудника\n\n"
                f"ID: {updated_employee.id}\n"
                f"Имя: {updated_employee.full_name}\n"
                f"Роль: {role_display.get(updated_employee.staff_role, updated_employee.staff_role.value)}\n"
                f"Подпись: {updated_employee.position}\n"
                f"Telegram ID: {updated_employee.tg_user_id or 'не указан'}\n"
                f"Статус: {'✅ Активен' if updated_employee.is_active else '❌ Деактивирован'}\n"
            )
            
            # Add backup manager info if configured
            if updated_employee.backup_manager_1_id or updated_employee.backup_manager_2_id:
                card_text += "\n🛡 Резервные менеджеры:\n"
                
                if updated_employee.backup_manager_1_id:
                    backup1_stmt = select(Staff_Member).where(
                        Staff_Member.id == updated_employee.backup_manager_1_id
                    )
                    backup1_result = await session.execute(backup1_stmt)
                    backup1 = backup1_result.scalar_one_or_none()
                    if backup1:
                        card_text += f"Резерв 1: {backup1.full_name}\n"
                
                if updated_employee.backup_manager_2_id:
                    backup2_stmt = select(Staff_Member).where(
                        Staff_Member.id == updated_employee.backup_manager_2_id
                    )
                    backup2_result = await session.execute(backup2_stmt)
                    backup2 = backup2_result.scalar_one_or_none()
                    if backup2:
                        card_text += f"Резерв 2: {backup2.full_name}\n"
            
            # Build employee card keyboard
            from bots.tg_bot.keyboards.admin_kb import get_employee_card_keyboard
            keyboard = await get_employee_card_keyboard(updated_employee)
            
            await message.answer(
                card_text,
                reply_markup=keyboard
            )
            
            logger.info(
                f"Administrator {user_id} updated name for employee {employee_id}: "
                f"new_name='{new_name}'"
            )
            
        except ValueError as ve:
            await message.answer(f"❌ {str(ve)}")
            logger.warning(f"Name update validation error: {ve}")
        
        # Clear FSM state
        await state.clear()
        
    except SQLAlchemyError as e:
        logger.error(f"Database error handling name edit: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обновлении имени в базе данных.")
        await state.clear()
    except Exception as e:
        logger.error(f"Error handling name edit: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обновлении имени.")
        await state.clear()


# ========== Change Employee Role ==========


@router.callback_query(EmployeeCallback.filter(F.action == "edit_role"))
async def handle_edit_role_start(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Change Role" button press.
    
    Displays role selection keyboard.
    
    Requirements: 4.3, 4.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee details
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        # Store employee ID in FSM data
        await state.update_data(editing_employee_id=employee_id)
        
        # Role display names
        role_display = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        # Show role selection keyboard
        from bots.tg_bot.keyboards.admin_kb import get_role_selection_keyboard
        keyboard = await get_role_selection_keyboard(
            employee_id=employee_id,
            current_role=employee.staff_role.value
        )
        
        await callback.message.edit_text(
            f"🎭 Изменение роли\n\n"
            f"Сотрудник: {employee.full_name}\n"
            f"Текущая роль: {role_display.get(employee.staff_role, employee.staff_role.value)}\n\n"
            f"Выберите новую роль:",
            reply_markup=keyboard
        )
        
        logger.info(f"Administrator {user_id} started role change for employee {employee_id}")
        
    except Exception as e:
        logger.error(
            f"Error starting role change: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(EmployeeRoleCallback.filter(F.employee_id.is_not(None)))
async def handle_role_change_selection(
    callback: CallbackQuery,
    callback_data: EmployeeRoleCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle role selection for existing employee.
    
    Updates the employee role and displays confirmation.
    
    Requirements: 4.4, 4.5
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            await state.clear()
            return
        
        # Map role string to StaffRole enum
        role_map = {
            "manager": StaffRole.MANAGER,
            "technical_support": StaffRole.TECHNICAL_SUPPORT,
            "duty_engineer": StaffRole.DUTY_ENGINEER,
            "administrator": StaffRole.ADMINISTRATOR
        }
        
        new_role = role_map.get(callback_data.role)
        if not new_role:
            await callback.answer("❌ Неверная роль.", show_alert=True)
            return
        
        employee_id = callback_data.employee_id
        
        # Update role
        from services.employee_service import update_staff_role
        
        try:
            updated_employee = await update_staff_role(
                session=session,
                employee_id=employee_id,
                new_role=new_role
            )
            
            await session.commit()
            
            # Role display names
            role_display = {
                StaffRole.MANAGER: "Менеджер",
                StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
                StaffRole.DUTY_ENGINEER: "Дежурный инженер",
                StaffRole.ADMINISTRATOR: "Администратор"
            }
            
            # Log action
            from database.models import Action_Log, ActionType
            action_log = Action_Log(
                action_type=ActionType.STAFF_UPDATED,
                staff_id=admin.id,
                action_details={
                    "employee_id": employee_id,
                    "field": "role",
                    "new_value": new_role.value
                }
            )
            session.add(action_log)
            await session.commit()
            
            logger.info(
                f"Administrator {user_id} updated role for employee {employee_id}: "
                f"new_role={new_role.value}"
            )
            
            # Build employee card text with updated role
            card_text = (
                f"✅ Роль успешно обновлена!\n\n"
                f"👤 Карточка сотрудника\n\n"
                f"ID: {updated_employee.id}\n"
                f"Имя: {updated_employee.full_name}\n"
                f"Роль: {role_display[new_role]}\n"
                f"Подпись: {updated_employee.position}\n"
                f"Telegram ID: {updated_employee.tg_user_id or 'не указан'}\n"
                f"Статус: {'✅ Активен' if updated_employee.is_active else '❌ Деактивирован'}\n"
            )
            
            # Add backup manager info if configured
            if updated_employee.backup_manager_1_id or updated_employee.backup_manager_2_id:
                card_text += "\n🛡 Резервные менеджеры:\n"
                
                if updated_employee.backup_manager_1_id:
                    backup1_stmt = select(Staff_Member).where(
                        Staff_Member.id == updated_employee.backup_manager_1_id
                    )
                    backup1_result = await session.execute(backup1_stmt)
                    backup1 = backup1_result.scalar_one_or_none()
                    if backup1:
                        card_text += f"Резерв 1: {backup1.full_name}\n"
                
                if updated_employee.backup_manager_2_id:
                    backup2_stmt = select(Staff_Member).where(
                        Staff_Member.id == updated_employee.backup_manager_2_id
                    )
                    backup2_result = await session.execute(backup2_stmt)
                    backup2 = backup2_result.scalar_one_or_none()
                    if backup2:
                        card_text += f"Резерв 2: {backup2.full_name}\n"
            
            # Build employee card keyboard
            from bots.tg_bot.keyboards.admin_kb import get_employee_card_keyboard
            keyboard = await get_employee_card_keyboard(updated_employee)
            
            # Return to employee card with confirmation message
            await callback.message.edit_text(
                card_text,
                reply_markup=keyboard
            )
            
        except ValueError as ve:
            await callback.answer(f"❌ {str(ve)}", show_alert=True)
            logger.warning(f"Role update failed: {ve}")
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error handling role change: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)
        await state.clear()


# ========== Deactivate Employee ==========


@router.callback_query(EmployeeCallback.filter(F.action == "deactivate"))
async def handle_deactivate_employee(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Deactivate" button press.
    
    Displays confirmation prompt before deactivating employee.
    
    Requirements: 5.1, 5.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee details
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        # Build confirmation keyboard
        from bots.tg_bot.keyboards.admin_kb import get_deactivation_confirmation_keyboard
        
        keyboard = await get_deactivation_confirmation_keyboard(employee_id)
        
        # Role display names
        role_display = {
            "MANAGER": "Менеджер",
            "TECHNICAL_SUPPORT": "Техподдержка",
            "DUTY_ENGINEER": "Дежурный инженер",
            "ADMINISTRATOR": "Администратор"
        }
        role_text = role_display.get(employee.staff_role.value.upper(), employee.staff_role.value)
        
        await callback.message.edit_text(
            f"⚠️ Подтверждение деактивации\n\n"
            f"Сотрудник: {employee.full_name}\n"
            f"Должность: {role_text}\n\n"
            f"При деактивации:\n"
            f"• Сотрудник потеряет доступ к системе\n"
            f"• Все его активные заявки будут переведены в статус NEW\n"
            f"• Заявки будут сняты с назначения\n\n"
            f"Вы уверены?",
            reply_markup=keyboard
        )
        
        logger.info(f"Administrator {user_id} requested deactivation confirmation for employee {employee_id}")
        
    except Exception as e:
        logger.error(
            f"Error showing deactivation confirmation: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(EmployeeCallback.filter(F.action == "confirm_deactivate"))
async def handle_confirm_deactivate(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle deactivation confirmation.
    
    Deactivates the employee and reassigns their tickets.
    
    Requirements: 5.2, 5.3, 5.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Deactivate employee
        from services.employee_service import deactivate_staff_member
        
        try:
            deactivated_employee, reassigned_count = await deactivate_staff_member(
                session=session,
                employee_id=employee_id
            )
            
            await session.commit()
            
            # Log action
            from database.models import Action_Log, ActionType
            action_log = Action_Log(
                action_type=ActionType.STAFF_DEACTIVATED,
                staff_id=admin.id,
                action_details={
                    "employee_id": employee_id,
                    "employee_name": deactivated_employee.full_name,
                    "reassigned_tickets": reassigned_count
                }
            )
            session.add(action_log)
            await session.commit()
            
            # Send confirmation with back button to employee list
            from bots.tg_bot.keyboards.admin_kb import get_employee_list_keyboard
            from sqlalchemy import select
            
            # Query all employees (including deactivated) for the list
            stmt = select(Staff_Member).where(
                Staff_Member.tg_user_id != user_id  # Exclude current user
            ).order_by(Staff_Member.full_name)
            result = await session.execute(stmt)
            all_employees = result.scalars().all()
            
            # Get keyboard with employee list
            keyboard = await get_employee_list_keyboard(all_employees, page=0)
            
            # Role display names
            role_display = {
                "MANAGER": "Менеджер",
                "TECHNICAL_SUPPORT": "Техподдержка",
                "DUTY_ENGINEER": "Дежурный инженер",
                "ADMINISTRATOR": "Администратор"
            }
            role_text = role_display.get(deactivated_employee.staff_role.value.upper(), deactivated_employee.staff_role.value)
            
            await callback.message.edit_text(
                f"✅ Сотрудник деактивирован\n\n"
                f"Имя: {deactivated_employee.full_name}\n"
                f"Должность: {role_text}\n\n"
                f"Переназначено заявок: {reassigned_count}\n\n"
                f"Сотрудник больше не имеет доступа к системе.",
                reply_markup=keyboard
            )
            
            logger.info(
                f"Administrator {user_id} deactivated employee {employee_id}: "
                f"name='{deactivated_employee.full_name}', reassigned_tickets={reassigned_count}"
            )
            
        except ValueError as ve:
            await callback.answer(f"❌ {str(ve)}", show_alert=True)
            logger.warning(f"Deactivation failed: {ve}")
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error deactivating employee: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при деактивации.", show_alert=True)


@router.callback_query(EmployeeCallback.filter(F.action == "activate"))
async def handle_activate_employee(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle employee activation.
    
    Activates a deactivated employee, restoring their access to the system.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        if employee.is_active:
            await callback.answer("⚠️ Сотрудник уже активен.", show_alert=True)
            return
        
        # Activate employee
        employee.is_active = True
        await session.commit()
        
        # Log action
        from database.models import Action_Log, ActionType
        action_log = Action_Log(
            action_type=ActionType.STAFF_ACTIVATED,
            staff_id=admin.id,
            action_details={
                "employee_id": employee_id,
                "employee_name": employee.full_name
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Show updated employee card
        role_display = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        card_text = (
            f"✅ Сотрудник активирован\n\n"
            f"👤 Карточка сотрудника\n\n"
            f"ID: {employee.id}\n"
            f"Имя: {employee.full_name}\n"
            f"Роль: {role_display.get(employee.staff_role, employee.staff_role.value)}\n"
            f"Подпись: {employee.position}\n"
            f"Telegram ID: {employee.tg_user_id or 'не указан'}\n"
            f"Статус: {'✅ Активен' if employee.is_active else '❌ Деактивирован'}\n"
        )
        
        # Add backup manager info if configured
        if employee.backup_manager_1_id or employee.backup_manager_2_id:
            card_text += "\n🛡 Резервные менеджеры:\n"
            
            if employee.backup_manager_1_id:
                backup1_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_1_id
                )
                backup1_result = await session.execute(backup1_stmt)
                backup1 = backup1_result.scalar_one_or_none()
                if backup1:
                    card_text += f"Резерв 1: {backup1.full_name}\n"
            
            if employee.backup_manager_2_id:
                backup2_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_2_id
                )
                backup2_result = await session.execute(backup2_stmt)
                backup2 = backup2_result.scalar_one_or_none()
                if backup2:
                    card_text += f"Резерв 2: {backup2.full_name}\n"
        
        # Build employee card keyboard
        from bots.tg_bot.keyboards.admin_kb import get_employee_card_keyboard
        keyboard = await get_employee_card_keyboard(employee)
        
        await callback.message.edit_text(
            card_text,
            reply_markup=keyboard
        )
        
        logger.info(
            f"Administrator {user_id} activated employee {employee_id}: "
            f"name='{employee.full_name}'"
        )
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error activating employee: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при активации.", show_alert=True)



# ========== Duty Support Configuration ==========


@router.callback_query(EmployeeCallback.filter(F.action == "set_duty_support"))
async def handle_set_duty_support(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Set as Duty Support" button press.
    
    Designates the selected employee as the duty support account for extended hours.
    Updates the system setting and shows confirmation.
    
    Requirements: 7.1 (Передача техподдержке по времени - Продленное время)
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        if not employee.is_active:
            await callback.answer(
                "⚠️ Нельзя назначить дежурным деактивированного сотрудника.",
                show_alert=True
            )
            return
        
        # Update duty support setting
        from services.settings_service import update_setting
        
        success, message = await update_setting(
            session=session,
            key="duty_support_account",
            value=str(employee_id),
            admin_id=admin.id
        )
        
        if not success:
            await callback.answer(f"❌ {message}", show_alert=True)
            return
        
        # Refresh session after commit in update_setting
        await session.refresh(employee)
        
        # Get both duty flags for display
        from services.settings_service import get_setting
        duty_manager_id = await get_setting(session, "duty_manager_account")
        is_duty_manager = duty_manager_id and int(duty_manager_id) == employee.id
        
        # Show updated employee card
        role_display = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        card_text = (
            f"✅ Сотрудник назначен дежурным ТП\n\n"
            f"👤 Карточка сотрудника\n\n"
            f"ID: {employee.id}\n"
            f"Имя: {employee.full_name}\n"
            f"Роль: {role_display.get(employee.staff_role, employee.staff_role.value)}\n"
            f"Подпись: {employee.position}\n"
            f"Telegram ID: {employee.tg_user_id or 'не указан'}\n"
            f"Статус: {'✅ Активен' if employee.is_active else '❌ Деактивирован'}\n\n"
            f"⚙️ Дежурный аккаунт ТП: ✅ Да\n"
            f"⚙️ Дежурный аккаунт менеджеров: {'✅ Да' if is_duty_manager else '❌ Нет'}\n"
        )
        
        # Add backup manager info if configured
        if employee.backup_manager_1_id or employee.backup_manager_2_id:
            card_text += "\n🛡 Резервные менеджеры:\n"
            
            if employee.backup_manager_1_id:
                backup1_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_1_id
                )
                backup1_result = await session.execute(backup1_stmt)
                backup1 = backup1_result.scalar_one_or_none()
                if backup1:
                    card_text += f"Резерв 1: {backup1.full_name}\n"
            
            if employee.backup_manager_2_id:
                backup2_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_2_id
                )
                backup2_result = await session.execute(backup2_stmt)
                backup2 = backup2_result.scalar_one_or_none()
                if backup2:
                    card_text += f"Резерв 2: {backup2.full_name}\n"
        
        # Build employee card keyboard
        from bots.tg_bot.keyboards.admin_kb import get_employee_card_keyboard
        keyboard = await get_employee_card_keyboard(
            employee, 
            is_duty_support=True,
            is_duty_manager=is_duty_manager
        )
        
        await callback.message.edit_text(
            card_text,
            reply_markup=keyboard
        )
        
        logger.info(
            f"Administrator {user_id} set employee {employee_id} as duty support: "
            f"name='{employee.full_name}'"
        )
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error setting duty support: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при назначении.", show_alert=True)


@router.callback_query(EmployeeCallback.filter(F.action == "unset_duty_support"))
async def handle_unset_duty_support(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Unset as Duty Support" button press.
    
    Removes the duty support designation from the selected employee.
    Clears the system setting and shows confirmation.
    
    Requirements: 7.1 (Передача техподдержке по времени - Продленное время)
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        # Clear duty support setting
        from services.settings_service import update_setting
        
        success, message = await update_setting(
            session=session,
            key="duty_support_account",
            value="",
            admin_id=admin.id
        )
        
        if not success:
            await callback.answer(f"❌ {message}", show_alert=True)
            return
        
        # Refresh session after commit in update_setting
        await session.refresh(employee)
        
        # Get duty manager flag for display
        from services.settings_service import get_setting
        duty_manager_id = await get_setting(session, "duty_manager_account")
        is_duty_manager = duty_manager_id and int(duty_manager_id) == employee.id
        
        # Show updated employee card
        role_display = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        card_text = (
            f"✅ Сотрудник снят с дежурства ТП\n\n"
            f"👤 Карточка сотрудника\n\n"
            f"ID: {employee.id}\n"
            f"Имя: {employee.full_name}\n"
            f"Роль: {role_display.get(employee.staff_role, employee.staff_role.value)}\n"
            f"Подпись: {employee.position}\n"
            f"Telegram ID: {employee.tg_user_id or 'не указан'}\n"
            f"Статус: {'✅ Активен' if employee.is_active else '❌ Деактивирован'}\n\n"
            f"⚙️ Дежурный аккаунт ТП: ❌ Нет\n"
            f"⚙️ Дежурный аккаунт менеджеров: {'✅ Да' if is_duty_manager else '❌ Нет'}\n"
        )
        
        # Add backup manager info if configured
        if employee.backup_manager_1_id or employee.backup_manager_2_id:
            card_text += "\n🛡 Резервные менеджеры:\n"
            
            if employee.backup_manager_1_id:
                backup1_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_1_id
                )
                backup1_result = await session.execute(backup1_stmt)
                backup1 = backup1_result.scalar_one_or_none()
                if backup1:
                    card_text += f"Резерв 1: {backup1.full_name}\n"
            
            if employee.backup_manager_2_id:
                backup2_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_2_id
                )
                backup2_result = await session.execute(backup2_stmt)
                backup2 = backup2_result.scalar_one_or_none()
                if backup2:
                    card_text += f"Резерв 2: {backup2.full_name}\n"
        
        # Build employee card keyboard
        from bots.tg_bot.keyboards.admin_kb import get_employee_card_keyboard
        keyboard = await get_employee_card_keyboard(
            employee, 
            is_duty_support=False,
            is_duty_manager=is_duty_manager
        )
        
        await callback.message.edit_text(
            card_text,
            reply_markup=keyboard
        )
        
        logger.info(
            f"Administrator {user_id} removed duty support from employee {employee_id}: "
            f"name='{employee.full_name}'"
        )
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error unsetting duty support: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при снятии с дежурства.", show_alert=True)


@router.callback_query(EmployeeCallback.filter(F.action == "set_duty_manager"))
async def handle_set_duty_manager(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Set as Duty Manager" button press.
    
    Designates the selected employee as the duty manager account for extended hours.
    Updates the system setting and shows confirmation.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        if not employee.is_active:
            await callback.answer(
                "⚠️ Нельзя назначить дежурным деактивированного сотрудника.",
                show_alert=True
            )
            return
        
        # Update duty manager setting
        from services.settings_service import update_setting
        
        success, message = await update_setting(
            session=session,
            key="duty_manager_account",
            value=str(employee_id),
            admin_id=admin.id
        )
        
        if not success:
            await callback.answer(f"❌ {message}", show_alert=True)
            return
        
        # Refresh session after commit in update_setting
        await session.refresh(employee)
        
        # Get both duty flags for display
        from services.settings_service import get_setting
        duty_support_id = await get_setting(session, "duty_support_account")
        is_duty_support = duty_support_id and int(duty_support_id) == employee.id
        
        # Show updated employee card
        role_display = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        card_text = (
            f"✅ Сотрудник назначен дежурным менеджеров\n\n"
            f"👤 Карточка сотрудника\n\n"
            f"ID: {employee.id}\n"
            f"Имя: {employee.full_name}\n"
            f"Роль: {role_display.get(employee.staff_role, employee.staff_role.value)}\n"
            f"Подпись: {employee.position}\n"
            f"Telegram ID: {employee.tg_user_id or 'не указан'}\n"
            f"Статус: {'✅ Активен' if employee.is_active else '❌ Деактивирован'}\n\n"
            f"⚙️ Дежурный аккаунт ТП: {'✅ Да' if is_duty_support else '❌ Нет'}\n"
            f"⚙️ Дежурный аккаунт менеджеров: ✅ Да\n"
        )
        
        # Add backup manager info if configured
        if employee.backup_manager_1_id or employee.backup_manager_2_id:
            card_text += "\n🛡 Резервные менеджеры:\n"
            
            if employee.backup_manager_1_id:
                backup1_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_1_id
                )
                backup1_result = await session.execute(backup1_stmt)
                backup1 = backup1_result.scalar_one_or_none()
                if backup1:
                    card_text += f"Резерв 1: {backup1.full_name}\n"
            
            if employee.backup_manager_2_id:
                backup2_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_2_id
                )
                backup2_result = await session.execute(backup2_stmt)
                backup2 = backup2_result.scalar_one_or_none()
                if backup2:
                    card_text += f"Резерв 2: {backup2.full_name}\n"
        
        # Build employee card keyboard
        from bots.tg_bot.keyboards.admin_kb import get_employee_card_keyboard
        keyboard = await get_employee_card_keyboard(
            employee, 
            is_duty_support=is_duty_support,
            is_duty_manager=True
        )
        
        await callback.message.edit_text(
            card_text,
            reply_markup=keyboard
        )
        
        logger.info(
            f"Administrator {user_id} set duty manager: employee_id={employee_id}, "
            f"name='{employee.full_name}'"
        )
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error setting duty manager: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при назначении дежурным.", show_alert=True)


@router.callback_query(EmployeeCallback.filter(F.action == "unset_duty_manager"))
async def handle_unset_duty_manager(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Unset Duty Manager" button press.
    
    Removes the duty manager designation from the selected employee.
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        # Clear duty manager setting
        from services.settings_service import update_setting
        
        success, message = await update_setting(
            session=session,
            key="duty_manager_account",
            value="",
            admin_id=admin.id
        )
        
        if not success:
            await callback.answer(f"❌ {message}", show_alert=True)
            return
        
        # Refresh session after commit in update_setting
        await session.refresh(employee)
        
        # Get duty support flag for display
        from services.settings_service import get_setting
        duty_support_id = await get_setting(session, "duty_support_account")
        is_duty_support = duty_support_id and int(duty_support_id) == employee.id
        
        # Show updated employee card
        role_display = {
            StaffRole.MANAGER: "Менеджер",
            StaffRole.TECHNICAL_SUPPORT: "Техподдержка",
            StaffRole.DUTY_ENGINEER: "Дежурный инженер",
            StaffRole.ADMINISTRATOR: "Администратор"
        }
        
        card_text = (
            f"✅ Сотрудник снят с дежурства менеджеров\n\n"
            f"👤 Карточка сотрудника\n\n"
            f"ID: {employee.id}\n"
            f"Имя: {employee.full_name}\n"
            f"Роль: {role_display.get(employee.staff_role, employee.staff_role.value)}\n"
            f"Подпись: {employee.position}\n"
            f"Telegram ID: {employee.tg_user_id or 'не указан'}\n"
            f"Статус: {'✅ Активен' if employee.is_active else '❌ Деактивирован'}\n\n"
            f"⚙️ Дежурный аккаунт ТП: {'✅ Да' if is_duty_support else '❌ Нет'}\n"
            f"⚙️ Дежурный аккаунт менеджеров: ❌ Нет\n"
        )
        
        # Add backup manager info if configured
        if employee.backup_manager_1_id or employee.backup_manager_2_id:
            card_text += "\n🛡 Резервные менеджеры:\n"
            
            if employee.backup_manager_1_id:
                backup1_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_1_id
                )
                backup1_result = await session.execute(backup1_stmt)
                backup1 = backup1_result.scalar_one_or_none()
                if backup1:
                    card_text += f"Резерв 1: {backup1.full_name}\n"
            
            if employee.backup_manager_2_id:
                backup2_stmt = select(Staff_Member).where(
                    Staff_Member.id == employee.backup_manager_2_id
                )
                backup2_result = await session.execute(backup2_stmt)
                backup2 = backup2_result.scalar_one_or_none()
                if backup2:
                    card_text += f"Резерв 2: {backup2.full_name}\n"
        
        # Build employee card keyboard
        from bots.tg_bot.keyboards.admin_kb import get_employee_card_keyboard
        keyboard = await get_employee_card_keyboard(
            employee, 
            is_duty_support=is_duty_support,
            is_duty_manager=False
        )
        
        await callback.message.edit_text(
            card_text,
            reply_markup=keyboard
        )
        
        logger.info(
            f"Administrator {user_id} removed duty manager from employee {employee_id}: "
            f"name='{employee.full_name}'"
        )
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error unsetting duty manager: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при снятии с дежурства.", show_alert=True)


# ========== Backup Manager Configuration ==========


@router.callback_query(EmployeeCallback.filter(F.action == "backups"))
async def handle_backup_manager_config(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Configure Backups" button press.
    
    Displays backup manager configuration interface with current assignments
    and options to select or remove backup managers for each slot.
    
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Clear any FSM state
        await state.clear()
        
        # Get employee ID from callback data
        employee_id = callback_data.employee_id
        if not employee_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch employee details
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        # Fetch all active staff members for backup selection (excluding employee themselves)
        available_stmt = select(Staff_Member).where(
            and_(
                Staff_Member.is_active == True,
                Staff_Member.id != employee_id
            )
        ).order_by(Staff_Member.full_name)
        available_result = await session.execute(available_stmt)
        available_staff = list(available_result.scalars().all())
        
        # Build backup manager configuration text
        employee_position = employee.position if employee.position else "Не указана"
        config_text = (
            f"🛡 Настройка резервных менеджеров\n\n"
            f"Сотрудник: {employee.full_name}\n"
            f"Должность: {employee_position}\n\n"
            f"Резервные менеджеры получают эскалированные заявки, "
            f"если основной сотрудник не отвечает в течение установленного времени.\n\n"
        )
        
        # Add current backup manager info
        if employee.backup_manager_1_id:
            backup1_stmt = select(Staff_Member).where(
                Staff_Member.id == employee.backup_manager_1_id
            )
            backup1_result = await session.execute(backup1_stmt)
            backup1 = backup1_result.scalar_one_or_none()
            if backup1:
                backup1_position = backup1.position if backup1.position else "Не указана"
                config_text += f"Резерв 1: {backup1.full_name} ({backup1_position})\n"
            else:
                config_text += "Резерв 1: Не назначен\n"
        else:
            config_text += "Резерв 1: Не назначен\n"
        
        if employee.backup_manager_2_id:
            backup2_stmt = select(Staff_Member).where(
                Staff_Member.id == employee.backup_manager_2_id
            )
            backup2_result = await session.execute(backup2_stmt)
            backup2 = backup2_result.scalar_one_or_none()
            if backup2:
                backup2_position = backup2.position if backup2.position else "Не указана"
                config_text += f"Резерв 2: {backup2.full_name} ({backup2_position})\n"
            else:
                config_text += "Резерв 2: Не назначен\n"
        else:
            config_text += "Резерв 2: Не назначен\n"
        
        # Build backup manager keyboard
        from bots.tg_bot.keyboards.admin_kb import get_backup_manager_keyboard
        keyboard = await get_backup_manager_keyboard(
            employee=employee,
            available_staff=available_staff
        )
        
        await callback.message.edit_text(
            config_text,
            reply_markup=keyboard
        )
        
        logger.info(f"Administrator {user_id} opened backup config for employee {employee_id}")
        
    except Exception as e:
        logger.error(
            f"Error showing backup config: user={callback.from_user.id}, "
            f"employee_id={callback_data.employee_id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(BackupManagerCallback.filter(F.action == "select_slot"))
async def handle_backup_slot_selection(
    callback: CallbackQuery,
    callback_data: BackupManagerCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle backup slot selection.
    
    Displays list of available staff members to assign as backup manager.
    
    Requirements: 8.7
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        employee_id = callback_data.employee_id
        slot = callback_data.slot
        
        if not employee_id or slot not in [1, 2]:
            await callback.answer("❌ Неверные параметры.", show_alert=True)
            return
        
        # Fetch employee details
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        # Fetch all active staff members except the employee themselves
        available_stmt = select(Staff_Member).where(
            and_(
                Staff_Member.is_active == True,
                Staff_Member.id != employee_id
            )
        ).order_by(Staff_Member.full_name)
        available_result = await session.execute(available_stmt)
        available_staff = list(available_result.scalars().all())
        
        if not available_staff:
            await callback.answer(
                "❌ Нет доступных сотрудников для назначения.",
                show_alert=True
            )
            return
        
        # Build selection keyboard
        from bots.tg_bot.keyboards.admin_kb import get_backup_manager_selection_keyboard
        keyboard = await get_backup_manager_selection_keyboard(
            employee_id=employee_id,
            slot=slot,
            available_staff=available_staff
        )
        
        await callback.message.edit_text(
            f"🛡 Выбор резервного менеджера\n\n"
            f"Сотрудник: {employee.full_name}\n"
            f"Слот: Резерв {slot}\n\n"
            f"Выберите сотрудника из списка:",
            reply_markup=keyboard
        )
        
        logger.info(
            f"Administrator {user_id} selecting backup for employee {employee_id}, slot {slot}"
        )
        
    except Exception as e:
        logger.error(
            f"Error showing backup selection: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(BackupManagerCallback.filter(F.action == "assign"))
async def handle_backup_manager_assignment(
    callback: CallbackQuery,
    callback_data: BackupManagerCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle backup manager assignment.
    
    Assigns the selected staff member as backup manager for the specified slot.
    
    Requirements: 8.8, 8.9, 8.10
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        employee_id = callback_data.employee_id
        slot = callback_data.slot
        backup_id = callback_data.backup_id
        
        if not employee_id or slot not in [1, 2] or not backup_id:
            await callback.answer("❌ Неверные параметры.", show_alert=True)
            return
        
        # Assign backup manager
        from services.employee_service import set_backup_manager
        
        try:
            updated_employee = await set_backup_manager(
                session=session,
                employee_id=employee_id,
                slot=slot,
                backup_id=backup_id
            )
            
            await session.commit()
            
            # Get backup manager details
            backup_stmt = select(Staff_Member).where(Staff_Member.id == backup_id)
            backup_result = await session.execute(backup_stmt)
            backup_manager = backup_result.scalar_one_or_none()
            
            # Log action
            from database.models import Action_Log, ActionType
            action_log = Action_Log(
                action_type=ActionType.STAFF_UPDATED,
                staff_id=admin.id,
                action_details={
                    "employee_id": employee_id,
                    "field": f"backup_manager_{slot}",
                    "backup_id": backup_id,
                    "backup_name": backup_manager.full_name if backup_manager else "Unknown"
                }
            )
            session.add(action_log)
            await session.commit()
            
            # Send confirmation and return to backup config
            await callback.message.edit_text(
                f"✅ Резервный менеджер назначен\n\n"
                f"Сотрудник: {updated_employee.full_name}\n"
                f"Резерв {slot}: {backup_manager.full_name if backup_manager else 'Unknown'}\n\n"
                f"Резервный менеджер будет получать эскалированные заявки."
            )
            
            # Wait a moment for user to read confirmation
            import asyncio
            await asyncio.sleep(1)
            
            # Return to backup config screen
            employee_callback = EmployeeCallback(
                action="backups",
                employee_id=employee_id
            )
            await handle_backup_manager_config(
                callback=callback,
                callback_data=employee_callback,
                session=session,
                state=state
            )
            
            logger.info(
                f"Administrator {user_id} assigned backup manager: "
                f"employee_id={employee_id}, slot={slot}, backup_id={backup_id}"
            )
            
        except ValueError as ve:
            await callback.answer(f"❌ {str(ve)}", show_alert=True)
            logger.warning(f"Backup assignment failed: {ve}")
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error assigning backup manager: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при назначении.", show_alert=True)


@router.callback_query(BackupManagerCallback.filter(F.action == "remove"))
async def handle_backup_manager_removal(
    callback: CallbackQuery,
    callback_data: BackupManagerCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle backup manager removal.
    
    Removes the backup manager from the specified slot.
    
    Requirements: 8.11, 8.12, 8.13
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        employee_id = callback_data.employee_id
        slot = callback_data.slot
        
        if not employee_id or slot not in [1, 2]:
            await callback.answer("❌ Неверные параметры.", show_alert=True)
            return
        
        # Fetch employee to get current backup manager name
        stmt = select(Staff_Member).where(Staff_Member.id == employee_id)
        result = await session.execute(stmt)
        employee = result.scalar_one_or_none()
        
        if not employee:
            await callback.answer("❌ Сотрудник не найден.", show_alert=True)
            return
        
        # Get current backup manager ID
        current_backup_id = (
            employee.backup_manager_1_id if slot == 1 
            else employee.backup_manager_2_id
        )
        
        # Get backup manager name for logging
        backup_name = "Unknown"
        if current_backup_id:
            backup_stmt = select(Staff_Member).where(Staff_Member.id == current_backup_id)
            backup_result = await session.execute(backup_stmt)
            backup_manager = backup_result.scalar_one_or_none()
            if backup_manager:
                backup_name = backup_manager.full_name
        
        # Remove backup manager
        from services.employee_service import set_backup_manager
        
        try:
            updated_employee = await set_backup_manager(
                session=session,
                employee_id=employee_id,
                slot=slot,
                backup_id=None  # None to remove
            )
            
            await session.commit()
            
            # Log action
            from database.models import Action_Log, ActionType
            action_log = Action_Log(
                action_type=ActionType.STAFF_UPDATED,
                staff_id=admin.id,
                action_details={
                    "employee_id": employee_id,
                    "field": f"backup_manager_{slot}",
                    "action": "removed",
                    "previous_backup_name": backup_name
                }
            )
            session.add(action_log)
            await session.commit()
            
            # Send confirmation and return to backup config
            await callback.message.edit_text(
                f"✅ Резервный менеджер удален\n\n"
                f"Сотрудник: {updated_employee.full_name}\n"
                f"Резерв {slot}: Не назначен\n\n"
                f"Слот резервного менеджера освобожден."
            )
            
            # Wait a moment for user to read confirmation
            import asyncio
            await asyncio.sleep(1)
            
            # Return to backup config screen
            employee_callback = EmployeeCallback(
                action="backups",
                employee_id=employee_id
            )
            await handle_backup_manager_config(
                callback=callback,
                callback_data=employee_callback,
                session=session,
                state=state
            )
            
            logger.info(
                f"Administrator {user_id} removed backup manager: "
                f"employee_id={employee_id}, slot={slot}"
            )
            
        except ValueError as ve:
            await callback.answer(f"❌ {str(ve)}", show_alert=True)
            logger.warning(f"Backup removal failed: {ve}")
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error removing backup manager: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при удалении.", show_alert=True)


@router.callback_query(BackupManagerCallback.filter(F.action == "back_to_config"))
async def handle_back_to_backup_config(
    callback: CallbackQuery,
    callback_data: BackupManagerCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Back" button from backup manager selection.
    
    Returns to backup manager configuration screen.
    
    Requirements: 6.1
    """
    await callback.answer()
    
    try:
        # Redirect to backup config handler
        employee_callback = EmployeeCallback(
            action="backups",
            employee_id=callback_data.employee_id
        )
        
        # Create a new callback query with the employee callback data
        await handle_backup_manager_config(
            callback=callback,
            callback_data=employee_callback,
            session=session,
            state=state
        )
        
    except Exception as e:
        logger.error(
            f"Error returning to backup config: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)



# ========== Ticket Transfer ==========


@router.callback_query(EmployeeCallback.filter(F.action == "transfer_ticket"))
async def handle_transfer_ticket_start(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Reassign Ticket" button press.
    
    Displays list of available staff members to transfer the ticket to.
    
    Requirements: 7.1, 7.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get ticket ID from callback data (assuming it's stored in employee_id field for this action)
        # Note: This assumes the callback data structure includes ticket_id
        # In a real implementation, you'd need a TicketTransferCallback or similar
        ticket_id = callback_data.employee_id  # Placeholder - needs proper callback data structure
        
        if not ticket_id:
            await callback.answer("❌ ID заявки не указан.", show_alert=True)
            return
        
        # Fetch ticket details
        from database.models import Ticket
        ticket_stmt = select(Ticket).where(Ticket.id == ticket_id)
        ticket_result = await session.execute(ticket_stmt)
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            await callback.answer("❌ Заявка не найдена.", show_alert=True)
            return
        
        # Get current assigned staff member
        current_staff_id = ticket.assigned_staff_id
        
        # Get available employees for transfer
        from services.employee_service import get_available_employees_for_transfer
        
        # Note: This requires the current employee's Telegram ID, not internal ID
        # We need to fetch the current staff member first
        if current_staff_id:
            current_staff_stmt = select(Staff_Member).where(Staff_Member.id == current_staff_id)
            current_staff_result = await session.execute(current_staff_stmt)
            current_staff = current_staff_result.scalar_one_or_none()
            current_tg_id = current_staff.tg_user_id if current_staff else 0
        else:
            current_tg_id = 0
        
        available_employees = await get_available_employees_for_transfer(
            session=session,
            ticket=ticket,
            current_employee_id=current_tg_id
        )
        
        if not available_employees:
            await callback.answer(
                "❌ Нет доступных сотрудников для передачи заявки.",
                show_alert=True
            )
            return
        
        # Store ticket ID in FSM data
        await state.update_data(transferring_ticket_id=ticket_id)
        
        # Build staff selection keyboard
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        builder = InlineKeyboardBuilder()
        
        # Role display names
        role_display = {
            "MANAGER": "Менеджер",
            "TECHNICAL_SUPPORT": "Техподдержка",
            "DUTY_ENGINEER": "Дежурный инженер",
            "ADMINISTRATOR": "Администратор"
        }
        
        for employee in available_employees:
            role_text = role_display.get(employee.staff_role.value, employee.staff_role.value)
            button_text = f"{employee.full_name} - {role_text}"
            
            builder.button(
                text=button_text,
                callback_data=EmployeeCallback(
                    action="confirm_ticket_transfer",
                    employee_id=employee.id
                )
            )
        
        # Cancel button
        builder.button(
            text="❌ Отмена",
            callback_data=AdminMenuCallback(action="employees")
        )
        
        builder.adjust(1)
        
        # Get ticket type display
        ticket_type_display = {
            "INVOICE": "Счет",
            "TECHNICAL_SUPPORT": "Техподдержка",
            "RENEWAL": "Продление"
        }
        ticket_type_text = ticket_type_display.get(
            ticket.ticket_type.value if hasattr(ticket.ticket_type, 'value') else str(ticket.ticket_type),
            str(ticket.ticket_type)
        )
        
        await callback.message.edit_text(
            f"🔄 Передача заявки\n\n"
            f"Заявка #{ticket_id}\n"
            f"Тип: {ticket_type_text}\n\n"
            f"Выберите сотрудника для передачи:",
            reply_markup=builder.as_markup()
        )
        
        logger.info(f"Administrator {user_id} started ticket transfer for ticket {ticket_id}")
        
    except Exception as e:
        logger.error(
            f"Error starting ticket transfer: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(EmployeeCallback.filter(F.action == "confirm_ticket_transfer"))
async def handle_confirm_ticket_transfer(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle ticket transfer confirmation.
    
    Transfers the ticket to the selected staff member and sends notifications.
    
    Requirements: 7.3, 7.4, 7.5
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get ticket ID from FSM data
        data = await state.get_data()
        ticket_id = data.get("transferring_ticket_id")
        
        if not ticket_id:
            await callback.answer("❌ Ошибка: данные не найдены.", show_alert=True)
            await state.clear()
            return
        
        # Get target staff ID from callback data
        to_staff_id = callback_data.employee_id
        
        if not to_staff_id:
            await callback.answer("❌ ID сотрудника не указан.", show_alert=True)
            return
        
        # Fetch ticket details
        from database.models import Ticket
        ticket_stmt = select(Ticket).where(Ticket.id == ticket_id)
        ticket_result = await session.execute(ticket_stmt)
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            await callback.answer("❌ Заявка не найдена.", show_alert=True)
            await state.clear()
            return
        
        from_staff_id = ticket.assigned_staff_id
        
        if not from_staff_id:
            await callback.answer("❌ Заявка не назначена ни на кого.", show_alert=True)
            await state.clear()
            return
        
        # Transfer ticket
        from services.employee_service import transfer_ticket
        
        try:
            updated_ticket = await transfer_ticket(
                session=session,
                ticket_id=ticket_id,
                from_staff_id=from_staff_id,
                to_staff_id=to_staff_id,
                admin_id=admin.id
            )
            
            await session.commit()
            
            # Get staff member details for notifications
            from_staff_stmt = select(Staff_Member).where(Staff_Member.id == from_staff_id)
            from_staff_result = await session.execute(from_staff_stmt)
            from_staff = from_staff_result.scalar_one_or_none()
            
            to_staff_stmt = select(Staff_Member).where(Staff_Member.id == to_staff_id)
            to_staff_result = await session.execute(to_staff_stmt)
            to_staff = to_staff_result.scalar_one_or_none()
            
            # Send notifications to both staff members
            try:
                from aiogram import Bot
                bot = callback.bot
                
                # Notify old assignee
                if from_staff and from_staff.tg_user_id:
                    await bot.send_message(
                        chat_id=from_staff.tg_user_id,
                        text=(
                            f"🔄 Заявка #{ticket_id} передана\n\n"
                            f"Заявка была передана от вас к {to_staff.full_name if to_staff else 'другому сотруднику'}.\n"
                            f"Администратор: {admin.full_name}"
                        )
                    )
                
                # Notify new assignee
                if to_staff and to_staff.tg_user_id:
                    await bot.send_message(
                        chat_id=to_staff.tg_user_id,
                        text=(
                            f"📥 Новая заявка #{ticket_id}\n\n"
                            f"Вам передана заявка от {from_staff.full_name if from_staff else 'другого сотрудника'}.\n"
                            f"Администратор: {admin.full_name}\n\n"
                            f"Используйте меню сотрудника для просмотра заявки."
                        )
                    )
                
                logger.info(f"Sent transfer notifications for ticket {ticket_id}")
                
            except Exception as notify_error:
                logger.warning(
                    f"Failed to send transfer notifications for ticket {ticket_id}: {notify_error}"
                )
            
            # Send confirmation to administrator
            await callback.message.edit_text(
                f"✅ Заявка успешно передана!\n\n"
                f"Заявка #{ticket_id}\n"
                f"От: {from_staff.full_name if from_staff else 'Unknown'}\n"
                f"Кому: {to_staff.full_name if to_staff else 'Unknown'}\n\n"
                f"Уведомления отправлены обоим сотрудникам."
            )
            
            logger.info(
                f"Administrator {user_id} transferred ticket {ticket_id}: "
                f"from_staff_id={from_staff_id} → to_staff_id={to_staff_id}"
            )
            
        except ValueError as ve:
            await callback.answer(f"❌ {str(ve)}", show_alert=True)
            logger.warning(f"Ticket transfer failed: {ve}")
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error confirming ticket transfer: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при передаче заявки.", show_alert=True)
        await state.clear()


# ========== Client Transfer ==========


@router.callback_query(EmployeeCallback.filter(F.action == "transfer_clients"))
async def handle_transfer_clients_start(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Transfer All Clients" button press.
    
    Displays list of available managers to transfer all clients to.
    
    Requirements: 9.1, 9.2, 9.3, 9.4
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get source manager ID from callback data
        source_manager_id = callback_data.employee_id
        
        if not source_manager_id:
            await callback.answer("❌ ID менеджера не указан.", show_alert=True)
            return
        
        # Fetch source manager details
        stmt = select(Staff_Member).where(Staff_Member.id == source_manager_id)
        result = await session.execute(stmt)
        source_manager = result.scalar_one_or_none()
        
        if not source_manager:
            await callback.answer("❌ Менеджер не найден.", show_alert=True)
            return
        
        # Verify source is a manager (Requirement 9.1, 9.2)
        if source_manager.staff_role != StaffRole.MANAGER:
            await callback.message.edit_text(
                "❌ Передача клиентов доступна только для менеджеров.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 Назад к карточке",
                        callback_data=EmployeeCallback(
                            action="view",
                            employee_id=source_manager_id
                        ).pack()
                    )
                ]])
            )
            return
        
        # Fetch all active managers except the source manager (Requirement 9.3, 9.4)
        managers_stmt = select(Staff_Member).where(
            and_(
                Staff_Member.is_active == True,
                Staff_Member.staff_role == StaffRole.MANAGER,
                Staff_Member.id != source_manager_id
            )
        ).order_by(Staff_Member.full_name)
        managers_result = await session.execute(managers_stmt)
        available_managers = list(managers_result.scalars().all())
        
        if not available_managers:
            await callback.message.edit_text(
                "❌ Нет доступных менеджеров для передачи клиентов.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 Назад к карточке",
                        callback_data=EmployeeCallback(
                            action="view",
                            employee_id=source_manager_id
                        ).pack()
                    )
                ]])
            )
            return
        
        # Store source manager ID in FSM data for later use
        await state.update_data(transferring_from_manager_id=source_manager_id)
        
        # Build manager selection keyboard
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        builder = InlineKeyboardBuilder()
        
        for manager in available_managers:
            builder.button(
                text=manager.full_name,
                callback_data=EmployeeCallback(
                    action="show_transfer_confirmation",
                    employee_id=manager.id
                )
            )
        
        # Cancel button (Requirement 9.4)
        builder.button(
            text="❌ Отмена",
            callback_data=EmployeeCallback(action="view", employee_id=source_manager_id)
        )
        
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"👤 Передача всех клиентов\n\n"
            f"От менеджера: {source_manager.full_name}\n\n"
            f"Выберите целевого менеджера:",
            reply_markup=builder.as_markup()
        )
        
        logger.info(
            f"Administrator {user_id} started client transfer from manager {source_manager_id}"
        )
        
    except Exception as e:
        logger.error(
            f"Error starting client transfer: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(EmployeeCallback.filter(F.action == "show_transfer_confirmation"))
async def handle_show_transfer_confirmation(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Display confirmation dialog for client transfer.
    
    Shows warning message with source and target manager names.
    
    Requirements: 9.5, 9.6, 9.7, 9.8
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get source manager ID from FSM data
        data = await state.get_data()
        source_manager_id = data.get("transferring_from_manager_id")
        
        if not source_manager_id:
            await callback.answer("❌ Ошибка: данные не найдены.", show_alert=True)
            await state.clear()
            return
        
        # Get target manager ID from callback data
        target_manager_id = callback_data.employee_id
        
        if not target_manager_id:
            await callback.answer("❌ ID менеджера не указан.", show_alert=True)
            return
        
        # Fetch both managers
        source_stmt = select(Staff_Member).where(Staff_Member.id == source_manager_id)
        source_result = await session.execute(source_stmt)
        source_manager = source_result.scalar_one_or_none()
        
        target_stmt = select(Staff_Member).where(Staff_Member.id == target_manager_id)
        target_result = await session.execute(target_stmt)
        target_manager = target_result.scalar_one_or_none()
        
        if not source_manager or not target_manager:
            await callback.answer("❌ Менеджер не найден.", show_alert=True)
            await state.clear()
            return
        
        # Display confirmation prompt with warning (Requirements 9.5, 9.6, 9.7)
        from bots.tg_bot.keyboards.admin_kb import get_client_transfer_confirmation_keyboard
        
        await callback.message.edit_text(
            f"⚠️ Подтверждение передачи клиентов\n\n"
            f"Эта операция передаст ВСЕХ клиентов (по ИНН) от выбранного менеджера "
            f"другому менеджеру через API i-TAT.\n\n"
            f"От: {source_manager.full_name}\n"
            f"Кому: {target_manager.full_name}\n\n"
            f"Вы уверены?",
            reply_markup=await get_client_transfer_confirmation_keyboard(
                source_employee_id=source_manager_id,
                target_employee_id=target_manager_id
            )
        )
        
        logger.info(
            f"Administrator {user_id} viewing transfer confirmation: "
            f"from={source_manager_id} to={target_manager_id}"
        )
        
    except Exception as e:
        logger.error(
            f"Error showing transfer confirmation: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(EmployeeCallback.filter(F.action == "confirm_transfer"))
async def handle_confirm_client_transfer(
    callback: CallbackQuery,
    callback_data: EmployeeCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Execute client transfer after confirmation.
    
    Transfers all clients from source manager to target manager via i-TAT API.
    
    Requirements: 9.9, 9.10, 9.11, 9.12, 9.13
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к административной панели.",
                show_alert=True
            )
            return
        
        # Get source manager ID from callback data (stored in employee_id)
        source_manager_id = callback_data.employee_id
        
        # Get target manager ID from callback data (stored in page field)
        target_manager_id = callback_data.page
        
        if not source_manager_id or not target_manager_id:
            await callback.answer("❌ Ошибка: данные не найдены.", show_alert=True)
            await state.clear()
            return
        
        # Transfer all clients (Requirement 9.10)
        from services.employee_service import transfer_all_clients
        
        try:
            transferred_count = await transfer_all_clients(
                session=session,
                from_manager_id=source_manager_id,
                to_manager_id=target_manager_id
            )
            
            # Get manager details for logging and display
            source_stmt = select(Staff_Member).where(Staff_Member.id == source_manager_id)
            source_result = await session.execute(source_stmt)
            source_manager = source_result.scalar_one_or_none()
            
            target_stmt = select(Staff_Member).where(Staff_Member.id == target_manager_id)
            target_result = await session.execute(target_stmt)
            target_manager = target_result.scalar_one_or_none()
            
            # Log action with ActionType.CLIENTS_TRANSFERRED (Requirement 9.11)
            from database.models import Action_Log, ActionType
            action_log = Action_Log(
                action_type=ActionType.CLIENTS_TRANSFERRED,
                staff_id=admin.id,
                action_details={
                    "from_manager_id": source_manager_id,
                    "to_manager_id": target_manager_id,
                    "from_manager_name": source_manager.full_name if source_manager else "Unknown",
                    "to_manager_name": target_manager.full_name if target_manager else "Unknown",
                    "transferred_count": transferred_count
                }
            )
            session.add(action_log)
            await session.commit()
            
            # Display confirmation with transfer count (Requirement 9.12)
            if transferred_count > 0:
                confirmation_text = (
                    f"✅ Клиенты успешно переданы!\n\n"
                    f"От: {source_manager.full_name if source_manager else 'Unknown'}\n"
                    f"Кому: {target_manager.full_name if target_manager else 'Unknown'}\n\n"
                    f"Передано клиентов (ИНН): {transferred_count}\n\n"
                    f"⚠️ Примечание: API i-TAT для передачи клиентов еще не реализован. "
                    f"Операция была зарегистрирована, но фактическая передача в CRM не выполнена."
                )
            else:
                confirmation_text = (
                    f"ℹ️ Передача клиентов\n\n"
                    f"От: {source_manager.full_name if source_manager else 'Unknown'}\n"
                    f"Кому: {target_manager.full_name if target_manager else 'Unknown'}\n\n"
                    f"У менеджера нет клиентов для передачи."
                )
            
            # Return to employee card (Requirement 9.13)
            await callback.message.edit_text(
                confirmation_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 Назад к карточке",
                        callback_data=EmployeeCallback(
                            action="view",
                            employee_id=source_manager_id
                        ).pack()
                    )
                ]])
            )
            
            logger.info(
                f"Administrator {user_id} transferred clients: "
                f"from_manager_id={source_manager_id} → to_manager_id={target_manager_id}, "
                f"count={transferred_count}"
            )
            
        except ValueError as ve:
            await callback.message.edit_text(
                f"❌ {str(ve)}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 Назад к карточке",
                        callback_data=EmployeeCallback(
                            action="view",
                            employee_id=source_manager_id
                        ).pack()
                    )
                ]])
            )
            logger.warning(f"Client transfer failed: {ve}")
        
        # Clear FSM state (Requirement 9.13)
        await state.clear()
        
    except Exception as e:
        logger.error(
            f"Error confirming client transfer: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка при передаче клиентов.", show_alert=True)
        await state.clear()


@router.callback_query(BackupManagerCallback.filter(F.action == "back_to_config"))
async def handle_back_to_backup_config(
    callback: CallbackQuery,
    callback_data: BackupManagerCallback,
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle "Back" button from backup manager selection.
    
    Returns to backup manager configuration screen.
    """
    await callback.answer()
    
    try:
        # Redirect to backup config handler
        employee_callback = EmployeeCallback(
            action="backups",
            employee_id=callback_data.employee_id
        )
        
        await handle_backup_manager_config(
            callback=callback,
            callback_data=employee_callback,
            session=session,
            state=state
        )
        
    except Exception as e:
        logger.error(
            f"Error returning to backup config: user={callback.from_user.id}, error={e}",
            exc_info=True
        )
        await callback.answer("❌ Произошла ошибка.", show_alert=True)
