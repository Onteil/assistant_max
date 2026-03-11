"""
Calendar Keyboards

Keyboard builders for calendar management interface.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_calendar_main_keyboard() -> InlineKeyboardMarkup:
    """
    Build main calendar menu keyboard.

    Buttons:
    - [📅 На неделю] [📅 На месяц]
    - [📋 Список правил] [🗑 Очистить период]
    - [❓ Пример команд]
    - [◀️ Назад в админ-панель]
    """
    builder = InlineKeyboardBuilder()

    # Row 1: Weekly and monthly views
    builder.row(
        InlineKeyboardButton(text="📅 На неделю", callback_data="calendar_weekly"),
        InlineKeyboardButton(text="📅 На месяц", callback_data="calendar_monthly"),
    )

    # Row 2: Rule list and clear period
    builder.row(
        InlineKeyboardButton(text="📋 Список правил", callback_data="calendar_rules"),
        InlineKeyboardButton(
            text="🗑 Очистить период", callback_data="calendar_clear"
        ),
    )

    # Row 3: Command examples
    builder.row(
        InlineKeyboardButton(
            text="❓ Пример команд", callback_data="calendar_examples"
        )
    )

    # Row 4: Back button
    builder.row(
        InlineKeyboardButton(
            text="◀️ Назад в админ-панель", callback_data="admin_panel"
        )
    )

    return builder.as_markup()


def get_clear_period_confirmation_keyboard() -> InlineKeyboardMarkup:
    """
    Build confirmation keyboard for period clearing.

    Buttons:
    - [Да, очистить] [Отмена]
    - [◀️ Назад к календарю]
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="Да, очистить", callback_data="calendar_clear_confirm"
        ),
        InlineKeyboardButton(text="Отмена", callback_data="calendar_clear_cancel"),
    )
    
    builder.row(
        InlineKeyboardButton(text="◀️ Назад к календарю", callback_data="calendar")
    )

    return builder.as_markup()


def get_back_to_calendar_keyboard() -> InlineKeyboardMarkup:
    """
    Build simple back button to return to calendar menu.

    Buttons:
    - [◀️ Назад к календарю]
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="◀️ Назад к календарю", callback_data="calendar")
    )

    return builder.as_markup()


def get_rule_list_pagination_keyboard(
    current_year: int,
    current_month: int,
    has_prev: bool,
    has_next: bool,
    prev_year: int | None = None,
    prev_month: int | None = None,
    next_year: int | None = None,
    next_month: int | None = None
) -> InlineKeyboardMarkup:
    """
    Build pagination keyboard for rule list with month navigation.

    Buttons:
    - [◀️ Пред. месяц] [След. месяц ▶️] (if applicable)
    - [◀️ Назад к календарю]
    
    Args:
        current_year: Current year being displayed
        current_month: Current month being displayed
        has_prev: Whether there's a previous month with rules
        has_next: Whether there's a next month with rules
        prev_year: Year of previous month (if has_prev)
        prev_month: Previous month number (if has_prev)
        next_year: Year of next month (if has_next)
        next_month: Next month number (if has_next)
    """
    from bots.tg_bot.callback_datas import CalendarCallback
    
    builder = InlineKeyboardBuilder()

    # Add pagination buttons if needed
    if has_prev or has_next:
        row_buttons = []
        
        if has_prev:
            row_buttons.append(
                InlineKeyboardButton(
                    text="◀️ Пред. месяц",
                    callback_data=CalendarCallback(
                        action="prev_month",
                        year=prev_year,
                        month=prev_month
                    ).pack()
                )
            )
        
        if has_next:
            row_buttons.append(
                InlineKeyboardButton(
                    text="След. месяц ▶️",
                    callback_data=CalendarCallback(
                        action="next_month",
                        year=next_year,
                        month=next_month
                    ).pack()
                )
            )
        
        builder.row(*row_buttons)

    # Back button
    builder.row(
        InlineKeyboardButton(text="◀️ Назад к календарю", callback_data="calendar")
    )

    return builder.as_markup()
