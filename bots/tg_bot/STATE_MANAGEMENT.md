# FSM State Management and Cancel Command

This document describes the state management implementation for the I-TAT Telegram bot, including the global cancel command and state cleanup procedures.

## Overview

The bot uses Aiogram's FSM (Finite State Machine) to manage multi-step conversation flows. Proper state management ensures:
- Users can cancel operations at any time
- No partial data is persisted when flows are cancelled
- State is properly cleaned up after flow completion
- Users return to appropriate menu after cancellation

## Requirements

This implementation satisfies the following requirements:
- **27.1-27.5**: FSM state cleanup after flow completion
- **28.1-28.5**: Cancel command functionality

## Global Cancel Handler

### Location
`bots/tg_bot/handlers/cancel.py`

### Functionality

The global cancel handler (`cmd_cancel`) provides:

1. **Universal Cancel Command**: `/cancel` works in any FSM state
2. **State Cleanup**: Completely clears FSM state data
3. **Smart Navigation**: Returns users to appropriate location based on registration status
4. **No Partial Data**: Ensures no database records are created when flow is cancelled

### Usage

Users can cancel any operation by:
- Sending `/cancel` command
- Pressing the "❌ Отмена" button (where available)

### Behavior

```python
# When user sends /cancel:
1. Get current FSM state (for logging)
2. Clear all FSM state data
3. Check user registration status
4. If ACTIVE: Show main menu
5. If not ACTIVE: Show start message
6. Log cancellation event
```

## State Cleanup After Flow Completion

All handlers implement proper state cleanup after successful flow completion:

### Registration Flow
```python
# In submit_registration()
await session.commit()
await state.clear()  # Clean up after successful registration
await message.answer(REGISTRATION_SUBMITTED)
```

### Invoice Request Flow
```python
# In create_invoice_ticket()
await session.commit()
await state.clear()  # Clean up after ticket creation
await message.answer(INVOICE_CREATED.format(...))
```

### Technical Support Flow
```python
# In create_support_ticket()
await session.commit()
await state.clear()  # Clean up after ticket creation
await message.answer(SUPPORT_TICKET_CREATED.format(...))
```

### Profile Management Flow
```python
# In process_new_inn(), process_new_key(), etc.
await session.commit()
await state.clear()  # Clean up after profile update
await message.answer(PROFILE_INN_ADDED.format(...))
```

## State Groups

The bot uses the following state groups:

### RegistrationStates
- `waiting_for_phone`: Waiting for phone number via contact button
- `waiting_for_name`: Waiting for full name input
- `waiting_for_inn`: Waiting for INN input
- `waiting_for_key`: Waiting for GS_Key input

### InvoiceStates
- `selecting_organization`: Selecting organization for invoice
- `adding_new_inn`: Adding new organization INN
- `selecting_keys`: Multi-selecting GS_Keys
- `adding_new_key`: Adding new GS_Key
- `entering_description`: Entering invoice description
- `selecting_delivery`: Selecting delivery method
- `entering_email`: Entering email address (if email delivery)

### SupportStates
- `entering_problem`: Entering problem description (text/photo/voice/document)
- `selecting_key_context`: Selecting related GS_Key (optional)

### ProfileStates
- `adding_inn`: Adding new organization to profile
- `adding_key`: Adding new GS_Key to profile
- `changing_phone`: Requesting phone number change

## Cancel Button Integration

### Inline Cancel Checks

Many handlers include inline cancel checks for the cancel button text:

```python
@router.message(SomeState.some_step, F.text)
async def process_input(message: Message, state: FSMContext):
    input_text = message.text.strip()
    
    # Check for cancel button
    if input_text == BTN_CANCEL:
        await state.clear()
        await message.answer("❌ Операция отменена.")
        return
    
    # Process normal input...
```

These work alongside the global `/cancel` command handler.

## Router Registration Order

The cancel router is registered **first** in the main router to ensure it has priority:

```python
# In bots/tg_bot/handlers/__init__.py
tg_bot_router.include_routers(
    cancel_router,        # First - handles /cancel in any state
    registration_router,  # Second - handles /start
    invoice_router,
    support_router,
    profile_router,
    commands_router,
    callbacks_router,
    messages_router
)
```

## Testing

Comprehensive tests are provided in `test_cancel_flow.py`:

- `test_cancel_command_no_state`: Cancel when no state is active
- `test_cancel_command_during_registration`: Cancel during registration
- `test_cancel_command_during_invoice_flow`: Cancel during invoice request
- `test_cancel_command_during_support_flow`: Cancel during support request
- `test_cancel_command_during_profile_flow`: Cancel during profile management
- `test_cancel_button_handler`: Cancel button text handler
- `test_state_cleanup_no_partial_data`: Verify no partial data persists
- `test_cancel_returns_to_main_menu_for_active_users`: Verify main menu return

## Best Practices

### When Adding New Flows

1. **Create State Group**: Define states in `bots/tg_bot/states.py`
2. **Add Cancel Checks**: Include inline cancel checks in text handlers
3. **Clean Up on Completion**: Call `await state.clear()` after successful completion
4. **Clean Up on Error**: Call `await state.clear()` in error handlers
5. **Test Cancel**: Add tests for cancel functionality in your flow

### Example New Flow

```python
class NewFlowStates(StatesGroup):
    """States for new flow."""
    step_one = State()
    step_two = State()

@router.message(NewFlowStates.step_one, F.text)
async def process_step_one(message: Message, state: FSMContext):
    input_text = message.text.strip()
    
    # Inline cancel check
    if input_text == BTN_CANCEL:
        await state.clear()
        await message.answer("❌ Операция отменена.")
        return
    
    # Process input
    await state.update_data(step_one_data=input_text)
    await state.set_state(NewFlowStates.step_two)
    await message.answer("Введите данные для шага 2:")

@router.message(NewFlowStates.step_two, F.text)
async def process_step_two(message: Message, state: FSMContext, session: AsyncSession):
    input_text = message.text.strip()
    
    # Inline cancel check
    if input_text == BTN_CANCEL:
        await state.clear()
        await message.answer("❌ Операция отменена.")
        return
    
    # Get all data
    data = await state.get_data()
    
    try:
        # Process and save to database
        # ... database operations ...
        await session.commit()
        
        # Clean up state after success
        await state.clear()
        
        await message.answer("✅ Операция завершена!")
    
    except Exception as e:
        await session.rollback()
        # Clean up state on error
        await state.clear()
        await message.answer("❌ Произошла ошибка.")
```

## Troubleshooting

### State Not Clearing

If state is not clearing properly:
1. Check that `await state.clear()` is called
2. Verify it's called in all exit paths (success, error, cancel)
3. Check for exceptions that might prevent cleanup

### Cancel Not Working

If cancel command doesn't work:
1. Verify cancel router is registered first
2. Check that handler has correct signature: `(message, state, session)`
3. Verify imports are correct

### Partial Data Persisting

If partial data is being saved:
1. Ensure `await state.clear()` is called before database commit
2. Use try/except with rollback on errors
3. Don't commit database changes until flow is complete

## Logging

All cancel operations are logged:

```python
logger.info(
    f"User {tg_user_id} cancelled operation, "
    f"previous state: {current_state or 'None'}"
)
```

This helps track:
- Which users are cancelling operations
- At what point in flows cancellations occur
- Frequency of cancellations (may indicate UX issues)

## Security Considerations

- State data is stored in FSM storage (Redis or in-memory)
- State is user-specific and isolated
- Clearing state removes all temporary data
- No sensitive data should be logged
- Database transactions are rolled back on cancel

## Performance

- State cleanup is fast (single operation)
- No database queries needed for cancel
- Minimal memory footprint
- State storage is automatically managed by Aiogram
