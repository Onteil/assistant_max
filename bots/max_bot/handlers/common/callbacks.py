"""
Callback Query Handlers for MAX Bot

This module handles callback queries from inline keyboard buttons.
Migrated from Telegram bot to use maxapi's message_callback decorator.

Pattern: Handle callback requests from inline buttons
- Use CallbackPayload factories with filters
- Always call event.answer() to acknowledge the callback
- Use messenger_adapter for message updates
- Handle errors (message may be deleted)

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

import logging

from maxapi import F, Router
from maxapi.fsm.context import FSMContext
from maxapi.types import MessageCallback

from bots.max_bot.callback_datas import (
    ExampleItemCallback,
    ExampleNavigationCallback,
)
from bots.max_bot.keyboards.common.inline_kb import create_paginated_keyboard_async
from bots.max_bot.messenger_adapter import MAXMessengerAdapter

logger = logging.getLogger(__name__)

router = Router(name="callbacks")


@router.message_callback(ExampleItemCallback.filter(F.action == "view"))
async def process_pagination(
    event: MessageCallback,
    payload: ExampleItemCallback,
    messenger_adapter: MAXMessengerAdapter
):
    """
    Handler for list pagination.
    
    Pattern:
    - Filter by action
    - Immediate callback response
    - Update only keyboard (without changing text)
    
    Requirements: 5.1, 5.2, 5.3, 5.6
    """
    # Answer callback to remove loading indicator
    await event.answer()

    page = payload.page or 0

    # Here should be logic to get data from database
    # items = await get_items_from_db()
    items = [{"id": i, "name": f"Item {i}"} for i in range(1, 51)]

    # Create paginated keyboard
    keyboard = await create_paginated_keyboard_async(
        items=items,
        page=page,
        callback_action="select",
        page_action="view"
    )

    try:
        # Edit message with new keyboard
        await messenger_adapter.edit_message(
            chat_id=event.chat.chat_id,
            message_id=event.message.message_id,
            text=event.message.body.text,  # Keep same text
            keyboard=keyboard
        )
    except Exception as e:
        logger.warning(f"Failed to edit message: {e}")
        await event.answer(new_text="An error occurred. Please try again.")


@router.message_callback(ExampleItemCallback.filter(F.action == "select"))
async def process_item_selection(
    event: MessageCallback,
    payload: ExampleItemCallback,
    messenger_adapter: MAXMessengerAdapter
):
    """
    Handler for item selection from list.
    
    Pattern:
    - Get data by ID
    - Update text and keyboard
    - Move to next step
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
    """
    # Answer callback
    await event.answer()

    item_id = payload.item_id

    # Here should be logic to get data by ID
    # item = await get_item_by_id(item_id)

    text = f"✅ You selected item #{item_id}\n\nWhat would you like to do next?"

    try:
        # Edit message with new text
        await messenger_adapter.edit_message(
            chat_id=event.chat.chat_id,
            message_id=event.message.message_id,
            text=text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Failed to edit message: {e}")
        # If edit fails, send new message
        await messenger_adapter.send_message(
            chat_id=event.chat.chat_id,
            text=text,
            parse_mode="HTML"
        )


@router.message_callback(ExampleItemCallback.filter(F.action == "cancel"))
async def process_cancel(
    event: MessageCallback,
    payload: ExampleItemCallback,
    state: FSMContext,
    messenger_adapter: MAXMessengerAdapter
):
    """
    Handler for cancel action.
    
    Pattern:
    - Clear state
    - Remove keyboard
    - Inform user
    
    Requirements: 5.1, 5.2, 5.3
    """
    # Answer callback
    await event.answer()

    # Clear FSM state
    await state.clear()

    text = "❌ Action cancelled.\nUse /start to begin."

    try:
        # Edit message and remove keyboard
        await messenger_adapter.edit_message(
            chat_id=event.chat.chat_id,
            message_id=event.message.message_id,
            text=text,
            keyboard=None
        )
    except Exception as e:
        logger.warning(f"Failed to edit message: {e}")
        # If edit fails, send new message
        await messenger_adapter.send_message(
            chat_id=event.chat.chat_id,
            text=text
        )


@router.message_callback(ExampleNavigationCallback.filter(F.action == "back"))
async def process_back_navigation(
    event: MessageCallback,
    payload: ExampleNavigationCallback,
    messenger_adapter: MAXMessengerAdapter
):
    """
    Handler for "Back" button.
    
    Pattern:
    - Contextual return (from_section)
    - Restore previous menu
    
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    # Answer callback
    await event.answer()

    from_section = payload.from_section

    text = f"⬅️ Returning from section: {from_section}"

    try:
        # Edit message with new text
        await messenger_adapter.edit_message(
            chat_id=event.chat.chat_id,
            message_id=event.message.message_id,
            text=text
        )
    except Exception as e:
        logger.warning(f"Failed to edit message: {e}")
        # If edit fails, send new message
        await messenger_adapter.send_message(
            chat_id=event.chat.chat_id,
            text=text
        )


@router.message_callback(F.callback.payload == "noop")
async def process_noop(event: MessageCallback):
    """
    Handler for "empty" buttons (e.g., page indicator).
    
    Pattern:
    - Simply answer callback without actions
    - Can show alert with information
    
    Requirements: 5.3, 5.6
    """
    # Answer callback with informational text
    await event.answer(new_text="This is a page indicator")
