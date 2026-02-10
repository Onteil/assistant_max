"""
Keyboards Package

Экспорт всех функций создания клавиатур для удобного импорта.
"""

from .inline_kb import create_confirmation_keyboard, create_navigation_keyboard, create_paginated_keyboard
from .invoice_kb import get_delivery_method_keyboard, get_key_selection_keyboard, get_organization_keyboard
from .registration_kb import get_cancel_keyboard, get_phone_request_keyboard
from .reply_kb import create_contact_keyboard, create_main_menu_keyboard, remove_keyboard

__all__ = [
    # Inline keyboards
    "create_paginated_keyboard",
    "create_confirmation_keyboard",
    "create_navigation_keyboard",
    # Reply keyboards
    "create_main_menu_keyboard",
    "create_contact_keyboard",
    "remove_keyboard",
    # Registration keyboards
    "get_phone_request_keyboard",
    "get_cancel_keyboard",
    # Invoice keyboards
    "get_organization_keyboard",
    "get_key_selection_keyboard",
    "get_delivery_method_keyboard",
]
