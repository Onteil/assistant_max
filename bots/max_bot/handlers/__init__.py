"""
Handlers Package for MAX Bot

Organized by feature domains with separate routers:
- user/: User-related handlers (registration, profile, commands, cancel)
- tickets/: Ticket-related handlers (invoice, support)
- employee/: Employee interface handlers
- common/: Shared handlers (callbacks, messages)

Migrated from Telegram bot to MAX messenger.
Uses maxapi Router for modular handler organization.

Requirements: 10.2, 10.3, 9.8, 10.4
"""

import logging

from maxapi import Router
from maxapi.filters import Command
from maxapi.utils.magic_filter import F

from bots.max_bot.callback_datas import (
    DeliveryCallback,
    ExampleItemCallback,
    ExampleNavigationCallback,
    KeyCallback,
    OrganizationCallback,
)
from bots.max_bot.filters import PrivateChatFilter

from .common.callbacks import (
    process_back_navigation,
    process_cancel,
    process_item_selection,
    process_noop,
    process_pagination,
)
from .tickets.invoice import (
    process_delivery_method,
    process_key_selection,
    process_organization_selection,
)
from .user.cancel import cmd_cancel, handle_cancel_button
from .user.commands import (
    handle_invoice_button,
    handle_profile_button,
    handle_support_button,
    help_command,
)
from .user.registration import cmd_start

logger = logging.getLogger(__name__)


def create_user_router() -> Router:
    """
    Create router for user-related handlers.
    
    Includes:
    - Command handlers (/start, /help, /cancel)
    - Main menu button handlers
    - Registration flow handlers
    - Profile management handlers
    
    Note: messenger_adapter is injected via MessengerAdapterMiddleware
    
    Requirements: 10.2, 10.3, 9.8, 10.4, 14.5
    """
    user_router = Router(router_id="user_handlers")

    # Apply private chat filter to all message and callback handlers
    # This ensures handlers only process updates from private chats
    user_router.message.filter(PrivateChatFilter())
    user_router.message_callback.filter(PrivateChatFilter())

    # ========== Command Handlers ==========

    @user_router.message(Command("start"))
    async def start_handler(message, state, session, messenger_adapter):
        """Handler for /start command"""
        await cmd_start(message, state, session, messenger_adapter)

    @user_router.message(Command("help"))
    async def help_handler(message, messenger_adapter):
        """Handler for /help command"""
        await help_command(message, messenger_adapter)

    @user_router.message(Command("cancel"))
    async def cancel_handler(message, state, session, messenger_adapter):
        """Handler for /cancel command"""
        await cmd_cancel(message, state, session, messenger_adapter)

    # ========== Main Menu Button Handlers ==========

    @user_router.message(F.message.body.text == "💰 Получить счет")
    async def invoice_button_handler(message, state, session, messenger_adapter):
        """Handler for invoice button"""
        await handle_invoice_button(message, state, session, messenger_adapter)

    @user_router.message(F.message.body.text == "🆘 Техподдержка")
    async def support_button_handler(message, state, session, messenger_adapter):
        """Handler for support button"""
        await handle_support_button(message, state, session, messenger_adapter)

    @user_router.message(F.message.body.text == "👤 Мой профиль")
    async def profile_button_handler(message, session, messenger_adapter):
        """Handler for profile button"""
        await handle_profile_button(message, session, messenger_adapter)

    @user_router.message(F.message.body.text == "❌ Отмена")
    async def cancel_button_handler(message, state, session, messenger_adapter):
        """Handler for cancel button"""
        await handle_cancel_button(message, state, session, messenger_adapter)

    logger.info("User router created with command and menu handlers (private chat filter applied)")
    return user_router


def create_tickets_router() -> Router:
    """
    Create router for ticket-related handlers.
    
    Includes:
    - Invoice flow handlers
    - Support ticket handlers
    - Ticket callback handlers
    
    Note: messenger_adapter is injected via MessengerAdapterMiddleware
    
    Requirements: 10.2, 10.3, 9.8, 10.4, 14.5
    """
    tickets_router = Router(router_id="tickets_handlers")

    # Apply private chat filter to all message and callback handlers
    tickets_router.message.filter(PrivateChatFilter())
    tickets_router.message_callback.filter(PrivateChatFilter())

    # ========== Invoice Flow Callbacks ==========

    @tickets_router.message_callback(OrganizationCallback.filter())
    async def organization_callback_handler(event, payload, state, session, messenger_adapter):
        """Handler for organization selection callbacks"""
        await process_organization_selection(event, payload, state, session, messenger_adapter)

    @tickets_router.message_callback(KeyCallback.filter())
    async def key_callback_handler(event, payload, state, session, messenger_adapter):
        """Handler for key selection callbacks"""
        await process_key_selection(event, payload, state, session, messenger_adapter)

    @tickets_router.message_callback(DeliveryCallback.filter())
    async def delivery_callback_handler(event, payload, state, session, messenger_adapter):
        """Handler for delivery method callbacks"""
        await process_delivery_method(event, payload, state, session, messenger_adapter)

    logger.info("Tickets router created with invoice and support handlers (private chat filter applied)")
    return tickets_router


def create_common_router() -> Router:
    """
    Create router for common/shared handlers.
    
    Includes:
    - Generic callback handlers (pagination, selection, cancel)
    - Navigation handlers
    - Utility handlers
    
    Note: messenger_adapter is injected via MessengerAdapterMiddleware
    
    Requirements: 10.2, 10.3, 9.8, 10.4, 14.5
    """
    common_router = Router(router_id="common_handlers")

    # Apply private chat filter to all message and callback handlers
    common_router.message.filter(PrivateChatFilter())
    common_router.message_callback.filter(PrivateChatFilter())

    # ========== Common Callback Handlers ==========

    @common_router.message_callback(ExampleItemCallback.filter(F.action == "view"))
    async def pagination_handler(event, payload, state, session, messenger_adapter):
        """Handler for pagination callbacks"""
        await process_pagination(event, payload, messenger_adapter)

    @common_router.message_callback(ExampleItemCallback.filter(F.action == "select"))
    async def item_selection_handler(event, payload, state, session, messenger_adapter):
        """Handler for item selection callbacks"""
        await process_item_selection(event, payload, messenger_adapter)

    @common_router.message_callback(ExampleItemCallback.filter(F.action == "cancel"))
    async def cancel_callback_handler(event, payload, state, session, messenger_adapter):
        """Handler for cancel callbacks"""
        await process_cancel(event, payload, state, messenger_adapter)

    @common_router.message_callback(ExampleNavigationCallback.filter(F.action == "back"))
    async def back_navigation_handler(event, payload, state, session, messenger_adapter):
        """Handler for back navigation callbacks"""
        await process_back_navigation(event, payload, messenger_adapter)

    @common_router.message_callback(F.callback.payload == "noop")
    async def noop_handler(event):
        """Handler for noop callbacks (page indicators)"""
        await process_noop(event)

    logger.info("Common router created with shared callback handlers (private chat filter applied)")
    return common_router


def create_employee_router() -> Router:
    """
    Create router for employee interface handlers.
    
    Includes:
    - Employee dashboard handlers
    - Employee action handlers
    - Employee message handlers
    
    Note: messenger_adapter is injected via MessengerAdapterMiddleware
    
    Requirements: 10.2, 10.3, 9.8, 10.4, 14.5
    """
    employee_router = Router(router_id="employee_handlers")

    # Apply private chat filter to all message and callback handlers
    employee_router.message.filter(PrivateChatFilter())
    employee_router.message_callback.filter(PrivateChatFilter())

    # TODO: Add employee handlers when migrated
    # @employee_router.message(Command("employee"))
    # async def employee_dashboard_handler(message, session, messenger_adapter):
    #     await show_employee_dashboard(message, session, messenger_adapter)

    logger.info("Employee router created (handlers to be added, private chat filter applied)")
    return employee_router


def register_max_handlers(dp, router):
    """
    Register all MAX bot handlers with the dispatcher using router hierarchy.
    
    This function creates separate routers for each feature domain and includes
    them in the main router. This provides a modular architecture where handlers
    are organized into logical groups and maintained in separate files.
    
    Router hierarchy:
    - main_router (passed as parameter)
      ├─ user_router (commands, registration, profile)
      ├─ tickets_router (invoice, support)
      ├─ common_router (shared callbacks, navigation)
      └─ employee_router (employee interface)
    
    Dependencies are injected via middleware:
    - messenger_adapter: Injected via MessengerAdapterMiddleware
    - session: Injected via DatabaseSessionMiddleware
    - state: Provided by maxapi FSMContext
    
    Args:
        dp: MAX Dispatcher instance
        router: Main MAX Router instance
    
    Requirements: 9.1, 9.2, 9.4, 9.7, 10.1, 10.2, 10.3, 5.1, 5.2, 5.3, 9.8, 14.5
    """

    # Create feature-specific routers
    # messenger_adapter is now injected via middleware, not passed as parameter
    user_router = create_user_router()
    tickets_router = create_tickets_router()
    common_router = create_common_router()
    employee_router = create_employee_router()

    # Include all routers in the main router
    # Order matters: more specific handlers should be registered first
    router.include_routers(
        user_router,      # User commands and menu handlers
        tickets_router,   # Invoice and support handlers
        common_router,    # Shared callback handlers
        employee_router,  # Employee interface handlers
    )

    logger.info("MAX bot handlers registered successfully with router hierarchy")


__all__ = ["register_max_handlers"]
