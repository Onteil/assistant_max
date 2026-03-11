"""
Telegram Bot Filters

Custom filters for handler routing and access control.
"""

from .is_staff import IsStaffFilter

__all__ = ["IsStaffFilter"]
