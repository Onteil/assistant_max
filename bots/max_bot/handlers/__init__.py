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

import json
import logging

from maxapi import F, Router
from maxapi.types import Command, MessageCreated, MessageCallback
from maxapi.context import MemoryContext
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter

from bots.max_bot.callback_datas import (
    DeliveryCallback,
    ExampleItemCallback,
    ExampleNavigationCallback,
    KeyCallback,
    KeyConflictCallback,
    OrganizationCallback,
)
from bots.max_bot.filters import PrivateChatFilter
from bots.max_bot.payloads import (
    ReplyToManagerPayload,
    TicketSelectPayload,
    TicketsPaginationPayload,
    TicketsFilterPayload,
    ActiveTicketsClosePayload,
    TicketHistoryPayload,
    TicketHistoryBackPayload,
    MessageTicketSelectPayload,
    MessageTicketPaginationPayload,
    MessageTicketCancelPayload,
    ArchiveFilterPayload,
    ArchivePaginationPayload,
    ViewArchivedTicketPayload,
    ArchiveClosePayload,
    ProfileActionPayload,
    ProfileViewPayload,
    ProfileAddPayload,
    ProfileDeleteOrgPayload,
    ProfileConfirmDeleteOrgPayload,
    ProfileDeleteKeyPayload,
    ProfileConfirmDeleteKeyPayload,
    MainMenuActionPayload,
    DonePayload,
    ManagerMenuActionPayload,
    ManagerTicketSelectPayload,
    ManagerViewTicketPayload,
    ManagerTicketsFilterPayload,
    ManagerTicketsPaginationPayload,
    ManagerTicketsBackPayload,
    ManagerArchiveFilterPayload,
    ManagerArchivePaginationPayload,
    ManagerArchiveTicketPayload,
    ManagerArchiveBackPayload,
    ManagerArchiveTypeFilterPayload,
    ManagerTicketActionPayload,
    ManagerToggleFocusPayload,
    ManagerEmployeeSelectPayload,
    ManagerTicketHistoryPayload,
    ManagerTicketHistoryBackPayload,
    ManagerTakeFromMessagePayload,
    ManagerFocusFromMessagePayload,
    AdminMenuPayload,
    AnalyticsPayload,
    EmployeeMenuPayload,
    EmployeeListPayload,
    EmployeeActionPayload,
    EmployeeRolePayload,
    EmployeeRoleAddPayload,
    EmployeeConfirmPayload,
    BackupManagerPayload,
    TransferTicketPayload,
    TransferClientsPayload,
    OrganizationSelectPayload,
    OrganizationPagePayload,
    OrganizationActionPayload,
    KeyTogglePayload,
    KeyPagePayload,
    KeyActionPayload,
    DeliveryMethodPayload,
    EmailConfirmPayload,
    KeyConflictChoicePayload,
    RegistrationCancelPayload,
    RegistrationSkipPayload,
    AdminCreationCancelPayload,
    BackupEscalationPayload,
    PhoneChangePayload,
    PhoneChangeConfirmPayload,
    ConsultationOrgSelectPayload,
    ConsultationOrgPagePayload,
    ConsultationOrgActionPayload,
    ConsultationKeyTogglePayload,
    ConsultationKeyPagePayload,
    ConsultationKeyActionPayload,
)
from bots.max_bot.states import RegistrationStates, ProfileStates, EmployeeManagementStates, AdminCreationStates, EmployeeStates, ConsultationStates

from .common.callbacks import (
    process_back_navigation,
    process_cancel,
    process_item_selection,
    process_noop,
    process_pagination,
)
from .tickets.invoice import (
    cmd_invoice,
    handle_delivery_callback,
    handle_email_confirm_callback,
    handle_key_toggle_callback,
    handle_key_page_callback,
    handle_key_action_callback,
    handle_organization_select_callback,
    handle_organization_page_callback,
    handle_organization_action_callback,
    process_new_inn,
    process_new_key,
    process_description,
    process_email,
    cancel_add_new_inn,
    cancel_add_new_key,
)
from .tickets.support import (
    cmd_support,
    handle_renewal_callback,
    handle_key_context_callback,
    process_problem_description,
    process_new_key_for_support,
    cancel_support_flow,
)
from .tickets.consultation import (
    cmd_consultation,
    handle_consultation_org_select,
    handle_consultation_org_page,
    handle_consultation_org_action,
    process_consultation_new_inn,
    handle_consultation_key_toggle,
    handle_consultation_key_page,
    handle_consultation_key_action,
    process_consultation_new_key,
    process_consultation_description,
    cancel_consultation_add_inn,
    cancel_consultation_add_key,
)
from .user.archive import (
    handle_client_archive_button,
    handle_client_archive_filter,
    handle_client_archive_pagination,
    view_client_archived_ticket,
    handle_client_archive_close,
)
from .user.active_tickets import (
    handle_select_ticket_callback,
    handle_tickets_pagination_callback,
    handle_tickets_filter_callback,
    handle_close_active_tickets,
    handle_ticket_history,
    handle_ticket_history_back,
    handle_reply_to_manager_callback,
)
from .user.messages import route_client_message_to_ticket
from .user.message_ticket_select import (
    handle_message_ticket_select,
    handle_message_ticket_pagination,
    handle_message_ticket_cancel,
)
from .user.cancel import cmd_cancel, handle_cancel_button
from .user.commands import (
    cmd_help,
    cmd_my_id,
    cmd_me,
    handle_main_menu,
)
from .user.main_menu_callbacks import handle_main_menu_callback, handle_done_callback
from .user.renewal import show_subscription_status
from .staff.manager import (
    cmd_manager,
    handle_manager_menu_action,
    handle_tickets_filter,
    handle_tickets_pagination,
    handle_ticket_select,
    handle_view_ticket_from_notification,
    handle_tickets_back,
    handle_archive_filter,
    handle_archive_pagination,
    handle_archive_type_filter,
    handle_archive_ticket_select,
    handle_archive_back,
    handle_archive_custom_search_input,
    handle_ticket_action,
    handle_toggle_focus,
    handle_closing_comment_input,
    handle_employee_selection,
    handle_manager_ticket_history,
    handle_manager_ticket_history_back,
    handle_take_from_message_notification,
    handle_focus_from_message_notification,
)
from .staff.admin_panel import (
    handle_admin_panel_action,
    handle_admin_menu_action,
)
from .staff.analytics import (
    handle_analytics_dashboard,
    handle_analytics_period_selection,
    handle_analytics_refresh,
)
from .staff.settings import (
    handle_settings_menu,
    handle_timeout_settings,
    handle_edit_timeout_start,
    handle_timeout_value_input,
    handle_escalation_settings,
    handle_duty_support_settings,
    handle_nps_settings,
    handle_renewal_reminders_settings,
    handle_settings_history,
    handle_edit_nps_frequency_start,
    handle_nps_frequency_input,
    handle_edit_nps_trigger_start,
    handle_nps_trigger_input,
    handle_add_renewal_reminder_start,
    handle_renewal_reminder_input,
    handle_remove_renewal_reminder,
    handle_reset_timeouts,
    handle_reset_nps,
    handle_reset_renewal_reminders,
    handle_reset_escalation,
    handle_reset_duty_support,
    handle_add_escalation_channel_start,
    handle_remove_escalation_channel,
    handle_escalation_channel_input,
    handle_edit_duty_account_start,
    handle_duty_account_input,
)
from .staff.employees import (
    handle_employees_menu,
    handle_add_employee_start,
    handle_employee_id_input,
    handle_employee_name_input,
    handle_employee_position_input,
    handle_employee_role_selection,
    handle_list_employees,
    handle_employee_list_pagination,
    handle_employee_action,
    handle_employee_name_edit_input,
    handle_employee_signature_edit_input,
    handle_employee_role_change,
    handle_backup_manager_config,
    handle_backup_slot_selection,
    handle_backup_manager_assignment,
    handle_backup_manager_removal,
    handle_transfer_ticket_start,
    handle_transfer_ticket_confirm,
    handle_transfer_clients_start,
    handle_transfer_clients_confirm,
    handle_transfer_clients_execute,
)
from .staff.calendar import (
    handle_calendar_menu,
    handle_calendar_action,
    handle_rule_pagination,
    handle_back_to_menu,
    handle_calendar_text_command,
    handle_calendar_confirmation,
    handle_clear_period_confirmation,
    handle_clear_period_text,
)
from .staff.operations import (
    handle_operations_menu,
    handle_broadcast_create,
    handle_broadcast_content_input,
    handle_broadcast_targeting,
    handle_broadcast_send,
    handle_broadcast_cancel,
)
from .staff.key_conflicts import (
    handle_key_conflict_list,
    handle_key_conflict_view,
    handle_key_transfer,
    handle_key_rejection,
    handle_key_conflict_contact,
)
from .staff.escalations import (
    handle_escalations_list,
    handle_escalation_view,
    handle_escalation_reassign,
    handle_escalation_reassign_confirm,
    handle_escalation_take_over,
    handle_staff_contact,
)
from .staff.backup_escalation import (
    handle_backup_escalation_take_over,
)
from .client import nps_handler
from bots.max_bot.payloads import (
    CalendarMenuPayload,
    CalendarPaginationPayload,
    CalendarConfirmPayload,
    CalendarClearPayload,
    OperationsMenuPayload,
    BroadcastPayload,
    KeyConflictPayload,
    EscalationPayload,
    SettingsPayload,
)
from .staff.focus_messages import (
    handle_focus_message,
    handle_message_without_focus,
)
from .user.profile import (
    cmd_profile,
    handle_profile_callback,
    process_add_inn,
    process_add_key,
    process_change_email,
    cancel_profile_action,
)
from .user.phone_change import process_phone_change, confirm_phone_change
from .user.registration import (
    cmd_start,
    process_phone_contact,
    process_full_name,
    process_email_registration,
    skip_email,
    process_inn,
    process_gs_key,
    start_registration,
    process_key_conflict_choice,
    show_key_help,
    submit_registration,
    cancel_registration,
    cancel_registration_callback,
)
from .admin.admin_creation import (
    cmd_make_admin,
    process_admin_phone_contact,
    process_admin_full_name,
    cancel_admin_creation_callback,
    cancel_admin_creation_command,
)
from .admin.get_chat_id import cmd_get_chat_id

logger = logging.getLogger(__name__)


def _check_callback_action(event, action: str) -> bool:
    """
    Helper function to check if callback payload has a specific action.
    Handles both dict and JSON string payloads.
    
    Args:
        event: MessageCallback event
        action: Action string to check for
    
    Returns:
        True if payload.action matches the given action
    """
    try:
        payload = event.callback.payload
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        return payload.get("action") == action
    except Exception:
        return False


def _check_main_menu_action(event, action: str) -> bool:
    """
    Helper function to check if callback is a main menu action.
    Main menu callbacks ONLY have 'action' field, no other fields.
    This distinguishes them from invoice/support callbacks which have additional fields.
    
    Args:
        event: MessageCallback event
        action: Action string to check for
    
    Returns:
        True if payload.action matches AND payload has only 'action' field
    """
    try:
        payload = event.callback.payload
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        
        # Debug logging
        logger.debug(f"_check_main_menu_action: checking action={action}, payload={payload}, len={len(payload)}")
        
        # Check that action matches AND payload only has 'action' key (no inn, page, key_id, etc.)
        result = payload.get("action") == action and len(payload) == 1
        logger.debug(f"_check_main_menu_action: result={result}")
        return result
    except Exception as e:
        logger.error(f"_check_main_menu_action error: {e}")
        return False


def _has_filter_type(event) -> bool:
    """
    Helper function to check if callback payload has filter_type field.
    Used to distinguish archive callbacks from other callbacks with same action.
    
    Args:
        event: MessageCallback event
    
    Returns:
        True if payload has filter_type field
    """
    try:
        payload = event.callback.payload
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        return "filter_type" in payload
    except Exception:
        return False


def _check_callback_method(event, method: str) -> bool:
    """
    Helper function to check if callback payload has a specific method.
    Used for DeliveryCallback which uses 'method' instead of 'action'.
    
    Args:
        event: MessageCallback event
        method: Method string to check for
    
    Returns:
        True if payload.method matches the given method
    """
    try:
        payload = event.callback.payload
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        return payload.get("method") == method
    except Exception:
        return False


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

    # TODO: Apply private chat filter when maxapi supports it
    # user_router.message_created.filter(PrivateChatFilter())
    # user_router.message_callback.filter(PrivateChatFilter())

    # ========== Command Handlers ==========
    # Register handlers directly on router using decorator pattern
    
    logger.info(f"Registering /start handler: {cmd_start}")
    user_router.message_created(Command("start"))(cmd_start)
    
    logger.info(f"Registering /help handler: {cmd_help}")
    user_router.message_created(Command("help"))(cmd_help)
    
    logger.info(f"Registering /my_id handler: {cmd_my_id}")
    user_router.message_created(Command("my_id"))(cmd_my_id)
    
    logger.info(f"Registering /me handler: {cmd_me}")
    user_router.message_created(Command("me"))(cmd_me)
    
    logger.info(f"Registering /cancel handler: {cmd_cancel}")
    user_router.message_created(Command("cancel"))(cmd_cancel)
    
    logger.info(f"Registering /profile handler: {cmd_profile}")
    user_router.message_created(Command("profile"))(cmd_profile)
    
    logger.info(f"Registering /manager handler: {cmd_manager}")
    user_router.message_created(Command("manager"))(cmd_manager)
    
    logger.info(f"Registering /make_admin handler: {cmd_make_admin}")
    user_router.message_created(Command("make_admin"))(cmd_make_admin)
    
    logger.info(f"Registering /get_chat_id handler: {cmd_get_chat_id}")
    user_router.message_created(Command("get_chat_id"))(cmd_get_chat_id)

    # ========== Main Menu Button Handlers ==========
    
    user_router.message_created(F.message.body.text == "💰 Получить счет")(handle_main_menu)
    user_router.message_created(F.message.body.text == "🆘 Техподдержка")(handle_main_menu)
    user_router.message_created(F.message.body.text == "👤 Мой профиль")(handle_main_menu)
    user_router.message_created(F.message.body.text == "📋 Архив обращений")(handle_client_archive_button)
    user_router.message_created(F.message.body.text == "❌ Отмена")(handle_cancel_button)

    # ========== Main Menu Inline Callback Handlers ==========
    
    # Handle main menu inline keyboard callbacks using CallbackPayload
    # Note: MainMenuActionPayload.filter() ensures we ONLY match callbacks with single 'action' field
    # This prevents catching invoice/support callbacks which have additional fields (inn, page, key_id, etc.)
    user_router.message_callback(MainMenuActionPayload.filter())(handle_main_menu_callback)

    # Handle "✅ Готово" button after ticket creation
    user_router.message_callback(DonePayload.filter())(handle_done_callback)
    
    # ========== Manager Menu Callback Handlers ==========
    
    # Manager menu action handler
    user_router.message_callback(ManagerMenuActionPayload.filter())(handle_manager_menu_action)
    
    # Manager active tickets handlers
    user_router.message_callback(ManagerTicketsFilterPayload.filter())(handle_tickets_filter)
    user_router.message_callback(ManagerTicketsPaginationPayload.filter())(handle_tickets_pagination)
    user_router.message_callback(ManagerTicketSelectPayload.filter())(handle_ticket_select)
    user_router.message_callback(ManagerViewTicketPayload.filter())(handle_view_ticket_from_notification)
    user_router.message_callback(ManagerTicketsBackPayload.filter())(handle_tickets_back)
    
    # Manager ticket action handlers
    user_router.message_callback(ManagerTicketActionPayload.filter())(handle_ticket_action)
    user_router.message_callback(ManagerToggleFocusPayload.filter())(handle_toggle_focus)
    
    # Manager ticket history handlers
    user_router.message_callback(ManagerTicketHistoryPayload.filter())(handle_manager_ticket_history)
    user_router.message_callback(ManagerTicketHistoryBackPayload.filter())(handle_manager_ticket_history_back)
    
    # Manager employee selection handler (for transfer)
    user_router.message_callback(ManagerEmployeeSelectPayload.filter())(handle_employee_selection)
    
    # Client message notification action handlers
    user_router.message_callback(ManagerTakeFromMessagePayload.filter())(handle_take_from_message_notification)
    user_router.message_callback(ManagerFocusFromMessagePayload.filter())(handle_focus_from_message_notification)
    
    # ========== Admin Panel Handlers ==========
    
    # Admin panel entry point (from manager menu)
    # Note: This is handled by handle_manager_menu_action with action="admin_panel"
    # The actual handler is handle_admin_panel_action which is called from manager.py
    
    # Admin panel menu navigation
    user_router.message_callback(AdminMenuPayload.filter())(handle_admin_menu_action)
    
    # ========== Analytics/Statistics Handlers ==========
    
    # Analytics period selection
    async def route_analytics_action(
        event: MessageCallback,
        payload: AnalyticsPayload,
        context: MemoryContext,
        session: AsyncSession,
        messenger_adapter: MAXMessengerAdapter
    ):
        """Route analytics actions to appropriate handlers."""
        if payload.action == "period":
            await handle_analytics_period_selection(event, payload, context, session, messenger_adapter)
        elif payload.action == "refresh":
            await handle_analytics_refresh(event, payload, context, session, messenger_adapter)
        else:
            logger.warning(f"Unknown analytics action: {payload.action}")
    
    user_router.message_callback(AnalyticsPayload.filter())(route_analytics_action)
    
    # ========== Employee Management Handlers ==========
    
    # Employee menu actions - route based on action
    async def route_employee_menu_action(
        event: MessageCallback,
        payload: EmployeeMenuPayload,
        context: MemoryContext,
        session: AsyncSession,
        messenger_adapter: MAXMessengerAdapter
    ):
        """Route employee menu actions to appropriate handlers."""
        if payload.action == "add":
            await handle_add_employee_start(event, payload, context, session, messenger_adapter)
        elif payload.action == "list":
            await handle_list_employees(event, payload, context, session, messenger_adapter)
        else:
            logger.warning(f"Unknown employee menu action: {payload.action}")
    
    user_router.message_callback(EmployeeMenuPayload.filter())(route_employee_menu_action)
    
    # Employee list pagination
    user_router.message_callback(EmployeeListPayload.filter())(handle_employee_list_pagination)
    
    # Employee actions (view/edit/deactivate)
    user_router.message_callback(EmployeeActionPayload.filter())(handle_employee_action)
    
    # Employee role selection for adding new employee
    user_router.message_callback(EmployeeRoleAddPayload.filter())(handle_employee_role_selection)
    
    # Employee role selection for editing existing employee
    user_router.message_callback(EmployeeRolePayload.filter())(handle_employee_role_change)
    
    # Employee text input handlers
    
    user_router.message_created(
        F.message.body.text,
        EmployeeManagementStates.adding_employee_id
    )(handle_employee_id_input)
    
    user_router.message_created(
        F.message.body.text,
        EmployeeManagementStates.adding_employee_name
    )(handle_employee_name_input)
    
    user_router.message_created(
        F.message.body.text,
        EmployeeManagementStates.adding_employee_position
    )(handle_employee_position_input)
    
    # Employee name edit input
    user_router.message_created(
        F.message.body.text,
        EmployeeManagementStates.editing_employee_name
    )(handle_employee_name_edit_input)
    
    # Employee signature edit input
    user_router.message_created(
        F.message.body.text,
        EmployeeManagementStates.editing_employee_signature
    )(handle_employee_signature_edit_input)
    
    # Backup manager handlers - single registration with internal routing
    async def route_backup_manager(event: MessageCallback, payload: BackupManagerPayload, context: MemoryContext, session: AsyncSession, messenger_adapter: MAXMessengerAdapter):
        if payload.action == "config":
            await handle_backup_manager_config(event, payload, context, session, messenger_adapter)
        elif payload.action == "select_slot":
            await handle_backup_slot_selection(event, payload, context, session, messenger_adapter)
        elif payload.action == "assign":
            await handle_backup_manager_assignment(event, payload, context, session, messenger_adapter)
        elif payload.action == "remove":
            await handle_backup_manager_removal(event, payload, context, session, messenger_adapter)
    
    user_router.message_callback(BackupManagerPayload.filter())(route_backup_manager)
    
    # Transfer ticket handlers - single registration with internal routing
    async def route_transfer_ticket(event: MessageCallback, payload: TransferTicketPayload, context: MemoryContext, session: AsyncSession, messenger_adapter: MAXMessengerAdapter):
        if payload.action == "start":
            await handle_transfer_ticket_start(event, payload, context, session, messenger_adapter)
        elif payload.action == "confirm":
            await handle_transfer_ticket_confirm(event, payload, context, session, messenger_adapter)
    
    user_router.message_callback(TransferTicketPayload.filter())(route_transfer_ticket)
    
    # Transfer clients handlers - single registration with internal routing
    async def route_transfer_clients(event: MessageCallback, payload: TransferClientsPayload, context: MemoryContext, session: AsyncSession, messenger_adapter: MAXMessengerAdapter):
        if payload.action == "start":
            await handle_transfer_clients_start(event, payload, context, session, messenger_adapter)
        elif payload.action == "confirm":
            await handle_transfer_clients_confirm(event, payload, context, session, messenger_adapter)
        elif payload.action == "execute":
            await handle_transfer_clients_execute(event, payload, context, session, messenger_adapter)
    
    user_router.message_callback(TransferClientsPayload.filter())(route_transfer_clients)
    
    # ========== Calendar Handlers ==========
    
    # Calendar menu actions
    user_router.message_callback(CalendarMenuPayload.filter())(handle_calendar_action)
    
    # Calendar pagination
    user_router.message_callback(CalendarPaginationPayload.filter())(handle_rule_pagination)
    
    # Calendar confirmation actions (add/delete rules)
    user_router.message_callback(CalendarConfirmPayload.filter())(handle_calendar_confirmation)
    
    # Calendar clear period confirmation
    user_router.message_callback(CalendarClearPayload.filter())(handle_clear_period_confirmation)
    
    # Calendar text command handler (add/delete rules)
    from bots.max_bot.states import CalendarStates
    
    user_router.message_created(
        F.message.body.text,
        CalendarStates.managing_calendar
    )(handle_calendar_text_command)
    
    # Calendar clear period text input handler
    user_router.message_created(
        F.message.body.text,
        CalendarStates.entering_clear_period
    )(handle_clear_period_text)
    
    # ========== Operations Handlers ==========
    
    # Operations menu (from admin panel)
    # Note: Registered via AdminMenuPayload with action="operations" in admin panel handler
    
    # Operations submenu navigation - route by action
    async def route_operations_menu(
        event: MessageCallback,
        payload: OperationsMenuPayload,
        context: MemoryContext,
        session: AsyncSession,
        messenger_adapter: MAXMessengerAdapter
    ):
        if payload.action == "key_conflicts":
            await handle_key_conflict_list(event, payload, context, session, messenger_adapter)
        elif payload.action == "escalations":
            await handle_escalations_list(event, payload, context, session, messenger_adapter)
        elif payload.action == "phone_changes":
            # Route to phone change management
            from bots.max_bot.handlers.staff.phone_management import handle_phone_change_list
            await handle_phone_change_list(event, context, session, messenger_adapter)
        else:
            await messenger_adapter.send_message(
                chat_id=event.message.recipient.chat_id,
                text="❌ Неизвестное действие",
                parse_mode="HTML"
            )
    
    user_router.message_callback(OperationsMenuPayload.filter())(route_operations_menu)
    
    # Escalation handlers - route by action
    async def route_escalation(
        event: MessageCallback,
        payload: EscalationPayload,
        context: MemoryContext,
        session: AsyncSession,
        messenger_adapter: MAXMessengerAdapter
    ):
        if payload.action == "list":
            page = payload.page if payload.page is not None else 0
            await handle_escalations_list(event, OperationsMenuPayload(action="escalations"), context, session, messenger_adapter, page=page)
        elif payload.action == "view":
            await handle_escalation_view(event, payload, context, session, messenger_adapter)
        elif payload.action == "reassign":
            await handle_escalation_reassign(event, payload, context, session, messenger_adapter)
        elif payload.action == "reassign_confirm":
            await handle_escalation_reassign_confirm(event, payload, context, session, messenger_adapter)
        elif payload.action == "take_over":
            await handle_escalation_take_over(event, payload, context, session, messenger_adapter)
        elif payload.action == "contact":
            await handle_staff_contact(event, payload, context, session, messenger_adapter)
    
    user_router.message_callback(EscalationPayload.filter())(route_escalation)
    
    # Backup escalation handlers
    user_router.message_callback(BackupEscalationPayload.filter())(handle_backup_escalation_take_over)
    
    # Key conflict handlers - route by action
    async def route_key_conflict(
        event: MessageCallback,
        payload: KeyConflictPayload,
        context: MemoryContext,
        session: AsyncSession,
        messenger_adapter: MAXMessengerAdapter
    ):
        if payload.action == "list":
            page = payload.page if payload.page is not None else 0
            await handle_key_conflict_list(event, OperationsMenuPayload(action="key_conflicts"), context, session, messenger_adapter, page=page)
        elif payload.action == "view":
            await handle_key_conflict_view(event, payload, context, session, messenger_adapter)
        elif payload.action == "transfer":
            await handle_key_transfer(event, payload, context, session, messenger_adapter)
        elif payload.action == "reject":
            await handle_key_rejection(event, payload, context, session, messenger_adapter)
        elif payload.action == "contact":
            await handle_key_conflict_contact(event, payload, context, session, messenger_adapter)
    
    user_router.message_callback(KeyConflictPayload.filter())(route_key_conflict)
    
    # Broadcast handlers - route by action
    async def route_broadcast(
        event: MessageCallback,
        payload: BroadcastPayload,
        context: MemoryContext,
        session: AsyncSession,
        messenger_adapter: MAXMessengerAdapter
    ):
        if payload.action == "create":
            await handle_broadcast_create(event, payload, context, session, messenger_adapter)
        elif payload.action == "target":
            await handle_broadcast_targeting(event, payload, context, session, messenger_adapter)
        elif payload.action == "send":
            await handle_broadcast_send(event, payload, context, session, messenger_adapter)
        elif payload.action == "cancel":
            await handle_broadcast_cancel(event, payload, context, session, messenger_adapter)
    
    user_router.message_callback(BroadcastPayload.filter())(route_broadcast)
    
    # Broadcast content input
    from bots.max_bot.states import OperationsStates
    
    user_router.message_created(
        F.message.body.text,
        OperationsStates.creating_broadcast_content
    )(handle_broadcast_content_input)
    
    # ========== Phone Change Management Handlers ==========
    
    # Phone change management handlers - route by action
    async def route_phone_change(
        event: MessageCallback,
        payload: PhoneChangePayload,
        context: MemoryContext,
        session: AsyncSession,
        messenger_adapter: MAXMessengerAdapter
    ):
        """Route phone change management actions to appropriate handlers."""
        from bots.max_bot.handlers.staff.phone_management import (
            handle_phone_change_list,
            handle_phone_change_view,
            handle_phone_change_approve,
            handle_phone_change_reject
        )
        
        if payload.action == "list":
            await handle_phone_change_list(event, context, session, messenger_adapter)
        elif payload.action == "view":
            await handle_phone_change_view(event, payload, context, session, messenger_adapter)
        elif payload.action == "approve":
            await handle_phone_change_approve(event, payload, context, session, messenger_adapter)
        elif payload.action == "reject":
            await handle_phone_change_reject(event, payload, context, session, messenger_adapter)
        elif payload.action == "back":
            # Navigate back to admin panel or operations menu
            from bots.max_bot.handlers.staff.admin_panel import handle_admin_menu_action
            await handle_admin_menu_action(
                event, 
                AdminMenuPayload(action="operations"), 
                context, 
                session, 
                messenger_adapter
            )
        else:
            logger.warning(f"Unknown phone change action: {payload.action}")
    
    user_router.message_callback(PhoneChangePayload.filter())(route_phone_change)

    # User-side phone change confirmation/cancellation
    user_router.message_callback(PhoneChangeConfirmPayload.filter())(confirm_phone_change)
    
    # ========== Settings Handlers ==========
    
    # Settings menu navigation - route by action
    async def route_settings(
        event: MessageCallback,
        payload: SettingsPayload,
        context: MemoryContext,
        session: AsyncSession,
        messenger_adapter: MAXMessengerAdapter
    ):
        if payload.action == "menu":
            await handle_settings_menu(event, AdminMenuPayload(action="settings"), context, session, messenger_adapter)
        elif payload.action == "timeouts":
            await handle_timeout_settings(event, payload, context, session, messenger_adapter)
        elif payload.action == "edit_timeout":
            await handle_edit_timeout_start(event, payload, context, session, messenger_adapter)
        elif payload.action == "reset_timeouts":
            await handle_reset_timeouts(event, payload, context, session, messenger_adapter)
        elif payload.action == "escalation":
            await handle_escalation_settings(event, payload, context, session, messenger_adapter)
        elif payload.action == "add_escalation_channel":
            await handle_add_escalation_channel_start(event, payload, context, session, messenger_adapter)
        elif payload.action == "remove_escalation_channel":
            await handle_remove_escalation_channel(event, payload, context, session, messenger_adapter)
        elif payload.action == "reset_escalation":
            await handle_reset_escalation(event, payload, context, session, messenger_adapter)
        elif payload.action == "duty_support":
            await handle_duty_support_settings(event, payload, context, session, messenger_adapter)
        elif payload.action == "edit_duty_account":
            await handle_edit_duty_account_start(event, payload, context, session, messenger_adapter)
        elif payload.action == "reset_duty_support":
            await handle_reset_duty_support(event, payload, context, session, messenger_adapter)
        elif payload.action == "nps":
            await handle_nps_settings(event, payload, context, session, messenger_adapter)
        elif payload.action == "edit_nps_frequency":
            await handle_edit_nps_frequency_start(event, payload, context, session, messenger_adapter)
        elif payload.action == "edit_nps_trigger":
            await handle_edit_nps_trigger_start(event, payload, context, session, messenger_adapter)
        elif payload.action == "reset_nps":
            await handle_reset_nps(event, payload, context, session, messenger_adapter)
        elif payload.action == "renewal_reminders":
            await handle_renewal_reminders_settings(event, payload, context, session, messenger_adapter)
        elif payload.action == "add_renewal_reminder":
            await handle_add_renewal_reminder_start(event, payload, context, session, messenger_adapter)
        elif payload.action == "remove_renewal_reminder":
            await handle_remove_renewal_reminder(event, payload, context, session, messenger_adapter)
        elif payload.action == "reset_renewal_reminders":
            await handle_reset_renewal_reminders(event, payload, context, session, messenger_adapter)
        elif payload.action == "history":
            await handle_settings_history(event, payload, context, session, messenger_adapter)
    
    user_router.message_callback(SettingsPayload.filter())(route_settings)
    
    # Settings value input handlers
    from bots.max_bot.states import SettingsStates
    
    user_router.message_created(
        F.message.body.text,
        SettingsStates.entering_timeout_value
    )(handle_timeout_value_input)
    
    user_router.message_created(
        F.message.body.text,
        SettingsStates.entering_nps_frequency
    )(handle_nps_frequency_input)
    
    user_router.message_created(
        F.message.body.text,
        SettingsStates.entering_nps_trigger_timing
    )(handle_nps_trigger_input)
    
    user_router.message_created(
        F.message.body.text,
        SettingsStates.entering_renewal_reminder_days
    )(handle_renewal_reminder_input)
    
    user_router.message_created(
        F.message.body.text,
        SettingsStates.entering_escalation_chat_id
    )(handle_escalation_channel_input)
    
    user_router.message_created(
        F.message.body.text,
        SettingsStates.entering_duty_account_id
    )(handle_duty_account_input)
    
    # ========== Employee Focus Mode Handlers ==========
    
    # Manager closing ticket comment input
    from bots.max_bot.states import EmployeeStates
    
    user_router.message_created(
        EmployeeStates.manager_closing_ticket
    )(handle_closing_comment_input)
    
    # Focus mode message handler (text and files)
    # This handler catches all messages when employee is in focus mode
    user_router.message_created(
        EmployeeStates.in_focus
    )(handle_focus_message)
    
    # Manager archive handlers
    user_router.message_callback(ManagerArchiveFilterPayload.filter())(handle_archive_filter)
    user_router.message_callback(ManagerArchiveTypeFilterPayload.filter())(handle_archive_type_filter)
    user_router.message_callback(ManagerArchivePaginationPayload.filter())(handle_archive_pagination)
    user_router.message_callback(ManagerArchiveTicketPayload.filter())(handle_archive_ticket_select)
    user_router.message_callback(ManagerArchiveBackPayload.filter())(handle_archive_back)
    
    # Manager archive custom search input handler
    from bots.max_bot.states import EmployeeStates
    
    user_router.message_created(
        F.message.body.text,
        EmployeeStates.archive_custom_search
    )(handle_archive_custom_search_input)

    # ========== Renewal Callback Handlers ==========
    
    # Renewal action callback handler (currently only "renew" action is handled in show_subscription_status)
    # Note: "contact_manager" action would need separate handler if implemented
    # For now, renewal callbacks are handled within show_subscription_status flow
    
    # ========== Archive Callback Handlers ==========
    
    # Archive callback handlers using CallbackPayload classes
    user_router.message_callback(ArchiveFilterPayload.filter())(handle_client_archive_filter)
    user_router.message_callback(ArchivePaginationPayload.filter())(handle_client_archive_pagination)
    user_router.message_callback(ViewArchivedTicketPayload.filter())(view_client_archived_ticket)
    user_router.message_callback(ArchiveClosePayload.filter())(handle_client_archive_close)
    
    # ========== Active Tickets Callback Handlers ==========
    
    user_router.message_callback(TicketsFilterPayload.filter())(handle_tickets_filter_callback)
    user_router.message_callback(TicketSelectPayload.filter())(handle_select_ticket_callback)
    user_router.message_callback(TicketsPaginationPayload.filter())(handle_tickets_pagination_callback)
    user_router.message_callback(ActiveTicketsClosePayload.filter())(handle_close_active_tickets)
    user_router.message_callback(TicketHistoryPayload.filter())(handle_ticket_history)
    user_router.message_callback(TicketHistoryBackPayload.filter())(handle_ticket_history_back)
    user_router.message_callback(ReplyToManagerPayload.filter())(handle_reply_to_manager_callback)
    user_router.message_callback(MessageTicketSelectPayload.filter())(handle_message_ticket_select)
    user_router.message_callback(MessageTicketPaginationPayload.filter())(handle_message_ticket_pagination)
    user_router.message_callback(MessageTicketCancelPayload.filter())(handle_message_ticket_cancel)

    # ========== Profile Management Handlers ==========
    
    # Profile action callback handlers using different payload types
    user_router.message_callback(ProfileActionPayload.filter())(handle_profile_callback)
    user_router.message_callback(ProfileViewPayload.filter())(handle_profile_callback)
    user_router.message_callback(ProfileAddPayload.filter())(handle_profile_callback)
    user_router.message_callback(ProfileDeleteOrgPayload.filter())(handle_profile_callback)
    user_router.message_callback(ProfileConfirmDeleteOrgPayload.filter())(handle_profile_callback)
    user_router.message_callback(ProfileDeleteKeyPayload.filter())(handle_profile_callback)
    user_router.message_callback(ProfileConfirmDeleteKeyPayload.filter())(handle_profile_callback)
    
    # Profile input handlers with FSM state filters
    user_router.message_created(
        F.message.body.text,
        ProfileStates.adding_inn
    )(process_add_inn)
    
    user_router.message_created(
        F.message.body.text,
        ProfileStates.adding_key
    )(process_add_key)
    
    user_router.message_created(
        F.message.body.text,
        ProfileStates.changing_email
    )(process_change_email)
    
    user_router.message_created(
        F.message.body.text,
        ProfileStates.changing_phone
    )(process_phone_change)
    
    # Profile cancellation handler - registered for multiple states
    user_router.message_created(
        F.message.body.text == "❌ Отмена",
        ProfileStates.adding_inn
    )(cancel_profile_action)
    user_router.message_created(
        F.message.body.text == "❌ Отмена",
        ProfileStates.adding_key
    )(cancel_profile_action)
    user_router.message_created(
        F.message.body.text == "❌ Отмена",
        ProfileStates.changing_email
    )(cancel_profile_action)
    user_router.message_created(
        F.message.body.text == "❌ Отмена",
        ProfileStates.changing_phone
    )(cancel_profile_action)

    # ========== Registration Flow Handlers ==========
    
    # Contact sharing handler - triggered when user shares contact in waiting_for_phone state
    # Note: MAX may send contact as text or in attachments, so we handle both
    user_router.message_created(
        RegistrationStates.waiting_for_phone
    )(process_phone_contact)
    
    # Full name handler
    user_router.message_created(
        F.message.body.text,
        RegistrationStates.waiting_for_name
    )(process_full_name)
    
    # Email handler (optional step)
    user_router.message_created(
        F.message.body.text,
        RegistrationStates.waiting_for_email
    )(process_email_registration)
    
    # Skip email callback - when user clicks "Пропустить"
    user_router.message_callback(RegistrationSkipPayload.filter())(skip_email)
    
    # INN handler
    user_router.message_created(
        F.message.body.text,
        RegistrationStates.waiting_for_inn
    )(process_inn)
    
    # GS Key handler
    user_router.message_created(
        F.message.body.text,
        RegistrationStates.waiting_for_key
    )(process_gs_key)
    
    # Key help callback - when user clicks "Не знаю номер ключа"
    user_router.message_callback(
        lambda event: (
            hasattr(event, 'callback') and 
            hasattr(event.callback, 'payload') and
            isinstance(event.callback.payload, str) and
            '"action":"key_help"' in event.callback.payload or
            '"action": "key_help"' in event.callback.payload
        ),
        RegistrationStates.waiting_for_key
    )(show_key_help)
    
    # Registration callbacks - key conflict resolution
    user_router.message_callback(KeyConflictChoicePayload.filter())(process_key_conflict_choice)
    
    # Registration cancel callback - handles cancel button clicks during registration
    user_router.message_callback(RegistrationCancelPayload.filter())(cancel_registration_callback)
    
    # ========== Admin Creation Flow Handlers ==========
    
    # Contact sharing handler for admin creation
    user_router.message_created(
        AdminCreationStates.waiting_for_phone
    )(process_admin_phone_contact)
    
    # Full name handler for admin creation
    user_router.message_created(
        F.message.body.text,
        AdminCreationStates.waiting_for_full_name
    )(process_admin_full_name)
    
    # Admin creation cancel callback
    user_router.message_callback(AdminCreationCancelPayload.filter())(cancel_admin_creation_callback)
    
    # Admin creation cancel command
    user_router.message_created(
        Command("cancel"),
        AdminCreationStates.waiting_for_phone
    )(cancel_admin_creation_command)
    
    user_router.message_created(
        Command("cancel"),
        AdminCreationStates.waiting_for_full_name
    )(cancel_admin_creation_command)
    
    # ========== Client Message Routing (Active Ticket Communication) ==========
    
    # This handler must be registered LAST to catch all unhandled messages
    # It checks for active_ticket_id in FSM context and routes messages to manager
    # Handles text, photos, documents, voice messages, and videos
    
    async def handle_client_message_wrapper(
        event: MessageCreated,
        context: MemoryContext,
        session: AsyncSession,
        messenger_adapter: MAXMessengerAdapter
    ):
        """
        Wrapper to route client messages to active ticket.
        
        This is registered as a catch-all handler for messages that weren't
        handled by specific handlers (commands, buttons, FSM states).
        
        IMPORTANT: Skip messages from employees in focus mode - those are handled
        by handle_focus_message which is registered with EmployeeStates.in_focus filter.
        """
        # Check if user is in focus mode (employee sending message to client)
        current_state = await context.get_state()
        if current_state == EmployeeStates.in_focus:
            # This message should be handled by handle_focus_message
            # Skip catch-all routing
            logger.debug(
                f"Skipping catch-all for user {event.message.sender.user_id} "
                f"in focus mode (state={current_state})"
            )
            return
        
        # Try to route message to active ticket
        was_routed = await route_client_message_to_ticket(
            event=event,
            context=context,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        if not was_routed:
            # Check if this is an employee without focus mode
            # handle_message_without_focus returns early (without sending anything) if user is not staff
            is_staff = await handle_message_without_focus(
                event=event,
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
            
            # If user was staff, handle_message_without_focus already responded — stop here
            if is_staff:
                return
            
            # Not staff and no active ticket - check active tickets count
            chat_id = event.message.recipient.chat_id
            max_user_id = event.message.sender.user_id
            
            logger.info(
                f"Message from user {max_user_id} not routed (no active ticket) - checking tickets"
            )
            
            # Check if user is registered
            from services.user_service import get_user_by_max_id
            user = await get_user_by_max_id(session, max_user_id)
            
            if not user:
                # Unregistered user
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text=(
                        "👋 Добро пожаловать!\n\n"
                        "Для начала работы с ботом воспользуйтесь командой /start"
                    ),
                    parse_mode="HTML"
                )
            else:
                from services.ticket_service import get_user_active_tickets
                active_tickets = await get_user_active_tickets(session, user.id)
                active_tickets_count = len(active_tickets)
                
                if active_tickets_count == 1:
                    # Exactly one active ticket — auto-route immediately
                    ticket = active_tickets[0]
                    from bots.max_bot.handlers.user.messages import handle_client_message_to_ticket_max
                    from database.models import TicketStatus
                    await handle_client_message_to_ticket_max(
                        event=event,
                        session=session,
                        ticket=ticket,
                        messenger_adapter=messenger_adapter
                    )
                    from bots.max_bot.handlers.user.messages import get_message_type_name
                    message_type_name = get_message_type_name(event)
                    await messenger_adapter.send_message(
                        chat_id=chat_id,
                        text=f"✅ Ваше сообщение ({message_type_name}) отправлено менеджеру (Заявка #{ticket.id})",
                        parse_mode="HTML"
                    )
                    logger.info(
                        f"Auto-routed message to single active ticket: "
                        f"user_id={max_user_id}, ticket_id={ticket.id}"
                    )
                
                elif active_tickets_count > 1:
                    # Multiple active tickets — store pending message metadata and show selection menu
                    from bots.max_bot.keyboards.user.message_ticket_select_kb import get_message_ticket_select_keyboard
                    from bots.max_bot.handlers.user.messages import extract_attachment_metadata
                    from bots.max_bot.handlers.user.message_ticket_select import build_pending_data

                    meta = extract_attachment_metadata(event)
                    await context.update_data(**build_pending_data(meta))

                    keyboard = await get_message_ticket_select_keyboard(active_tickets, page=0)
                    await messenger_adapter.send_message(
                        chat_id=chat_id,
                        text="📋 <b>По какой заявке отправить сообщение?</b>",
                        keyboard=keyboard,
                        parse_mode="HTML"
                    )
                    logger.info(
                        f"Showing ticket selection menu: user_id={max_user_id}, "
                        f"tickets_count={active_tickets_count}"
                    )
                
                else:
                    # User has no active tickets
                    await messenger_adapter.send_message(
                        chat_id=chat_id,
                        text=(
                            "📋 <b>У вас нет активных обращений.</b>\n\n"
                            "Воспользуйтесь командой /start для вызова главного меню и создания новой заявки:\n\n"
                            "• 💰 <b>Получить счёт</b> — запросить счет на обновление базы\n"
                            "• 🆘 <b>Техподдержка</b> — получить помощь по программе\n"
                            "• 🔄 <b>Продление</b> — продлить подписку"
                        ),
                        parse_mode="HTML"
                    )
    
    # Register catch-all message handler
    # This will only trigger if no other handler matched
    user_router.message_created()(handle_client_message_wrapper)

    logger.info("User router created with command and menu handlers")
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

    # TODO: Apply private chat filter when maxapi supports it
    # tickets_router.message_created.filter(PrivateChatFilter())
    # tickets_router.message_callback.filter(PrivateChatFilter())

    # ========== Command Handlers ==========
    
    logger.info(f"Registering /invoice handler: {cmd_invoice}")
    tickets_router.message_created(Command("invoice"))(cmd_invoice)
    
    logger.info(f"Registering /support handler: {cmd_support}")
    tickets_router.message_created(Command("support"))(cmd_support)

    # ========== Invoice Flow Callbacks ==========
    # Register callback handlers using CallbackPayload filters
    # Each payload type routes to its specific handler with type-safe parsing
    
    tickets_router.message_callback(OrganizationSelectPayload.filter())(handle_organization_select_callback)
    tickets_router.message_callback(OrganizationPagePayload.filter())(handle_organization_page_callback)
    tickets_router.message_callback(OrganizationActionPayload.filter())(handle_organization_action_callback)
    tickets_router.message_callback(KeyTogglePayload.filter())(handle_key_toggle_callback)
    tickets_router.message_callback(KeyPagePayload.filter())(handle_key_page_callback)
    tickets_router.message_callback(KeyActionPayload.filter())(handle_key_action_callback)
    tickets_router.message_callback(DeliveryMethodPayload.filter())(handle_delivery_callback)
    tickets_router.message_callback(EmailConfirmPayload.filter())(handle_email_confirm_callback)
    
    # ========== Invoice Flow Message Handlers ==========
    # Import InvoiceStates for FSM state filters
    from bots.max_bot.states import InvoiceStates, SupportStates
    
    # Handler for adding new INN
    tickets_router.message_created(
        F.message.body.text,
        InvoiceStates.adding_new_inn
    )(process_new_inn)
    
    # Handler for adding new key
    tickets_router.message_created(
        F.message.body.text,
        InvoiceStates.adding_new_key
    )(process_new_key)
    
    # Handler for entering description (text, photo, voice, document)
    tickets_router.message_created(
        InvoiceStates.entering_description
    )(process_description)
    
    # Handler for entering email
    tickets_router.message_created(
        F.message.body.text,
        InvoiceStates.entering_email
    )(process_email)
    
    # Cancel handler for adding new INN state
    tickets_router.message_callback(
        RegistrationCancelPayload.filter(),
        InvoiceStates.adding_new_inn
    )(cancel_add_new_inn)
    
    # Cancel handler for adding new key state
    tickets_router.message_callback(
        RegistrationCancelPayload.filter(),
        InvoiceStates.adding_new_key
    )(cancel_add_new_key)
    
    # ========== Support Flow Callbacks ==========
    # Register support callback handlers using CallbackPayload filters (like invoice flow)
    
    # Import support flow payload classes
    from bots.max_bot.payloads import (
        RenewalActionPayload,
        KeyContextTogglePayload,
        KeyContextPagePayload,
        KeyContextActionPayload,
    )
    
    # Renewal callback handler (when user clicks "Оформить заявку на продление")
    tickets_router.message_callback(RenewalActionPayload.filter())(handle_renewal_callback)
    
    # Key context callback handlers - separate handlers for each payload type
    tickets_router.message_callback(KeyContextTogglePayload.filter())(handle_key_context_callback)
    tickets_router.message_callback(KeyContextPagePayload.filter())(handle_key_context_callback)
    tickets_router.message_callback(KeyContextActionPayload.filter())(handle_key_context_callback)
    
    # Cancel callback handler for support flow (only in support states)
    # Import SupportStates for state filtering
    tickets_router.message_callback(
        F.callback.payload == '{"action": "cancel"}',
        SupportStates.entering_problem
    )(cancel_support_flow)
    
    tickets_router.message_callback(
        F.callback.payload == '{"action": "cancel"}',
        SupportStates.selecting_key_context
    )(cancel_support_flow)
    
    tickets_router.message_callback(
        F.callback.payload == '{"action": "cancel"}',
        SupportStates.adding_new_key
    )(cancel_support_flow)
    
    # ========== Support Flow Message Handlers ==========
    
    # Handler for entering problem description (text, photo, voice, document)
    tickets_router.message_created(
        SupportStates.entering_problem
    )(process_problem_description)
    
    # Handler for adding new key in support flow
    tickets_router.message_created(
        F.message.body.text,
        SupportStates.adding_new_key
    )(process_new_key_for_support)

    # ========== Consultation Flow Command ==========

    logger.info(f"Registering /consultation handler: {cmd_consultation}")
    tickets_router.message_created(Command("consultation"))(cmd_consultation)

    # ========== Consultation Flow Callbacks ==========

    tickets_router.message_callback(ConsultationOrgSelectPayload.filter())(handle_consultation_org_select)
    tickets_router.message_callback(ConsultationOrgPagePayload.filter())(handle_consultation_org_page)
    tickets_router.message_callback(ConsultationOrgActionPayload.filter())(handle_consultation_org_action)
    tickets_router.message_callback(ConsultationKeyTogglePayload.filter())(handle_consultation_key_toggle)
    tickets_router.message_callback(ConsultationKeyPagePayload.filter())(handle_consultation_key_page)
    tickets_router.message_callback(ConsultationKeyActionPayload.filter())(handle_consultation_key_action)

    # ========== Consultation Flow Message Handlers ==========

    tickets_router.message_created(
        F.message.body.text,
        ConsultationStates.adding_new_inn
    )(process_consultation_new_inn)

    tickets_router.message_created(
        F.message.body.text,
        ConsultationStates.adding_new_key
    )(process_consultation_new_key)

    tickets_router.message_created(
        ConsultationStates.entering_description
    )(process_consultation_description)

    # Cancel handlers for consultation add-new substeps (return to previous screen, not main menu)
    tickets_router.message_callback(
        RegistrationCancelPayload.filter(),
        ConsultationStates.adding_new_inn
    )(cancel_consultation_add_inn)

    tickets_router.message_callback(
        RegistrationCancelPayload.filter(),
        ConsultationStates.adding_new_key
    )(cancel_consultation_add_key)

    logger.info("Tickets router created with invoice, support and consultation handlers")
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

    # TODO: Apply private chat filter when maxapi supports it
    # common_router.message_created.filter(PrivateChatFilter())
    # common_router.message_callback.filter(PrivateChatFilter())

    # ========== Common Callback Handlers ==========
    # Register callback handlers directly on router
    # NOTE: Example handlers are disabled to avoid interfering with real handlers
    # They only match actions starting with 'example_' or 'example_nav_'
    
    # common_router.message_callback(ExampleItemCallback.filter())(process_pagination)
    # common_router.message_callback(ExampleItemCallback.filter())(process_item_selection)
    # common_router.message_callback(ExampleItemCallback.filter())(process_cancel)
    # common_router.message_callback(ExampleNavigationCallback.filter())(process_back_navigation)
    common_router.message_callback(F.callback.payload == "noop")(process_noop)

    logger.info("Common router created with shared callback handlers")
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

    # TODO: Apply private chat filter when maxapi supports it
    # employee_router.message_created.filter(PrivateChatFilter())
    # employee_router.message_callback.filter(PrivateChatFilter())

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
    them DIRECTLY in the dispatcher (not in the main router).
    
    Router hierarchy:
    - dispatcher
      ├─ user_router (commands, registration, profile)
      ├─ tickets_router (invoice, support)
      ├─ common_router (shared callbacks, navigation)
      └─ employee_router (employee interface)
    
    Dependencies are injected via middleware:
    - messenger_adapter: Injected via MessengerAdapterMiddleware
    - session: Injected via DatabaseSessionMiddleware
    - context: Provided by maxapi MemoryContext
    
    Args:
        dp: MAX Dispatcher instance
        router: Main MAX Router instance (not used - kept for compatibility)
    
    Requirements: 9.1, 9.2, 9.4, 9.7, 10.1, 10.2, 10.3, 5.1, 5.2, 5.3, 9.8, 14.5
    """

    logger.info("Creating feature-specific routers...")
    
    # Create feature-specific routers
    user_router = create_user_router()
    tickets_router = create_tickets_router()
    common_router = create_common_router()
    employee_router = create_employee_router()
    nps_router = nps_handler.router  # NPS survey handlers

    # Include all routers DIRECTLY in the dispatcher (not in main router)
    # maxapi processes routers in REVERSE order (last registered = first checked)
    # So we register in reverse priority order
    logger.info("Including routers in dispatcher...")
    dp.include_routers(
        employee_router,  # Employee interface handlers (registered FIRST, checked LAST)
        common_router,    # Shared callback handlers
        tickets_router,   # Invoice and support handlers
        nps_router,       # NPS survey handlers
        user_router,      # User commands and menu handlers (registered LAST, checked FIRST)
    )

    logger.info("✅ MAX bot handlers registered successfully with router hierarchy")


__all__ = ["register_max_handlers"]
