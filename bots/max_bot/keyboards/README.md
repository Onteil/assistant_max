# MAX Bot Keyboards

Keyboards are organized by feature domains for better maintainability and clarity.

## Structure

```
keyboards/
├── user/              # User-related keyboards
│   ├── registration_kb.py # Registration flow keyboards
│   ├── profile_kb.py      # Profile management keyboards
│   └── main_menu_kb.py    # Main menu keyboard
│
├── tickets/           # Ticket-related keyboards
│   ├── invoice_kb.py      # Invoice request keyboards
│   └── support_kb.py      # Support request keyboards
│
├── employee/          # Employee interface keyboards
│   └── employee_kb.py     # Employee menu and action keyboards
│
└── common/            # Shared keyboard utilities
    ├── keyboard_builder.py  # Core keyboard builder utility
    ├── inline_kb.py         # Inline keyboard helpers
    └── reply_kb.py          # Reply keyboard helpers
```

## Keyboard Patterns

### Using KeyboardBuilder

```python
from bots.max_bot.keyboards.common.keyboard_builder import KeyboardBuilder

# Create inline keyboard
builder = KeyboardBuilder(inline=True)
builder.add_callback_button("Option 1", payload={"action": "select", "id": 1})
builder.add_callback_button("Option 2", payload={"action": "select", "id": 2})
builder.row()
builder.add_callback_button("Cancel", payload={"action": "cancel"})
keyboard = builder.build()

# Create reply keyboard
builder = KeyboardBuilder(inline=False, one_time=True)
builder.add_contact_button("📱 Share Contact")
builder.row()
builder.add_button("Cancel")
keyboard = builder.build()
```

### Convenience Functions

```python
from bots.max_bot.keyboards.common.keyboard_builder import (
    create_paginated_keyboard,
    create_confirmation_keyboard,
    create_navigation_keyboard,
)

# Paginated keyboard
items = [{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}]
keyboard = create_paginated_keyboard(items, page=0)

# Confirmation keyboard
keyboard = create_confirmation_keyboard(
    confirm_text="✅ Yes",
    cancel_text="❌ No"
)

# Navigation keyboard
keyboard = create_navigation_keyboard(back_text="⬅️ Back")
```

## Integration with Messenger Adapter

All keyboards use the messenger abstraction layer (Keyboard, KeyboardButton) to remain messenger-agnostic.
