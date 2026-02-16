"""
Reply Keyboards for MAX Bot

This module provides reply keyboard creation functions using the KeyboardBuilder
utility. Reply keyboards appear as persistent keyboards in the chat interface
and can include special buttons like contact and location requests.

Pattern: Use KeyboardBuilder for reply keyboards
- Set inline=False when creating KeyboardBuilder
- Use one_time=True for keyboards that should hide after use
- Support contact and location request buttons
- Provide common reply keyboard patterns

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""


from bots.max_bot.keyboards.keyboard_builder import KeyboardBuilder
from bots.max_bot.messenger_adapter import Keyboard


async def create_main_menu_keyboard() -> Keyboard:
    """
    Create the main menu reply keyboard.
    
    This keyboard provides quick access to main bot functions and is
    displayed persistently in the chat interface.
    
    Returns:
        Reply keyboard with main menu options
        
    Example:
        keyboard = await create_main_menu_keyboard()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Main menu:",
            keyboard=keyboard
        )
    """
    builder = KeyboardBuilder(inline=False, one_time=False)

    # First row: Primary actions
    builder.add_button("📋 Catalog")
    builder.add_button("ℹ️ Information")
    builder.row()

    # Second row: Secondary actions
    builder.add_button("⚙️ Settings")
    builder.add_button("📞 Support")

    return builder.build()


async def create_contact_keyboard(
    contact_button_text: str = "📱 Share Contact",
    add_cancel: bool = True
) -> Keyboard:
    """
    Create a keyboard for requesting user contact.
    
    This keyboard includes a special contact request button that, when pressed,
    prompts the user to share their phone number.
    
    Args:
        contact_button_text: Text for the contact request button
        add_cancel: Whether to add a cancel button
        
    Returns:
        Reply keyboard with contact request button
        
    Example:
        keyboard = await create_contact_keyboard()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Please share your contact:",
            keyboard=keyboard
        )
    """
    builder = KeyboardBuilder(inline=False, one_time=True)

    # Add contact request button
    builder.add_contact_button(text=contact_button_text)
    builder.row()

    # Add cancel button if requested
    if add_cancel:
        builder.add_button("❌ Cancel")

    return builder.build()


async def create_location_keyboard(
    location_button_text: str = "📍 Share Location",
    add_cancel: bool = True
) -> Keyboard:
    """
    Create a keyboard for requesting user location.
    
    This keyboard includes a special location request button that, when pressed,
    prompts the user to share their location.
    
    Args:
        location_button_text: Text for the location request button
        add_cancel: Whether to add a cancel button
        
    Returns:
        Reply keyboard with location request button
        
    Example:
        keyboard = await create_location_keyboard()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Please share your location:",
            keyboard=keyboard
        )
    """
    builder = KeyboardBuilder(inline=False, one_time=True)

    # Add location request button
    builder.add_location_button(text=location_button_text)
    builder.row()

    # Add cancel button if requested
    if add_cancel:
        builder.add_button("❌ Cancel")

    return builder.build()


async def create_custom_reply_keyboard(
    buttons: list[str],
    buttons_per_row: int = 2,
    one_time: bool = False
) -> Keyboard:
    """
    Create a custom reply keyboard with text buttons.
    
    Args:
        buttons: List of button texts
        buttons_per_row: Number of buttons per row
        one_time: Whether keyboard should hide after first use
        
    Returns:
        Reply keyboard with custom buttons
        
    Example:
        buttons = ["Option 1", "Option 2", "Option 3", "Cancel"]
        keyboard = await create_custom_reply_keyboard(buttons, buttons_per_row=2)
    """
    builder = KeyboardBuilder(inline=False, one_time=one_time)

    # Add all buttons
    for button_text in buttons:
        builder.add_button(button_text)

    # Adjust layout
    if buttons:
        builder.row()
        import math
        num_rows = math.ceil(len(buttons) / buttons_per_row)
        widths = [buttons_per_row] * num_rows
        builder.adjust(*widths)

    return builder.build()


async def create_yes_no_reply_keyboard(
    yes_text: str = "✅ Yes",
    no_text: str = "❌ No",
    one_time: bool = True
) -> Keyboard:
    """
    Create a simple yes/no reply keyboard.
    
    Args:
        yes_text: Text for yes button
        no_text: Text for no button
        one_time: Whether keyboard should hide after first use
        
    Returns:
        Reply keyboard with yes/no buttons
    """
    builder = KeyboardBuilder(inline=False, one_time=one_time)

    builder.add_button(yes_text)
    builder.add_button(no_text)

    return builder.build()


async def create_cancel_keyboard(
    cancel_text: str = "❌ Cancel"
) -> Keyboard:
    """
    Create a simple keyboard with just a cancel button.
    
    Args:
        cancel_text: Text for cancel button
        
    Returns:
        Reply keyboard with cancel button
    """
    builder = KeyboardBuilder(inline=False, one_time=False)

    builder.add_button(cancel_text)

    return builder.build()


def remove_keyboard() -> None:
    """
    Remove the reply keyboard.
    
    Note: In the messenger abstraction layer, removing keyboards is handled
    by sending a message with keyboard=None. This function is provided for
    compatibility with existing code patterns.
    
    Returns:
        None (send message with keyboard=None to remove keyboard)
        
    Example:
        # To remove keyboard, send message without keyboard parameter
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Keyboard removed",
            keyboard=None
        )
    """
    return None
