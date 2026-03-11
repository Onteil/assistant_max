"""
Admin Keyboards Package

Keyboards for administrator-specific functionality.
"""

from .admin_creation_kb import (
    get_admin_phone_keyboard,
    get_admin_cancel_keyboard,
)

__all__ = [
    "get_admin_phone_keyboard",
    "get_admin_cancel_keyboard",
]
