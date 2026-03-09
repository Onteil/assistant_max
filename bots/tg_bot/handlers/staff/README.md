# Staff Handlers

This directory contains handlers for staff members (managers, technical support, administrators).

## Structure

- `common.py` - Common staff interface (menu, ticket management, settings)
- `messages.py` - Staff messaging and ticket communication

## Access Control

All handlers in this directory are protected by `StaffMemberCheckMiddleware`:
- Verifies user is an active staff member
- Provides employee record to handlers via `data["employee"]`
- Blocks access for non-staff users

## Staff Roles

Defined in `database.models.StaffRole`:
- `MANAGER` - Handles invoice requests and client management
- `TECHNICAL_SUPPORT` - Handles technical support tickets
- `DUTY_ENGINEER` - Extended hours support
- `ADMINISTRATOR` - Full system access

## Staff Menu Buttons

- 📥 Активные заявки (Active Tickets)
- 🗄 Архив обращений (Archive Search)
- ⚙️ Настройки (Settings)
- 🔐 Админ-панель (Admin Panel - administrators only)

## Ticket Management

Staff can:
- View and take tickets into work
- Communicate with clients through bot
- Change ticket status (waiting, closed)
- Transfer tickets to other staff
- View ticket history
- Search archived tickets

## Focus Mode

When working with a ticket, staff enters "focus mode":
- All messages are sent to the specific client
- Inline keyboard for quick actions
- Can switch between multiple active tickets
