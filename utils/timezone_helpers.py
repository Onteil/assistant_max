"""
Timezone utilities for consistent Moscow time handling across the application.

This module provides centralized timezone handling to ensure all datetime operations
use Moscow timezone (Europe/Moscow) consistently across the application.
"""

from datetime import datetime
import pytz

# Moscow timezone constant
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


def get_moscow_now() -> datetime:
    """
    Get current datetime in Moscow timezone.
    
    Returns:
        datetime: Current datetime with Moscow timezone info
        
    Example:
        >>> now = get_moscow_now()
        >>> print(now.tzinfo)  # <DstTzInfo 'Europe/Moscow' MSK+3:00:00 STD>
    """
    return datetime.now(MOSCOW_TZ)


def get_moscow_now_naive() -> datetime:
    """
    Get current datetime in Moscow timezone as naive datetime.
    
    This is used for database operations where TIMESTAMP WITHOUT TIME ZONE
    columns are used and we want to store Moscow time directly.
    
    Returns:
        datetime: Current Moscow time as naive datetime (no timezone info)
        
    Example:
        >>> now = get_moscow_now_naive()
        >>> print(now.tzinfo)  # None
    """
    return datetime.now(MOSCOW_TZ).replace(tzinfo=None)


def convert_utc_to_moscow_naive(utc_dt: datetime) -> datetime:
    """
    Convert UTC datetime to Moscow timezone as naive datetime.
    
    Args:
        utc_dt: UTC datetime (can be naive or timezone-aware)
        
    Returns:
        datetime: Moscow time as naive datetime
        
    Example:
        >>> utc_time = datetime(2024, 1, 1, 12, 0, 0)  # Naive UTC
        >>> msk_time = convert_utc_to_moscow_naive(utc_time)
        >>> print(msk_time)  # 2024-01-01 15:00:00 (Moscow time)
    """
    if utc_dt.tzinfo is None:
        # Assume naive datetime is UTC
        utc_dt = pytz.utc.localize(utc_dt)
    elif utc_dt.tzinfo != pytz.utc:
        # Convert to UTC first if it's in different timezone
        utc_dt = utc_dt.astimezone(pytz.utc)
    
    # Convert to Moscow time and make naive
    moscow_dt = utc_dt.astimezone(MOSCOW_TZ)
    return moscow_dt.replace(tzinfo=None)


def format_moscow_datetime(dt: datetime, format_str: str = "%d.%m.%Y %H:%M МСК") -> str:
    """
    Format datetime as Moscow time string.
    
    Args:
        dt: Datetime to format (assumed to be Moscow time if naive)
        format_str: Format string for strftime
        
    Returns:
        str: Formatted datetime string
        
    Example:
        >>> dt = datetime(2024, 1, 1, 15, 30, 0)
        >>> formatted = format_moscow_datetime(dt)
        >>> print(formatted)  # "01.01.2024 15:30 МСК"
    """
    if dt.tzinfo is None:
        # Assume naive datetime is already Moscow time
        return dt.strftime(format_str)
    else:
        # Convert to Moscow time if timezone-aware
        moscow_dt = dt.astimezone(MOSCOW_TZ)
        return moscow_dt.strftime(format_str)