"""
Handlers Package

Role-based organization:
- client/ - Handlers for regular users (estimators/clients)
- staff/ - Handlers for staff members (managers, technical support, administrators)

Each role has its own router with appropriate middleware applied.
"""

from aiogram import Router

from .client import client_router
from .staff import staff_router

# Main router for the entire Telegram bot
tg_bot_router = Router(name="tg_bot_main")

# Register role-based routers
# Client router registered BEFORE staff router
# This allows client handlers to process client messages first
# Staff handlers will only process messages from staff members (checked in handlers)
tg_bot_router.include_routers(
    client_router,
    staff_router
)

__all__ = ["tg_bot_router"]
