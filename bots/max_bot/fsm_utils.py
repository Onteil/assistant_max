"""
FSM Context Operations Utilities for MAX Bot

This module provides utility functions and documentation for working with
maxapi's FSM (Finite State Machine) context operations. The MemoryContext
is automatically injected into handlers and provides state management
functionality.

Key Features:
- State management: set_state(), get_state(), clear()
- Data storage: update_data(), get_data()
- Automatic chat_id-based state isolation
- Async/await support for all operations

Usage Pattern:
    @dp.message_created(Command('start'))
    async def start_handler(event: MessageCreated, context: MemoryContext):
        await context.set_state(RegistrationStates.waiting_for_phone)
        await context.update_data(started_at=datetime.now())
"""

from typing import Any, Dict, Optional
from maxapi.context import MemoryContext, State


async def set_state(context: MemoryContext, state: State) -> None:
    """
    Set the current FSM state for the user.
    
    The state is automatically associated with the chat_id from the event context.
    This replaces the Aiogram pattern of state.set_state().
    
    Args:
        context: MemoryContext instance (injected by maxapi)
        state: State instance from a StatesGroup
        
    Example:
        await set_state(context, RegistrationStates.waiting_for_phone)
    """
    await context.set_state(state)


async def get_state(context: MemoryContext) -> Optional[str]:
    """
    Get the current FSM state for the user.
    
    Returns the state name as a string, or None if no state is set.
    The state is automatically retrieved based on the chat_id.
    
    Args:
        context: MemoryContext instance (injected by maxapi)
        
    Returns:
        Current state name as string, or None
        
    Example:
        current_state = await get_state(context)
        if current_state == str(RegistrationStates.waiting_for_phone):
            # Handle phone input
    """
    return await context.get_state()


async def clear_state(context: MemoryContext) -> None:
    """
    Clear the current FSM state and all associated data.
    
    This removes both the state and all data stored via update_data().
    Useful for resetting conversation flows or handling /start command.
    
    Args:
        context: MemoryContext instance (injected by maxapi)
        
    Example:
        await clear_state(context)  # Reset everything
    """
    await context.clear()


async def update_data(context: MemoryContext, **kwargs: Any) -> None:
    """
    Update FSM context data with new key-value pairs.
    
    Data is stored per chat_id and persists across handler calls
    until explicitly cleared. This replaces the Aiogram pattern of
    state.update_data().
    
    Args:
        context: MemoryContext instance (injected by maxapi)
        **kwargs: Key-value pairs to store in context
        
    Example:
        await update_data(context, phone="+79991234567", name="Ivan")
        await update_data(context, inn="1234567890")
    """
    await context.update_data(**kwargs)


async def get_data(context: MemoryContext) -> Dict[str, Any]:
    """
    Retrieve all FSM context data for the current user.
    
    Returns a dictionary containing all data stored via update_data().
    The data is automatically retrieved based on the chat_id.
    
    Args:
        context: MemoryContext instance (injected by maxapi)
        
    Returns:
        Dictionary containing all stored context data
        
    Example:
        data = await get_data(context)
        phone = data.get('phone')
        name = data.get('name', 'Unknown')
    """
    return await context.get_data()


async def get_data_value(context: MemoryContext, key: str, default: Any = None) -> Any:
    """
    Retrieve a specific value from FSM context data.
    
    Convenience method to get a single value without retrieving all data.
    
    Args:
        context: MemoryContext instance (injected by maxapi)
        key: Data key to retrieve
        default: Default value if key doesn't exist
        
    Returns:
        Value associated with key, or default if not found
        
    Example:
        phone = await get_data_value(context, 'phone', 'Not provided')
    """
    data = await context.get_data()
    return data.get(key, default)


# ========== Migration Notes ==========
"""
Aiogram to maxapi FSM Migration Guide:

1. State Setting:
   Aiogram:  await state.set_state(RegistrationStates.waiting_for_phone)
   maxapi:   await context.set_state(RegistrationStates.waiting_for_phone)

2. State Getting:
   Aiogram:  current_state = await state.get_state()
   maxapi:   current_state = await context.get_state()

3. State Clearing:
   Aiogram:  await state.clear()
   maxapi:   await context.clear()

4. Data Update:
   Aiogram:  await state.update_data(phone=phone, name=name)
   maxapi:   await context.update_data(phone=phone, name=name)

5. Data Retrieval:
   Aiogram:  data = await state.get_data()
   maxapi:   data = await context.get_data()

6. Handler Injection:
   Aiogram:  async def handler(message: Message, state: FSMContext):
   maxapi:   async def handler(event: MessageCreated, context: MemoryContext):

7. State Key Identifier:
   Aiogram:  Uses user_id + chat_id (FSMStrategy.USER_IN_CHAT)
   maxapi:   Uses chat_id automatically (simpler, suitable for private chats)

8. State Decorators:
   Aiogram:  @router.message(StateFilter(RegistrationStates.waiting_for_phone))
   maxapi:   @dp.message_created(F.message.body.text, RegistrationStates.waiting_for_phone)
"""
