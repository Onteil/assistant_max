# MAX Bot Middleware

This directory contains middleware components for the MAX bot. Middleware intercepts and processes updates before and after handlers execute.

## Available Middleware

### 1. DatabaseSessionMiddleware
**Purpose:** Injects database session into handler context

**Usage:**
```python
from bots.max_bot.middlewares import DatabaseSessionMiddleware

# Register globally
dp.middleware(DatabaseSessionMiddleware())

# Access in handler
@dp.message_created(Command('start'))
async def start_handler(event: MessageCreated, session: AsyncSession):
    user = await session.execute(select(User).where(User.id == event.from_user.user_id))
    # ... use session
```

**Features:**
- Automatic session creation and cleanup
- Automatic commit on success
- Automatic rollback on error

---

### 2. ThrottlingMiddleware
**Purpose:** Rate-limits requests by chat_id to prevent flooding

**Usage:**
```python
from bots.max_bot.middlewares import ThrottlingMiddleware

# Register with custom rate limit (1 request per second)
throttling = ThrottlingMiddleware(rate_limit=1.0)
dp.middleware(throttling)
```

**Features:**
- Uses Redis for distributed rate limiting
- Sends "Too many requests" message when throttled
- Configurable rate limit window

---

### 3. BotInReconstructionMiddleware
**Purpose:** Blocks all updates during maintenance mode

**Usage:**
```python
from bots.max_bot.middlewares import BotInReconstructionMiddleware

# Register globally
dp.middleware(BotInReconstructionMiddleware())
```

**Features:**
- Checks `BOT_ON_RECONSTRUCTION` config flag
- Sends maintenance message to users
- Blocks all handler execution during maintenance

---

### 4. UserDataMiddleware
**Purpose:** Loads user data from database and attaches to context

**Usage:**
```python
from bots.max_bot.middlewares import UserDataMiddleware

# Register globally (must be after DatabaseSessionMiddleware)
dp.middleware(UserDataMiddleware())

# Access in handler
@dp.message_created(Command('profile'))
async def profile_handler(event: MessageCreated, user_data: Optional[User]):
    if user_data:
        await event.message.answer(f"Hello, {user_data.name}!")
```

**Features:**
- Queries database for user information
- Adds user data to context as `user_data`
- Returns None if user not found

---

### 5. ErrorHandlerMiddleware
**Purpose:** Catches and logs handler exceptions

**Usage:**
```python
from bots.max_bot.middlewares import ErrorHandlerMiddleware

# Register globally
dp.middleware(ErrorHandlerMiddleware())
```

**Features:**
- Prevents application crashes from unhandled exceptions
- Logs detailed error information with traceback
- Sends error notifications to admin channel (if configured)
- Sends user-friendly error messages

---

### 6. StateClearerMiddleware
**Purpose:** Clears FSM state on specific global commands

**Usage:**
```python
from bots.max_bot.middlewares import StateClearerMiddleware

# Register with custom commands
state_clearer = StateClearerMiddleware(
    global_commands=["/start", "/cancel", "/clear_state"]
)
dp.middleware(state_clearer)
```

**Features:**
- Clears FSM state when global commands are received
- Configurable list of commands
- Logs state clearing actions

---

### 7. AlbumMiddleware
**Purpose:** Groups multiple media attachments into albums

**Usage:**
```python
from bots.max_bot.middlewares import AlbumMiddleware

# Register with custom latency
album_mw = AlbumMiddleware(latency=0.5)
dp.middleware(album_mw)

# Access in handler
@dp.message_created()
async def handle_media(event: MessageCreated, album: list[MessageCreated], is_last: bool):
    if is_last:
        # Process complete album
        for msg in album:
            # Process each media item
            pass
```

**Features:**
- Groups messages with same media_group_id
- Treats single media as album with one item
- Configurable latency for collecting album messages
- Provides `album` list and `is_last` flag in context

---

## Middleware Registration Order

The order of middleware registration is important. Recommended order:

```python
from bots.max_bot.middlewares import (
    ErrorHandlerMiddleware,
    BotInReconstructionMiddleware,
    ThrottlingMiddleware,
    DatabaseSessionMiddleware,
    UserDataMiddleware,
    StateClearerMiddleware,
    AlbumMiddleware,
)

# 1. Error handler (should be first to catch all errors)
dp.middleware(ErrorHandlerMiddleware())

# 2. Maintenance mode check (block early if in maintenance)
dp.middleware(BotInReconstructionMiddleware())

# 3. Throttling (rate limit before processing)
dp.middleware(ThrottlingMiddleware(rate_limit=1.0))

# 4. Database session (needed by UserDataMiddleware)
dp.middleware(DatabaseSessionMiddleware())

# 5. User data loading (depends on database session)
dp.middleware(UserDataMiddleware())

# 6. State clearer (clear state on global commands)
dp.middleware(StateClearerMiddleware(global_commands=["/start", "/cancel", "/clear_state"]))

# 7. Album grouping (process media albums)
dp.middleware(AlbumMiddleware(latency=0.5))
```

## Creating Custom Middleware

To create custom middleware, inherit from `BaseMiddleware`:

```python
from typing import Any, Awaitable, Callable, Dict
from maxapi.filters.middleware import BaseMiddleware
from maxapi.types import UpdateUnion

class CustomMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[UpdateUnion, Dict[str, Any]], Awaitable[Any]],
        event: UpdateUnion,
        data: Dict[str, Any],
    ) -> Any:
        # Pre-processing
        print(f"Before handler: {event.update_type}")
        
        # Add data to context
        data["custom_key"] = "custom_value"
        
        # Call next handler
        result = await handler(event, data)
        
        # Post-processing
        print(f"After handler: {event.update_type}")
        
        return result
```

## Notes

- Middleware executes in the order they are registered
- Each middleware can modify the context data dictionary
- Middleware can prevent handler execution by returning early (without calling handler)
- Middleware can catch exceptions from handlers
- Context data is passed to handlers as keyword arguments
