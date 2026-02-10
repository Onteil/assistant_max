# Logging and Error Handling System

This document describes the comprehensive logging and error handling system implemented for the I-TAT Telegram bot dispatcher.

## Overview

The system provides:
- **Centralized error handling** with user-friendly message sanitization
- **Action logging** for audit trails
- **API retry queue** with exponential backoff
- **Structured logging** with context
- **Error categorization** and routing

## Requirements

Implements requirements:
- 25.1-25.5: API error handling with retry logic
- 32.1-32.5: Action logging for user actions, ticket creation, key conflicts
- 33.1-33.5: Error logging with context for debugging

## Components

### 1. Error Handler Service (`error_handler.py`)

Provides centralized error handling and message sanitization.

#### Key Functions:

**`sanitize_error_message(error, user_friendly=True)`**
- Converts technical exceptions to user-friendly messages
- Removes sensitive information and technical details
- Maps exception types to appropriate messages

**`log_error_with_context(logger, error, context, operation)`**
- Logs errors with full context for debugging
- Includes operation name, error type, and context dictionary
- Uses structured logging with extra fields

**`handle_api_error(error, operation, payload, session, tg_user_id)`**
- Handles API errors with retry queue
- Determines if operation should be retried
- Returns user-friendly message

**`handle_database_error(error, operation, context, session)`**
- Handles database errors with rollback
- Logs error with context
- Returns user-friendly message

**`format_validation_error(field_name, error_message, user_input, format_example)`**
- Formats validation errors with helpful guidance
- Includes user input and format examples
- Provides clear retry instructions

#### Example Usage:

```python
from services.error_handler import handle_api_error, sanitize_error_message

try:
    result = await api_client.register_user(**data)
except Exception as e:
    should_retry, user_message = await handle_api_error(
        error=e,
        operation="register_user",
        payload=data,
        session=session,
        tg_user_id=user_id
    )
    await message.answer(user_message)
```

### 2. Retry Service (`retry_service.py`)

Manages failed API operations with exponential backoff.

#### Configuration:

- **Retry delays**: 5min, 15min, 30min, 1hr, 2hr
- **Max attempts**: 5
- **Escalation**: After max attempts, creates admin notification

#### Key Functions:

**`queue_api_retry(session, operation, payload, tg_user_id)`**
- Queues failed API operation for retry
- Creates API_Retry_Queue record
- Schedules first retry after 5 minutes

**`get_pending_retries(session)`**
- Retrieves all pending retries due for processing
- Filters by status, next_retry_at, and attempt_count

**`process_retry(session, retry_record, api_client)`**
- Processes a single retry operation
- Calls API method with stored payload
- Updates retry status based on result

**`mark_retry_success(session, retry_id)`**
- Marks retry as successful
- Sets completed_at timestamp

**`mark_retry_failed(session, retry_id, error_message)`**
- Increments attempt count
- Schedules next retry with exponential backoff
- Escalates to admin after max attempts

**`cleanup_old_retries(session, days_old=30)`**
- Cleans up completed/failed retries older than specified days
- Prevents table bloat

#### Example Usage:

```python
from services.retry_service import queue_api_retry, get_pending_retries, process_retry

# Queue a failed operation
await queue_api_retry(
    session=session,
    operation="register_user",
    payload={"tg_user_id": 123, "phone": "+79991234567", ...},
    tg_user_id=123
)

# Process pending retries (background task)
pending = await get_pending_retries(session)
for retry in pending:
    success = await process_retry(session, retry, api_client)
```

### 3. Logging Service (`logging_service.py`)

Provides structured logging utilities for action and error logging.

#### Key Functions:

**`log_user_action(session, action_type, tg_user_id, action_details, ticket_id)`**
- Logs user action to Action_Log table
- Creates audit trail entry
- Includes JSON details

**`log_ticket_action(session, action_type, ticket_id, action_details, tg_user_id, staff_id)`**
- Logs ticket-related action
- Links to ticket, user, and staff

**`log_key_conflict(session, tg_user_id, key_number, conflict_status, action_details)`**
- Specialized logging for GS_Key conflicts
- Creates KEY_CONFLICT_DETECTED action log

**`log_api_error(operation, error, context)`**
- Logs API error with full context
- Uses structured logging with extra fields
- Categorizes as "api_error"

**`log_validation_error(field_name, user_input, error_message, tg_user_id)`**
- Logs validation error
- Truncates long inputs
- Categorizes as "validation_error"

**`log_database_error(operation, error, context)`**
- Logs database error with full context
- Categorizes as "database_error"

#### Helper Functions:

- `get_user_context(tg_user_id, **kwargs)` - Build user context dictionary
- `get_ticket_context(ticket_id, **kwargs)` - Build ticket context dictionary
- `get_api_context(operation, **kwargs)` - Build API context dictionary

#### Example Usage:

```python
from services.logging_service import log_user_action, log_api_error
from database.models import ActionType

# Log user registration
await log_user_action(
    session=session,
    action_type=ActionType.USER_REGISTERED,
    tg_user_id=user.tg_user_id,
    action_details={
        "phone_number": user.phone_number,
        "full_name": user.full_name,
        "registration_status": user.registration_status.value
    }
)

# Log API error
log_api_error(
    operation="register_user",
    error=exception,
    context={"tg_user_id": 123, "phone": "+79991234567"}
)
```

### 4. Enhanced API Client (`i_tat_service.py`)

Updated with comprehensive error handling.

#### Changes:

- Added `_make_request()` internal method with error handling
- All API methods now use `_make_request()` wrapper
- Proper exception propagation with logging
- Detailed error logging for timeouts, HTTP errors, connection errors

#### Error Handling:

```python
async def _make_request(self, method, endpoint, **kwargs):
    """Internal method with error handling"""
    try:
        if method.upper() == "GET":
            response = await self.client.get(endpoint, **kwargs)
        elif method.upper() == "POST":
            response = await self.client.post(endpoint, **kwargs)
        
        response.raise_for_status()
        return response.json()
    
    except httpx.TimeoutException:
        logger.error(f"API timeout: endpoint={endpoint}")
        raise
    
    except httpx.HTTPStatusError as e:
        logger.error(f"API HTTP error: status={e.response.status_code}")
        raise
    
    except httpx.ConnectError:
        logger.error(f"API connection error: endpoint={endpoint}")
        raise
```

## Database Models

### API_Retry_Queue

Stores failed API operations for retry processing.

**Fields:**
- `id` - Primary key
- `operation` - API method name (e.g., "register_user")
- `payload` - JSON request payload
- `tg_user_id` - User context (optional)
- `attempt_count` - Number of retry attempts
- `status` - PENDING, SUCCESS, or FAILED
- `next_retry_at` - Scheduled retry time
- `created_at` - Creation timestamp
- `completed_at` - Completion timestamp
- `last_error` - Last error message

**Indexes:**
- `ix_api_retry_queue_status_next_retry` - For efficient retry processing

### Action_Log (Enhanced)

Added new action type:
- `API_RETRY_FAILED` - Logged when retry fails after max attempts

## Error Message Examples

### User-Friendly Messages:

**API Timeout:**
```
⚠️ Сервис временно недоступен. Ваш запрос сохранен и будет обработан в ближайшее время.
```

**API 500 Error:**
```
⚠️ Сервис временно недоступен. Пожалуйста, попробуйте позже.
```

**Connection Error:**
```
⚠️ Не удается подключиться к сервису. Ваш запрос сохранен и будет обработан позже.
```

**Duplicate Entry:**
```
❌ Такая запись уже существует.
```

**Database Error:**
```
❌ Произошла ошибка. Пожалуйста, попробуйте еще раз через минуту.
```

**Validation Error (INN):**
```
❌ ИНН должен содержать ровно 10 или 12 цифр

Вы ввели: 123

Пример правильного формата: 1234567890

Пожалуйста, попробуйте еще раз:
```

## Integration with Handlers

### Registration Handler Example:

```python
from services.error_handler import handle_api_error, format_validation_error
from services.logging_service import log_user_action
from services.validation_service import validate_inn
from database.models import ActionType

async def process_inn(message: Message, state: FSMContext, session: AsyncSession):
    """Process INN input with validation and error handling"""
    inn = message.text.strip()
    
    # Validate INN
    is_valid, error_msg = validate_inn(inn)
    
    if not is_valid:
        # Log validation error
        from services.logging_service import log_validation_error
        log_validation_error(
            field_name="inn",
            user_input=inn,
            error_message=error_msg,
            tg_user_id=message.from_user.id
        )
        
        # Format user-friendly error
        error_text = format_validation_error(
            field_name="ИНН",
            error_message=error_msg,
            user_input=inn,
            format_example="1234567890"
        )
        await message.answer(error_text)
        return
    
    # Store in FSM
    await state.update_data(inn=inn)
    await state.set_state(RegistrationStates.waiting_for_key)
    await message.answer("Отлично! Теперь введите номер ключа ГРАНД-Сметы:")


async def submit_registration(state: FSMContext, session: AsyncSession, api_client: ITatAPIClient):
    """Submit registration with error handling and retry"""
    data = await state.get_data()
    
    try:
        # Call API
        result = await api_client.register_user(
            tg_user_id=data["tg_user_id"],
            phone=data["phone_number"],
            name=data["first_name"],
            surname=data["last_name"],
            inn=data["inn"],
            grand_key=data["gs_key"]
        )
        
        if result.get("status") == "ok":
            # Create user record
            user = await create_user(session, data)
            
            # Log successful registration
            await log_user_action(
                session=session,
                action_type=ActionType.USER_REGISTERED,
                tg_user_id=user.tg_user_id,
                action_details={
                    "phone_number": user.phone_number,
                    "full_name": user.full_name
                }
            )
            
            return user
    
    except Exception as e:
        # Handle API error with retry queue
        should_retry, user_message = await handle_api_error(
            error=e,
            operation="register_user",
            payload={
                "tg_user_id": data["tg_user_id"],
                "phone": data["phone_number"],
                "name": data["first_name"],
                "surname": data["last_name"],
                "inn": data["inn"],
                "grand_key": data["gs_key"]
            },
            session=session,
            tg_user_id=data["tg_user_id"]
        )
        
        # Create user record locally even if API failed
        user = await create_user(session, data)
        
        # Notify user
        await message.answer(user_message)
        
        return user
```

## Background Tasks

### Retry Processing Task:

```python
import asyncio
from services.retry_service import get_pending_retries, process_retry
from services.i_tat_service import get_itat_client

async def process_retry_queue():
    """Background task to process API retry queue"""
    while True:
        try:
            async with get_db_session() as session:
                api_client = get_itat_client()
                
                # Get pending retries
                pending = await get_pending_retries(session)
                
                # Process each retry
                for retry in pending:
                    await process_retry(session, retry, api_client)
                
                await session.commit()
        
        except Exception as e:
            logger.error(f"Error processing retry queue: {e}", exc_info=True)
        
        # Wait 5 minutes before next check
        await asyncio.sleep(300)
```

### Cleanup Task:

```python
from services.retry_service import cleanup_old_retries

async def cleanup_old_retries_task():
    """Background task to cleanup old retry records"""
    while True:
        try:
            async with get_db_session() as session:
                count = await cleanup_old_retries(session, days_old=30)
                logger.info(f"Cleaned up {count} old retry records")
                await session.commit()
        
        except Exception as e:
            logger.error(f"Error cleaning up retries: {e}", exc_info=True)
        
        # Run daily
        await asyncio.sleep(86400)
```

## Testing

### Unit Tests:

```python
import pytest
from services.error_handler import sanitize_error_message, format_validation_error
import httpx

def test_sanitize_timeout_error():
    """Test timeout error sanitization"""
    error = httpx.TimeoutException("Request timeout")
    message = sanitize_error_message(error, user_friendly=True)
    
    assert "временно недоступен" in message
    assert "timeout" not in message.lower()

def test_format_validation_error():
    """Test validation error formatting"""
    message = format_validation_error(
        field_name="ИНН",
        error_message="Должен содержать 10 или 12 цифр",
        user_input="123",
        format_example="1234567890"
    )
    
    assert "❌" in message
    assert "123" in message
    assert "1234567890" in message
    assert "попробуйте еще раз" in message.lower()
```

## Monitoring and Alerts

### Key Metrics to Monitor:

1. **Retry Queue Size**: Number of pending retries
2. **Failed Retries**: Retries that failed after max attempts
3. **API Error Rate**: Frequency of API errors by type
4. **Validation Error Rate**: Frequency of validation errors by field
5. **Database Error Rate**: Frequency of database errors

### Alert Thresholds:

- Retry queue size > 100: Investigate API availability
- Failed retries > 10/hour: Check API integration
- API error rate > 5%: Service degradation
- Database error rate > 1%: Database issues

## Best Practices

1. **Always use error handlers**: Don't expose technical details to users
2. **Log with context**: Include user_id, operation, and relevant parameters
3. **Queue for retry**: Use retry queue for transient API failures
4. **Validate early**: Validate user input before API calls
5. **Graceful degradation**: Store data locally if API unavailable
6. **Monitor metrics**: Track error rates and retry queue size
7. **Clean up regularly**: Run cleanup tasks to prevent table bloat

## Migration

To apply the database changes:

```bash
# Run migration
alembic upgrade head

# Verify migration
alembic current
```

## Summary

This comprehensive logging and error handling system provides:

✅ User-friendly error messages without technical details  
✅ Comprehensive error logging with context for debugging  
✅ Automatic retry queue for failed API operations  
✅ Action logging for audit trails  
✅ Structured logging for monitoring and alerting  
✅ Graceful degradation when external services fail  
✅ Exponential backoff retry logic  
✅ Admin escalation for persistent failures  

The system ensures users receive clear, helpful messages while developers have detailed logs for debugging and monitoring.
