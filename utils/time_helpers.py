"""Time formatting utilities for the bot application."""

from datetime import datetime
from utils.timezone_helpers import get_moscow_now_naive


def format_relative_time(event_date: datetime) -> str:
    """
    Format a datetime as a relative time expression in Russian.
    
    Args:
        event_date: The past event date to format
        
    Returns:
        Russian relative time string:
        - "вчера" for 1 day ago
        - "N дней назад" for multiple days ago (with correct plural form)
        
    Examples:
        >>> format_relative_time(datetime.now() - timedelta(days=1))
        'вчера'
        >>> format_relative_time(datetime.now() - timedelta(days=2))
        '2 дня назад'
        >>> format_relative_time(datetime.now() - timedelta(days=5))
        '5 дней назад'
    """
    now = get_moscow_now_naive()
    days_diff = (now - event_date).days
    
    if days_diff == 1:
        return "вчера"
    
    # Handle Russian plural forms for "день" (day)
    # 1 день, 2-4 дня, 5+ дней
    if days_diff % 10 == 1 and days_diff % 100 != 11:
        return f"{days_diff} день назад"
    elif 2 <= days_diff % 10 <= 4 and (days_diff % 100 < 10 or days_diff % 100 >= 20):
        return f"{days_diff} дня назад"
    else:
        return f"{days_diff} дней назад"
