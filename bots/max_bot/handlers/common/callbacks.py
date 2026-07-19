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
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback

from bots.max_bot.callback_datas import (
    ExampleItemCallback,
    ExampleNavigationCallback,
)
from bots.max_bot.keyboards.common.inline_kb import create_paginated_keyboard_async
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.utils.callback_utils import answer_max_callback

logger = logging.getLogger(__name__)

router = Router(router_id="callbacks")


@router.message_callback(ExampleItemCallback.filter(F.action == "view"))
async def process_pagination(
    event: MessageCallback,
    messenger_adapter: MAXMessengerAdapter
):
    """
    Handler for list pagination.
    
    Pattern:
    - Filter by action
    - Immediate callback response
    - In MAX API, we can't send keyboards in callback responses
    - Just acknowledge the callback
    
    Requirements: 5.1, 5.2, 5.3, 5.6
    """
    # Parse payload manually
    import json
    raw_payload = event.callback.payload
    if isinstance(raw_payload, str):
        payload_dict = json.loads(raw_payload) if raw_payload else {}
    else:
        payload_dict = raw_payload or {}
    
    page = payload_dict.get("page", 0)

    # Answer callback with notification
    if not await answer_max_callback(
        event,
        notification=f"Page {page + 1} selected",
    ):
        return


@router.message_callback(ExampleItemCallback.filter(F.action == "select"))
async def process_item_selection(
    event: MessageCallback,
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
    if not await answer_max_callback(event):
        return

    # Parse payload manually
    import json
    raw_payload = event.callback.payload
    if isinstance(raw_payload, str):
        payload_dict = json.loads(raw_payload) if raw_payload else {}
    else:
        payload_dict = raw_payload or {}
    
    item_id = payload_dict.get("item_id")

    # Here should be logic to get data by ID
    # item = await get_item_by_id(item_id)

    text = f"✅ You selected item #{item_id}\n\nWhat would you like to do next?"

    try:
        # Delete old message and send new one
        try:
            await event.message.delete()
        except Exception:
            pass
        
        # Send new message
        await messenger_adapter.send_message(
            chat_id=event.chat.chat_id,
            text=text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Failed to send message: {e}")
        await answer_max_callback(event, notification=text)


@router.message_callback(ExampleItemCallback.filter(F.action == "cancel"))
async def process_cancel(
    event: MessageCallback,
    state: MemoryContext,
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
    if not await answer_max_callback(event):
        return

    # Clear FSM state
    await state.clear()

    text = "❌ Action cancelled.\nUse /start to begin."

    try:
        # Delete old message and send new one
        try:
            await event.message.delete()
        except Exception:
            pass
        
        # Send new message
        await messenger_adapter.send_message(
            chat_id=event.chat.chat_id,
            text=text
        )
    except Exception as e:
        logger.warning(f"Failed to send message: {e}")
        await answer_max_callback(event, notification=text)


@router.message_callback(ExampleNavigationCallback.filter(F.action == "back"))
async def process_back_navigation(
    event: MessageCallback,
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
    if not await answer_max_callback(event):
        return

    # Parse payload manually
    import json
    raw_payload = event.callback.payload
    if isinstance(raw_payload, str):
        payload_dict = json.loads(raw_payload) if raw_payload else {}
    else:
        payload_dict = raw_payload or {}
    
    from_section = payload_dict.get("from_section")

    text = f"⬅️ Returning from section: {from_section}"

    try:
        # Edit message with new text
        await messenger_adapter.edit_message(
            chat_id=event.chat.chat_id,
            message_id=None,  # MAX API callbacks don't provide message_id
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
    await answer_max_callback(
        event,
        notification="This is a page indicator",
    )


