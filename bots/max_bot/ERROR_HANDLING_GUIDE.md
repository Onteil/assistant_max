# MAX Bot Error Handling Guide

This guide explains how to use the error handling utilities in the MAX Bot implementation.

## Overview

The error handling system provides:

1. **MAXAPIError Exception**: Custom exception for MAX API errors with error codes
2. **Retry Logic**: Automatic retry with exponential backoff for transient errors
3. **Safe Handler Execution**: Wrapper for handlers with automatic error recovery
4. **Error Handler Middleware**: Global error catching and user-friendly messages

## Components

### 1. MAXAPIError Exception

Custom exception class for MAX API errors:

```python
from bots.max_bot.exceptions import MAXAPIError

# Raise MAX API error
raise MAXAPIError(
    code=429,
    message="Rate limit exceeded",
    response={"error": "too_many_requests"}
)

# Check error type
try:
    # API call
    pass
except MAXAPIError as e:
    if e.is_rate_limit_error():
        print("Rate limited!")
    elif e.is_server_error():
        print("Server error!")
    elif e.is_auth_error():
        print("Auth error!")
```

### 2. Retry with Exponential Backoff

Automatically retry failed operations:

```python
from bots.max_bot.exceptions import retry_with_exponential_backoff, with_retry

# Using the function directly
result = await retry_with_exponential_backoff(
    some_async_function,
    arg1,
    arg2,
    max_retries=3,
    initial_delay=1.0,
    max_delay=60.0,
    backoff_factor=2.0
)

# Using the decorator
@with_retry(max_retries=3, initial_delay=1.0)
async def send_important_message(chat_id: int, text: str):
    await bot.send_message(chat_id=chat_id, text=text)
```

### 3. Safe Handler Execution

Wrap handlers with automatic error recovery:

```python
from bots.max_bot.exceptions import safe_handler_execution, safe_handler

# Using the function
@dp.message(Command("start"))
async def start_handler(message: MessageCreated, bot: Bot, **kwargs):
    result = await safe_handler_execution(
        actual_handler,
        message,
        kwargs,
        bot=bot,
        error_message="Failed to start bot"
    )

# Using the decorator (recommended)
@dp.message(Command("start"))
@safe_handler(error_message="Не удалось запустить бота. Попробуйте позже.")
async def start_handler(message: MessageCreated, bot: Bot, **kwargs):
    await bot.send_message(message.chat.chat_id, "Welcome!")
```

### 4. Messenger Adapter Error Handling

The MAXMessengerAdapter automatically converts exceptions to MAXAPIError:

```python
from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.exceptions import MAXAPIError

adapter = MAXMessengerAdapter(bot)

try:
    message_id = await adapter.send_message(
        chat_id=12345,
        text="Hello!",
        keyboard=some_keyboard
    )
except MAXAPIError as e:
    if e.is_retryable():
        # Retry the operation
        pass
    else:
        # Handle non-retryable error
        pass
```

## Error Handling Strategy

### Rate Limiting (429)

- **Action**: Retry with exponential backoff
- **User Message**: "⏳ Слишком много запросов. Пожалуйста, подождите немного."
- **Logging**: Warning level

### Server Errors (5xx)

- **Action**: Retry with exponential backoff
- **User Message**: "❌ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
- **Logging**: Error level

### Authentication Errors (401)

- **Action**: Fail immediately, notify admin
- **User Message**: "🔒 Ошибка авторизации. Пожалуйста, обратитесь к администратору."
- **Logging**: Critical level
- **Admin Notification**: Sent to ERROR_CHANNEL

### Client Errors (4xx)

- **Action**: Fail immediately
- **User Message**: "❌ Произошла ошибка при обработке вашего запроса."
- **Logging**: Error level

## Best Practices

### 1. Use Safe Handler Decorator

Always wrap your handlers with `@safe_handler`:

```python
@dp.message(Command("profile"))
@safe_handler(error_message="Не удалось загрузить профиль.")
async def profile_handler(message: MessageCreated, bot: Bot, session: AsyncSession):
    user = await get_user(session, message.from_user.user_id)
    await bot.send_message(message.chat.chat_id, f"Profile: {user.name}")
```

### 2. Use Retry for Critical Operations

For critical operations that must succeed, use retry logic:

```python
@with_retry(max_retries=5, initial_delay=2.0)
async def send_payment_confirmation(chat_id: int, payment_id: str):
    await bot.send_message(
        chat_id=chat_id,
        text=f"Payment {payment_id} confirmed!"
    )
```

### 3. Handle Specific Error Types

Handle specific error types when you need custom behavior:

```python
try:
    await adapter.send_message(chat_id, text)
except MAXAPIError as e:
    if e.is_rate_limit_error():
        # Wait longer for rate limits
        await asyncio.sleep(60)
        await adapter.send_message(chat_id, text)
    elif e.is_auth_error():
        # Critical error - notify admin immediately
        await notify_admin("Bot token is invalid!")
        raise
    else:
        # Log and continue
        logger.error(f"Failed to send message: {e}")
```

### 4. Configure Error Channel

Set the ERROR_CHANNEL environment variable to receive admin notifications:

```bash
ERROR_CHANNEL=123456789  # Your admin chat ID
```

## Error Flow Diagram

```
User Action
    ↓
Handler Execution
    ↓
[Error Occurs?] → No → Success
    ↓ Yes
[MAXAPIError?] → No → Generic Error Handler
    ↓ Yes
[Retryable?] → Yes → Exponential Backoff → Retry
    ↓ No
[Auth Error?] → Yes → Notify Admin
    ↓
Send User-Friendly Message
    ↓
Log Error
    ↓
Return None
```

## Testing Error Handling

### Unit Tests

Test error handling with mock errors:

```python
import pytest
from bots.max_bot.exceptions import MAXAPIError, handle_max_api_error

@pytest.mark.asyncio
async def test_rate_limit_handling():
    error = MAXAPIError(code=429, message="Rate limit")
    action = await handle_max_api_error(error)
    assert action == "retry"

@pytest.mark.asyncio
async def test_auth_error_handling():
    error = MAXAPIError(code=401, message="Unauthorized")
    action = await handle_max_api_error(error)
    assert action == "fail"
```

### Integration Tests

Test retry logic with simulated failures:

```python
@pytest.mark.asyncio
async def test_retry_with_backoff():
    call_count = 0
    
    async def failing_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise MAXAPIError(code=500, message="Server error")
        return "success"
    
    result = await retry_with_exponential_backoff(
        failing_function,
        max_retries=3,
        initial_delay=0.1
    )
    
    assert result == "success"
    assert call_count == 3
```

## Monitoring and Logging

All errors are logged with structured data:

```python
logger.error(
    f"MAX API error: {e}",
    extra={
        "error_code": e.code,
        "error_message": e.message,
        "event_type": "message",
        "user_id": 12345
    }
)
```

Use log aggregation tools to monitor:
- Error rates by type
- Retry success rates
- User-facing error frequency
- Critical auth errors

## Summary

The error handling system provides robust, automatic error recovery with:
- ✅ Automatic retries for transient errors
- ✅ User-friendly error messages
- ✅ Admin notifications for critical errors
- ✅ Detailed logging for debugging
- ✅ Easy-to-use decorators and wrappers
