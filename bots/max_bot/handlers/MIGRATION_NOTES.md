# MAX Bot Message Handlers Migration Notes

## Completed Migrations

### 10.1 Registration Flow Handlers ✅
- **File**: `bots/max_bot/handlers/registration.py`
- **Status**: Fully migrated
- **Key Changes**:
  - Replaced `message.from_user.id` with `message.from_user.user_id`
  - Replaced `message.chat.id` with `message.chat.chat_id`
  - Replaced `message.text` with `message.body.text`
  - Used maxapi's FSM state decorators (`state.set_state()`, `state.get_data()`, `state.update_data()`)
  - All message sending goes through `messenger_adapter.send_message()`
  - All message editing goes through `messenger_adapter.edit_message()`
  - Callback answers use maxapi's `callback.answer()` method

### 10.2 Invoice Flow Handlers ✅
- **File**: `bots/max_bot/handlers/invoice.py`
- **Status**: Fully migrated
- **Key Changes**:
  - Same attribute mapping as registration handlers
  - Callback query handlers migrated to use maxapi types
  - FSM state transitions use maxapi methods
  - All business logic preserved without modification

## Remaining Migrations (Follow Same Pattern)

### 10.3 Support Flow Handlers
- **Source**: `bots/tg_bot/handlers/support.py`
- **Target**: `bots/max_bot/handlers/support.py`
- **Migration Pattern**:
  ```python
  # OLD (Aiogram):
  @router.message(SupportStates.entering_problem, F.text)
  async def process_problem_description_text(message: Message, state: FSMContext, session: AsyncSession):
      description = message.text.strip()
      telegram_id = message.from_user.id
      await message.answer(text)
  
  # NEW (maxapi):
  async def process_problem_description_text(
      message: Message, 
      state: FSMContext, 
      session: AsyncSession,
      messenger_adapter
  ):
      description = message.body.text.strip()
      user_id = message.from_user.user_id
      chat_id = message.chat.chat_id
      await messenger_adapter.send_message(chat_id=chat_id, text=text, keyboard=None, parse_mode="HTML")
  ```

### 10.4 Profile Management Handlers
- **Source**: `bots/tg_bot/handlers/profile.py`
- **Target**: `bots/max_bot/handlers/profile.py`
- **Key Handlers to Migrate**:
  - `show_profile()` - Display user profile
  - `handle_profile_action()` - Route profile actions
  - `process_new_inn()` - Add organization
  - `process_new_key()` - Add GS_Key
  - `process_phone_change_request()` - Request phone change
  - `toggle_notifications()` - Toggle notification preferences

### 10.5 Employee Interface Handlers
- **Source**: `bots/tg_bot/handlers/employee.py`
- **Target**: `bots/max_bot/handlers/employee.py`
- **Key Handlers to Migrate**:
  - `show_employee_menu()` - Display employee menu
  - `show_active_tickets()` - List active tickets
  - `take_ticket_into_work()` - Take ticket and enter focus mode
  - `set_ticket_waiting()` - Set ticket to waiting for client
  - `initiate_ticket_close()` - Start ticket closing flow
  - `complete_ticket_close()` - Complete ticket closing
  - `initiate_ticket_transfer()` - Start ticket transfer flow
  - `complete_ticket_transfer()` - Complete ticket transfer
  - `view_ticket_history()` - Display ticket history
  - `execute_archive_search()` - Search closed tickets

## Universal Migration Rules

### 1. Message Attribute Mapping
```python
# Aiogram → maxapi
message.from_user.id → message.from_user.user_id
message.chat.id → message.chat.chat_id
message.text → message.body.text
message.photo → message.photo  # Same
message.document → message.document  # Same
message.voice → message.voice  # Same
message.contact → message.contact  # Same
```

### 2. FSM State Management
```python
# Aiogram → maxapi (Same API)
await state.set_state(State)
await state.get_state()
await state.clear()
await state.update_data(**kwargs)
await state.get_data()
```

### 3. Message Sending
```python
# OLD (Aiogram):
await message.answer(text, reply_markup=keyboard)

# NEW (maxapi via adapter):
await messenger_adapter.send_message(
    chat_id=message.chat.chat_id,
    text=text,
    keyboard=keyboard,  # Abstract keyboard
    parse_mode="HTML"
)
```

### 4. Message Editing
```python
# OLD (Aiogram):
await callback.message.edit_text(text, reply_markup=keyboard)

# NEW (maxapi via adapter):
await messenger_adapter.edit_message(
    chat_id=callback.message.chat.chat_id,
    message_id=callback.message.message_id,
    text=text,
    keyboard=keyboard,
    parse_mode="HTML"
)
```

### 5. Callback Query Handling
```python
# OLD (Aiogram):
@router.callback_query(StateFilter(State), CallbackData.filter())
async def handler(callback: CallbackQuery, callback_data: CallbackData, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(text)

# NEW (maxapi):
async def handler(
    callback: CallbackQuery, 
    callback_data: CallbackData, 
    state: FSMContext,
    messenger_adapter
):
    await callback.answer()  # Same
    await messenger_adapter.edit_message(
        chat_id=callback.message.chat.chat_id,
        message_id=callback.message.message_id,
        text=text,
        keyboard=None,
        parse_mode="HTML"
    )
```

### 6. Media Handling
```python
# Photo handling (same structure)
photo = message.photo[-1]  # Get largest photo
file_id = photo.file_id

# Document handling (same structure)
document = message.document
file_id = document.file_id
file_name = document.file_name

# Voice handling (same structure)
voice = message.voice
file_id = voice.file_id
duration = voice.duration
```

## Handler Registration

All migrated handlers need to be registered in the MAX bot dispatcher. This will be done in a separate task when setting up the dispatcher architecture.

Example registration pattern:
```python
from maxapi import Dispatcher, Router
from bots.max_bot.handlers import registration, invoice, support, profile, employee

# Create router
router = Router()

# Register handlers with state filters
router.message.register(
    registration.process_full_name,
    StateFilter(RegistrationStates.waiting_for_name),
    F.message.body.text
)

# Register callback handlers
router.message_callback.register(
    invoice.process_organization_selection,
    StateFilter(InvoiceStates.selecting_organization),
    OrganizationCallback.filter()
)
```

## Testing Checklist

For each migrated handler:
- [ ] Verify message attribute mapping (user_id, chat_id, text)
- [ ] Verify FSM state transitions work correctly
- [ ] Verify messenger_adapter is used for all message operations
- [ ] Verify callback.answer() is called for all callback queries
- [ ] Verify business logic is preserved without modification
- [ ] Verify error handling is maintained
- [ ] Verify logging statements are updated with correct variable names

## Next Steps

1. Complete migration of remaining handlers (10.3, 10.4, 10.5)
2. Create keyboard abstraction implementations
3. Register all handlers in MAX bot dispatcher
4. Test end-to-end flows with MAX messenger
5. Update middleware to work with maxapi types
