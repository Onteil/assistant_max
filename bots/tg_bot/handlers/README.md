# Telegram Bot Handlers

This directory contains all message and callback handlers for the Telegram bot, organized by user roles.

## Structure

```
handlers/
├── client/          # Client (Estimator) handlers
│   ├── registration.py
│   ├── invoice.py
│   ├── support.py
│   ├── profile.py
│   ├── commands.py
│   ├── callbacks.py
│   ├── messages.py
│   └── cancel.py
├── staff/           # Staff member handlers
│   ├── common.py    # Staff interface and ticket management
│   └── messages.py  # Staff messaging
└── __init__.py      # Main router configuration
```

## Role-Based Organization

### Client Handlers (`client/`)
Handlers for regular users (estimators/clients):
- No access restrictions
- Registration and authentication
- Service requests (invoice, support, renewal)
- Profile management

### Staff Handlers (`staff/`)
Handlers for staff members (managers, technical support, administrators):
- Protected by `StaffMemberCheckMiddleware`
- Ticket management and communication
- Staff interface and settings
- Role-based functionality

## Access Control

### Client Access
All users can access client handlers without restrictions.

### Staff Access
Staff handlers require:
1. User must exist in `Staff_Member` table
2. User must have `is_active = True`
3. Middleware provides `employee` record to handlers

## Router Hierarchy

```
tg_bot_router (main)
├── client_router
│   ├── cancel_router
│   ├── registration_router
│   ├── invoice_router
│   ├── support_router
│   ├── profile_router
│   ├── commands_router
│   ├── callbacks_router
│   └── messages_router
└── staff_router (with StaffMemberCheckMiddleware)
    ├── common_router
    └── messages_router
```

## Adding New Handlers

### For Client Functionality
1. Create handler file in `client/` directory
2. Create router in the file
3. Import and register in `client/__init__.py`

### For Staff Functionality
1. Create handler file in `staff/` directory
2. Create router in the file
3. Import and register in `staff/__init__.py`
4. Middleware will be applied automatically

## Migration Notes

This structure was reorganized from flat structure to role-based organization:
- Old `employee.py` → `staff/common.py`
- Old `employee_messages.py` → `staff/messages.py`
- All client handlers moved to `client/` directory
- Middleware now applied at router level instead of individual handlers
