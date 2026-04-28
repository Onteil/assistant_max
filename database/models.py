"""
Database models for I-TAT Telegram bot dispatcher system.
SQLAlchemy ORM models with async support.
"""

import datetime
import enum

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Table, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

# ========== Base and Mixins ==========

Base = declarative_base()


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps in Moscow timezone"""
    from utils.timezone_helpers import get_moscow_now_naive
    
    created_at = Column(DateTime, default=get_moscow_now_naive, nullable=False)
    updated_at = Column(DateTime, onupdate=get_moscow_now_naive, nullable=True)


# ========== Enum Definitions ==========


class RegistrationStatus(enum.Enum):
    """User registration status values"""
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    UNDER_REVIEW = "under_review"


class SubscriptionStatus(enum.Enum):
    """User subscription status values"""
    ACTIVE = "active"
    EXPIRED = "expired"
    NONE = "none"


class KeyConflictStatus(enum.Enum):
    """GS_Key conflict status values"""
    NONE = "NONE"
    PENDING_REVIEW = "PENDING_REVIEW"
    RESOLVED = "RESOLVED"


class StaffRole(enum.Enum):
    """Staff member role values"""
    MANAGER = "manager"
    TECHNICAL_SUPPORT = "technical_support"
    DUTY_ENGINEER = "duty_engineer"
    ADMINISTRATOR = "administrator"


class TicketType(enum.Enum):
    """Ticket type values"""
    INVOICE = "invoice"
    TECHNICAL_SUPPORT = "technical_support"
    CONSULTATION = "consultation"
    RENEWAL = "renewal"
    PHONE_CHANGE = "phone_change"
    KEY_CONFLICT = "key_conflict"


class TicketStatus(enum.Enum):
    """Ticket status values"""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    WAITING_CLIENT = "waiting_client"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class DeliveryMethod(enum.Enum):
    """Ticket delivery method values"""
    TELEGRAM = "telegram"
    EMAIL = "email"
    NONE = "none"


class SenderType(enum.Enum):
    """Message sender type values"""
    USER = "user"
    STAFF = "staff"
    SYSTEM = "system"


class MessageType(enum.Enum):
    """Message type values"""
    TEXT = "text"
    PHOTO = "photo"
    DOCUMENT = "document"
    VOICE = "voice"
    VIDEO = "video"
    AUDIO = "audio"
    VIDEO_NOTE = "video_note"
    SYSTEM_NOTIFICATION = "system_notification"


class FileType(enum.Enum):
    """File attachment type values"""
    PDF = "pdf"
    IMAGE = "image"
    DOCUMENT = "document"
    OTHER = "other"


class UploaderType(enum.Enum):
    """File uploader type values"""
    USER = "user"
    STAFF = "staff"


class ActionType(enum.Enum):
    """Action log type values"""
    TICKET_CREATED = "ticket_created"
    TICKET_ASSIGNED = "ticket_assigned"
    TICKET_TAKEN = "ticket_taken"
    TICKET_ESCALATED = "ticket_escalated"
    REMINDER_SENT = "reminder_sent"
    ESCALATED = "escalated"
    TICKET_CLOSED = "ticket_closed"
    STATUS_CHANGED = "status_changed"
    MESSAGE_SENT = "message_sent"
    FILE_UPLOADED = "file_uploaded"
    USER_REGISTERED = "user_registered"
    KEY_CONFLICT_DETECTED = "key_conflict_detected"
    API_RETRY_FAILED = "api_retry_failed"
    STAFF_ADDED = "staff_added"
    STAFF_UPDATED = "staff_updated"
    STAFF_DEACTIVATED = "staff_deactivated"
    STAFF_ACTIVATED = "staff_activated"
    CLIENTS_TRANSFERRED = "clients_transferred"
    CALENDAR_RULE_CREATED = "calendar_rule_created"
    CALENDAR_RULE_DELETED = "calendar_rule_deleted"
    CALENDAR_PERIOD_CLEARED = "calendar_period_cleared"
    BROADCAST_SENT = "broadcast_sent"
    SETTING_CHANGED = "setting_changed"
    SETTING_RESET = "setting_reset"
    PHONE_CHANGE_REQUESTED = "phone_change_requested"
    PHONE_CHANGE_APPROVED = "phone_change_approved"
    PHONE_CHANGE_REJECTED = "phone_change_rejected"


class WorkMode(enum.Enum):
    """Calendar rule work mode values"""
    REGULAR = "regular"
    EXTENDED = "extended"
    NON_WORKING = "non_working"


class EventType(enum.Enum):
    """Notification event type values"""
    RENEWAL_REMINDER_30 = "renewal_reminder_30"
    RENEWAL_REMINDER_7 = "renewal_reminder_7"
    NPS_SURVEY = "nps_survey"


class EventStatus(enum.Enum):
    """Notification event status values"""
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RetryStatus(enum.Enum):
    """API retry queue status values"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class BroadcastStatus(enum.Enum):
    """Broadcast status values"""
    DRAFT = "draft"
    SENDING = "sending"
    COMPLETED = "completed"
    FAILED = "failed"


class DeliveryStatus(enum.Enum):
    """Broadcast delivery status values"""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class EscalationType(enum.Enum):
    """Escalation type values"""
    REMINDER_10MIN = "reminder_10min"
    ESCALATION_20MIN = "escalation_20min"


class SurveyType(enum.Enum):
    """NPS survey type values"""
    LOYALTY = "loyalty"  # Post-payment survey
    SERVICE_QUALITY = "service_quality"  # Post-support survey


class ResolutionAction(enum.Enum):
    """Escalation resolution action values"""
    REASSIGNED = "reassigned"
    TAKEN_OVER = "taken_over"
    CONTACTED = "contacted"
    AUTO_RESOLVED = "auto_resolved"


class SettingDataType(enum.Enum):
    """Data types for system settings"""
    INTEGER = "integer"
    JSON = "json"
    CHAT_ID = "chat_id"
    USER_ID = "user_id"


class SettingCategory(enum.Enum):
    """Categories for organizing settings"""
    TIMEOUTS = "timeouts"
    ESCALATION = "escalation"
    DUTY_SUPPORT = "duty_support"
    NPS = "nps"
    RENEWAL_REMINDERS = "renewal_reminders"



# ========== Association Tables ==========
# These must be defined before the models that reference them


user_organizations = Table(
    "user_organizations",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=False),
    Column("user_id", BigInteger, ForeignKey("users.id"), nullable=False),
    Column("organization_inn", String(12), ForeignKey("organizations.inn"), nullable=False),
    Column("added_at", DateTime, default=datetime.datetime.utcnow, nullable=False),
    UniqueConstraint("user_id", "organization_inn", name="uq_user_organization")
)


ticket_keys = Table(
    "ticket_keys",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True, nullable=False),
    Column("ticket_id", Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
    Column("key_id", Integer, ForeignKey("gs_keys.id"), nullable=False),
    Column("added_at", DateTime, default=datetime.datetime.utcnow, nullable=False),
    UniqueConstraint("ticket_id", "key_id", name="uq_ticket_key")
)


# ========== Core Identity Models ==========


class MAX_Messenger_Data(Base, TimestampMixin):
    """
    MAX messenger data - stores MAX user_id to chat_id mapping.
    
    MAX API requires chat_id for sending messages, not user_id.
    This table maintains the relationship between user, max_user_id, and max_chat_id.
    
    Requirements: 15.3
    """
    __tablename__ = "max_messenger_data"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Foreign key to users table
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # MAX messenger identifiers
    max_user_id = Column(BigInteger, nullable=False, unique=True, index=True)
    max_chat_id = Column(BigInteger, nullable=False, index=True)
    
    # Timestamps inherited from TimestampMixin: created_at, updated_at
    
    # Relationships
    user = relationship("User", back_populates="max_messenger_data")


class User(Base, TimestampMixin):
    """
    User model - stores client profiles with authentication and subscription data.
    
    Supports multiple messengers (Telegram, MAX).
    
    Requirements: 1.1-1.10
    """
    __tablename__ = "users"
    
    # Primary key - internal bot database ID
    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    
    # Messenger IDs (nullable, unique, indexed)
    tg_user_id = Column(BigInteger, unique=True, nullable=True, index=True)
    max_user_id = Column(BigInteger, unique=True, nullable=True, index=True)
    
    # Contact information
    phone_number = Column(String(15), unique=True, nullable=False)
    email = Column(String(255), nullable=True)
    username = Column(String(32), nullable=True)
    first_name = Column(String(64), nullable=True)
    last_name = Column(String(64), nullable=True)
    middle_name = Column(String(64), nullable=True)  # Отчество (optional)
    full_name = Column(String(128), nullable=True)
    
    # Status fields
    registration_status = Column(
        Enum(RegistrationStatus),
        default=RegistrationStatus.PENDING,
        nullable=False
    )
    subscription_status = Column(
        Enum(SubscriptionStatus),
        default=SubscriptionStatus.NONE,
        nullable=False
    )
    
    # Subscription tracking
    subscription_end_date = Column(DateTime, nullable=True)
    
    # Preferences
    notification_preferences = Column(Boolean, default=True, nullable=False)
    
    # Manager assignment (references staff internal ID)
    default_manager_id = Column(BigInteger, ForeignKey("staff_members.id"), nullable=True)
    
    # NPS tracking
    last_nps_sent_at = Column(DateTime, nullable=True)
    
    # Timestamps inherited from TimestampMixin: created_at, updated_at
    
    # Relationships
    organizations = relationship(
        "Organization",
        secondary=user_organizations,
        back_populates="users"
    )
    gs_keys = relationship(
        "GS_Key",
        back_populates="user"
    )
    tickets = relationship(
        "Ticket",
        back_populates="user"
    )
    manager_assignments = relationship(
        "Manager_Assignment",
        back_populates="user"
    )
    notification_events = relationship(
        "Notification_Event",
        back_populates="user"
    )
    default_manager = relationship(
        "Staff_Member",
        foreign_keys=[default_manager_id],
        back_populates="managed_users"
    )
    broadcast_deliveries = relationship(
        "Broadcast_Delivery",
        back_populates="user"
    )
    action_logs = relationship(
        "Action_Log",
        back_populates="user"
    )
    api_retries = relationship(
        "API_Retry_Queue",
        back_populates="user"
    )
    nps_responses = relationship(
        "NPS_Response",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    max_messenger_data = relationship(
        "MAX_Messenger_Data",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    def __str__(self) -> str:
        """Custom string representation for admin select fields"""
        name = self.full_name or f"{self.first_name or ''} {self.last_name or ''}".strip() or "Без имени"
        phone = self.phone_number or "N/A"
        max_id = self.max_user_id or "N/A"
        reg_date = self.created_at.strftime('%d.%m.%Y') if self.created_at else "N/A"
        
        # Add status indicator
        status_icon = {
            RegistrationStatus.ACTIVE: "✓",
            RegistrationStatus.PENDING: "⏳",
            RegistrationStatus.UNDER_REVIEW: "🔍",
            RegistrationStatus.REJECTED: "✗"
        }.get(self.registration_status, "?")
        
        return f"{status_icon} {name} | {phone} | MAX: {max_id} | Рег: {reg_date}"


class Organization(Base):
    """
    Organization model - stores legal entities identified by INN.
    
    Requirements: 2.1, 2.2, 2.3
    """
    __tablename__ = "organizations"
    
    # Primary key
    inn = Column(String(12), primary_key=True, nullable=False)
    
    # Organization details
    organization_name = Column(String(256), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    users = relationship(
        "User",
        secondary=user_organizations,
        back_populates="organizations"
    )
    tickets = relationship(
        "Ticket",
        back_populates="organization"
    )
    manager_assignments = relationship(
        "Manager_Assignment",
        back_populates="organization"
    )
    
    def __str__(self) -> str:
        """Custom string representation for admin select fields"""
        name = self.organization_name or "Без названия"
        return f"{name} | ИНН: {self.inn}"


class GS_Key(Base):
    """
    GS_Key model - stores GRAND-Smeta license keys with conflict tracking.
    
    Requirements: 2.5, 2.6, 2.7, 2.8, 2.9
    """
    __tablename__ = "gs_keys"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Key identification
    key_number = Column(String(32), unique=True, nullable=False)
    
    # Owner reference
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    
    # Conflict tracking
    conflict_status = Column(
        Enum(KeyConflictStatus),
        default=KeyConflictStatus.NONE,
        nullable=False
    )
    conflict_reported_at = Column(DateTime, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship(
        "User",
        back_populates="gs_keys"
    )
    tickets = relationship(
        "Ticket",
        secondary=ticket_keys,
        back_populates="gs_keys"
    )
    
    def __str__(self) -> str:
        """Custom string representation for admin select fields"""
        user_name = f"{self.user.first_name} {self.user.last_name}" if self.user else "N/A"
        conflict = "⚠️" if self.conflict_status != KeyConflictStatus.NONE else "✓"
        return f"Ключ: {self.key_number} | Владелец: {user_name} | {conflict}"


class Staff_Member(Base, TimestampMixin):
    """
    Staff_Member model - stores internal employees with roles and backup assignments.
    
    Supports multiple messengers (Telegram, MAX).
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
    """
    __tablename__ = "staff_members"
    
    # Primary key - internal bot database ID
    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    
    # Messenger IDs (nullable, unique, indexed)
    tg_user_id = Column(BigInteger, unique=True, nullable=True, index=True)
    max_user_id = Column(BigInteger, unique=True, nullable=True, index=True)
    max_chat_id = Column(BigInteger, nullable=True, index=True)
    
    # Staff details
    full_name = Column(String(128), nullable=False)
    position = Column(String(128), nullable=False)
    staff_role = Column(Enum(StaffRole), nullable=False)
    
    # Specialist flags
    is_estimate_tech_specialist = Column(Boolean, default=False, nullable=False, comment="Сметный тех. специалист — получает заявки типа Консультация")
    
    # Soft delete flag
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Availability flag — can be toggled by the employee themselves
    # False means the employee is temporarily unavailable (sick, day off, etc.)
    # and should not receive new ticket assignments
    is_working_today = Column(Boolean, default=True, nullable=False, comment="Сотрудник доступен сегодня — если False, не получает новые заявки")
    
    # Self-referential backup manager references
    backup_manager_1_id = Column(BigInteger, ForeignKey("staff_members.id"), nullable=True)
    backup_manager_2_id = Column(BigInteger, ForeignKey("staff_members.id"), nullable=True)
    
    # Timestamps inherited from TimestampMixin: created_at, updated_at
    
    # Relationships
    tickets_assigned = relationship(
        "Ticket",
        foreign_keys="Ticket.assigned_staff_id",
        back_populates="assigned_staff"
    )
    manager_assignments = relationship(
        "Manager_Assignment",
        back_populates="manager"
    )
    backup_manager_1 = relationship(
        "Staff_Member",
        foreign_keys=[backup_manager_1_id],
        remote_side="Staff_Member.id",
        back_populates="backed_up_by_1"
    )
    backup_manager_2 = relationship(
        "Staff_Member",
        foreign_keys=[backup_manager_2_id],
        remote_side="Staff_Member.id",
        back_populates="backed_up_by_2"
    )
    backed_up_by_1 = relationship(
        "Staff_Member",
        foreign_keys=[backup_manager_1_id],
        back_populates="backup_manager_1"
    )
    backed_up_by_2 = relationship(
        "Staff_Member",
        foreign_keys=[backup_manager_2_id],
        back_populates="backup_manager_2"
    )
    broadcasts_created = relationship(
        "Broadcast",
        back_populates="created_by"
    )
    managed_users = relationship(
        "User",
        foreign_keys="User.default_manager_id",
        back_populates="default_manager"
    )
    action_logs = relationship(
        "Action_Log",
        back_populates="staff"
    )
    
    def __str__(self) -> str:
        """Custom string representation for admin select fields"""
        role = self.staff_role.value if self.staff_role else "N/A"
        position = self.position or "N/A"
        max_id = self.max_user_id or "N/A"
        status = "✓" if self.is_active else "✗"
        return f"{self.full_name} | {position} ({role}) | MAX: {max_id} | {status}"


# ========== Assignment Models ==========


class Manager_Assignment(Base):
    """
    Manager_Assignment model - maps user-organization pairs to assigned managers.
    
    Requirements: 4.1, 4.2, 4.3, 4.5, 4.6
    """
    __tablename__ = "manager_assignments"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # User-organization pair
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    organization_inn = Column(String(12), ForeignKey("organizations.inn"), nullable=False)
    
    # Assigned manager
    manager_id = Column(BigInteger, ForeignKey("staff_members.id"), nullable=False)
    
    # Timestamp
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Unique constraint on user-organization pair
    __table_args__ = (
        UniqueConstraint("user_id", "organization_inn", name="uq_user_org_assignment"),
    )
    
    # Relationships
    user = relationship(
        "User",
        back_populates="manager_assignments"
    )
    organization = relationship(
        "Organization",
        back_populates="manager_assignments"
    )
    manager = relationship(
        "Staff_Member",
        back_populates="manager_assignments"
    )


# ========== Ticket and Messaging Models ==========


class Ticket(Base, TimestampMixin):
    """
    Ticket model - stores customer requests with status and assignment tracking.
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 5.14
    """
    __tablename__ = "tickets"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Ticket classification
    ticket_type = Column(Enum(TicketType), nullable=False)
    ticket_status = Column(
        Enum(TicketStatus),
        default=TicketStatus.NEW,
        nullable=False
    )
    
    # Foreign keys
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assigned_staff_id = Column(BigInteger, ForeignKey("staff_members.id", ondelete="SET NULL"), nullable=True)
    organization_inn = Column(String(12), ForeignKey("organizations.inn"), nullable=True)
    
    # Ticket details
    description = Column(String, nullable=True)
    
    # Phone change specific fields
    old_phone = Column(String(20), nullable=True, comment="Old phone number for phone change requests")
    new_phone = Column(String(20), nullable=True, comment="New phone number for phone change requests")
    resolution_comment = Column(String, nullable=True, comment="Resolution comment for closed tickets")
    
    # Delivery configuration
    delivery_method = Column(
        Enum(DeliveryMethod),
        default=DeliveryMethod.TELEGRAM,
        nullable=False
    )
    delivery_email = Column(String(256), nullable=True)
    
    # Escalation tracking
    escalation_level = Column(Integer, default=0, nullable=False)
    escalated_at = Column(DateTime, nullable=True)
    escalation_task_reminder_id = Column(String(255), nullable=True, comment="ID Celery задачи напоминания")
    escalation_task_escalation_id = Column(String(255), nullable=True, comment="ID Celery задачи эскалации")
    is_escalated = Column(Boolean, default=False, nullable=False, index=True, comment="Флаг эскалированной заявки")
    
    # Timestamps
    closed_at = Column(DateTime, nullable=True)
    queue_notification_sent_at = Column(
        DateTime, nullable=True,
        comment="Timestamp when queue notification was sent (prevents duplicate notifications)"
    )
    # created_at and updated_at inherited from TimestampMixin
    
    # Relationships
    user = relationship(
        "User",
        back_populates="tickets"
    )
    assigned_staff = relationship(
        "Staff_Member",
        foreign_keys=[assigned_staff_id],
        back_populates="tickets_assigned"
    )
    organization = relationship(
        "Organization",
        back_populates="tickets"
    )
    gs_keys = relationship(
        "GS_Key",
        secondary=ticket_keys,
        back_populates="tickets"
    )
    messages = relationship(
        "Message",
        back_populates="ticket",
        cascade="all, delete-orphan"
    )
    file_attachments = relationship(
        "File_Attachment",
        back_populates="ticket",
        cascade="all, delete-orphan"
    )
    action_logs = relationship(
        "Action_Log",
        back_populates="ticket"
    )
    notification_events = relationship(
        "Notification_Event",
        back_populates="related_ticket"
    )
    escalations = relationship(
        "Escalation",
        back_populates="ticket",
        cascade="all, delete-orphan"
    )
    
    def __str__(self) -> str:
        """Custom string representation for admin select fields"""
        ticket_type = self.ticket_type.value if self.ticket_type else "N/A"
        status = self.ticket_status.value if self.ticket_status else "N/A"
        user_name = f"{self.user.first_name} {self.user.last_name}" if self.user else "N/A"
        created = self.created_at.strftime('%d.%m.%Y %H:%M') if self.created_at else "N/A"
        return f"#{self.id} | {ticket_type} | {status} | {user_name} | {created}"


class Message(Base):
    """
    Message model - stores conversation history within tickets.
    
    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9
    """
    __tablename__ = "messages"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Ticket reference
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    
    # Sender tracking
    sender_type = Column(Enum(SenderType), nullable=False)
    sender_id = Column(BigInteger, nullable=True)
    
    # Message content
    message_text = Column(String, nullable=False)
    message_type = Column(Enum(MessageType), nullable=False)
    
    # Timestamp - use Moscow timezone
    from utils.timezone_helpers import get_moscow_now_naive
    sent_at = Column(DateTime, default=get_moscow_now_naive, nullable=False)
    
    # Relationships
    ticket = relationship(
        "Ticket",
        back_populates="messages"
    )
    file_attachments = relationship(
        "File_Attachment",
        back_populates="message"
    )


class File_Attachment(Base):
    """
    File_Attachment model - stores references to files uploaded to Telegram or MAX.
    
    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10
    """
    __tablename__ = "file_attachments"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Ticket and message references
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    
    # File metadata
    file_type = Column(Enum(FileType), nullable=False)
    telegram_file_id = Column(Text, nullable=False)
    file_name = Column(String(256), nullable=True)
    file_size = Column(Integer, nullable=True)
    
    # MAX messenger file URL (used when file was uploaded via MAX bot)
    max_file_url = Column(Text, nullable=True)
    
    # Uploader tracking
    uploader_id = Column(BigInteger, nullable=False)
    uploader_type = Column(Enum(UploaderType), nullable=False)
    
    # Timestamp
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    ticket = relationship(
        "Ticket",
        back_populates="file_attachments"
    )
    message = relationship(
        "Message",
        back_populates="file_attachments"
    )


# ========== Audit and Scheduling Models ==========


class Action_Log(Base):
    """
    Action_Log model - audit trail for all significant system actions.
    
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8
    """
    __tablename__ = "action_logs"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Action classification
    action_type = Column(Enum(ActionType), nullable=False)
    
    # Optional foreign keys for related entities
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    staff_id = Column(BigInteger, ForeignKey("staff_members.id"), nullable=True)
    
    # Action details as JSON
    action_details = Column(JSON, nullable=True)
    
    # Timestamp
    action_timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    ticket = relationship(
        "Ticket",
        back_populates="action_logs"
    )
    user = relationship(
        "User",
        back_populates="action_logs"
    )
    staff = relationship(
        "Staff_Member",
        back_populates="action_logs"
    )



class Calendar_Rule(Base):
    """
    Calendar_Rule model - defines working hours for specific dates and date ranges.
    
    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10
    """
    __tablename__ = "calendar_rules"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Date range
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    # Work mode
    work_mode = Column(Enum(WorkMode), nullable=False)
    
    # Working hours (nullable for non_working mode)
    work_start_time = Column(Time, nullable=True)
    work_end_time = Column(Time, nullable=True)
    
    # Priority for overlapping rules
    rule_priority = Column(Integer, default=0, nullable=False)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)



class Notification_Event(Base):
    """
    Notification_Event model - schedules and tracks notification delivery.
    
    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10
    """
    __tablename__ = "notification_events"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # User reference
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    
    # Event classification
    event_type = Column(Enum(EventType), nullable=False)
    event_status = Column(
        Enum(EventStatus),
        default=EventStatus.SCHEDULED,
        nullable=False
    )
    
    # Scheduling
    scheduled_for = Column(DateTime, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    
    # Optional ticket reference
    related_ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=True)
    
    # Event data as JSON
    event_data = Column(JSON, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship(
        "User",
        back_populates="notification_events"
    )
    related_ticket = relationship(
        "Ticket",
        back_populates="notification_events"
    )



class Broadcast(Base):
    """
    Broadcast model - stores admin-initiated mass messages.
    
    Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
    """
    __tablename__ = "broadcasts"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Creator reference
    created_by_staff_id = Column(BigInteger, ForeignKey("staff_members.id"), nullable=False)
    
    # Message content
    message_text = Column(Text, nullable=False)
    
    # Broadcast status
    broadcast_status = Column(
        Enum(BroadcastStatus),
        default=BroadcastStatus.DRAFT,
        nullable=False
    )
    
    # Delivery tracking
    target_user_count = Column(Integer, default=0, nullable=False)
    delivered_count = Column(Integer, default=0, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    
    # Relationships
    created_by = relationship(
        "Staff_Member",
        back_populates="broadcasts_created"
    )
    deliveries = relationship(
        "Broadcast_Delivery",
        back_populates="broadcast"
    )


class Broadcast_Delivery(Base):
    """
    Broadcast_Delivery model - tracks individual broadcast delivery status.
    
    Requirements: 11.7, 11.8, 11.9
    """
    __tablename__ = "broadcast_deliveries"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Broadcast and user references
    broadcast_id = Column(Integer, ForeignKey("broadcasts.id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    
    # Delivery status
    delivery_status = Column(
        Enum(DeliveryStatus),
        default=DeliveryStatus.PENDING,
        nullable=False
    )
    
    # Delivery tracking
    delivered_at = Column(DateTime, nullable=True)
    error_message = Column(String(512), nullable=True)
    
    # Unique constraint on broadcast-user pair
    __table_args__ = (
        UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_user_delivery"),
    )
    
    # Relationships
    broadcast = relationship(
        "Broadcast",
        back_populates="deliveries"
    )
    user = relationship(
        "User",
        back_populates="broadcast_deliveries"
    )


class API_Retry_Queue(Base):
    """
    API_Retry_Queue model - manages failed API operations with retry logic.
    
    Stores failed API calls for retry with exponential backoff.
    After max attempts, escalates to admin notification.
    
    Requirements: 25.3, 34.1-34.5
    """
    __tablename__ = "api_retry_queue"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Operation details
    operation = Column(String(100), nullable=False)  # API method name
    payload = Column(JSON, nullable=False)  # Request payload for retry
    
    # User context (optional)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    
    # Retry tracking
    attempt_count = Column(Integer, default=0, nullable=False)
    status = Column(Enum(RetryStatus, values_callable=lambda x: [e.value for e in x]), default=RetryStatus.PENDING, nullable=False)
    
    # Scheduling
    next_retry_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Error tracking
    last_error = Column(Text, nullable=True)
    
    # Relationships
    user = relationship(
        "User",
        back_populates="api_retries"
    )


class Escalation(Base, TimestampMixin):
    """
    Escalation model - tracks ticket escalations with resolution tracking.
    
    Stores escalation events when tickets exceed time thresholds.
    Supports reminder (10 min) and escalation (20 min) types.
    
    Requirements: 2.1, 2.2, 2.3
    """
    __tablename__ = "escalations"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Ticket reference
    ticket_id = Column(
        Integer,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Escalation classification
    escalation_type = Column(Enum(EscalationType), nullable=False)
    
    # Resolution tracking
    is_resolved = Column(Boolean, default=False, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by_staff_id = Column(
        BigInteger,
        ForeignKey("staff_members.id", ondelete="SET NULL"),
        nullable=True
    )
    resolution_action = Column(Enum(ResolutionAction), nullable=True)
    
    # Timestamps inherited from TimestampMixin: created_at, updated_at
    
    # Relationships
    ticket = relationship(
        "Ticket",
        back_populates="escalations"
    )
    resolved_by = relationship(
        "Staff_Member",
        foreign_keys=[resolved_by_staff_id]
    )


class System_Settings(Base):
    """
    System_Settings model - stores system-wide configuration parameters.
    
    Each setting has a key, value, data type, validation constraints,
    and default value. Settings are organized into categories for
    easier navigation.
    
    Requirements: 1.1, 1.2, 1.3, 1.4
    """
    __tablename__ = "system_settings"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # Setting identification
    key = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(Enum(SettingCategory, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    
    # Setting value and type
    value = Column(Text, nullable=True)  # Stored as string, converted based on data_type
    data_type = Column(Enum(SettingDataType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    
    # Default and constraints
    default_value = Column(Text, nullable=False)
    min_value = Column(Integer, nullable=True)  # For numeric types
    max_value = Column(Integer, nullable=True)  # For numeric types
    
    # Metadata
    description = Column(Text, nullable=False)
    display_name = Column(String(200), nullable=False)
    requires_test = Column(Boolean, default=False, nullable=False)  # Whether to test before saving
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    updated_by = Column(BigInteger, ForeignKey("staff_members.id"), nullable=True)
    
    # Relationships
    updater = relationship("Staff_Member", foreign_keys=[updated_by])



class NPS_Response(Base, TimestampMixin):
    """
    NPS_Response model - stores user survey responses.
    
    Tracks NPS ratings with survey type, trigger event,
    and timestamps for analytics.
    
    Requirements: 5.1, 12.1, 12.2, 12.3, 12.4
    """
    __tablename__ = "nps_responses"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    
    # User reference
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Survey classification
    survey_type = Column(
        Enum(SurveyType),
        nullable=False,
        index=True
    )
    
    # Rating value (0-10)
    rating = Column(
        Integer,
        nullable=False
    )
    
    # Trigger event reference
    # For LOYALTY: invoice_id
    # For SERVICE_QUALITY: ticket_id
    trigger_event_id = Column(
        Integer,
        nullable=False
    )
    
    # Timestamps
    sent_at = Column(
        DateTime,
        nullable=False,
        index=True
    )
    responded_at = Column(
        DateTime,
        nullable=False,
        index=True
    )
    
    # Optional feedback comment (for low ratings 0-7)
    feedback_comment = Column(
        Text,
        nullable=True
    )
    
    # Timestamps inherited from TimestampMixin: created_at, updated_at
    
    # Relationships
    user = relationship(
        "User",
        back_populates="nps_responses"
    )
    
    # Composite indexes for analytics queries
    __table_args__ = (
        Index("idx_nps_user_responded", "user_id", "responded_at"),
        Index("idx_nps_type_responded", "survey_type", "responded_at"),
    )
