# MAX Bot Handlers

Handlers are organized by feature domains for better maintainability and clarity.

## Structure

```
handlers/
├── user/              # User-related handlers
│   ├── registration.py    # User registration flow
│   ├── profile.py         # Profile management
│   ├── commands.py        # General bot commands
│   └── cancel.py          # Cancel operation handler
│
├── tickets/           # Ticket-related handlers
│   ├── invoice.py         # Invoice request flow
│   └── support.py         # Technical support flow
│
├── employee/          # Employee interface handlers
│   ├── employee.py        # Employee menu and ticket management
│   └── employee_messages.py  # Employee message handling
│
└── common/            # Shared handlers
    ├── callbacks.py       # Callback query handlers
    └── messages.py        # General message handlers
```

## Handler Patterns

All handlers follow these patterns:

1. **Use messenger_adapter** for all message operations
2. **Use maxapi FSM** for state management (state.clear(), state.set_state())
3. **Extract IDs properly**: message.from_user.user_id, message.chat.chat_id
4. **Use message.body.text** for text content
5. **Log important actions** for debugging and monitoring

## Migration Notes

See `MIGRATION_NOTES.md` for detailed migration patterns from Telegram bot to MAX messenger.
