"""
Calendar Command Parser

Parses Russian natural language commands for calendar management.
Supports single dates, date ranges, and various work modes.
"""

import re
from dataclasses import dataclass
from datetime import date, time
from typing import Optional

from database.models import WorkMode


@dataclass
class ParsedRule:
    """Structured representation of a parsed schedule rule."""

    start_date: date
    end_date: date
    work_mode: WorkMode
    work_start_time: Optional[time]
    work_end_time: Optional[time]


class CalendarCommandParser:
    """
    Parses Russian natural language commands for calendar management.
    """

    # Russian month names mapping (genitive case)
    MONTHS = {
        "января": 1,
        "февраля": 2,
        "марта": 3,
        "апреля": 4,
        "мая": 5,
        "июня": 6,
        "июля": 7,
        "августа": 8,
        "сентября": 9,
        "октября": 10,
        "ноября": 11,
        "декабря": 12,
    }

    def parse_add_rule_command(self, text: str) -> Optional[ParsedRule]:
        """
        Parse text command for adding a schedule rule.

        Supported formats:
        - "31 января рабочее время с 9 до 15"
        - "с 1 по 5 февраля нерабочее время"
        - "31 января продленное рабочее время с 17 до 20"

        Returns ParsedRule if successful, None if parsing fails.
        """
        normalized = self._normalize_text(text)
        
        # Try to parse as date range first (more specific pattern)
        date_range_result = self._parse_date_range_command(normalized)
        if date_range_result:
            return date_range_result
        
        # Try to parse as single date
        single_date_result = self._parse_single_date_command(normalized)
        if single_date_result:
            return single_date_result
        
        return None
    
    def _parse_single_date_command(self, normalized_text: str) -> Optional[ParsedRule]:
        """
        Parse single date command.
        
        Patterns:
        - "[day] [month] рабочее время с [hour] до [hour]"
        - "[day] [month] продленное рабочее время с [hour] до [hour]"
        - "[day] [month] нерабочее время"
        """
        # Build month pattern
        month_pattern = "|".join(self.MONTHS.keys())
        
        # Pattern for single date with work mode and optional time
        # Group 1: day, Group 2: month, Group 3: work mode type, Group 4: start hour, Group 5: end hour
        pattern = rf"(\d{{1,2}})\s+({month_pattern})\s+(рабочее|продленное рабочее|нерабочее)\s+время(?:\s+с\s+(\d{{1,2}})\s+до\s+(\d{{1,2}}))?"
        
        match = re.match(pattern, normalized_text)
        if not match:
            return None
        
        day_str, month_name, mode_str, start_hour_str, end_hour_str = match.groups()
        
        # Parse date
        try:
            day = int(day_str)
        except ValueError:
            return None
        
        parsed_date = self._parse_single_date(day, month_name)
        if parsed_date is None:
            return None
        
        # Determine work mode
        if mode_str == "нерабочее":
            work_mode = WorkMode.NON_WORKING
            work_start_time = None
            work_end_time = None
        elif mode_str == "продленное рабочее":
            work_mode = WorkMode.EXTENDED
            # Time is required for EXTENDED mode
            if not start_hour_str or not end_hour_str:
                return None
            work_start_time = self._parse_time(start_hour_str)
            work_end_time = self._parse_time(end_hour_str)
            if work_start_time is None or work_end_time is None:
                return None
            # Validate time range
            if work_start_time >= work_end_time:
                return None
        else:  # "рабочее"
            work_mode = WorkMode.REGULAR
            # Time is required for REGULAR mode
            if not start_hour_str or not end_hour_str:
                return None
            work_start_time = self._parse_time(start_hour_str)
            work_end_time = self._parse_time(end_hour_str)
            if work_start_time is None or work_end_time is None:
                return None
            # Validate time range
            if work_start_time >= work_end_time:
                return None
        
        return ParsedRule(
            start_date=parsed_date,
            end_date=parsed_date,
            work_mode=work_mode,
            work_start_time=work_start_time,
            work_end_time=work_end_time,
        )

    def parse_delete_rule_command(self, text: str) -> Optional[int]:
        """
        Parse text command for deleting a rule.

        Format: "Удалить правило 3"

        Returns rule number if successful, None if parsing fails.
        """
        normalized = self._normalize_text(text)
        
        # Pattern: "удалить правило [number]"
        pattern = r"удалить\s+правило\s+(\d+)"
        
        match = re.match(pattern, normalized)
        if not match:
            return None
        
        try:
            rule_number = int(match.group(1))
            return rule_number
        except ValueError:
            return None
    
    def _parse_date_range_command(self, normalized_text: str) -> Optional[ParsedRule]:
        """
        Parse date range command.
        
        Patterns:
        - "с [day] [month] по [day] [month] рабочее время с [hour] до [hour]"
        - "с [day] по [day] [month] рабочее время с [hour] до [hour]"
        - "с [day] [month] по [day] [month] нерабочее время"
        """
        # Build month pattern
        month_pattern = "|".join(self.MONTHS.keys())
        
        # Pattern 1: "с [day] [month] по [day] [month] [mode] время [optional time]"
        pattern1 = rf"с\s+(\d{{1,2}})\s+({month_pattern})\s+по\s+(\d{{1,2}})\s+({month_pattern})\s+(рабочее|продленное рабочее|нерабочее)\s+время(?:\s+с\s+(\d{{1,2}})\s+до\s+(\d{{1,2}}))?"
        
        # Pattern 2: "с [day] по [day] [month] [mode] время [optional time]"
        pattern2 = rf"с\s+(\d{{1,2}})\s+по\s+(\d{{1,2}})\s+({month_pattern})\s+(рабочее|продленное рабочее|нерабочее)\s+время(?:\s+с\s+(\d{{1,2}})\s+до\s+(\d{{1,2}}))?"
        
        match1 = re.match(pattern1, normalized_text)
        match2 = re.match(pattern2, normalized_text)
        
        if match1:
            start_day_str, start_month_name, end_day_str, end_month_name, mode_str, start_hour_str, end_hour_str = match1.groups()
            
            # Parse dates
            try:
                start_day = int(start_day_str)
                end_day = int(end_day_str)
            except ValueError:
                return None
            
            start_date = self._parse_single_date(start_day, start_month_name)
            end_date = self._parse_single_date(end_day, end_month_name)
            
            if start_date is None or end_date is None:
                return None
            
        elif match2:
            start_day_str, end_day_str, month_name, mode_str, start_hour_str, end_hour_str = match2.groups()
            
            # Parse dates (both use same month)
            try:
                start_day = int(start_day_str)
                end_day = int(end_day_str)
            except ValueError:
                return None
            
            start_date = self._parse_single_date(start_day, month_name)
            end_date = self._parse_single_date(end_day, month_name)
            
            if start_date is None or end_date is None:
                return None
        else:
            return None
        
        # Validate date range
        if start_date > end_date:
            return None
        
        # Determine work mode
        if mode_str == "нерабочее":
            work_mode = WorkMode.NON_WORKING
            work_start_time = None
            work_end_time = None
        elif mode_str == "продленное рабочее":
            work_mode = WorkMode.EXTENDED
            # Time is required for EXTENDED mode
            if not start_hour_str or not end_hour_str:
                return None
            work_start_time = self._parse_time(start_hour_str)
            work_end_time = self._parse_time(end_hour_str)
            if work_start_time is None or work_end_time is None:
                return None
            # Validate time range
            if work_start_time >= work_end_time:
                return None
        else:  # "рабочее"
            work_mode = WorkMode.REGULAR
            # Time is required for REGULAR mode
            if not start_hour_str or not end_hour_str:
                return None
            work_start_time = self._parse_time(start_hour_str)
            work_end_time = self._parse_time(end_hour_str)
            if work_start_time is None or work_end_time is None:
                return None
            # Validate time range
            if work_start_time >= work_end_time:
                return None
        
        return ParsedRule(
            start_date=start_date,
            end_date=end_date,
            work_mode=work_mode,
            work_start_time=work_start_time,
            work_end_time=work_end_time,
        )

    def parse_date_range(self, text: str) -> Optional[tuple[date, date]]:
        """
        Parse date range from text.

        Formats:
        - "с 1 по 5 февраля"
        - "с 1 января по 5 февраля"

        Returns (start_date, end_date) if successful, None if parsing fails.
        """
        normalized = self._normalize_text(text)
        
        # Build month pattern
        month_pattern = "|".join(self.MONTHS.keys())
        
        # Pattern 1: "с [day] [month] по [day] [month]"
        pattern1 = rf"с\s+(\d{{1,2}})\s+({month_pattern})\s+по\s+(\d{{1,2}})\s+({month_pattern})"
        
        # Pattern 2: "с [day] по [day] [month]"
        pattern2 = rf"с\s+(\d{{1,2}})\s+по\s+(\d{{1,2}})\s+({month_pattern})"
        
        match1 = re.match(pattern1, normalized)
        match2 = re.match(pattern2, normalized)
        
        if match1:
            start_day_str, start_month_name, end_day_str, end_month_name = match1.groups()
            
            # Parse dates
            try:
                start_day = int(start_day_str)
                end_day = int(end_day_str)
            except ValueError:
                return None
            
            start_date = self._parse_single_date(start_day, start_month_name)
            end_date = self._parse_single_date(end_day, end_month_name)
            
            if start_date is None or end_date is None:
                return None
            
        elif match2:
            start_day_str, end_day_str, month_name = match2.groups()
            
            # Parse dates (both use same month)
            try:
                start_day = int(start_day_str)
                end_day = int(end_day_str)
            except ValueError:
                return None
            
            start_date = self._parse_single_date(start_day, month_name)
            end_date = self._parse_single_date(end_day, month_name)
            
            if start_date is None or end_date is None:
                return None
        else:
            return None
        
        # Validate date range
        if start_date > end_date:
            return None
        
        return (start_date, end_date)

    def _parse_single_date(self, day: int, month_name: str) -> Optional[date]:
        """
        Parse a single date from day number and Russian month name.
        
        Implements year inference logic:
        - If date is in the future relative to today, use current year
        - If date has passed, use next year
        - Special case: If date is slightly in the past (within current month or previous month),
          still use current year to allow creating rules for ongoing periods
        
        Returns None if date is invalid (e.g., February 30).
        """
        from datetime import datetime
        
        # Normalize month name
        month_name = month_name.lower()
        
        # Get month number
        month = self.MONTHS.get(month_name)
        if month is None:
            return None
        
        # Get current date
        today = datetime.now().date()
        current_year = today.year
        
        # Try to create date with current year
        try:
            parsed_date = date(current_year, month, day)
        except ValueError:
            # Invalid date (e.g., February 30)
            return None
        
        # If date is more than 60 days in the past, use next year
        # This allows creating rules for recent past dates (e.g., periods spanning past and future)
        days_diff = (today - parsed_date).days
        if days_diff > 60:
            try:
                parsed_date = date(current_year + 1, month, day)
            except ValueError:
                return None
        
        return parsed_date

    def _parse_time(self, hour_str: str) -> Optional[time]:
        """
        Parse time from hour string (supports with/without leading zeros).
        
        Accepts:
        - "9" -> 09:00
        - "09" -> 09:00
        - "17" -> 17:00
        
        Returns None if hour is invalid (>23 or <0).
        """
        try:
            hour = int(hour_str)
            if hour < 0 or hour > 23:
                return None
            return time(hour, 0)
        except ValueError:
            return None

    def _normalize_text(self, text: str) -> str:
        """Normalize text: lowercase, strip extra spaces."""
        return " ".join(text.lower().strip().split())
