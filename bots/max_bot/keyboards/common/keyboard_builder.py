"""
Keyboard Builder Utility for MAX Bot

This module provides a high-level keyboard builder that works with the messenger
abstraction layer, making it easy to create keyboards that are messenger-agnostic.

Pattern: Use KeyboardBuilder for flexible keyboard construction
- Supports both inline and reply keyboards
- Provides fluent API for adding buttons and rows
- Integrates with messenger abstraction layer (Keyboard, KeyboardButton)
- Supports all button types: callback, link, contact, location

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

from typing import Optional

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton


class KeyboardBuilder:
    """
    Builder for creating messenger-agnostic keyboards.
    
    This builder provides a fluent API for constructing keyboards that work
    with the messenger abstraction layer. It supports both inline and reply
    keyboards, and all button types (callback, link, contact, location).
    
    Example usage:
        # Create inline keyboard with callback buttons
        builder = KeyboardBuilder(inline=True)
        builder.add_button("Option 1", payload={"action": "select", "id": 1})
        builder.add_button("Option 2", payload={"action": "select", "id": 2})
        builder.row()
        builder.add_button("Cancel", payload={"action": "cancel"})
        keyboard = builder.build()
        
        # Create reply keyboard with contact button
        builder = KeyboardBuilder(inline=False)
        builder.add_contact_button("Share Contact")
        builder.row()
        builder.add_button("Cancel")
        keyboard = builder.build()
    """

    def __init__(self, inline: bool = True, one_time: bool = False):
        """
        Initialize keyboard builder.
        
        Args:
            inline: If True, creates inline keyboard; if False, creates reply keyboard
            one_time: If True, keyboard will be hidden after first use (reply keyboards only)
        """
        self.inline = inline
        self.one_time = one_time
        self.buttons: list[list[KeyboardButton]] = []
        self.current_row: list[KeyboardButton] = []

    def add_button(
        self,
        text: str,
        payload: Optional[dict] = None,
        button_type: str = "callback"
    ) -> "KeyboardBuilder":
        """
        Add a callback button to the current row.
        
        Args:
            text: Button text to display
            payload: Optional payload dictionary for callback data
            button_type: Button type (callback, link, contact, location)
            
        Returns:
            Self for method chaining
        """
        button = KeyboardButton(
            text=text,
            payload=payload,
            button_type=button_type
        )
        self.current_row.append(button)
        return self

    def add_callback_button(
        self,
        text: str,
        payload: dict
    ) -> "KeyboardBuilder":
        """
        Add a callback button to the current row.
        
        This is a convenience method for adding callback buttons with payloads.
        
        Args:
            text: Button text to display
            payload: Payload dictionary for callback data
            
        Returns:
            Self for method chaining
        """
        return self.add_button(text, payload=payload, button_type="callback")

    def add_link_button(
        self,
        text: str,
        url: str
    ) -> "KeyboardBuilder":
        """
        Add a link button to the current row.
        
        Args:
            text: Button text to display
            url: URL to open when button is clicked
            
        Returns:
            Self for method chaining
        """
        button = KeyboardButton(
            text=text,
            url=url,
            button_type="link"
        )
        self.current_row.append(button)
        return self

    def add_contact_button(
        self,
        text: str = "📱 Share Contact"
    ) -> "KeyboardBuilder":
        """
        Add a contact request button to the current row.
        
        Args:
            text: Button text to display
            
        Returns:
            Self for method chaining
        """
        button = KeyboardButton(
            text=text,
            button_type="contact"
        )
        self.current_row.append(button)
        return self

    def add_location_button(
        self,
        text: str = "📍 Share Location"
    ) -> "KeyboardBuilder":
        """
        Add a location request button to the current row.
        
        Args:
            text: Button text to display
            
        Returns:
            Self for method chaining
        """
        button = KeyboardButton(
            text=text,
            button_type="location"
        )
        self.current_row.append(button)
        return self

    def row(self) -> "KeyboardBuilder":
        """
        Finish the current row and start a new one.
        
        Returns:
            Self for method chaining
        """
        if self.current_row:
            self.buttons.append(self.current_row)
            self.current_row = []
        return self

    def adjust(self, *widths: int) -> "KeyboardBuilder":
        """
        Adjust button layout by specifying buttons per row.
        
        This method takes all buttons in the current row and redistributes them
        according to the specified widths. For example, adjust(2, 1) will create
        two rows: first with 2 buttons, second with 1 button.
        
        Args:
            *widths: Number of buttons per row
            
        Returns:
            Self for method chaining
            
        Example:
            builder.add_button("1").add_button("2").add_button("3")
            builder.adjust(2, 1)  # Creates [[1, 2], [3]]
        """
        if not self.current_row:
            return self

        # Finish current row first
        if self.current_row:
            self.buttons.append(self.current_row)
            self.current_row = []

        # Get all buttons from the last row
        if not self.buttons:
            return self

        all_buttons = self.buttons[-1]
        self.buttons.pop()  # Remove the last row

        # Redistribute buttons according to widths
        button_index = 0
        for width in widths:
            if button_index >= len(all_buttons):
                break

            row = all_buttons[button_index:button_index + width]
            if row:
                self.buttons.append(row)
            button_index += width

        # Add remaining buttons if any
        if button_index < len(all_buttons):
            remaining = all_buttons[button_index:]
            if remaining:
                self.buttons.append(remaining)

        return self

    def build(self) -> Keyboard:
        """
        Build and return the final keyboard.
        
        Returns:
            Keyboard object ready to be used with messenger adapter
        """
        # Add any remaining buttons in current row
        if self.current_row:
            self.buttons.append(self.current_row)
            self.current_row = []

        return Keyboard(
            buttons=self.buttons,
            inline=self.inline,
            one_time=self.one_time
        )

    def clear(self) -> "KeyboardBuilder":
        """
        Clear all buttons and start fresh.
        
        Returns:
            Self for method chaining
        """
        self.buttons = []
        self.current_row = []
        return self


def create_paginated_keyboard(
    items: list[dict],
    page: int = 0,
    items_per_page: int = 10,
    buttons_per_row: int = 2,
    item_text_key: str = "name",
    item_id_key: str = "id",
    callback_action: str = "select",
    page_action: str = "page"
) -> Keyboard:
    """
    Create a paginated keyboard for displaying lists of items.
    
    This is a convenience function for creating keyboards with pagination controls.
    It automatically adds navigation buttons (previous/next) and a cancel button.
    
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
        items = [{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}]
        keyboard = create_paginated_keyboard(items, page=0)
    """
    import math

    builder = KeyboardBuilder(inline=True)

    # Calculate pagination
    total_pages = math.ceil(len(items) / items_per_page)
    start_index = page * items_per_page
    end_index = start_index + items_per_page
    items_on_page = items[start_index:end_index]

    # Add item buttons
    for item in items_on_page:
        builder.add_callback_button(
            text=item[item_text_key],
            payload={
                "action": callback_action,
                item_id_key: item[item_id_key]
            }
        )

    # Adjust layout for items
    if items_on_page:
        builder.row()
        # Redistribute buttons according to buttons_per_row
        num_rows = math.ceil(len(items_on_page) / buttons_per_row)
        widths = [buttons_per_row] * num_rows
        builder.adjust(*widths)

    # Add pagination controls if needed
    if total_pages > 1:
        if page > 0:
            builder.add_callback_button(
                text="⬅️ Previous",
                payload={"action": page_action, "page": page - 1}
            )

        builder.add_callback_button(
            text=f"{page + 1}/{total_pages}",
            payload={"action": "noop"}
        )

        if page < total_pages - 1:
            builder.add_callback_button(
                text="Next ➡️",
                payload={"action": page_action, "page": page + 1}
            )

        builder.row()

    # Add cancel button
    builder.add_callback_button(
        text="❌ Cancel",
        payload={"action": "cancel"}
    )

    return builder.build()


def create_confirmation_keyboard(
    confirm_text: str = "✅ Confirm",
    cancel_text: str = "❌ Cancel",
    confirm_payload: Optional[dict] = None,
    cancel_payload: Optional[dict] = None
) -> Keyboard:
    """
    Create a simple confirmation keyboard with confirm and cancel buttons.
    
    Args:
        confirm_text: Text for confirm button
        cancel_text: Text for cancel button
        confirm_payload: Payload for confirm button (defaults to {"action": "confirm"})
        cancel_payload: Payload for cancel button (defaults to {"action": "cancel"})
        
    Returns:
        Keyboard with confirmation buttons
    """
    builder = KeyboardBuilder(inline=True)

    builder.add_callback_button(
        text=confirm_text,
        payload=confirm_payload or {"action": "confirm"}
    )

    builder.add_callback_button(
        text=cancel_text,
        payload=cancel_payload or {"action": "cancel"}
    )

    return builder.build()


def create_navigation_keyboard(
    back_text: str = "⬅️ Back",
    back_payload: Optional[dict] = None
) -> Keyboard:
    """
    Create a simple navigation keyboard with a back button.
    
    Args:
        back_text: Text for back button
        back_payload: Payload for back button (defaults to {"action": "back"})
        
    Returns:
        Keyboard with navigation button
    """
    builder = KeyboardBuilder(inline=True)

    builder.add_callback_button(
        text=back_text,
        payload=back_payload or {"action": "back"}
    )

    return builder.build()
