# MAX Bot Implementation

This directory contains the MAX messenger bot implementation using the maxapi library.

## Overview

The MAX bot is a migration from the Telegram bot (Aiogram 3.24.0) to MAX messenger. It maintains all business logic, FSM state management, and user experience while using the maxapi framework.

## Architecture

### Core Components

1. **Bot Instance** (`loaders.py`)
   - Initialized with `MAX_BOT_TOKEN` from environment
   - Configured with HTML parse mode by default
   - Auto-requests enabled for chat/user object population

2. **Dispatcher** (`loaders.py`)
   - Routes incoming updates to appropriate handlers
   - Manages middleware execution
   - Handles webhook and polling modes

3. **Router** (`loaders.py`)
   - Organizes handlers into logical groups
   - Main router: `max_bot_router` with ID "max_bot_main"

4. **FSM Storage** (`loaders.py`)
   - Uses `MemoryContext` for development
   - Can be switched to Redis for production
   - Automatically manages state per chat_id

5. **Messenger Adapter** (`messenger_adapter.py`)
   - Abstraction layer over MAX API
   - Provides messenger-agnostic interfaces
   - Enables future messenger migrations

## State Management

### State Groups (`states.py`)

All FSM state groups have been migrated from Aiogram to maxapi:

- `RegistrationStates` - User registration flow
- `InvoiceStates` - Invoice request flow
- `SupportStates` - Technical support flow
- `ProfileStates` - Profile management
- `FormStates` - Form filling
- `EmployeeStates` - Employee interface

### FSM Operations (`fsm_utils.py`)

The FSM context provides these operations:

```python
# Set state
await context.set_state(RegistrationStates.waiting_for_phone)

# Get current state
current_state = await context.get_state()

# Clear state and data
await context.clear()

# Update context data
await context.update_data(phone="+79991234567", name="Ivan")

# Get all context data
data = await context.get_data()
```

### Key Differences from Aiogram

| Aspect | Aiogram | maxapi |
|--------|---------|--------|
| State parameter | `state: FSMContext` | `context: MemoryContext` |
| State key | `user_id + chat_id` | `chat_id` only |
| State setting | `await state.set_state()` | `await context.set_state()` |
| Data storage | `await state.update_data()` | `await context.update_data()` |
| Import | `from aiogram.fsm.context` | `from maxapi.context` |

## Messenger Adapter

### Abstract Interface (`IMessengerAdapter`)

Provides messenger-agnostic operations:
- `send_message()` - Send text messages
- `edit_message()` - Edit existing messages
- `delete_message()` - Delete messages
- `send_photo()` - Upload and send photos
- `send_document()` - Upload and send documents
- `answer_callback()` - Answer callback queries
- `download_file()` - Download files from URLs

### MAX Implementation (`MAXMessengerAdapter`)

Implements the interface using maxapi:
- Converts abstract keyboards to MAX format
- Handles button types (callback, link, contact, location)
- Manages file uploads with `InputMedia`
- Supports HTML and Markdown parse modes

## Usage Examples

### Basic Handler

```python
from maxapi import F
from maxapi.types import MessageCreated, Command
from maxapi.context import MemoryContext
from bots.max_bot.states import RegistrationStates

@dp.message_created(Command('start'))
async def start_handler(event: MessageCreated, context: MemoryContext):
    await context.clear()
    await event.message.answer('Welcome to MAX bot!')
```

### State-Based Handler

```python
@dp.message_created(F.message.body.text, RegistrationStates.waiting_for_phone)
async def handle_phone(event: MessageCreated, context: MemoryContext):
    phone = event.message.body.text
    await context.update_data(phone=phone)
    await context.set_state(RegistrationStates.waiting_for_name)
    await event.message.answer('Please enter your name:')
```

### Using Messenger Adapter

```python
from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton

# Create keyboard
keyboard = Keyboard(
    buttons=[
        [KeyboardButton(text="Option 1", payload={"action": "select", "id": 1})],
        [KeyboardButton(text="Option 2", payload={"action": "select", "id": 2})],
    ],
    inline=True
)

# Send message with keyboard
await max_messenger_adapter.send_message(
    chat_id=event.chat.chat_id,
    text="Choose an option:",
    keyboard=keyboard,
    parse_mode="HTML"
)
```

## Configuration

### Environment Variables

Required environment variables in `.env`:

```bash
# MAX Bot Configuration
MAX_BOT_TOKEN=your_max_bot_token_here
WEBHOOK_PATH_MAX=/max/webhook
```

### Initialization

The MAX bot is initialized in `loaders.py`:

```python
from maxapi import Bot as MAXBot
from maxapi import Dispatcher as MAXDispatcher
from maxapi import Router as MAXRouter
from maxapi.context import MemoryContext
from bots.max_bot.messenger_adapter import MAXMessengerAdapter

# Bot instance
max_bot = MAXBot(token=MAX_BOT_TOKEN, parse_mode=ParseMode.HTML)

# Dispatcher
max_dp = MAXDispatcher()

# Router
max_bot_router = MAXRouter(router_id="max_bot_main")

# FSM storage
max_storage = MemoryContext()

# Messenger adapter
max_messenger_adapter = MAXMessengerAdapter(bot=max_bot)
```

## Next Steps

The following tasks remain to complete the migration:

1. **Middleware Migration** (Task 7)
   - Database session middleware
   - Throttling middleware
   - User data middleware
   - Error handler middleware
   - State clearer middleware
   - Album middleware

2. **Handler Migration** (Tasks 9-11)
   - Command handlers (/start, /help, etc.)
   - Message handlers (registration, invoice, support, profile)
   - Callback query handlers (button interactions)

3. **Testing** (Task 17)
   - Unit tests for adapter
   - Integration tests for FSM flows
   - Property-based tests for correctness

## References

- [maxapi Documentation](https://github.com/love-apples/maxapi)
- [MAX Messenger API](https://max.mail.ru/api)
- [Migration Design Document](../../.kiro/specs/telegram-to-max-migration/design.md)
- [Migration Requirements](../../.kiro/specs/telegram-to-max-migration/requirements.md)
# Напоминания о незавершённом оформлении счёта

Явные текстовые команды («открой профиль», «меню», «закрыть заявку») обрабатываются
до ввода данных и пересылки в обращение, в том числе внутри AI-диалога и без GPT.
Если активных обращений несколько, закрытие текстом требует выбора номера.
Вопрос о подписках на ключе запускает запрос ключа, отдельно от активации ИТС.
Получение фактических подписок по ключу из 1С пока не подключено: бот сообщает,
что проверить их наличие не может. AI-диалог и шаг закрытия сохраняются в Redis
между процессами приложения, но не получают таймер передачи менеджеру.

MAX сохраняет черновик счёта в Redis (`REDIS`, `AIOGRAM_REDIS_DB_NUMBER`,
отдельные ключи `max:invoice-followup:*`). После 15 минут без ответа бот
спрашивает об актуальности. Ещё через 30 минут без ответа создаётся обращение
менеджеру с собранными ИНН, ключами, описанием и вложениями. Это обращение для
уточнения запроса, а не автоматическое выставление счёта. Действуют обычные
правила назначения менеджера и очереди в нерабочее время.

Интервалы задаются в `.env`: `MAX_INVOICE_REMINDER_MINUTES=15` и
`MAX_INVOICE_HANDOFF_MINUTES=30` (второй отсчитывается от отправки напоминания).
Любое сообщение или нажатие кнопки в форме перезапускает отсчёт. Отмена,
`/start`, уход из формы и завершение оформления снимают напоминание.
Черновики восстанавливаются после перезапуска приложения, если Redis сохранил
данные. Фоновая проверка работает каждые 30 секунд в FastAPI; дополнительная
очередь Celery и миграция БД не нужны. После обновления перезапустите приложение.
