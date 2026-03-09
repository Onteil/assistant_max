"""
Staff Handlers Package

Handlers for staff members (managers, technical support, administrators):
- Common staff interface
- Ticket management
- Staff messaging
- Admin panel (for administrators only)
"""

from aiogram import Router

from .common import router as common_router
from .messages import router as messages_router
from .admin_panel import router as admin_router
from .operations import router as operations_router
from .escalations import router as escalations_router
from .registrations import router as registrations_router


# Staff router - combines all staff-facing handlers
staff_router = Router(name="staff")

# Register all staff sub-routers
# Admin router MUST be registered FIRST to handle admin panel button before catch-all handlers
# Calendar router and all settings routers are now included inside admin_router for proper routing
staff_router.include_routers(
    admin_router,  # Admin handlers first (includes calendar router and all settings routers)
    operations_router,  # Admin operations handlers
    escalations_router,
    registrations_router,  # Registration approval handlers
    common_router,
    messages_router
)

__all__ = ["staff_router"]
