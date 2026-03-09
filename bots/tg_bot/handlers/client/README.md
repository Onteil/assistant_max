# Client (Estimator) Handlers

This directory contains handlers for regular users (estimators/clients).

## Structure

- `registration.py` - User registration flow
- `invoice.py` - Invoice request flow (Получить счет)
- `support.py` - Technical support requests (Техподдержка)
- `profile.py` - Profile management (Мои данные)
- `commands.py` - Common commands
- `callbacks.py` - Common callback handlers
- `messages.py` - Common message handlers
- `cancel.py` - Cancel operation handler

## Access Control

These handlers are accessible to all users without staff verification.

## Main Menu Buttons

- 📄 Получить счет (Invoice)
- 🛠 Техподдержка (Technical Support)
- 🔄 Продление (Renewal)
- ⭐ Оценить сервис (Rate Service)
- 👤 Мой профиль (My Profile)

## User Flow

1. Registration (first time users)
2. Main menu access
3. Request services (invoice, support, renewal)
4. Manage profile and settings
