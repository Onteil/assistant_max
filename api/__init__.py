from fastapi import APIRouter

from .admin import router as admin_router
from .admin_panel import router as admin_panel_router
from .payments import router as clientbot_api_router
from .endpoints.ticket_history import router as ticket_history_router
from .endpoints.calendar_rules import router as calendar_rules_router
from .endpoints.escalation_test import router as escalation_test_router
from .endpoints.admin_data import router as admin_data_router
from .webhooks.nps_webhooks import router as nps_webhooks_router
from .webhooks.renewal_webhooks import router as renewal_webhooks_router
from .webhooks.registration_webhooks import router as registration_webhooks_router
from .webhooks.user_update_webhooks import router as user_update_webhooks_router
from .webhooks.manager_assignment_webhooks import router as manager_assignment_webhooks_router
from .webhooks.staff_update_webhooks import router as staff_update_webhooks_router
from .webhooks.key_conflict_webhooks import router as key_conflict_webhooks_router
from .webhooks.subscription_webhooks import router as subscription_webhooks_router
from .webhooks.ticket_status_webhooks import router as ticket_status_webhooks_router
from .webhooks.ticket_reassignment_webhooks import router as ticket_reassignment_webhooks_router
from .webhooks.broadcast_webhooks import router as broadcast_webhooks_router

api_router = APIRouter()
api_router.include_router(clientbot_api_router, prefix="/test")
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_panel_router, tags=["admin-panel"])
api_router.include_router(admin_data_router, tags=["admin-data"])
api_router.include_router(ticket_history_router, tags=["api"])
api_router.include_router(calendar_rules_router, tags=["api"])
api_router.include_router(escalation_test_router, tags=["api"])
api_router.include_router(nps_webhooks_router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(renewal_webhooks_router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(registration_webhooks_router, prefix="/webhooks", tags=["webhooks"])
# Alias without /webhooks prefix for backward compatibility with 1C CRM
api_router.include_router(registration_webhooks_router, tags=["webhooks"])
api_router.include_router(user_update_webhooks_router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(manager_assignment_webhooks_router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(staff_update_webhooks_router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(key_conflict_webhooks_router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(subscription_webhooks_router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(ticket_status_webhooks_router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(ticket_reassignment_webhooks_router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(broadcast_webhooks_router, prefix="/webhooks", tags=["webhooks"])
