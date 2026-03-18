"""
Calendar Management Handlers

Handlers for admin calendar/work schedule management.
Supports natural language commands and visual calendar interfaces.
"""

import logging

from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, BaseFilter, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.states import CalendarStates
from bots.tg_bot.callback_datas import CalendarCallback
from services.calendar_parser import CalendarCommandParser
from services.calendar_service import CalendarService
from services.calendar_formatter import CalendarFormatter

logger = logging.getLogger(__name__)

router = Router(name="admin_calendar_management")


# ========== Custom Filters ==========


class IsAdminFilter(BaseFilter):
    """Filter to check if user is an administrator."""
    
    async def __call__(self, message: Message, session: AsyncSession) -> bool:
        """Check if user is admin in database."""
        user_id = message.from_user.id
        admin = await is_admin(session, user_id)
        result = admin is not None
        logger.info(f"[CALENDAR ROUTER] IsAdminFilter check: user_id={user_id}, is_admin={result}")
        return result


# ========== Helper Functions ==========


async def is_admin(session: AsyncSession, user_id: int):
    """
    Check if user is an administrator.
    
    Args:
        session: Database session
        user_id: Telegram user ID
    
    Returns:
        Staff_Member object if user is admin, None otherwise
    """
    try:
        from sqlalchemy import select
        from database.models import Staff_Member, StaffRole
        
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


# ========== Calendar Menu Handlers ==========


@router.callback_query(F.data == "calendar")
async def handle_calendar_callback_router(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Router wrapper for handle_calendar_callback."""
    await handle_calendar_callback(callback, session, state)


async def handle_calendar_callback(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """
    Handle "Back to Calendar" button press.
    Returns to the main calendar menu.
    """
    await callback.answer()

    # Clear FSM state when returning to main calendar menu
    await state.clear()
    logger.info(f"[CALENDAR ROUTER] Cleared FSM state for user {callback.from_user.id}")

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

        # Import calendar services
        from datetime import datetime
        import pytz
        from bots.tg_bot.keyboards.calendar_kb import get_calendar_main_keyboard

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

        logger.info(f"Administrator {user_id} returned to calendar menu")

    except Exception as e:
        logger.error(f"Error showing calendar menu: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке календаря.",
            show_alert=True
        )



@router.callback_query(F.data == "admin_panel")
async def handle_admin_panel_callback(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """
    Handle "Back to Admin Panel" button press.
    Returns to the main admin panel menu.
    """
    await callback.answer()
    
    # Clear FSM state when returning to admin panel
    await state.clear()
    logger.info(f"[CALENDAR ROUTER] Cleared FSM state for user {callback.from_user.id}")
    
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
        
        # Import admin panel keyboard
        from bots.tg_bot.keyboards.admin_kb import get_admin_panel_keyboard
        
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
        
        logger.info(f"Administrator {user_id} returned to admin panel")
        
    except Exception as e:
        logger.error(f"Error showing admin panel: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке административной панели.",
            show_alert=True
        )


@router.callback_query(F.data == "calendar_weekly")
async def handle_weekly_view_callback(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Wrapper for handle_weekly_view with callback routing."""
    await handle_weekly_view(callback, session)


@router.callback_query(F.data == "calendar_monthly")
async def handle_monthly_view_callback(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Wrapper for handle_monthly_view with callback routing."""
    await handle_monthly_view(callback, session)


@router.callback_query(F.data == "calendar_rules")
async def handle_rule_list_callback(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Wrapper for handle_rule_list with callback routing."""
    logger.info(f"[CALENDAR ROUTER] handle_rule_list_callback called by user {callback.from_user.id}")
    await handle_rule_list(callback, session, state)


@router.callback_query(F.data == "calendar_examples")
async def handle_command_examples_callback(callback: CallbackQuery) -> None:
    """Wrapper for handle_command_examples with callback routing."""
    await handle_command_examples(callback)


@router.callback_query(F.data == "calendar_clear")
async def handle_clear_period_start_callback(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Wrapper for handle_clear_period_start with callback routing."""
    await handle_clear_period_start(callback, state, session)


@router.callback_query(F.data == "calendar_clear_confirm")
async def handle_clear_period_confirm_callback(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Wrapper for handle_clear_period_confirm with callback routing."""
    await handle_clear_period_confirm(callback, state, session)


@router.callback_query(F.data == "calendar_clear_cancel")
async def handle_clear_period_cancel_callback(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Wrapper for handle_clear_period_cancel with callback routing."""
    await handle_clear_period_cancel(callback, state)


# ========== Confirmation Handlers ==========


@router.callback_query(CalendarCallback.filter(F.action == "confirm_add"))
async def handle_confirm_add_rule_callback(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Handle confirmation of adding a calendar rule."""
    await handle_confirm_add_rule(callback, state, session)


@router.callback_query(CalendarCallback.filter(F.action == "cancel_add"))
async def handle_cancel_add_rule_callback(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Handle cancellation of adding a calendar rule."""
    await handle_cancel_add_rule(callback, state, session)


@router.callback_query(CalendarCallback.filter(F.action == "confirm_delete"))
async def handle_confirm_delete_rule_callback(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Handle confirmation of deleting a calendar rule."""
    await handle_confirm_delete_rule(callback, state, session)


@router.callback_query(CalendarCallback.filter(F.action == "cancel_delete"))
async def handle_cancel_delete_rule_callback(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Handle cancellation of deleting a calendar rule."""
    await handle_cancel_delete_rule(callback, state, session)


@router.callback_query(CalendarCallback.filter(F.action == "next_month"))
async def handle_next_month_callback(
    callback: CallbackQuery, callback_data: CalendarCallback, state: FSMContext, session: AsyncSession
) -> None:
    """Handle navigation to next month in rule list."""
    await handle_rule_list(
        callback, 
        session, 
        state, 
        target_year=callback_data.year, 
        target_month=callback_data.month
    )


@router.callback_query(CalendarCallback.filter(F.action == "prev_month"))
async def handle_prev_month_callback(
    callback: CallbackQuery, callback_data: CalendarCallback, state: FSMContext, session: AsyncSession
) -> None:
    """Handle navigation to previous month in rule list."""
    await handle_rule_list(
        callback, 
        session, 
        state, 
        target_year=callback_data.year, 
        target_month=callback_data.month
    )


# ========== Text Message Handlers ==========


@router.message(StateFilter(CalendarStates.waiting_for_clear_period_input), F.text)
async def handle_clear_period_input_message(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Handler for text input during period clearing flow."""
    await handle_clear_period_input(message, state, session)


@router.message(StateFilter(CalendarStates.managing_calendar), F.text)
async def handle_calendar_text_commands(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """
    Handle text commands for calendar management (add rule, delete rule).
    Only processes commands from admin users when in managing_calendar state.
    """
    user_id = message.from_user.id
    
    # Check if user is an administrator manually to bypass inner middleware dependency issues
    admin = await is_admin(session, user_id)
    if not admin:
        logger.warning(f"Non-admin user {user_id} attempted to use calendar text commands.")
        await state.clear()
        return

    current_state = await state.get_state()
    
    logger.info(
        f"[CALENDAR ROUTER] handle_calendar_text_commands called: "
        f"user_id={user_id}, state={current_state}, text='{message.text[:50] if message.text else None}'"
    )
    
    # Check if message is a delete command
    if message.text and message.text.lower().startswith("удалить правило"):
        logger.info(f"[CALENDAR ROUTER] Processing delete rule command")
        await handle_delete_rule_text(message, state, session)
        return
    
    # Check if message looks like an add rule command
    # (contains date-related keywords)
    text_lower = message.text.lower() if message.text else ""
    date_keywords = ["января", "февраля", "марта", "апреля", "мая", "июня",
                     "июля", "августа", "сентября", "октября", "ноября", "декабря",
                     "рабочее время", "продленное", "нерабочее"]
    
    if any(keyword in text_lower for keyword in date_keywords):
        logger.info(f"[CALENDAR ROUTER] Processing add rule command")
        await handle_add_rule_text(message, state, session)
        return
    
    # If we got here, it's not a recognized calendar command
    # Show error with examples
    logger.info(f"[CALENDAR ROUTER] Not a recognized calendar command, showing examples")
    formatter = CalendarFormatter()
    examples_text = formatter.format_command_examples()
    
    await message.answer(
        "❌ Команда не распознана.\n\n"
        "Пожалуйста, используйте один из следующих форматов:\n\n"
        f"{examples_text}",
        parse_mode="HTML"
    )


# ========== Calendar View Handlers ==========


async def handle_calendar_menu(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """
    Display the main calendar management menu.
    Shows current status, active rules, and action buttons.
    """
    # Implementation placeholder
    await callback.answer("Календарь работы")


async def handle_add_rule_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """
    Process text commands for adding schedule rules.
    Parses natural language input and creates rules.
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 14.1, 14.2, 14.3, 14.4, 15.1, 15.3
    """
    try:
        user_id = message.from_user.id
        logger.info(
            f"[CALENDAR ROUTER] handle_add_rule_text called by user {user_id}, "
            f"text='{message.text[:100] if message.text else None}'"
        )
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await message.answer(
                "❌ У вас нет доступа к управлению календарем.\n"
                "Эта функция доступна только администраторам."
            )
            logger.warning(f"Non-admin user {user_id} attempted to add calendar rule")
            return
        
        logger.info(f"[CALENDAR ROUTER] User {user_id} is admin, parsing command")
        
        # Parse command
        parser = CalendarCommandParser()
        parsed_rule = parser.parse_add_rule_command(message.text)
        
        if not parsed_rule:
            # Parsing failed - display error with examples
            formatter = CalendarFormatter()
            examples_text = formatter.format_command_examples()
            
            await message.answer(
                "❌ Не удалось распознать команду.\n\n"
                "Пожалуйста, используйте один из следующих форматов:\n\n"
                f"{examples_text}",
                parse_mode="HTML"
            )
            logger.warning(
                f"[CALENDAR ROUTER] Failed to parse add rule command: "
                f"user_id={user_id}, text='{message.text}'"
            )
            return
        
        # Validate dates - prevent rules on past dates
        from datetime import datetime
        import pytz
        
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_date = datetime.now(moscow_tz).date()
        
        # Check if end_date is in the past
        if parsed_rule.end_date < current_date:
            await message.answer(
                "❌ Нельзя создать правило на прошедшие даты.\n\n"
                f"Конечная дата правила: {parsed_rule.end_date.strftime('%d.%m.%Y')}\n"
                f"Сегодня: {current_date.strftime('%d.%m.%Y')}\n\n"
                "Пожалуйста, укажите даты в будущем или включающие сегодняшний день.",
                parse_mode="HTML"
            )
            logger.warning(
                f"[CALENDAR ROUTER] Rejected rule with past end_date: "
                f"user_id={user_id}, end_date={parsed_rule.end_date}, current_date={current_date}"
            )
            return
        
        # If start_date is in the past but end_date is in the future, allow it
        # (period spanning past and future)
        if parsed_rule.start_date < current_date < parsed_rule.end_date:
            logger.info(
                f"[CALENDAR ROUTER] Allowing rule with past start_date but future end_date: "
                f"user_id={user_id}, start_date={parsed_rule.start_date}, end_date={parsed_rule.end_date}"
            )
        
        # Store parsed rule data in FSM for confirmation
        await state.update_data(
            pending_rule={
                "start_date": parsed_rule.start_date.isoformat(),
                "end_date": parsed_rule.end_date.isoformat(),
                "work_mode": parsed_rule.work_mode.value,
                "work_start_time": parsed_rule.work_start_time.isoformat() if parsed_rule.work_start_time else None,
                "work_end_time": parsed_rule.work_end_time.isoformat() if parsed_rule.work_end_time else None,
                "original_text": message.text
            }
        )
        
        # Format confirmation message
        formatter = CalendarFormatter()
        
        # Create temporary rule object for formatting
        from database.models import Calendar_Rule, WorkMode
        from datetime import datetime
        
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
        
        # Create inline keyboard with confirm/cancel buttons
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from bots.tg_bot.callback_datas import CalendarCallback
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=CalendarCallback(action="confirm_add").pack()
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=CalendarCallback(action="cancel_add").pack()
                )
            ]
        ])
        
        await message.answer(
            f"📝 <b>Ваша команда:</b>\n{message.text}\n\n"
            f"<b>Интерпретация системы:</b>\n{preview_text}\n\n"
            "Подтвердите добавление правила:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        # Set state to confirming
        await state.set_state(CalendarStates.confirming_add_rule)
        
        logger.info(
            f"[CALENDAR ROUTER] Showing confirmation for add rule: "
            f"user_id={user_id}, dates={parsed_rule.start_date} to {parsed_rule.end_date}"
        )
            
    except Exception as e:
        logger.error(f"Error handling add rule text: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке команды.\n"
            "Пожалуйста, попробуйте позже."
        )


async def handle_confirm_add_rule(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """
    Confirm and save the pending calendar rule.
    
    Requirements: 10.1, 17.1
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        logger.info(f"[CALENDAR ROUTER] handle_confirm_add_rule called by user {user_id}")
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.message.edit_text(
                "❌ У вас нет доступа к управлению календарем."
            )
            return
        
        # Get pending rule data from FSM
        data = await state.get_data()
        pending_rule = data.get("pending_rule")
        
        if not pending_rule:
            await callback.message.edit_text(
                "❌ Данные правила не найдены. Пожалуйста, введите команду заново."
            )
            await state.clear()
            return
        
        # Parse stored data
        from datetime import date, time
        from database.models import WorkMode
        
        start_date = date.fromisoformat(pending_rule["start_date"])
        end_date = date.fromisoformat(pending_rule["end_date"])
        work_mode = WorkMode(pending_rule["work_mode"])
        work_start_time = time.fromisoformat(pending_rule["work_start_time"]) if pending_rule["work_start_time"] else None
        work_end_time = time.fromisoformat(pending_rule["work_end_time"]) if pending_rule["work_end_time"] else None
        
        # Create rule with CalendarService
        calendar_service = CalendarService()
        
        try:
            new_rule = await calendar_service.create_rule(
                session=session,
                start_date=start_date,
                end_date=end_date,
                work_mode=work_mode,
                work_start_time=work_start_time,
                work_end_time=work_end_time
            )
            
            # Log rule creation
            from database.models import Action_Log, ActionType
            action_log = Action_Log(
                action_type=ActionType.CALENDAR_RULE_CREATED,
                staff_id=admin.id,
                action_details={
                    "rule_id": new_rule.id,
                    "start_date": str(new_rule.start_date),
                    "end_date": str(new_rule.end_date),
                    "work_mode": new_rule.work_mode.value,
                    "work_start_time": str(new_rule.work_start_time) if new_rule.work_start_time else None,
                    "work_end_time": str(new_rule.work_end_time) if new_rule.work_end_time else None,
                    "priority": new_rule.rule_priority
                }
            )
            session.add(action_log)
            await session.commit()
            
            # Format confirmation
            formatter = CalendarFormatter()
            confirmation_text = formatter.format_rule_confirmation(new_rule)
            
            # Get calendar main menu keyboard
            from bots.tg_bot.keyboards.calendar_kb import get_calendar_main_keyboard
            keyboard = get_calendar_main_keyboard()
            
            await callback.message.edit_text(
                f"✅ Правило успешно добавлено!\n\n{confirmation_text}",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            # Clear state and return to main calendar menu
            await state.clear()
            
            logger.info(
                f"[CALENDAR ROUTER] Successfully created calendar rule: "
                f"user_id={user_id}, rule_id={new_rule.id}, "
                f"dates={new_rule.start_date} to {new_rule.end_date}"
            )
            
        except Exception as db_error:
            await session.rollback()
            logger.error(
                f"[CALENDAR ROUTER] Database error creating calendar rule: "
                f"user_id={user_id}, error={db_error}",
                exc_info=True
            )
            await callback.message.edit_text(
                "❌ Произошла ошибка при сохранении правила.\n"
                "Пожалуйста, попробуйте позже."
            )
            await state.clear()
            
    except Exception as e:
        logger.error(f"Error confirming add rule: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при подтверждении правила."
        )
        await state.clear()


async def handle_cancel_add_rule(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """
    Cancel adding a calendar rule and return to input.
    
    Requirements: 10.1, 17.1
    """
    await callback.answer("Отменено")
    
    try:
        user_id = callback.from_user.id
        logger.info(f"[CALENDAR ROUTER] handle_cancel_add_rule called by user {user_id}")
        
        # Get original text from FSM
        data = await state.get_data()
        pending_rule = data.get("pending_rule")
        original_text = pending_rule.get("original_text") if pending_rule else None
        
        # Return to managing_calendar state for re-input
        await state.set_state(CalendarStates.managing_calendar)
        
        await callback.message.edit_text(
            "❌ Добавление правила отменено.\n\n"
            "Введите команду заново или используйте кнопки меню:",
            parse_mode="HTML"
        )
        
        logger.info(f"[CALENDAR ROUTER] Cancelled add rule for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error cancelling add rule: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при отмене."
        )
        await state.clear()


async def handle_weekly_view(callback: CallbackQuery, session: AsyncSession) -> None:
    """
    Display calendar view for the current week (7 days).
    
    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
    """
    await callback.answer()
    
    try:
        from datetime import datetime, timedelta
        import pytz
        from bots.tg_bot.keyboards.calendar_kb import get_back_to_calendar_keyboard
        
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
        
        # Get back to calendar keyboard
        keyboard = get_back_to_calendar_keyboard()
        
        # Display weekly view
        await callback.message.edit_text(
            view_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        import logging
        logging.error(f"Error showing weekly view: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке недельного вида.",
            show_alert=True
        )


async def handle_monthly_view(callback: CallbackQuery, session: AsyncSession) -> None:
    """
    Display calendar view for the current month.
    
    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
    """
    await callback.answer()
    
    try:
        from datetime import datetime
        import pytz
        from bots.tg_bot.keyboards.calendar_kb import get_back_to_calendar_keyboard
        
        # Initialize services
        calendar_service = CalendarService()
        calendar_formatter = CalendarFormatter()
        
        # Get current Moscow time
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_dt = datetime.now(moscow_tz)
        year = current_dt.year
        month = current_dt.month
        
        # Get first and last day of month
        from calendar import monthrange
        from datetime import date
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        
        # Get rules for the month
        rules = await calendar_service.get_rules_for_date_range(
            session, first_day, last_day
        )
        
        # Format monthly view
        view_text = calendar_formatter.format_monthly_view(year, month, rules)
        
        # Get back to calendar keyboard
        keyboard = get_back_to_calendar_keyboard()
        
        # Display monthly view
        # Check if message is too long and needs splitting
        if len(view_text) > 4096:
            # Split into multiple messages
            parts = []
            current_part = ""
            for line in view_text.split('\n'):
                if len(current_part) + len(line) + 1 > 4000:
                    parts.append(current_part)
                    current_part = line + '\n'
                else:
                    current_part += line + '\n'
            if current_part:
                parts.append(current_part)
            
            # Send first part with edit
            await callback.message.edit_text(
                parts[0],
                parse_mode="HTML"
            )
            
            # Send remaining parts as new messages
            for part in parts[1:-1]:
                await callback.message.answer(
                    part,
                    parse_mode="HTML"
                )
            
            # Send last part with keyboard
            if len(parts) > 1:
                await callback.message.answer(
                    parts[-1],
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        else:
            # Single message
            await callback.message.edit_text(
                view_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
    except Exception as e:
        import logging
        logging.error(f"Error showing monthly view: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке месячного вида.",
            show_alert=True
        )


async def handle_rule_list(
    callback: CallbackQuery, 
    session: AsyncSession, 
    state: FSMContext,
    target_year: int | None = None,
    target_month: int | None = None
) -> None:
    """
    Display list of all active schedule rules with numbers and month pagination.
    
    Args:
        callback: Callback query
        session: Database session
        state: FSM context
        target_year: Specific year to display (None = first month with rules)
        target_month: Specific month to display (None = first month with rules)
    
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
    """
    await callback.answer()
    
    def _get_month_name_ru(month: int) -> str:
        """Get Russian month name."""
        months = {
            1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
            5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
            9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
        }
        return months.get(month, "")
    
    try:
        logger.info(f"[CALENDAR ROUTER] handle_rule_list called by user {callback.from_user.id}")
        
        from bots.tg_bot.keyboards.calendar_kb import get_back_to_calendar_keyboard, get_rule_list_pagination_keyboard
        
        # Set FSM state to managing_calendar so text commands are processed
        await state.set_state(CalendarStates.managing_calendar)
        logger.info(f"[CALENDAR ROUTER] Set state to CalendarStates.managing_calendar for user {callback.from_user.id}")
        
        # Initialize services
        calendar_service = CalendarService()
        calendar_formatter = CalendarFormatter()
        
        # Get all rules
        rules = await calendar_service.get_all_rules(session)
        logger.info(f"[CALENDAR ROUTER] Found {len(rules)} rules")
        
        # First message: Instructions for adding rules (only on initial call, not pagination)
        if target_year is None and target_month is None:
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
                "<b>Варианты формулировок:</b>\n"
                "• Режим: <code>рабочее время</code> / <code>нерабочее время</code> / <code>продленное время</code>\n"
                "• Дата: <code>31 января</code> / <code>31.01</code> / <code>31 янв</code>\n"
                "• Время: <code>с 9 до 15</code> / <code>9-15</code> / <code>с 09:00 до 15:00</code>\n\n"
                "<i>После отправки команды система покажет интерпретацию и попросит подтверждение.</i>"
            )
            
            # Edit the callback message with instructions
            await callback.message.edit_text(
                instructions_text,
                parse_mode="HTML"
            )
        
        # Format rule list
        if not rules:
            list_text = (
                "📋 <b>Список правил</b>\n\n"
                "<i>Нет активных правил. Действует базовый график.</i>"
            )
            keyboard = get_back_to_calendar_keyboard()
        else:
            # Get current date for pagination starting point
            from datetime import datetime
            import pytz
            
            moscow_tz = pytz.timezone('Europe/Moscow')
            current_date = datetime.now(moscow_tz).date()
            
            # Determine which month to display
            if target_year is not None and target_month is not None:
                display_year = target_year
                display_month = target_month
            else:
                # Start with current month
                display_year = current_date.year
                display_month = current_date.month
            
            # Group rules by month for display
            from collections import defaultdict
            
            rules_by_month = defaultdict(list)
            for rule in rules:
                month_key = (rule.start_date.year, rule.start_date.month)
                rules_by_month[month_key].append(rule)
            
            # Get rules for display month
            display_month_key = (display_year, display_month)
            month_rules = rules_by_month.get(display_month_key, [])
            
            # Calculate prev/next months (always available, not limited to months with rules)
            # Previous month
            if display_month == 1:
                prev_year = display_year - 1
                prev_month = 12
            else:
                prev_year = display_year
                prev_month = display_month - 1
            
            # Next month
            if display_month == 12:
                next_year = display_year + 1
                next_month = 1
            else:
                next_year = display_year
                next_month = display_month + 1
            
            # Always show pagination buttons (user can navigate freely)
            has_prev = True
            has_next = True
            
            # Format month name
            month_name_ru = _get_month_name_ru(display_month) + f" {display_year}"
            
            lines = [
                f"📋 <b>Список правил - {month_name_ru}</b>",
                "<i>(упорядочены по приоритету)</i>\n"
            ]
            
            if not month_rules:
                lines.append("<i>Нет правил на этот месяц.</i>")
            else:
                # Calculate global rule numbers (across all months)
                # Sort all months to maintain consistent numbering
                all_months_sorted = sorted(rules_by_month.keys())
                
                rule_number = 1
                for month_key in all_months_sorted:
                    if month_key == display_month_key:
                        # This is our display month, add rules with numbers
                        for rule in rules_by_month[month_key]:
                            rule_str = calendar_formatter._format_rule_detail(rule_number, rule)
                            
                            # Check if adding this rule would exceed limit
                            potential_text = "\n".join(lines + [rule_str])
                            if len(potential_text) > 3800:
                                lines.append("\n<i>... (список сокращен из-за ограничения длины сообщения)</i>")
                                break
                            
                            lines.append(rule_str)
                            rule_number += 1
                        break
                    else:
                        # Count rules in previous months to maintain global numbering
                        rule_number += len(rules_by_month[month_key])
            
            lines.append("\n<i>Чтобы удалить правило, отправьте:</i>")
            lines.append("<code>Удалить правило [номер]</code>")
            
            list_text = "\n".join(lines)
            
            # Build pagination keyboard
            keyboard = get_rule_list_pagination_keyboard(
                current_year=display_year,
                current_month=display_month,
                has_prev=has_prev,
                has_next=has_next,
                prev_year=prev_year,
                prev_month=prev_month,
                next_year=next_year,
                next_month=next_month
            )
            
            logger.info(
                f"[CALENDAR ROUTER] Displaying month: {display_year}-{display_month:02d}, "
                f"rules_count={len(month_rules)}, prev={prev_year}-{prev_month:02d}, "
                f"next={next_year}-{next_month:02d}"
            )
        
        # Send or edit message based on whether this is initial call or pagination
        if target_year is None and target_month is None:
            # Initial call - send new message
            await callback.message.answer(
                list_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            # Pagination - edit existing message
            await callback.message.edit_text(
                list_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
    except Exception as e:
        import logging
        logging.error(f"Error showing rule list: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке списка правил.",
            show_alert=True
        )


async def handle_delete_rule_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """
    Process text commands for deleting rules by number - show confirmation.
    
    Requirements: 9.1, 9.2, 9.3, 9.5, 15.2, 15.3
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await message.answer(
                "❌ У вас нет доступа к управлению календарем.\n"
                "Эта функция доступна только администраторам."
            )
            logger.warning(f"Non-admin user {user_id} attempted to delete calendar rule")
            return
        
        # Parse delete command
        parser = CalendarCommandParser()
        rule_number = parser.parse_delete_rule_command(message.text)
        
        if rule_number is None:
            # Parsing failed - display error
            await message.answer(
                "❌ Не удалось распознать команду удаления.\n\n"
                "Используйте формат: <b>Удалить правило N</b>\n"
                "Например: Удалить правило 3\n\n"
                "Чтобы увидеть список правил с номерами, используйте кнопку "
                "📋 Список правил в меню календаря.",
                parse_mode="HTML"
            )
            logger.warning(
                f"[CALENDAR ROUTER] Failed to parse delete rule command: "
                f"user_id={user_id}, text='{message.text}'"
            )
            return
        
        # Get all rules to map number to ID
        calendar_service = CalendarService()
        all_rules = await calendar_service.get_all_rules(session)
        
        if not all_rules:
            await message.answer(
                "❌ Нет активных правил для удаления.\n\n"
                "Список правил пуст."
            )
            return
        
        # Check if rule number is valid
        if rule_number < 1 or rule_number > len(all_rules):
            await message.answer(
                f"❌ Правило с номером {rule_number} не найдено.\n\n"
                f"Всего правил: {len(all_rules)}\n"
                "Используйте кнопку 📋 Список правил для просмотра доступных номеров."
            )
            logger.info(f"Administrator {user_id} attempted to delete non-existent rule number: {rule_number}")
            return
        
        # Get the rule by number (1-indexed)
        rule_to_delete = all_rules[rule_number - 1]
        
        # Store rule data in FSM for confirmation
        await state.update_data(
            pending_delete={
                "rule_id": rule_to_delete.id,
                "rule_number": rule_number,
                "start_date": rule_to_delete.start_date.isoformat(),
                "end_date": rule_to_delete.end_date.isoformat(),
                "work_mode": rule_to_delete.work_mode.value,
                "work_start_time": rule_to_delete.work_start_time.isoformat() if rule_to_delete.work_start_time else None,
                "work_end_time": rule_to_delete.work_end_time.isoformat() if rule_to_delete.work_end_time else None,
                "original_text": message.text
            }
        )
        
        # Format preview message
        formatter = CalendarFormatter()
        preview_text = formatter.format_rule_preview(rule_to_delete)
        
        # Create inline keyboard with confirm/cancel buttons
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from bots.tg_bot.callback_datas import CalendarCallback
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить удаление",
                    callback_data=CalendarCallback(action="confirm_delete").pack()
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=CalendarCallback(action="cancel_delete").pack()
                )
            ]
        ])
        
        await message.answer(
            f"📝 <b>Ваша команда:</b>\n{message.text}\n\n"
            f"<b>Правило для удаления (#{rule_number}):</b>\n{preview_text}\n\n"
            "⚠️ Подтвердите удаление правила:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        # Set state to confirming
        await state.set_state(CalendarStates.confirming_delete_rule)
        
        logger.info(
            f"[CALENDAR ROUTER] Showing confirmation for delete rule: "
            f"user_id={user_id}, rule_number={rule_number}, rule_id={rule_to_delete.id}"
        )
        
    except Exception as e:
        logger.error(f"Error handling delete rule text: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке команды.\n"
            "Пожалуйста, попробуйте позже."
        )
    except Exception as e:
        logger.error(f"Error handling delete rule text: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке команды.\n"
            "Пожалуйста, попробуйте позже."
        )


async def handle_confirm_delete_rule(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """
    Confirm and execute the pending rule deletion.
    
    Requirements: 9.1, 9.2, 9.3, 9.5, 15.2, 15.3
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        logger.info(f"[CALENDAR ROUTER] handle_confirm_delete_rule called by user {user_id}")
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.message.edit_text(
                "❌ У вас нет доступа к управлению календарем."
            )
            return
        
        # Get pending delete data from FSM
        data = await state.get_data()
        pending_delete = data.get("pending_delete")
        
        if not pending_delete:
            await callback.message.edit_text(
                "❌ Данные правила не найдены. Пожалуйста, введите команду заново."
            )
            await state.clear()
            return
        
        rule_id = pending_delete["rule_id"]
        rule_number = pending_delete["rule_number"]
        
        # Delete rule
        calendar_service = CalendarService()
        success = await calendar_service.delete_rule(session, rule_id)
        
        if not success:
            await callback.message.edit_text(
                f"❌ Не удалось удалить правило {rule_number}.\n"
                "Возможно, оно уже было удалено."
            )
            await state.clear()
            return
        
        # Log rule deletion
        from database.models import Action_Log, ActionType
        action_log = Action_Log(
            action_type=ActionType.CALENDAR_RULE_DELETED,
            staff_id=admin.id,
            action_details={
                "rule_id": rule_id,
                "rule_number": rule_number,
                "start_date": pending_delete["start_date"],
                "end_date": pending_delete["end_date"],
                "work_mode": pending_delete["work_mode"]
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Format confirmation
        from datetime import date
        from database.models import WorkMode
        
        start_date = date.fromisoformat(pending_delete["start_date"])
        end_date = date.fromisoformat(pending_delete["end_date"])
        
        if start_date == end_date:
            date_str = start_date.strftime("%d.%m.%Y")
        else:
            date_str = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
        
        work_mode_display = {
            "regular": "Рабочее время",
            "extended": "Продленное рабочее время",
            "non_working": "Нерабочее время"
        }
        mode_str = work_mode_display.get(pending_delete["work_mode"], pending_delete["work_mode"])
        
        # Get calendar main menu keyboard
        from bots.tg_bot.keyboards.calendar_kb import get_calendar_main_keyboard
        keyboard = get_calendar_main_keyboard()
        
        await callback.message.edit_text(
            f"✅ Правило {rule_number} успешно удалено!\n\n"
            f"Даты: {date_str}\n"
            f"Режим: {mode_str}\n\n"
            f"Для этих дат теперь будет использоваться базовое расписание.",
            reply_markup=keyboard
        )
        
        # Clear state and return to main calendar menu
        await state.clear()
        
        logger.info(
            f"[CALENDAR ROUTER] Successfully deleted calendar rule: "
            f"user_id={user_id}, rule_id={rule_id}, rule_number={rule_number}"
        )
        
    except Exception as e:
        logger.error(f"Error confirming delete rule: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при удалении правила."
        )
        await state.clear()


async def handle_cancel_delete_rule(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """
    Cancel rule deletion and return to rule list.
    
    Requirements: 9.1, 9.2, 9.3
    """
    await callback.answer("Отменено")
    
    try:
        user_id = callback.from_user.id
        logger.info(f"[CALENDAR ROUTER] handle_cancel_delete_rule called by user {user_id}")
        
        # Return to managing_calendar state
        await state.set_state(CalendarStates.managing_calendar)
        
        await callback.message.edit_text(
            "❌ Удаление правила отменено.\n\n"
            "Введите команду заново или используйте кнопки меню:",
            parse_mode="HTML"
        )
        
        logger.info(f"[CALENDAR ROUTER] Cancelled delete rule for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error cancelling delete rule: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при отмене."
        )
        await state.clear()


async def handle_clear_period_start(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """
    Initiate period clearing flow, prompt for date range.
    
    Requirements: 10.1, 17.1
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к управлению календарем.",
                show_alert=True
            )
            logger.warning(f"Non-admin user {user_id} attempted to clear period")
            return
        
        # Import CalendarStates
        from bots.tg_bot.states import CalendarStates
        
        # Set FSM state to waiting for date range input
        await state.set_state(CalendarStates.waiting_for_clear_period_input)
        logger.info(
            f"[CALENDAR ROUTER] Set state to CalendarStates.waiting_for_clear_period_input "
            f"for user {user_id}"
        )
        
        # Display prompt for date range input
        from bots.tg_bot.keyboards.calendar_kb import get_back_to_calendar_keyboard
        
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
        
        keyboard = get_back_to_calendar_keyboard()
        
        await callback.message.edit_text(
            prompt_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} initiated period clearing flow")
        
    except Exception as e:
        logger.error(f"Error starting period clearing: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при запуске очистки периода.",
            show_alert=True
        )


async def handle_clear_period_input(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """
    Process date range input for period clearing.
    
    Requirements: 10.2, 10.3, 17.2
    """
    try:
        user_id = message.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await message.answer(
                "❌ У вас нет доступа к управлению календарем.\n"
                "Эта функция доступна только администраторам."
            )
            logger.warning(f"Non-admin user {user_id} attempted to input clear period")
            await state.clear()
            return
        
        # Parse date range with CalendarCommandParser
        parser = CalendarCommandParser()
        date_range = parser.parse_date_range(message.text)
        
        if not date_range:
            # Parsing failed - display error and stay in state
            await message.answer(
                "❌ Не удалось распознать диапазон дат.\n\n"
                "<b>Используйте формат:</b>\n"
                "• с [день] [месяц] по [день] [месяц]\n"
                "• с [день] по [день] [месяц]\n\n"
                "<b>Примеры:</b>\n"
                "• с 1 января по 31 января\n"
                "• с 1 по 15 февраля\n\n"
                "Попробуйте еще раз или отправьте /cancel для отмены.",
                parse_mode="HTML"
            )
            logger.info(f"Administrator {user_id} sent unparseable date range: {message.text}")
            return
        
        # Parsing succeeded - store date range in FSM data
        start_date, end_date = date_range
        await state.update_data(
            start_date=start_date,
            end_date=end_date
        )
        
        # Get count of rules to be deleted
        calendar_service = CalendarService()
        rules_to_delete = await calendar_service.get_rules_for_date_range(
            session, start_date, end_date
        )
        count = len(rules_to_delete)
        
        # Display confirmation prompt with count
        from bots.tg_bot.keyboards.calendar_kb import get_clear_period_confirmation_keyboard
        
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
        
        keyboard = get_clear_period_confirmation_keyboard()
        
        await message.answer(
            confirmation_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        # Set FSM state to waiting for confirmation
        from bots.tg_bot.states import CalendarStates
        await state.set_state(CalendarStates.waiting_for_clear_period_confirmation)
        
        logger.info(
            f"Administrator {user_id} entered date range for clearing: "
            f"{start_date} to {end_date}, {count} rules to delete"
        )
        
    except Exception as e:
        logger.error(f"Error handling clear period input: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке диапазона дат.\n"
            "Пожалуйста, попробуйте позже."
        )
        await state.clear()


async def handle_clear_period_confirm(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """
    Execute period clearing after confirmation.
    
    Requirements: 10.4, 10.5, 17.3, 15.3
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        admin = await is_admin(session, user_id)
        if not admin:
            await callback.answer(
                "❌ У вас нет доступа к управлению календарем.",
                show_alert=True
            )
            logger.warning(f"Non-admin user {user_id} attempted to confirm period clearing")
            await state.clear()
            return
        
        # Get date range from FSM data
        data = await state.get_data()
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not start_date or not end_date:
            await callback.message.edit_text(
                "❌ Ошибка: диапазон дат не найден.\n"
                "Пожалуйста, начните процесс заново."
            )
            await state.clear()
            logger.error(f"Missing date range in FSM data for user {user_id}")
            return
        
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
        from bots.tg_bot.keyboards.calendar_kb import get_back_to_calendar_keyboard
        keyboard = get_back_to_calendar_keyboard()
        
        await callback.message.edit_text(
            confirmation_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        # Log period clearing with admin ID
        from database.models import Action_Log, ActionType
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
            f"Administrator {user_id} ({admin.full_name}) cleared calendar period: "
            f"{start_date} to {end_date}, deleted {deleted_count} rules"
        )
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error confirming period clearing: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при очистке периода.",
            show_alert=True
        )
        await state.clear()


async def handle_clear_period_cancel(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """
    Cancel period clearing and return to main calendar menu.
    
    Requirements: 17.3
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Clear FSM state
        await state.clear()
        
        # Return to main calendar menu
        from datetime import datetime
        import pytz
        from bots.tg_bot.keyboards.calendar_kb import get_calendar_main_keyboard
        from sqlalchemy.ext.asyncio import AsyncSession
        
        # Get session from callback (we need to handle this differently)
        # For now, just show a simple cancellation message with back button
        from bots.tg_bot.keyboards.calendar_kb import get_back_to_calendar_keyboard
        
        await callback.message.edit_text(
            "❌ <b>Очистка периода отменена</b>\n\n"
            "Возвращайтесь в меню календаря для управления расписанием.",
            reply_markup=get_back_to_calendar_keyboard(),
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} cancelled period clearing")
        
    except Exception as e:
        logger.error(f"Error cancelling period clearing: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при отмене.",
            show_alert=True
        )
        await state.clear()


async def handle_command_examples(callback: CallbackQuery) -> None:
    """
    Display examples of valid text commands.
    
    Requirements: 13.1, 13.2, 13.3, 13.4, 13.5
    """
    await callback.answer()
    
    try:
        from bots.tg_bot.keyboards.calendar_kb import get_back_to_calendar_keyboard
        
        # Initialize formatter
        calendar_formatter = CalendarFormatter()
        
        # Format command examples
        examples_text = calendar_formatter.format_command_examples()
        
        # Get back to calendar keyboard
        keyboard = get_back_to_calendar_keyboard()
        
        # Display command examples
        await callback.message.edit_text(
            examples_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        import logging
        logging.error(f"Error showing command examples: {e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке примеров команд.",
            show_alert=True
        )



# ========== Cancel Handler ==========


@router.message(Command("cancel"), StateFilter(CalendarStates))
async def handle_calendar_cancel(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle /cancel command during calendar operations.
    
    Clears FSM state and returns to main calendar menu.
    
    Requirements: 17.4
    """
    user_id = message.from_user.id
    
    # Get current state for logging
    current_state = await state.get_state()
    
    # Clear FSM state
    await state.clear()
    
    logger.info(
        f"Administrator {user_id} cancelled calendar operation, "
        f"previous state: {current_state or 'None'}"
    )
    
    # Verify user is administrator
    admin = await is_admin(session, user_id)
    if not admin:
        await message.answer(
            "❌ У вас нет доступа к административной панели."
        )
        return
    
    try:
        # Import calendar services
        from datetime import datetime
        import pytz
        from bots.tg_bot.keyboards.calendar_kb import get_calendar_main_keyboard
        
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
        
        # Display calendar menu with cancellation message
        await message.answer(
            "❌ Операция отменена.\n\n" + menu_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(
            f"Error in calendar cancel handler for user {user_id}: {e}",
            exc_info=True
        )
        # Fallback - just show cancellation message
        await message.answer(
            "❌ Операция отменена. Используйте /admin для возврата в административную панель."
        )