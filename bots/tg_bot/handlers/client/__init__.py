"""
Client (Estimator) Handlers Package

Handlers for regular users (estimators/clients):
- Registration flow
- Invoice requests
- Technical support requests
- Profile management
- Common commands and messages
- NPS survey responses
"""

from aiogram import Router

from .cancel import router as cancel_router
from .commands import router as commands_router
from .invoice import router as invoice_router
from .profile import router as profile_router
from .registration import router as registration_router
from .renewal import router as renewal_router
from .support import router as support_router
from .callbacks import router as callbacks_router
from .messages import router as messages_router
from .nps_handler import router as nps_router
from .active_tickets import router as active_tickets_router
from .archive import router as archive_router

# Client router - combines all client-facing handlers
client_router = Router(name="client")

# Register all client sub-routers
# Cancel router should be first to handle /cancel in any state
# Registration router should be second to handle /start command
# Renewal router should be before catch-all handlers
client_router.include_routers(
    cancel_router,
    registration_router,
    invoice_router,
    support_router,
    profile_router,
    commands_router,
    nps_router,
    active_tickets_router,
    renewal_router,
    archive_router,
    callbacks_router,
    messages_router
)

__all__ = ["client_router"]
