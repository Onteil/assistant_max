# Telegram Bot Handler Migration Guide

This guide explains the reorganization of Telegram bot handlers from flat structure to role-based organization.

## What Changed

### Old Structure (Flat)

```
handlers/
├── callbacks.py
├── cancel.py
├── commands.py
├── employee.py
├── employee_messages.py
├── invoice.py
├── messages.py
├── profile.py
├── registration.py
└── support.py
```

### New Structure (Role-Based)

```
handlers/
├── client/
│   ├── callbacks.py
│   ├── cancel.py
│   ├── commands.py
│   ├── invoice.py
│   ├── messages.py
│   ├── profile.py
│   ├── registration.py
│   └── support.py
└── staff/
    ├── common.py (was employee.py)
    └── messages.py (was employee_messages.py)
```

## File Mapping

| Old Location | New Location | Notes |
|-------------|--------------|-------|
| `callbacks.py` | `client/callbacks.py` | Client callback handlers |
| `cancel.py` | `client/cancel.py` | Cancel operation handler |
| `commands.py` | `client/commands.py` | Client commands |
| `invoice.py` | `client/invoice.py` | Invoice request flow |
| `messages.py` | `client/messages.py` | Client message handlers |
| `profile.py` | `client/profile.py` | Profile management |
| `registration.py` | `client/registration.py` | User registration |
| `support.py` | `client/support.py` | Technical support |
| `employee.py` | `staff/common.py` | Staff interface and ticket management |
| `employee_messages.py` | `staff/messages.py` | Staff messaging |

## Import Changes

### Before

```python
from bots.tg_bot.handlers.employee import router as employee_router
from bots.tg_bot.handlers.invoice import router as invoice_router
```

### After

```python
from bots.tg_bot.handlers.client import client_router
from bots.tg_bot.handlers.staff import staff_router
```

## Middleware Changes

### Before

```python
# In handlers/__init__.py
staff_check_middleware = StaffMemberCheckMiddleware()
employee_router.message.middleware(staff_check_middleware)
employee_router.callback_query.middleware(staff_check_middleware)
employee_messages_router.message.middleware(staff_check_middleware)
employee_messages_router.callback_query.middleware(staff_check_middleware)
```

### After

```python
# In handlers/staff/__init__.py
staff_check_middleware = StaffMemberCheckMiddleware()
staff_router.message.middleware(staff_check_middleware)
staff_router.callback_query.middleware(staff_check_middleware)
```

Middleware is now applied at the router level, automatically covering all staff handlers.

## Router Hierarchy

### Before

```
tg_bot_router
├── cancel_router
├── registration_router
├── employee_router (with middleware)
├── employee_messages_router (with middleware)
├── invoice_router
├── support_router
├── profile_router
├── commands_router
├── callbacks_router
└── messages_router
```

### After

```
tg_bot_router
├── client_router
│   ├── cancel_router
│   ├── registration_router
│   ├── invoice_router
│   ├── support_router
│   ├── profile_router
│   ├── commands_router
│   ├── callbacks_router
│   └── messages_router
└── staff_router (with middleware)
    ├── common_router
    └── messages_router
```

## Benefits

1. **Clear Separation** - Client and staff functionality clearly separated
2. **Better Access Control** - Middleware applied at router level
3. **Easier Maintenance** - Related handlers grouped together
4. **Consistent Structure** - Matches MAX bot organization
5. **Scalability** - Easy to add new roles or functionality

## Migration Checklist

If you're updating code that references old handler locations:

- [ ] Update imports to use new paths
- [ ] Update router references
- [ ] Verify middleware is applied correctly
- [ ] Test access control for staff handlers
- [ ] Update any documentation references
- [ ] Run tests to verify functionality

## Testing

After migration, verify:

1. **Client Handlers**
   - All users can access client functionality
   - Registration flow works
   - Invoice and support requests work
   - Profile management works

2. **Staff Handlers**
   - Only active staff members can access
   - Non-staff users are blocked with appropriate message
   - Employee record is provided to handlers
   - Ticket management works
   - Staff messaging works

3. **Middleware**
   - StaffMemberCheckMiddleware blocks non-staff users
   - Error messages are displayed correctly
   - Employee data is available in handlers

## Rollback

If you need to rollback to the old structure:

1. Move files back to flat structure
2. Restore old `handlers/__init__.py`
3. Apply middleware to individual routers
4. Update imports throughout codebase

However, the new structure is recommended for better organization and maintainability.

## Questions?

If you have questions about the migration:

1. Check `handlers/README.md` for structure overview
2. Check `handlers/client/README.md` for client handlers
3. Check `handlers/staff/README.md` for staff handlers
4. Review `docs/HANDLER_STRUCTURE.md` for detailed documentation
5. Review `docs/ARCHITECTURE_OVERVIEW.md` for system architecture
