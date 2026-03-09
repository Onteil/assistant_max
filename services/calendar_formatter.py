"""
Calendar Formatter

Formats calendar data for display in Telegram messages.
Handles Russian date/time formatting and emoji selection.
"""

from datetime import date, datetime, time
from typing import List, Optional
from calendar import monthrange

from database.models import Calendar_Rule, WorkMode


class CalendarFormatter:
    """
    Formats calendar data for display in Telegram.
    """
    
    # Russian month names (genitive case for dates)
    MONTHS_GENITIVE = {
        1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
        5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
        9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
    }
    
    # Russian month names (nominative case for headers)
    MONTHS_NOMINATIVE = {
        1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
        5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
        9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }
    
    # Russian day names (abbreviated)
    DAYS_OF_WEEK = {
        0: 'Пн', 1: 'Вт', 2: 'Ср', 3: 'Чт',
        4: 'Пт', 5: 'Сб', 6: 'Вс'
    }
    
    # Russian day names (full)
    DAYS_OF_WEEK_FULL = {
        0: 'Понедельник', 1: 'Вторник', 2: 'Среда', 3: 'Четверг',
        4: 'Пятница', 5: 'Суббота', 6: 'Воскресенье'
    }
    
    def _format_work_mode_emoji(self, mode: WorkMode) -> str:
        """
        Get emoji for work mode.
        
        Args:
            mode: WorkMode enum value
        
        Returns:
            Emoji string (✅ for REGULAR, 🛠 for EXTENDED, 🌙 for NON_WORKING)
        """
        if mode == WorkMode.REGULAR:
            return "✅"
        elif mode == WorkMode.EXTENDED:
            return "🛠"
        elif mode == WorkMode.NON_WORKING:
            return "🌙"
        else:
            return "❓"
    
    def _format_date_ru(self, d: date) -> str:
        """
        Format date in Russian.
        
        Args:
            d: Date to format
        
        Returns:
            Formatted date string (e.g., "31 января 2024")
        """
        month_name = self.MONTHS_GENITIVE[d.month]
        return f"{d.day} {month_name} {d.year}"
    
    def _format_day_of_week_ru(self, d: date) -> str:
        """
        Get Russian day of week abbreviation.
        
        Args:
            d: Date to get day of week for
        
        Returns:
            Day abbreviation (Пн, Вт, Ср, Чт, Пт, Сб, Вс)
        """
        return self.DAYS_OF_WEEK[d.weekday()]
    
    def _format_time(self, t: Optional[time]) -> str:
        """
        Format time in HH:MM format.
        
        Args:
            t: Time to format
        
        Returns:
            Formatted time string (e.g., "09:00")
        """
        if t is None:
            return ""
        return f"{t.hour:02d}:{t.minute:02d}"

    def format_main_menu(
        self,
        current_date: date,
        current_mode: WorkMode,
        active_rules: List[Calendar_Rule]
    ) -> str:
        """
        Format the main calendar menu message.
        
        Includes:
        - Current date and day of week
        - Current work mode with emoji
        - Emoji legend
        - Base schedule
        - Active exceptions for current week only
        
        Args:
            current_date: Today's date
            current_mode: Current work mode
            active_rules: List of active schedule rules
        
        Returns:
            Formatted message string (max 4096 chars)
        """
        from datetime import timedelta
        
        # Header with current date
        day_of_week = self.DAYS_OF_WEEK_FULL[current_date.weekday()]
        date_str = self._format_date_ru(current_date)
        emoji = self._format_work_mode_emoji(current_mode)
        
        lines = [
            "📅 <b>Управление графиком работы</b>\n",
            f"Сегодня: {day_of_week}, {date_str}",
            f"Текущий режим: {emoji} <b>{self._format_work_mode_name(current_mode)}</b>\n",
            "<b>Обозначения:</b>",
            "✅ Рабочее время (офис)",
            "🛠 Продленное рабочее время (дежурство)",
            "🌙 Нерабочее время (выходной)\n",
            "<b>Базовый график:</b>",
            "• Пн-Пт: 08:00-17:00 (Офис) ✅",
            "• Пн-Пт: 17:00-20:00 (Дежурство) 🛠",
            "• Сб: 09:00-13:00 (Дежурство) 🛠",
            "• Вс: Выходной 🌙"
        ]
        
        # Filter rules for current week (next 7 days from today)
        week_end = current_date + timedelta(days=6)
        week_rules = [
            rule for rule in active_rules
            if rule.start_date <= week_end and rule.end_date >= current_date
        ]
        
        # Add active exceptions for current week
        if week_rules:
            lines.append("\n<b>Исключения на текущую неделю:</b>")
            for rule in week_rules[:10]:  # Max 10 rules to avoid overflow
                rule_str = self._format_rule_summary_with_highlight(rule, current_date)
                lines.append(f"• {rule_str}")
        else:
            lines.append("\n<i>Нет исключений на текущую неделю</i>")
        
        # Join and check length
        result = "\n".join(lines)
        
        # Truncate if too long (shouldn't happen with week filter, but safety check)
        if len(result) > 4000:
            lines = lines[:15]  # Keep header and base info
            lines.append("\n<i>... (список сокращен)</i>")
            result = "\n".join(lines)
        
        return result
    
    def _format_work_mode_name(self, mode: WorkMode) -> str:
        """
        Get Russian name for work mode.
        
        Args:
            mode: WorkMode enum value
        
        Returns:
            Russian mode name
        """
        if mode == WorkMode.REGULAR:
            return "Рабочее время"
        elif mode == WorkMode.EXTENDED:
            return "Продленное рабочее время"
        elif mode == WorkMode.NON_WORKING:
            return "Нерабочее время"
        else:
            return "Неизвестно"
    
    def _format_rule_summary(self, rule: Calendar_Rule) -> str:
        """
        Format a brief summary of a rule for lists.
        
        Args:
            rule: Calendar_Rule to format
        
        Returns:
            Brief rule description
        """
        emoji = self._format_work_mode_emoji(rule.work_mode)
        
        # Format date or date range
        if rule.start_date == rule.end_date:
            date_str = self._format_date_ru(rule.start_date)
        else:
            start_str = self._format_date_ru(rule.start_date)
            end_str = self._format_date_ru(rule.end_date)
            date_str = f"{start_str} - {end_str}"
        
        return f"{emoji} {date_str}"
    
    def _format_rule_summary_with_highlight(self, rule: Calendar_Rule, today: date) -> str:
        """
        Format a brief summary of a rule with highlighting for today.
        
        Args:
            rule: Calendar_Rule to format
            today: Current date to highlight
        
        Returns:
            Brief rule description with underline for today
        """
        emoji = self._format_work_mode_emoji(rule.work_mode)
        
        # Check if today is within this rule
        is_today = rule.start_date <= today <= rule.end_date
        
        # Format date or date range
        if rule.start_date == rule.end_date:
            date_str = self._format_date_ru(rule.start_date)
            if is_today:
                date_str = f"<u>{date_str}</u>"
        else:
            start_str = self._format_date_ru(rule.start_date)
            end_str = self._format_date_ru(rule.end_date)
            if is_today:
                date_str = f"<u>{start_str} - {end_str}</u>"
            else:
                date_str = f"{start_str} - {end_str}"
        
        return f"{emoji} {date_str}"
        # Format time range if applicable
        if rule.work_mode != WorkMode.NON_WORKING and rule.work_start_time and rule.work_end_time:
            time_str = f" ({self._format_time(rule.work_start_time)}-{self._format_time(rule.work_end_time)})"
        else:
            time_str = ""
        
        return f"{emoji} {date_str}{time_str}"

    def format_weekly_view(
        self,
        start_date: date,
        rules: List[Calendar_Rule]
    ) -> str:
        """
        Format calendar view for 7 days.
        
        For each day:
        - Date and day of week
        - Work hours (or "ВЫХОДНОЙ")
        - Highlight days with exceptions
        
        Args:
            start_date: First day of the week to display
            rules: List of rules that may apply to this week
        
        Returns:
            Formatted weekly view string
        """
        from datetime import timedelta
        
        # Calculate end date for header
        end_date = start_date + timedelta(days=6)
        start_str = f"{start_date.day:02d}.{start_date.month:02d}"
        end_str = f"{end_date.day:02d}.{end_date.month:02d}.{end_date.year}"
        
        lines = [
            "📅 <b>График на неделю</b>",
            f"<i>{start_str} - {end_str}</i>\n"
        ]
        
        for i in range(7):
            current_date = start_date + timedelta(days=i)
            day_str = self._format_day_view(current_date, rules)
            lines.append(day_str)
        
        return "\n".join(lines)
    
    def _format_day_view(self, day: date, rules: List[Calendar_Rule]) -> str:
        """
        Format a single day's schedule.
        
        Args:
            day: Date to format
            rules: List of all rules to check
        
        Returns:
            Formatted day string with emoji indicator for days with rules
        """
        day_of_week = self._format_day_of_week_ru(day)
        date_str = f"{day.day:02d}.{day.month:02d}"
        
        # Find applicable rule for this day
        applicable_rule = None
        for rule in rules:
            if rule.start_date <= day <= rule.end_date:
                applicable_rule = rule
                break  # Rules are already sorted by priority
        
        # Determine if this is an exception (has a rule)
        is_exception = applicable_rule is not None
        
        # Get work hours
        if applicable_rule:
            work_mode = applicable_rule.work_mode
            work_start = applicable_rule.work_start_time
            work_end = applicable_rule.work_end_time
        else:
            # Use base schedule
            work_mode, work_start, work_end = self._get_base_schedule_for_day(day)
        
        # Format the day line
        emoji = self._format_work_mode_emoji(work_mode)
        
        if work_mode == WorkMode.NON_WORKING:
            hours_str = "🌙 ВЫХОДНОЙ"
        else:
            hours_str = f"{self._format_time(work_start)}-{self._format_time(work_end)}"
        
        # Add indicator emoji at the start for days with rules
        if is_exception:
            indicator = "📌 "  # Pin emoji to mark days with custom rules
            return f"{indicator}<b>{day_of_week} {date_str}</b> {emoji} <b>{hours_str}</b>"
        else:
            return f"{day_of_week} {date_str} {emoji} {hours_str}"
    
    def _get_base_schedule_for_day(self, day: date) -> tuple[WorkMode, Optional[time], Optional[time]]:
        """
        Get base schedule for a specific day.
        
        Args:
            day: Date to get schedule for
        
        Returns:
            Tuple of (WorkMode, start_time, end_time)
        """
        day_of_week = day.weekday()
        
        # Sunday - NON_WORKING
        if day_of_week == 6:
            return (WorkMode.NON_WORKING, None, None)
        
        # Saturday - EXTENDED 09:00-13:00
        elif day_of_week == 5:
            return (WorkMode.EXTENDED, time(9, 0), time(13, 0))
        
        # Monday-Friday - Show REGULAR hours (08:00-17:00)
        # Note: Extended hours (17:00-20:00) are also available but we show primary hours
        else:
            return (WorkMode.REGULAR, time(8, 0), time(17, 0))

    def format_monthly_view(
        self,
        year: int,
        month: int,
        rules: List[Calendar_Rule]
    ) -> str:
        """
        Format calendar view for entire month.
        
        Similar to weekly view but for all days in month.
        Ensures output doesn't exceed Telegram message limits (4096 chars).
        Separates weeks with dividers.
        
        Args:
            year: Year to display
            month: Month to display (1-12)
            rules: List of rules that may apply to this month
        
        Returns:
            Formatted monthly view string
        """
        month_name = self.MONTHS_NOMINATIVE[month]
        lines = [f"📅 <b>График на {month_name} {year}</b>\n"]
        
        # Get number of days in month
        days_in_month = monthrange(year, month)[1]
        
        # Format each day, adding week dividers
        current_week = None
        for day_num in range(1, days_in_month + 1):
            current_date = date(year, month, day_num)
            
            # Add week divider when week changes (Monday or first day)
            week_of_month = (day_num - 1) // 7 + 1
            if week_of_month != current_week:
                if current_week is not None:  # Not the first week
                    lines.append("─────────────────────")
                current_week = week_of_month
            
            day_str = self._format_day_view(current_date, rules)
            
            # Check if adding this line would exceed limit (leave buffer)
            potential_output = "\n".join(lines + [day_str])
            if len(potential_output) > 3800:
                lines.append("\n<i>(Сообщение слишком длинное, показаны не все дни)</i>")
                break
            
            lines.append(day_str)
        
        return "\n".join(lines)

    def format_rule_list(
        self,
        rules: List[Calendar_Rule]
    ) -> str:
        """
        Format list of rules with sequential numbers.
        
        Shows:
        - Rule number
        - Date or date range
        - Work mode
        - Time interval
        - Priority indicator
        
        Args:
            rules: List of Calendar_Rule (should be pre-sorted by priority)
        
        Returns:
            Formatted rule list string
        """
        if not rules:
            lines = [
                "📋 <b>Список правил</b>\n",
                "<i>Нет активных правил. Действует базовый график.</i>\n",
                "Чтобы добавить правило, отправьте команду в формате:",
                "• <code>31 января рабочее время с 9 до 15</code>",
                "• <code>с 1 по 5 февраля нерабочее время</code>"
            ]
            return "\n".join(lines)
        
        lines = [
            "📋 <b>Список правил</b>",
            "<i>(упорядочены по приоритету)</i>\n"
        ]
        
        for idx, rule in enumerate(rules, start=1):
            rule_str = self._format_rule_detail(idx, rule)
            lines.append(rule_str)
        
        lines.append("\n<b>Управление правилами:</b>")
        lines.append("\n<i>Чтобы добавить правило:</i>")
        lines.append("• <code>31 января рабочее время с 9 до 15</code>")
        lines.append("• <code>с 1 по 5 февраля нерабочее время</code>")
        lines.append("\n<i>Чтобы удалить правило:</i>")
        lines.append("• <code>Удалить правило [номер]</code>")
        
        return "\n".join(lines)
    
    def _format_rule_detail(self, number: int, rule: Calendar_Rule) -> str:
        """
        Format detailed rule information for list display.
        
        Args:
            number: Sequential number for the rule
            rule: Calendar_Rule to format
        
        Returns:
            Formatted rule string
        """
        emoji = self._format_work_mode_emoji(rule.work_mode)
        mode_name = self._format_work_mode_name(rule.work_mode)
        
        # Format date or date range
        if rule.start_date == rule.end_date:
            date_str = self._format_date_ru(rule.start_date)
            priority_indicator = "⭐ (одна дата)"
        else:
            start_str = self._format_date_ru(rule.start_date)
            end_str = self._format_date_ru(rule.end_date)
            date_str = f"{start_str} - {end_str}"
            priority_indicator = "📅 (период)"
        
        # Format time range if applicable
        if rule.work_mode != WorkMode.NON_WORKING and rule.work_start_time and rule.work_end_time:
            time_str = f"\n   Время: {self._format_time(rule.work_start_time)}-{self._format_time(rule.work_end_time)}"
        else:
            time_str = ""
        
        return f"<b>{number}.</b> {emoji} {mode_name}\n   {date_str} {priority_indicator}{time_str}\n"

    def format_rule_confirmation(
        self,
        rule: Calendar_Rule
    ) -> str:
        """
        Format confirmation message after rule creation.
        
        Shows:
        - Date or date range
        - Work mode
        - Time interval (if applicable)
        
        Args:
            rule: Calendar_Rule that was created
        
        Returns:
            Formatted confirmation message
        """
        emoji = self._format_work_mode_emoji(rule.work_mode)
        mode_name = self._format_work_mode_name(rule.work_mode)
        
        # Format date or date range
        if rule.start_date == rule.end_date:
            date_str = self._format_date_ru(rule.start_date)
        else:
            start_str = self._format_date_ru(rule.start_date)
            end_str = self._format_date_ru(rule.end_date)
            date_str = f"с {start_str} по {end_str}"
        
        lines = [
            "✅ <b>Правило добавлено</b>\n",
            f"{emoji} <b>{mode_name}</b>",
            f"Дата: {date_str}"
        ]
        
        # Add time range if applicable
        if rule.work_mode != WorkMode.NON_WORKING and rule.work_start_time and rule.work_end_time:
            time_str = f"{self._format_time(rule.work_start_time)}-{self._format_time(rule.work_end_time)}"
            lines.append(f"Время: {time_str}")
        
        return "\n".join(lines)

    def format_rule_preview(
        self,
        rule: Calendar_Rule
    ) -> str:
        """
        Format rule preview for confirmation before adding.
        
        Shows:
        - Date or date range
        - Work mode
        - Time interval (if applicable)
        
        Args:
            rule: Calendar_Rule to preview
        
        Returns:
            Formatted preview message
        """
        emoji = self._format_work_mode_emoji(rule.work_mode)
        mode_name = self._format_work_mode_name(rule.work_mode)
        
        # Format date or date range
        if rule.start_date == rule.end_date:
            date_str = self._format_date_ru(rule.start_date)
            date_label = "Дата"
        else:
            start_str = self._format_date_ru(rule.start_date)
            end_str = self._format_date_ru(rule.end_date)
            date_str = f"с {start_str} по {end_str}"
            date_label = "Период"
        
        lines = [
            f"{emoji} <b>{mode_name}</b>",
            f"{date_label}: {date_str}"
        ]
        
        # Add time range if applicable
        if rule.work_mode != WorkMode.NON_WORKING and rule.work_start_time and rule.work_end_time:
            time_str = f"{self._format_time(rule.work_start_time)}-{self._format_time(rule.work_end_time)}"
            lines.append(f"Время работы: {time_str}")
        elif rule.work_mode == WorkMode.NON_WORKING:
            lines.append("<i>Выходной день</i>")
        
        return "\n".join(lines)

    def format_command_examples(self) -> str:
        """
        Format examples of valid commands.
        
        Shows examples for:
        - Single date rules (all modes)
        - Date range rules (all modes)
        - Deletion and clearing
        - Priority rules explanation
        
        Returns:
            Formatted command examples string
        """
        lines = [
            "❓ <b>Примеры команд</b>\n",
            "<b>Добавить правило на одну дату:</b>",
            "• <code>31 января рабочее время с 9 до 15</code>",
            "  <i>Офисный режим с 9:00 до 15:00</i>",
            "• <code>1 февраля продленное рабочее время с 17 до 20</code>",
            "  <i>Дежурство с 17:00 до 20:00</i>",
            "• <code>8 марта нерабочее время</code>",
            "  <i>Выходной день</i>\n",
            "<b>Добавить правило на период:</b>",
            "• <code>с 1 по 5 января нерабочее время</code>",
            "  <i>Новогодние каникулы</i>",
            "• <code>с 10 по 15 февраля рабочее время с 10 до 16</code>",
            "  <i>Сокращенный график на неделю</i>\n",
            "<b>Удалить правило:</b>",
            "• <code>Удалить правило 3</code>",
            "  <i>Удалить правило под номером 3 из списка</i>\n",
            "<b>Очистить период:</b>",
            "• Нажмите кнопку [🗑 Очистить период]",
            "• Введите даты: <code>с 1 по 31 января</code>",
            "  <i>Удалит все правила в указанном периоде</i>\n",
            "<b>Приоритет правил:</b>",
            "• Правила на <b>одну дату</b> имеют <b>высший приоритет</b> (⭐)",
            "• Правила на <b>период</b> имеют <b>обычный приоритет</b> (📅)",
            "• При пересечении правил применяется правило с более высоким приоритетом",
            "• Пример: если есть правило на период 1-10 февраля и отдельное правило на 5 февраля, то 5 февраля будет применено правило на одну дату\n",
            "<b>Форматы дат:</b>",
            "• День и месяц: <code>31 января</code>, <code>1 февраля</code>",
            "• Регистр не важен: <code>ЯНВАРЯ</code>, <code>Января</code>, <code>января</code>",
            "• Год указывать не нужно (определяется автоматически)\n",
            "<b>Форматы времени:</b>",
            "• С ведущим нулем: <code>09:00</code>",
            "• Без ведущего нуля: <code>9</code> (означает 09:00)",
            "• Диапазон: <code>с 9 до 17</code>"
        ]
        
        return "\n".join(lines)
