"""
Inline Keyboards for MAX Bot

This module provides inline keyboard creation functions using the KeyboardBuilder
utility and maxapi integration. Inline keyboards appear as buttons attached to
messages and support callback actions, links, and other interactive elements.

Pattern: Use KeyboardBuilder for flexible keyboard construction
- Import and use KeyboardBuilder from keyboard_builder module
- Use convenience functions for common keyboard patterns
- Support pagination, confirmation, and navigation keyboards
- Integrate with messenger abstraction layer

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

import math
from typing import Optional

from bots.max_bot.keyboards.common.keyboard_builder import (
    KeyboardBuilder,
    create_confirmation_keyboard,
    create_navigation_keyboard,
    create_paginated_keyboard,
)
from bots.max_bot.messenger_adapter import Keyboard

# Constants for pagination
ITEMS_PER_PAGE = 10


async def create_paginated_keyboard_async(
    items: list[dict],
    page: int = 0,
    items_per_page: int = ITEMS_PER_PAGE,
    buttons_per_row: int = 2,
    item_text_key: str = "name",
    item_id_key: str = "id",
    callback_action: str = "select",
    page_action: str = "page"
) -> Keyboard:
    """
    Create a paginated inline keyboard (async version for compatibility).
    
    This is an async wrapper around create_paginated_keyboard for compatibility
    with existing async keyboard creation patterns.
    
    Args:
        items: List of items to display (dicts with id and name keys)
        page: Current page number (0-indexed)
        items_per_page: Number of items to show per page
        buttons_per_row: Number of buttons per row for items
        item_text_key: Key to use for button text from item dict
        item_id_key: Key to use for item ID from item dict
        callback_action: Action string for item selection callbacks
        page_action: Action string for pagination callbacks
        
    Returns:
        Keyboard with paginated items and navigation
        
    Example:
        items = [{"id": 1, "name": "Org 1"}, {"id": 2, "name": "Org 2"}]
        keyboard = await create_paginated_keyboard_async(items, page=0)
    """
    return create_paginated_keyboard(
        items=items,
        page=page,
        items_per_page=items_per_page,
        buttons_per_row=buttons_per_row,
        item_text_key=item_text_key,
        item_id_key=item_id_key,
        callback_action=callback_action,
        page_action=page_action
    )


async def create_confirmation_keyboard_async(
    confirm_text: str = "✅ Confirm",
    cancel_text: str = "❌ Cancel",
    confirm_payload: Optional[dict] = None,
    cancel_payload: Optional[dict] = None
) -> Keyboard:
    """
    Create a confirmation keyboard (async version for compatibility).
    
    Args:
        confirm_text: Text for confirm button
        cancel_text: Text for cancel button
        confirm_payload: Payload for confirm button
        cancel_payload: Payload for cancel button
        
    Returns:
        Keyboard with confirmation buttons
    """
    return create_confirmation_keyboard(
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        confirm_payload=confirm_payload,
        cancel_payload=cancel_payload
    )


async def create_navigation_keyboard_async(
    back_text: str = "⬅️ Back",
    back_payload: Optional[dict] = None
) -> Keyboard:
    """
    Create a navigation keyboard (async version for compatibility).
    
    Args:
        back_text: Text for back button
        back_payload: Payload for back button
        
    Returns:
        Keyboard with navigation button
    """
    return create_navigation_keyboard(
        back_text=back_text,
        back_payload=back_payload
    )


# Example: Custom keyboard for specific use case
async def create_organization_selection_keyboard(
    organizations: list[dict],
    page: int = 0
) -> Keyboard:
    """
    Create a keyboard for organization selection with pagination.
    
    This is an example of a domain-specific keyboard that uses the
    KeyboardBuilder for custom layout and functionality.
    
    Args:
        organizations: List of organization dicts with 'id', 'name', 'inn' keys
        page: Current page number
        
    Returns:
        Keyboard for organization selection
    """
    builder = KeyboardBuilder(inline=True)

    # Calculate pagination
    items_per_page = 5
    total_pages = math.ceil(len(organizations) / items_per_page)
    start_index = page * items_per_page
    end_index = start_index + items_per_page
    orgs_on_page = organizations[start_index:end_index]

    # Add organization buttons (one per row for better readability)
    for org in orgs_on_page:
        builder.add_callback_button(
            text=f"{org['name']} (ИНН: {org['inn']})",
            payload={
                "action": "select_org",
                "inn": org["inn"],
                "id": org["id"]
            }
        )
        builder.row()

    # Add pagination controls
    if total_pages > 1:
        if page > 0:
            builder.add_callback_button(
                text="⬅️",
                payload={"action": "org_page", "page": page - 1}
            )

        builder.add_callback_button(
            text=f"{page + 1}/{total_pages}",
            payload={"action": "noop"}
        )

        if page < total_pages - 1:
            builder.add_callback_button(
                text="➡️",
                payload={"action": "org_page", "page": page + 1}
            )

        builder.row()

    # Add cancel button
    builder.add_callback_button(
        text="❌ Cancel",
        payload={"action": "cancel"}
    )

    return builder.build()


async def create_action_keyboard(
    actions: list[tuple[str, dict]],
    buttons_per_row: int = 2,
    add_cancel: bool = True
) -> Keyboard:
    """
    Create a keyboard with custom action buttons.
    
    Args:
        actions: List of (button_text, payload) tuples
        buttons_per_row: Number of buttons per row
        add_cancel: Whether to add a cancel button at the end
        
    Returns:
        Keyboard with action buttons
        
    Example:
        actions = [
            ("Edit Profile", {"action": "edit_profile"}),
            ("View History", {"action": "view_history"}),
            ("Settings", {"action": "settings"})
        ]
        keyboard = await create_action_keyboard(actions, buttons_per_row=2)
    """
    builder = KeyboardBuilder(inline=True)

    # Add action buttons
    for text, payload in actions:
        builder.add_callback_button(text=text, payload=payload)

    # Adjust layout
    if actions:
        builder.row()
        num_rows = math.ceil(len(actions) / buttons_per_row)
        widths = [buttons_per_row] * num_rows
        builder.adjust(*widths)

    # Add cancel button if requested
    if add_cancel:
        builder.add_callback_button(
            text="❌ Cancel",
            payload={"action": "cancel"}
        )

    return builder.build()


async def create_yes_no_keyboard(
    yes_text: str = "✅ Yes",
    no_text: str = "❌ No",
    yes_payload: Optional[dict] = None,
    no_payload: Optional[dict] = None
) -> Keyboard:
    """
    Create a simple yes/no keyboard.
    
    Args:
        yes_text: Text for yes button
        no_text: Text for no button
        yes_payload: Payload for yes button (defaults to {"action": "yes"})
        no_payload: Payload for no button (defaults to {"action": "no"})
        
    Returns:
        Keyboard with yes/no buttons
    """
    builder = KeyboardBuilder(inline=True)

    builder.add_callback_button(
        text=yes_text,
        payload=yes_payload or {"action": "yes"}
    )

    builder.add_callback_button(
        text=no_text,
        payload=no_payload or {"action": "no"}
    )

    return builder.build()
