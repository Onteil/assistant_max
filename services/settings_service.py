"""
Settings service layer for managing system configuration parameters.

Provides async functions for CRUD operations on system settings,
validation, default value management, and audit logging.

Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 3.1, 3.2, 4.1, 4.2, 5.1, 5.2, 6.1, 6.2, 8.1, 8.2, 8.3, 8.4
"""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Action_Log,
    ActionType,
    SettingCategory,
    SettingDataType,
    Staff_Member,
    StaffRole,
    System_Settings,
)

logger = logging.getLogger(__name__)


# ========== Default Settings Configuration ==========

DEFAULT_SETTINGS = {
    # Timeouts (in minutes)
    "manager_response_timeout": {
        "value": "10",
        "category": SettingCategory.TIMEOUTS,
        "data_type": SettingDataType.INTEGER,
        "min_value": 1,
        "max_value": 60,
        "display_name": "Таймаут эскалации",
        "description": "Время ожидания перед эскалацией заявки (применяется ко всем типам эскалации: резервные менеджеры, техподдержка)",
        "requires_test": False,
    },
    # Escalation channels (stored as JSON arrays of chat IDs)
    "escalation_manager_channel": {
        "value": "[]",
        "category": SettingCategory.ESCALATION,
        "data_type": SettingDataType.JSON,
        "display_name": "Каналы эскалации менеджеров",
        "description": "Список MAX чатов для уведомлений об эскалации менеджеров (JSON массив)",
        "requires_test": False,
        "min_value": None,
        "max_value": None,
    },
    "escalation_duty_channel": {
        "value": "[]",
        "category": SettingCategory.ESCALATION,
        "data_type": SettingDataType.JSON,
        "display_name": "Каналы эскалации дежурной",
        "description": "Список MAX чатов для уведомлений об эскалации дежурной поддержки (только для заявок типа Техподдержка)",
        "requires_test": False,
        "min_value": None,
        "max_value": None,
    },
    "escalation_consultant_channel": {
        "value": "[]",
        "category": SettingCategory.ESCALATION,
        "data_type": SettingDataType.JSON,
        "display_name": "Каналы эскалации консультантов",
        "description": "Список MAX чатов для уведомлений об эскалации сметных консультантов (только для заявок типа Консультация)",
        "requires_test": False,
        "min_value": None,
        "max_value": None,
    },
    # Duty support
    "duty_support_account": {
        "value": None,
        "category": SettingCategory.DUTY_SUPPORT,
        "data_type": SettingDataType.USER_ID,
        "display_name": "Аккаунт дежурной поддержки",
        "description": "Telegram ID сотрудника дежурной поддержки",
        "requires_test": False,
        "min_value": None,
        "max_value": None,
    },
    "duty_manager_account": {
        "value": None,
        "category": SettingCategory.DUTY_SUPPORT,
        "data_type": SettingDataType.USER_ID,
        "display_name": "Аккаунт дежурных менеджеров",
        "description": "Telegram ID сотрудника для дежурных менеджеров",
        "requires_test": False,
        "min_value": None,
        "max_value": None,
    },
    # NPS configuration
    "nps_frequency_days": {
        "value": "30",
        "category": SettingCategory.NPS,
        "data_type": SettingDataType.INTEGER,
        "min_value": 1,
        "max_value": 365,
        "display_name": "Частота NPS опросов",
        "description": "Минимальный интервал между NPS опросами для одного пользователя (дни)",
        "requires_test": False,
    },
    "nps_trigger_after_payment": {
        "value": "10",
        "category": SettingCategory.NPS,
        "data_type": SettingDataType.INTEGER,
        "min_value": 0,
        "max_value": 90,
        "display_name": "NPS после оплаты",
        "description": "Через сколько дней после оплаты отправлять NPS опрос",
        "requires_test": False,
    },
    "nps_trigger_after_support": {
        "value": "1",
        "category": SettingCategory.NPS,
        "data_type": SettingDataType.INTEGER,
        "min_value": 0,
        "max_value": 90,
        "display_name": "NPS после поддержки",
        "description": "Через сколько дней после закрытия тикета отправлять NPS опрос",
        "requires_test": False,
    },
    # Renewal reminders
    "renewal_reminder_days": {
        "value": "[30, 7]",
        "category": SettingCategory.RENEWAL_REMINDERS,
        "data_type": SettingDataType.JSON,
        "display_name": "Дни напоминаний о продлении",
        "description": "За сколько дней до истечения подписки отправлять напоминания",
        "requires_test": False,
        "min_value": None,
        "max_value": None,
    },
}


# ========== Access Control ==========


async def verify_admin_access(session: AsyncSession, user_id: int) -> bool:
    """
    Verify user has administrator role and log unauthorized attempts.
    
    Checks if the user is an active administrator. If not, logs the
    unauthorized access attempt for security audit.
    
    Args:
        session: Database session
        user_id: Telegram user ID to verify
    
    Returns:
        True if user is administrator, False otherwise
    
    Requirements: 8.1, 8.2, 8.3, 8.4
    """
    try:
        # Check if user is an active administrator
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == user_id,
            Staff_Member.is_active == True,
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR
        )
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()
        
        if admin is None:
            # Log unauthorized access attempt
            logger.warning(
                f"Unauthorized settings access attempt by user {user_id}"
            )
            
            # Create audit log for unauthorized attempt
            action_log = Action_Log(
                action_type=ActionType.UNAUTHORIZED_ACCESS,
                staff_id=None,  # No staff_id since user is not authorized
                action_details={
                    "attempted_action": "settings_access",
                    "tg_user_id": user_id,
                    "reason": "User is not an active administrator"
                }
            )
            session.add(action_log)
            await session.commit()
            
            return False
        
        return True
    
    except Exception as e:
        logger.error(
            f"Error verifying admin access for user {user_id}: {e}",
            exc_info=True
        )
        return False


# ========== Initialization Function ==========


async def initialize_default_settings(session: AsyncSession) -> None:
    """
    Initialize database with default settings if not present.
    
    This function should be called on application startup to ensure
    all required settings exist in the database with their default values.
    
    Args:
        session: Database session
    
    Requirements: 1.4
    """
    try:
        for key, config in DEFAULT_SETTINGS.items():
            # Check if setting already exists
            result = await session.execute(
                select(System_Settings).where(System_Settings.key == key)
            )
            existing_setting = result.scalar_one_or_none()
            
            if existing_setting is None:
                # Create new setting with default configuration
                new_setting = System_Settings(
                    key=key,
                    category=config["category"],
                    value=config["value"],
                    data_type=config["data_type"],
                    default_value=config["value"] if config["value"] is not None else "",
                    min_value=config.get("min_value"),
                    max_value=config.get("max_value"),
                    description=config["description"],
                    display_name=config["display_name"],
                    requires_test=config.get("requires_test", False),
                )
                session.add(new_setting)
                logger.info(f"Initialized default setting: {key}")
        
        await session.commit()
        logger.info("Default settings initialization completed")
    
    except Exception as e:
        await session.rollback()
        logger.error(f"Error initializing default settings: {e}", exc_info=True)
        raise


# ========== CRUD Operations ==========


async def get_setting(session: AsyncSession, key: str) -> Any:
    """
    Get a setting value by key, returning the typed value.
    Returns default if no custom value is set.
    
    Args:
        session: Database session
        key: Setting key
    
    Returns:
        Typed setting value (int, str, dict, etc.)
    
    Requirements: 2.1, 3.1, 4.1, 5.1, 6.1
    """
    result = await session.execute(
        select(System_Settings).where(System_Settings.key == key)
    )
    setting = result.scalar_one_or_none()
    
    if setting is None:
        logger.warning(f"Setting not found: {key}")
        return None
    
    # Use custom value if set, otherwise use default
    value_str = setting.value if setting.value is not None else setting.default_value
    
    # Convert based on data type
    return _convert_value(value_str, setting.data_type)


async def get_settings_by_category(
    session: AsyncSession,
    category: SettingCategory
) -> dict[str, Any]:
    """
    Get all settings in a category as a dictionary.
    
    Args:
        session: Database session
        category: Setting category
    
    Returns:
        Dictionary mapping setting keys to typed values
    
    Requirements: 2.1, 3.1, 4.1, 5.1, 6.1
    """
    result = await session.execute(
        select(System_Settings).where(System_Settings.category == category)
    )
    settings = result.scalars().all()
    
    return {
        setting.key: _convert_value(
            setting.value if setting.value is not None else setting.default_value,
            setting.data_type
        )
        for setting in settings
    }


async def get_escalation_channels(session: AsyncSession, key: str) -> list[str]:
    """
    Get escalation channel list for a given setting key.

    Returns a list of chat ID strings. Always returns a list (empty if not set).

    Args:
        session: Database session
        key: Setting key (e.g. 'escalation_manager_channel')

    Returns:
        List of chat ID strings
    """
    value = await get_setting(session, key)
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    # Legacy single chat_id string
    return [str(value)]


async def add_channel_to_setting(
    session: AsyncSession,
    key: str,
    chat_id: str,
    admin_id: int,
    chat_title: str | None = None
) -> tuple[bool, str]:
    """
    Add a chat ID to an escalation channel list setting.

    Args:
        session: Database session
        key: Setting key
        chat_id: Chat ID to add
        admin_id: Administrator user ID
        chat_title: Optional display name for the channel

    Returns:
        Tuple of (success, message)
    """
    channels = await get_escalation_channels(session, key)
    if chat_id in channels:
        return False, "Этот канал уже добавлен"
    channels.append(chat_id)
    return await update_setting(session, key, channels, admin_id, chat_title)


async def remove_channel_from_setting(
    session: AsyncSession,
    key: str,
    chat_id: str,
    admin_id: int
) -> tuple[bool, str]:
    """
    Remove a chat ID from an escalation channel list setting.

    Args:
        session: Database session
        key: Setting key
        chat_id: Chat ID to remove
        admin_id: Administrator user ID

    Returns:
        Tuple of (success, message)
    """
    channels = await get_escalation_channels(session, key)
    if chat_id not in channels:
        return False, "Канал не найден в списке"
    channels.remove(chat_id)
    return await update_setting(session, key, channels, admin_id)


async def update_setting(
    session: AsyncSession,
    key: str,
    value: Any,
    admin_id: int,
    chat_title: str | None = None
) -> tuple[bool, str]:
    """
    Update a setting value with validation.
    Creates audit log entry.
    
    Args:
        session: Database session
        key: Setting key
        value: New value
        admin_id: Administrator Telegram or MAX user ID making the change
        chat_title: Optional chat title for escalation channels
    
    Returns:
        Tuple of (success, message)
    
    Requirements: 2.1, 2.2, 3.1, 4.1, 5.1, 6.1
    """
    try:
        # Get staff member internal ID from Telegram or MAX user ID
        from database.models import Staff_Member
        from sqlalchemy import or_
        staff_result = await session.execute(
            select(Staff_Member.id).where(
                or_(
                    Staff_Member.tg_user_id == admin_id,
                    Staff_Member.max_user_id == admin_id
                )
            )
        )
        staff_id = staff_result.scalar_one_or_none()
        
        if staff_id is None:
            logger.error(f"Staff member not found for user_id {admin_id}")
            return False, "Staff member not found"
        
        # Get existing setting
        result = await session.execute(
            select(System_Settings).where(System_Settings.key == key)
        )
        setting = result.scalar_one_or_none()
        
        if setting is None:
            return False, f"Setting not found: {key}"
        
        # Validate value
        is_valid, error_message, typed_value = await validate_setting_value(setting, value)
        if not is_valid:
            return False, error_message
        
        # Store old value for audit
        old_value = setting.value
        
        # Convert typed value to string for storage
        new_value_str = _value_to_string(typed_value, setting.data_type)
        
        # Update setting
        setting.value = new_value_str
        setting.updated_by = staff_id
        
        # Create audit log with optional chat title
        await _log_setting_change(
            session=session,
            action_type=ActionType.SETTING_CHANGED,
            staff_id=staff_id,
            key=key,
            old_value=old_value,
            new_value=new_value_str,
            chat_title=chat_title
        )
        
        await session.commit()
        logger.info(f"Setting updated: {key} by staff {staff_id} (user_id {admin_id})")
        return True, "Setting updated successfully"
    
    except Exception as e:
        await session.rollback()
        logger.error(f"Error updating setting {key}: {e}", exc_info=True)
        return False, "Error updating setting"


async def reset_setting(
    session: AsyncSession,
    key: str,
    admin_id: int
) -> tuple[bool, str]:
    """
    Reset a setting to its default value.
    Creates audit log entry.
    
    Args:
        session: Database session
        key: Setting key
        admin_id: Administrator Telegram or MAX user ID making the change
    
    Returns:
        Tuple of (success, message)
    
    Requirements: 1.4, 2.2
    """
    try:
        # Get staff member internal ID from Telegram or MAX user ID
        from database.models import Staff_Member
        from sqlalchemy import or_
        staff_result = await session.execute(
            select(Staff_Member.id).where(
                or_(
                    Staff_Member.tg_user_id == admin_id,
                    Staff_Member.max_user_id == admin_id
                )
            )
        )
        staff_id = staff_result.scalar_one_or_none()
        
        if staff_id is None:
            logger.error(f"Staff member not found for user_id {admin_id}")
            return False, "Staff member not found"
        
        # Get existing setting
        result = await session.execute(
            select(System_Settings).where(System_Settings.key == key)
        )
        setting = result.scalar_one_or_none()
        
        if setting is None:
            return False, f"Setting not found: {key}"
        
        # Store old value for audit
        old_value = setting.value
        
        # Reset to default
        setting.value = setting.default_value
        setting.updated_by = staff_id
        
        # Create audit log
        await _log_setting_change(
            session=session,
            action_type=ActionType.SETTING_RESET,
            staff_id=staff_id,
            key=key,
            old_value=old_value,
            new_value=setting.default_value
        )
        
        await session.commit()
        logger.info(f"Setting reset to default: {key} by staff {staff_id} (user_id {admin_id})")
        return True, "Setting reset to default"
    
    except Exception as e:
        await session.rollback()
        logger.error(f"Error resetting setting {key}: {e}", exc_info=True)
        return False, "Error resetting setting"


# ========== Validation Functions ==========


async def validate_setting_value(
    setting: System_Settings,
    value: Any
) -> tuple[bool, str, Any]:
    """
    Validate a setting value against its constraints.
    
    Args:
        setting: System_Settings instance
        value: Value to validate
    
    Returns:
        Tuple of (is_valid, error_message, typed_value)
    
    Requirements: 2.1, 2.2, 3.1, 4.1, 5.1, 6.1
    """
    try:
        # Type-specific validation
        if setting.data_type == SettingDataType.INTEGER:
            return _validate_integer(value, setting.min_value, setting.max_value)
        elif setting.data_type == SettingDataType.JSON:
            return _validate_json(value)
        elif setting.data_type == SettingDataType.CHAT_ID:
            return _validate_chat_id(value)
        elif setting.data_type == SettingDataType.USER_ID:
            return _validate_user_id(value)
        else:
            return False, f"Unknown data type: {setting.data_type}", None
    
    except Exception as e:
        logger.error(f"Validation error for {setting.key}: {e}", exc_info=True)
        return False, f"Validation error: {str(e)}", None


def _validate_integer(value: Any, min_value: int | None, max_value: int | None) -> tuple[bool, str, int]:
    """Validate integer value with min/max constraints."""
    try:
        int_value = int(value)
        
        if min_value is not None and int_value < min_value:
            return False, f"Value must be at least {min_value}", None
        
        if max_value is not None and int_value > max_value:
            return False, f"Value must be at most {max_value}", None
        
        return True, "", int_value
    
    except (ValueError, TypeError):
        return False, "Value must be a valid integer", None


def _validate_json(value: Any) -> tuple[bool, str, Any]:
    """Validate JSON value."""
    try:
        if isinstance(value, str):
            parsed = json.loads(value)
        else:
            parsed = value
        
        return True, "", parsed
    
    except json.JSONDecodeError:
        return False, "Value must be valid JSON", None


def _validate_chat_id(value: Any) -> tuple[bool, str, str]:
    """Validate Telegram chat ID format."""
    try:
        str_value = str(value)
        
        # Chat IDs should be numeric (can be negative for groups/channels)
        int(str_value)
        
        return True, "", str_value
    
    except (ValueError, TypeError):
        return False, "Value must be a valid chat ID (numeric)", None


def _validate_user_id(value: Any) -> tuple[bool, str, str]:
    """Validate Telegram user ID format."""
    try:
        str_value = str(value)
        
        # User IDs should be positive integers
        user_id = int(str_value)
        if user_id <= 0:
            return False, "User ID must be positive", None
        
        return True, "", str_value
    
    except (ValueError, TypeError):
        return False, "Value must be a valid user ID (positive integer)", None


# ========== Helper Functions ==========


def _convert_value(value_str: str, data_type: SettingDataType) -> Any:
    """Convert string value to appropriate type."""
    if value_str is None or value_str == "":
        return None
    
    if data_type == SettingDataType.INTEGER:
        return int(value_str)
    elif data_type == SettingDataType.JSON:
        return json.loads(value_str)
    elif data_type in (SettingDataType.CHAT_ID, SettingDataType.USER_ID):
        return value_str
    else:
        return value_str


def _value_to_string(value: Any, data_type: SettingDataType) -> str:
    """Convert typed value to string for storage."""
    if value is None:
        return ""
    
    if data_type == SettingDataType.JSON:
        return json.dumps(value)
    else:
        return str(value)


async def _log_setting_change(
    session: AsyncSession,
    action_type: ActionType,
    staff_id: int,
    key: str,
    old_value: str | None,
    new_value: str | None,
    chat_title: str | None = None
) -> None:
    """
    Create audit log entry for setting change.
    
    Logs all configuration changes with administrator ID, parameter name,
    old value, new value, and timestamp for compliance and audit trail.
    
    Args:
        session: Database session
        action_type: Type of action (SETTING_CHANGED or SETTING_RESET)
        staff_id: Administrator ID making the change
        key: Setting key that was changed
        old_value: Previous value (None if not set)
        new_value: New value after change
        chat_title: Optional chat title for escalation channels
    
    Requirements: 2.1, 2.2, 8.3
    """
    action_details = {
        "setting_key": key,
        "old_value": old_value,
        "new_value": new_value,
    }
    
    # Add chat title if provided (for escalation channels)
    if chat_title:
        action_details["chat_title"] = chat_title
    
    log_entry = Action_Log(
        action_type=action_type,
        staff_id=staff_id,
        action_details=action_details
    )
    session.add(log_entry)
    logger.info(
        f"Audit log created: {action_type.value} for setting '{key}' "
        f"by staff {staff_id}"
    )


# ========== Test Functions ==========


async def test_escalation_channel(bot: Any, chat_id: str) -> tuple[bool, str, str | None]:
    """
    Test if bot can send messages to escalation channel.
    
    Sends a test message to verify the bot has access to the channel
    and proper permissions to send messages. Also retrieves chat title.
    
    Args:
        bot: Bot instance (Aiogram Bot or MAX Bot)
        chat_id: Chat ID to test (Telegram or MAX format)
    
    Returns:
        Tuple of (success, message, chat_title)
    
    Requirements: 3.1, 3.2
    """
    try:
        chat_title = None
        
        # Get chat information to retrieve title
        # MAX Bot uses get_chat_by_id (positional arg), Aiogram uses get_chat (keyword arg)
        if hasattr(bot, 'get_chat_by_id'):
            # MAX Bot API - positional argument
            try:
                chat = await bot.get_chat_by_id(int(chat_id))
                chat_title = chat.title if hasattr(chat, 'title') else None
            except Exception as e:
                logger.warning(f"Could not get chat info for MAX bot: {e}")
        else:
            # Aiogram Bot API - keyword argument
            try:
                chat = await bot.get_chat(chat_id=chat_id)
                chat_title = chat.title if hasattr(chat, 'title') else None
            except Exception as e:
                logger.warning(f"Could not get chat info for Telegram bot: {e}")
        
        # Send test message
        test_message = "🔔 Тестовое сообщение эскалации\n\nЭто тестовое сообщение для проверки канала эскалации."
        
        # Send message (both MAX and Telegram use send_message)
        await bot.send_message(chat_id=int(chat_id), text=test_message)
        
        logger.info(f"Test message sent successfully to chat {chat_id} ({chat_title})")
        return True, "✅ Тестовое сообщение отправлено успешно", chat_title
    
    except Exception as e:
        logger.error(f"Failed to send test message to chat {chat_id}: {e}", exc_info=True)
        return False, f"❌ Не удалось отправить сообщение. Проверьте, что бот добавлен в чат и имеет права на отправку сообщений. Ошибка: {str(e)}", None


# ========== History Functions ==========


async def get_settings_history(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0
) -> tuple[list[Action_Log], int]:
    """
    Get recent settings changes with pagination.
    
    Returns settings change history in reverse chronological order
    (most recent first) with pagination support.
    
    Args:
        session: Database session
        limit: Maximum number of records to return
        offset: Number of records to skip
    
    Returns:
        Tuple of (logs, total_count)
    
    Requirements: 2.3
    """
    from sqlalchemy import func, desc
    from sqlalchemy.orm import selectinload
    
    try:
        # Query for settings changes (SETTING_CHANGED and SETTING_RESET)
        # Eagerly load staff relationship to avoid lazy loading issues
        query = select(Action_Log).options(
            selectinload(Action_Log.staff)
        ).where(
            Action_Log.action_type.in_([
                ActionType.SETTING_CHANGED,
                ActionType.SETTING_RESET
            ])
        ).order_by(desc(Action_Log.action_timestamp))
        
        # Get total count
        count_query = select(func.count()).select_from(Action_Log).where(
            Action_Log.action_type.in_([
                ActionType.SETTING_CHANGED,
                ActionType.SETTING_RESET
            ])
        )
        count_result = await session.execute(count_query)
        total_count = count_result.scalar()
        
        # Apply pagination
        query = query.limit(limit).offset(offset)
        
        # Execute query
        result = await session.execute(query)
        logs = result.scalars().all()
        
        return list(logs), total_count
    
    except Exception as e:
        logger.error(f"Error fetching settings history: {e}", exc_info=True)
        return [], 0
