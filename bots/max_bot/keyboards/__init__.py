"""
Keyboard utilities for MAX Bot.

Organized by feature domains:
- user/: User-related keyboards (registration, profile, main menu)
- tickets/: Ticket-related keyboards (invoice, support)
- employee/: Employee interface keyboards
- common/: Shared keyboard utilities (builder, inline, reply)

This module exports keyboard builder classes and convenience functions
for creating inline and reply keyboards.
"""

from .common.keyboard_builder import (
    KeyboardBuilder,
    create_confirmation_keyboard,
    create_navigation_keyboard,
    create_paginated_keyboard,
)

__all__ = [
    "KeyboardBuilder",
    "create_confirmation_keyboard",
    "create_navigation_keyboard",
    "create_paginated_keyboard",
]
