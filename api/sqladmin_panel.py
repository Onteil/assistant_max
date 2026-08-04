"""
SQLAdmin Panel Integration

Provides Django-like admin interface for SQLAlchemy models.
Accessible at /admin endpoint with authentication.
"""

import os
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse

from database.models import (
    User,
    Organization,
    GS_Key,
    Staff_Member,
    Manager_Assignment,
    Ticket,
    Message,
    File_Attachment,
    Action_Log,
    Calendar_Rule,
    Notification_Event,
    Broadcast,
    Broadcast_Delivery,
    API_Retry_Queue,
    Escalation,
    System_Settings,
    NPS_Response,
    MAX_Messenger_Data,
    TechSupportKnowledge,
)


class AdminAuth(AuthenticationBackend):
    """
    Simple authentication backend for SQLAdmin.
    
    Uses environment variables for credentials.
    In production, replace with proper authentication system.
    """
    
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        
        # Get credentials from environment
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin")
        
        if username == admin_username and password == admin_password:
            request.session.update({"token": "authenticated"})
            return True
        return False
    
    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True
    
    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        return token == "authenticated"


# ========== Model Views ==========

class UserAdmin(ModelView, model=User):
    """User management interface"""
    
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-user"
    category = "Пользователи"
    
    # Display configuration
    column_list = [
        User.id,
        User.max_user_id,
        User.tg_user_id,
        User.first_name,
        User.last_name,
        User.phone_number,
        User.email,
        User.registration_status,
        User.subscription_status,
        User.created_at,
    ]
    
    column_searchable_list = [
        User.phone_number,
        User.first_name,
        User.last_name,
        User.email,
    ]
    
    column_sortable_list = [
        User.id,
        User.created_at,
    ]
    
    column_filters = []
    
    # Relationship display configuration
    column_formatters = {
        User.organizations: lambda m, a: ", ".join([org.organization_name or org.inn for org in m.organizations]) if m.organizations else "—",
        User.gs_keys: lambda m, a: ", ".join([key.key_number for key in m.gs_keys]) if m.gs_keys else "—",
        User.tickets: lambda m, a: f"{len(m.tickets)} заявок" if m.tickets else "0 заявок",
        User.manager_assignments: lambda m, a: f"{len(m.manager_assignments)} назначений" if m.manager_assignments else "0 назначений",
        User.notification_events: lambda m, a: f"{len(m.notification_events)} событий" if m.notification_events else "0 событий",
        User.default_manager: lambda m, a: m.default_manager.full_name if m.default_manager else "—",
        User.broadcast_deliveries: lambda m, a: f"{len(m.broadcast_deliveries)} рассылок" if m.broadcast_deliveries else "0 рассылок",
        User.action_logs: lambda m, a: f"{len(m.action_logs)} действий" if m.action_logs else "0 действий",
        User.api_retries: lambda m, a: f"{len(m.api_retries)} повторов" if m.api_retries else "0 повторов",
        User.nps_responses: lambda m, a: f"{len(m.nps_responses)} ответов" if m.nps_responses else "0 ответов",
        User.max_messenger_data: lambda m, a: f"MAX ID: {m.max_messenger_data.max_user_id}" if m.max_messenger_data else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Form configuration
    form_columns = [
        User.max_user_id,
        User.tg_user_id,
        User.phone_number,
        User.email,
        User.first_name,
        User.last_name,
        User.middle_name,
        User.registration_status,
        User.subscription_status,
        User.subscription_end_date,
        User.notification_preferences,
    ]
    
    can_delete = False  # Prevent accidental deletion
    can_export = True


class OrganizationAdmin(ModelView, model=Organization):
    """Organization management interface"""
    
    name = "Организация"
    name_plural = "Организации"
    icon = "fa-solid fa-building"
    category = "Пользователи"
    
    column_list = [
        Organization.inn,
        Organization.organization_name,
        Organization.created_at,
    ]
    
    column_searchable_list = [
        Organization.inn,
        Organization.organization_name,
    ]
    
    column_sortable_list = [
        Organization.inn,
    ]
    
    # Relationship display
    column_formatters = {
        Organization.users: lambda m, a: f"{len(m.users)} пользователей" if m.users else "0 пользователей",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Form configuration
    form_columns = [
        Organization.inn,
        Organization.organization_name,
    ]
    
    can_export = True


class GS_KeyAdmin(ModelView, model=GS_Key):
    """GS Key management interface"""
    
    name = "GS Ключ"
    name_plural = "GS Ключи"
    icon = "fa-solid fa-key"
    category = "Пользователи"
    
    column_list = [
        GS_Key.id,
        GS_Key.key_number,
        GS_Key.user_id,
        GS_Key.created_at,
    ]
    
    column_searchable_list = [GS_Key.key_number]
    
    column_sortable_list = [
        GS_Key.id,
    ]
    
    # Display user info
    column_formatters = {
        GS_Key.user: lambda m, a: f"{m.user.first_name} {m.user.last_name} ({m.user.phone_number})" if m.user else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        GS_Key.user,
        GS_Key.tickets,
    ]
    
    can_export = True


class StaffMemberAdmin(ModelView, model=Staff_Member):
    """Staff member management interface"""
    
    name = "Сотрудник"
    name_plural = "Сотрудники"
    icon = "fa-solid fa-user-tie"
    category = "Персонал"
    
    column_list = [
        Staff_Member.id,
        Staff_Member.max_user_id,
        Staff_Member.tg_user_id,
        Staff_Member.full_name,
        Staff_Member.position,
        Staff_Member.staff_role,
        Staff_Member.is_active,
        Staff_Member.created_at,
    ]
    
    column_searchable_list = [Staff_Member.full_name, Staff_Member.position]
    
    column_sortable_list = [
        Staff_Member.id,
    ]
    
    column_filters = []
    
    # Display backup managers and relationships
    column_formatters = {
        Staff_Member.backup_manager_1: lambda m, a: m.backup_manager_1.full_name if m.backup_manager_1 else "—",
        Staff_Member.backup_manager_2: lambda m, a: m.backup_manager_2.full_name if m.backup_manager_2 else "—",
        Staff_Member.tickets_assigned: lambda m, a: f"{len(m.tickets_assigned)} заявок" if m.tickets_assigned else "0 заявок",
        Staff_Member.manager_assignments: lambda m, a: f"{len(m.manager_assignments)} назначений" if m.manager_assignments else "0 назначений",
        Staff_Member.backed_up_by_1: lambda m, a: f"{len(m.backed_up_by_1)} сотрудников" if m.backed_up_by_1 else "0 сотрудников",
        Staff_Member.backed_up_by_2: lambda m, a: f"{len(m.backed_up_by_2)} сотрудников" if m.backed_up_by_2 else "0 сотрудников",
        Staff_Member.broadcasts_created: lambda m, a: f"{len(m.broadcasts_created)} рассылок" if m.broadcasts_created else "0 рассылок",
        Staff_Member.managed_users: lambda m, a: f"{len(m.managed_users)} пользователей" if m.managed_users else "0 пользователей",
        Staff_Member.action_logs: lambda m, a: f"{len(m.action_logs)} действий" if m.action_logs else "0 действий",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        Staff_Member.tickets_assigned,
        Staff_Member.manager_assignments,
        Staff_Member.backup_manager_1,
        Staff_Member.backup_manager_2,
        Staff_Member.backed_up_by_1,
        Staff_Member.backed_up_by_2,
        Staff_Member.broadcasts_created,
        Staff_Member.managed_users,
        Staff_Member.action_logs,
    ]
    
    can_export = True


class ManagerAssignmentAdmin(ModelView, model=Manager_Assignment):
    """Manager assignment management interface"""
    
    name = "Назначение менеджера"
    name_plural = "Назначения менеджеров"
    icon = "fa-solid fa-user-check"
    category = "Персонал"
    
    column_list = [
        Manager_Assignment.id,
        Manager_Assignment.user_id,
        Manager_Assignment.organization_inn,
        Manager_Assignment.manager_id,
        Manager_Assignment.assigned_at,
    ]
    
    column_sortable_list = [
        Manager_Assignment.id,
    ]
    
    # Display related objects
    column_formatters = {
        Manager_Assignment.user: lambda m, a: f"{m.user.first_name} {m.user.last_name}" if m.user else "—",
        Manager_Assignment.organization: lambda m, a: m.organization.organization_name or m.organization.inn if m.organization else "—",
        Manager_Assignment.manager: lambda m, a: m.manager.full_name if m.manager else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        Manager_Assignment.user,
        Manager_Assignment.organization,
        Manager_Assignment.manager,
    ]
    
    can_export = True


class TicketAdmin(ModelView, model=Ticket):
    """Ticket management interface"""
    
    name = "Заявка"
    name_plural = "Заявки"
    icon = "fa-solid fa-ticket"
    category = "Заявки"
    
    column_list = [
        Ticket.id,
        Ticket.user_id,
        Ticket.ticket_type,
        Ticket.ticket_status,
        Ticket.assigned_staff_id,
        Ticket.created_at,
        Ticket.updated_at,
    ]
    
    column_searchable_list = [
        Ticket.description,
    ]
    
    column_sortable_list = [
        Ticket.id,
        Ticket.created_at,
        Ticket.updated_at,
    ]
    
    column_filters = []
    
    # Relationship display for both list and details
    column_formatters = {
        Ticket.user: lambda m, a: f"{m.user.first_name} {m.user.last_name} ({m.user.phone_number})" if m.user else "—",
        Ticket.assigned_staff: lambda m, a: m.assigned_staff.full_name if m.assigned_staff else "Не назначен",
        Ticket.organization: lambda m, a: m.organization.organization_name or m.organization.inn if m.organization else "—",
        Ticket.gs_keys: lambda m, a: ", ".join([key.key_number for key in m.gs_keys]) if m.gs_keys else "—",
        Ticket.messages: lambda m, a: f"{len(m.messages)} сообщений" if m.messages else "0 сообщений",
        Ticket.file_attachments: lambda m, a: f"{len(m.file_attachments)} файлов" if m.file_attachments else "0 файлов",
        Ticket.action_logs: lambda m, a: f"{len(m.action_logs)} действий" if m.action_logs else "0 действий",
        Ticket.notification_events: lambda m, a: f"{len(m.notification_events)} событий" if m.notification_events else "0 событий",
        Ticket.escalations: lambda m, a: f"{len(m.escalations)} эскалаций" if m.escalations else "0 эскалаций",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Form configuration - exclude relationships from form
    form_excluded_columns = [
        Ticket.user,
        Ticket.assigned_staff,
        Ticket.organization,
        Ticket.gs_keys,
        Ticket.messages,
        Ticket.file_attachments,
        Ticket.action_logs,
        Ticket.notification_events,
        Ticket.escalations,
    ]
    
    can_export = True


class MessageAdmin(ModelView, model=Message):
    """Message management interface"""
    
    name = "Сообщение"
    name_plural = "Сообщения"
    icon = "fa-solid fa-message"
    category = "Сообщения"
    
    column_list = [
        Message.id,
        Message.ticket_id,
        Message.sender_type,
        Message.message_type,
        Message.message_text,
        Message.sent_at,
    ]
    
    column_searchable_list = [Message.message_text]
    
    column_sortable_list = [
        Message.id,
    ]
    
    column_filters = []
    
    # Display ticket info and file attachments
    column_formatters = {
        Message.ticket: lambda m, a: f"Заявка #{m.ticket.id} ({m.ticket.ticket_type.value})" if m.ticket else "—",
        Message.file_attachments: lambda m, a: f"{len(m.file_attachments)} файлов" if m.file_attachments else "0 файлов",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        Message.ticket,
        Message.file_attachments,
    ]
    
    can_delete = False
    can_export = True


class FileAttachmentAdmin(ModelView, model=File_Attachment):
    """File attachment management interface"""
    
    name = "Файл"
    name_plural = "Файлы"
    icon = "fa-solid fa-file"
    category = "Сообщения"
    
    column_list = [
        File_Attachment.id,
        File_Attachment.message_id,
        File_Attachment.file_type,
        File_Attachment.file_name,
        File_Attachment.file_size,
        File_Attachment.uploaded_at,
    ]
    
    column_searchable_list = [File_Attachment.file_name]
    
    column_sortable_list = [
        File_Attachment.id,
        File_Attachment.file_size,
    ]
    
    column_filters = []
    
    # Display message info
    column_formatters = {
        File_Attachment.message: lambda m, a: f"Сообщение #{m.message.id}" if m.message else "—",
        File_Attachment.ticket: lambda m, a: f"Заявка #{m.ticket.id}" if m.ticket else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        File_Attachment.message,
        File_Attachment.ticket,
    ]
    
    can_export = True


class ActionLogAdmin(ModelView, model=Action_Log):
    """Action log management interface"""
    
    name = "Лог действий"
    name_plural = "Логи действий"
    icon = "fa-solid fa-list"
    category = "Система"
    
    column_list = [
        Action_Log.id,
        Action_Log.user_id,
        Action_Log.staff_id,
        Action_Log.action_type,
        Action_Log.action_timestamp,
    ]
    
    column_sortable_list = [
        Action_Log.id,
    ]
    
    column_filters = []
    
    # Display related objects
    column_formatters = {
        Action_Log.ticket: lambda m, a: f"Заявка #{m.ticket.id}" if m.ticket else "—",
        Action_Log.user: lambda m, a: f"{m.user.first_name} {m.user.last_name}" if m.user else "—",
        Action_Log.staff: lambda m, a: m.staff.full_name if m.staff else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        Action_Log.ticket,
        Action_Log.user,
        Action_Log.staff,
    ]
    
    can_create = False
    can_edit = False
    can_delete = False
    can_export = True


class CalendarRuleAdmin(ModelView, model=Calendar_Rule):
    """Calendar rule management interface"""
    
    name = "Правило календаря"
    name_plural = "Правила календаря"
    icon = "fa-solid fa-calendar"
    category = "Система"
    
    column_list = [
        Calendar_Rule.id,
        Calendar_Rule.work_mode,
        Calendar_Rule.start_date,
        Calendar_Rule.end_date,
        Calendar_Rule.work_start_time,
        Calendar_Rule.work_end_time,
        Calendar_Rule.rule_priority,
    ]
    
    column_sortable_list = [
        Calendar_Rule.id,
        Calendar_Rule.rule_priority,
    ]
    
    column_filters = []
    
    can_export = True


class NotificationEventAdmin(ModelView, model=Notification_Event):
    """Notification event management interface"""
    
    name = "Событие уведомления"
    name_plural = "События уведомлений"
    icon = "fa-solid fa-bell"
    category = "Уведомления"
    
    column_list = [
        Notification_Event.id,
        Notification_Event.event_type,
        Notification_Event.event_status,
        Notification_Event.scheduled_for,
        Notification_Event.sent_at,
    ]
    
    column_sortable_list = [
        Notification_Event.id,
    ]
    
    column_filters = []
    
    # Display related objects
    column_formatters = {
        Notification_Event.user: lambda m, a: f"{m.user.first_name} {m.user.last_name}" if m.user else "—",
        Notification_Event.related_ticket: lambda m, a: f"Заявка #{m.related_ticket.id}" if m.related_ticket else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        Notification_Event.user,
        Notification_Event.related_ticket,
    ]
    
    can_export = True


class BroadcastAdmin(ModelView, model=Broadcast):
    """Broadcast management interface"""
    
    name = "Рассылка"
    name_plural = "Рассылки"
    icon = "fa-solid fa-bullhorn"
    category = "Уведомления"
    
    column_list = [
        Broadcast.id,
        Broadcast.broadcast_status,
        Broadcast.created_by_staff_id,
        Broadcast.target_user_count,
        Broadcast.delivered_count,
        Broadcast.created_at,
        Broadcast.sent_at,
    ]
    
    column_sortable_list = [
        Broadcast.id,
    ]
    
    column_filters = []
    
    # Display related objects
    column_formatters = {
        Broadcast.created_by: lambda m, a: m.created_by.full_name if m.created_by else "—",
        Broadcast.deliveries: lambda m, a: f"{len(m.deliveries)} доставок" if m.deliveries else "0 доставок",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        Broadcast.created_by,
        Broadcast.deliveries,
    ]
    
    can_export = True


class BroadcastDeliveryAdmin(ModelView, model=Broadcast_Delivery):
    """Broadcast delivery management interface"""
    
    name = "Доставка рассылки"
    name_plural = "Доставки рассылок"
    icon = "fa-solid fa-paper-plane"
    category = "Уведомления"
    
    column_list = [
        Broadcast_Delivery.id,
        Broadcast_Delivery.broadcast_id,
        Broadcast_Delivery.user_id,
        Broadcast_Delivery.delivery_status,
        Broadcast_Delivery.delivered_at,
    ]
    
    column_sortable_list = [
        Broadcast_Delivery.id,
    ]
    
    column_filters = []
    
    # Display related objects
    column_formatters = {
        Broadcast_Delivery.broadcast: lambda m, a: f"Рассылка #{m.broadcast.id}" if m.broadcast else "—",
        Broadcast_Delivery.user: lambda m, a: f"{m.user.first_name} {m.user.last_name}" if m.user else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        Broadcast_Delivery.broadcast,
        Broadcast_Delivery.user,
    ]
    
    can_create = False
    can_edit = False
    can_export = True


class APIRetryQueueAdmin(ModelView, model=API_Retry_Queue):
    """API retry queue management interface"""
    
    name = "Очередь повторов API"
    name_plural = "Очереди повторов API"
    icon = "fa-solid fa-rotate"
    category = "Система"
    
    column_list = [
        API_Retry_Queue.id,
        API_Retry_Queue.operation,
        API_Retry_Queue.status,
        API_Retry_Queue.attempt_count,
        API_Retry_Queue.next_retry_at,
        API_Retry_Queue.created_at,
    ]
    
    column_sortable_list = [
        API_Retry_Queue.id,
    ]
    
    column_filters = []
    
    # Display related objects
    column_formatters = {
        API_Retry_Queue.user: lambda m, a: f"{m.user.first_name} {m.user.last_name}" if m.user else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        API_Retry_Queue.user,
    ]
    
    can_export = True


class EscalationAdmin(ModelView, model=Escalation):
    """Escalation management interface"""
    
    name = "Эскалация"
    name_plural = "Эскалации"
    icon = "fa-solid fa-arrow-up"
    category = "Заявки"
    
    column_list = [
        Escalation.id,
        Escalation.ticket_id,
        Escalation.escalation_type,
        Escalation.is_resolved,
        Escalation.created_at,
        Escalation.resolved_at,
    ]
    
    column_sortable_list = [
        Escalation.id,
    ]
    
    column_filters = []
    
    # Display related objects
    column_formatters = {
        Escalation.ticket: lambda m, a: f"Заявка #{m.ticket.id} ({m.ticket.ticket_type.value})" if m.ticket else "—",
        Escalation.resolved_by: lambda m, a: m.resolved_by.full_name if m.resolved_by else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        Escalation.ticket,
        Escalation.resolved_by,
    ]
    
    can_export = True


class SystemSettingsAdmin(ModelView, model=System_Settings):
    """System settings management interface"""
    
    name = "Настройка системы"
    name_plural = "Настройки системы"
    icon = "fa-solid fa-gear"
    category = "Система"
    
    column_list = [
        System_Settings.id,
        System_Settings.key,
        System_Settings.category,
        System_Settings.data_type,
        System_Settings.value,
        System_Settings.updated_at,
    ]
    
    column_searchable_list = [
        System_Settings.key,
        System_Settings.description,
    ]
    
    column_sortable_list = [
        System_Settings.id,
    ]
    
    column_filters = []
    
    can_export = True


class NPSResponseAdmin(ModelView, model=NPS_Response):
    """NPS response management interface"""
    
    name = "NPS Ответ"
    name_plural = "NPS Ответы"
    icon = "fa-solid fa-star"
    category = "Опросы"
    
    column_list = [
        NPS_Response.id,
        NPS_Response.user_id,
        NPS_Response.survey_type,
        NPS_Response.rating,
        NPS_Response.responded_at,
        NPS_Response.created_at,
    ]
    
    column_sortable_list = [
        NPS_Response.id,
        NPS_Response.rating,
    ]
    
    column_filters = []
    
    # Display related objects
    column_formatters = {
        NPS_Response.user: lambda m, a: f"{m.user.first_name} {m.user.last_name}" if m.user else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude relationships from form
    form_excluded_columns = [
        NPS_Response.user,
    ]
    
    can_create = False
    can_edit = False
    can_delete = False
    can_export = True


class MAXMessengerDataAdmin(ModelView, model=MAX_Messenger_Data):
    """MAX messenger data management interface"""
    
    name = "MAX Данные"
    name_plural = "MAX Данные"
    icon = "fa-solid fa-database"
    category = "Система"
    
    column_list = [
        MAX_Messenger_Data.id,
        MAX_Messenger_Data.user_id,
        MAX_Messenger_Data.max_user_id,
        MAX_Messenger_Data.max_chat_id,
        MAX_Messenger_Data.created_at,
        MAX_Messenger_Data.updated_at,
    ]
    
    column_sortable_list = [
        MAX_Messenger_Data.id,
    ]
    
    # Display user info instead of object reference
    column_formatters = {
        MAX_Messenger_Data.user: lambda m, a: f"{m.user.first_name} {m.user.last_name} ({m.user.phone_number})" if m.user else "—",
    }
    
    # Apply formatters to details page too
    column_formatters_detail = column_formatters
    
    # Exclude user relationship from form
    form_excluded_columns = [
        MAX_Messenger_Data.user,
    ]
    
    can_export = True


class TechSupportKnowledgeAdmin(ModelView, model=TechSupportKnowledge):
    """Technical support knowledge base management interface"""

    name = "База ошибки"
    name_plural = "База ошибок"
    icon = "fa-solid fa-book-medical"
    category = "Техподдержка"

    column_list = [
        TechSupportKnowledge.id,
        TechSupportKnowledge.title,
        TechSupportKnowledge.is_active,
        TechSupportKnowledge.source,
        TechSupportKnowledge.created_at,
        TechSupportKnowledge.updated_at,
    ]

    column_searchable_list = [
        TechSupportKnowledge.title,
        TechSupportKnowledge.error_text,
        TechSupportKnowledge.solution_text,
        TechSupportKnowledge.keywords,
    ]

    column_sortable_list = [
        TechSupportKnowledge.id,
        TechSupportKnowledge.created_at,
        TechSupportKnowledge.updated_at,
    ]

    form_columns = [
        TechSupportKnowledge.title,
        TechSupportKnowledge.error_text,
        TechSupportKnowledge.solution_text,
        TechSupportKnowledge.keywords,
        TechSupportKnowledge.screenshot_url,
        TechSupportKnowledge.source,
        TechSupportKnowledge.is_active,
    ]

    can_export = True


def setup_admin(app, engine):
    """
    Setup SQLAdmin with all model views.
    
    Args:
        app: FastAPI application instance
        engine: SQLAlchemy async engine
    
    Returns:
        Admin: Configured SQLAdmin instance
    """
    
    # Get secret key from environment
    secret_key = os.getenv("ADMIN_SECRET_KEY")
    if not secret_key:
        import secrets
        secret_key = secrets.token_urlsafe(32)
        print(f"WARNING: ADMIN_SECRET_KEY not set. Using generated key: {secret_key}")
        print("Add this to your .env file: ADMIN_SECRET_KEY=" + secret_key)
    
    # Create authentication backend
    authentication_backend = AdminAuth(secret_key=secret_key)
    
    # Initialize admin
    admin = Admin(
        app,
        engine,
        title="i-TAT Bot Admin",
        base_url="/admin",
        authentication_backend=authentication_backend,
    )
    
    # Register all model views
    admin.add_view(UserAdmin)
    admin.add_view(OrganizationAdmin)
    admin.add_view(GS_KeyAdmin)
    admin.add_view(StaffMemberAdmin)
    admin.add_view(ManagerAssignmentAdmin)
    admin.add_view(TicketAdmin)
    admin.add_view(MessageAdmin)
    admin.add_view(FileAttachmentAdmin)
    admin.add_view(ActionLogAdmin)
    admin.add_view(CalendarRuleAdmin)
    admin.add_view(NotificationEventAdmin)
    admin.add_view(BroadcastAdmin)
    admin.add_view(BroadcastDeliveryAdmin)
    admin.add_view(APIRetryQueueAdmin)
    admin.add_view(EscalationAdmin)
    admin.add_view(SystemSettingsAdmin)
    admin.add_view(NPSResponseAdmin)
    admin.add_view(MAXMessengerDataAdmin)
    admin.add_view(TechSupportKnowledgeAdmin)
    
    return admin
