# Database Utilities

This directory contains the database models and utility functions for the I-TAT Telegram bot dispatcher system.

## Components

### Models (`models.py`)
SQLAlchemy ORM models for all database tables including:
- User, Organization, GS_Key, Staff_Member
- Manager_Assignment, Ticket, Message, File_Attachment
- Action_Log, Calendar_Rule, Notification_Event, Broadcast, Broadcast_Delivery

### Session Management (`session.py`)
Async session management with connection pooling and retry logic.

**Usage:**
```python
from database import init_db, get_session

# Initialize database (once at startup)
init_db("postgresql+asyncpg://user:pass@localhost/dbname")

# Use sessions
async with get_session() as session:
    user = await session.get(User, user_id)
    # ... perform operations
    # Automatically commits on success, rolls back on error
```

**Features:**
- Automatic connection retry with exponential backoff
- Connection pooling configuration
- Async context manager for clean session lifecycle

### Query Helpers (`query_helpers.py`)
Helper functions for common database operations.

**get_or_create:**
```python
from database import get_or_create

user, created = await get_or_create(
    session,
    User,
    defaults={'full_name': 'John Doe'},
    tg_user_id=123456,
    phone_number='+79991234567'
)
```

**Bulk Insert:**
```python
from database import bulk_insert

users_data = [
    {'tg_user_id': 1, 'phone_number': '+79991111111'},
    {'tg_user_id': 2, 'phone_number': '+79992222222'},
]
users = await bulk_insert(session, User, users_data, return_instances=True)
```

**Eager Loading:**
```python
from database import get_user_with_full_context, get_ticket_with_full_context

# Load user with all relationships in one query
user = await get_user_with_full_context(session, user_id)

# Load ticket with all relationships
ticket = await get_ticket_with_full_context(session, ticket_id)
```

**Query Performance Logging:**
```python
from database import QueryPerformanceLogger

with QueryPerformanceLogger("my_complex_query", slow_query_threshold=0.5):
    result = await session.execute(stmt)
```

### Validators (`validators.py`)
Field validation functions to ensure data integrity.

**Basic Validation:**
```python
from database import (
    validate_phone_number,
    validate_inn,
    validate_key_number,
    validate_email
)

# Raises ValidationError if invalid
validate_phone_number("+79991234567")
validate_inn("1655060636")
validate_key_number("MG123456")
validate_email("user@example.com")
```

**Safe Validation (no exceptions):**
```python
from database import safe_validate_phone_number

is_valid, error_message = safe_validate_phone_number("+79991234567")
if not is_valid:
    print(f"Validation failed: {error_message}")
```

**Batch Validation:**
```python
from database import validate_user_data, validate_ticket_data

# Validate multiple fields at once
errors = validate_user_data(
    phone_number="+79991234567",
    email="user@example.com"
)

if errors:
    print(f"Validation errors: {errors}")
```

## Validation Rules

### Phone Number
- Format: `+[country_code][number]`
- Length: 10-15 digits
- May contain spaces, hyphens, parentheses for formatting
- Examples: `+79991234567`, `+7 (999) 123-45-67`

### INN (Tax ID)
- Format: Exactly 10 or 12 digits
- Examples: `1655060636`, `165506063612`

### Key Number
- Format: 2 uppercase letters + 6 digits
- Example: `MG123456`

### Email
- Standard email format: `local@domain.tld`
- Example: `user@example.com`

### Escalation Level
- Valid values: 0 (primary), 1 (backup1), 2 (backup2)

## Error Handling

All utilities implement proper error handling:

**Session Management:**
- Automatic retry on connection errors (3 attempts with exponential backoff)
- Automatic rollback on exceptions
- Connection pool management

**Validators:**
- Raise `ValidationError` with field name and message
- Safe variants return `(is_valid, error_message)` tuples
- Batch validators return error dictionaries

**Query Helpers:**
- Performance logging for slow queries
- Automatic relationship loading to avoid N+1 queries
- Optimized bulk operations

## Testing

Run validation tests:
```bash
python -c "from database.validators import *; validate_phone_number('+79991234567'); print('✓ Validators working')"
```

Check imports:
```bash
python -c "from database import *; print('✓ All imports working')"
```

## Requirements

- Python 3.11+
- SQLAlchemy 2.x with async support
- PostgreSQL 12+
- asyncpg (async PostgreSQL driver)
- tenacity (retry logic)
