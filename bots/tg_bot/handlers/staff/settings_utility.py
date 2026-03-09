"""
Settings Utility Handlers

Handles utility functions for settings:
- History viewing with pagination
- Reset to default values

Requirements: 1.4, 2.3, 8.1, 8.2, 8.3
"""

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import SettingsCallback
from bots.tg_bot.keyboards.admin_kb import get_settings_history_keyboard
from database.models import ActionType, Staff_Member, StaffRole
from services.settings_service import (
    get_settings_history,
    reset_setting,
    verify_admin_access,
)

logger = logging.getLogger(__name__)

router = Router(name="settings_utility")


# ========== History Handlers ==========


async def _format_setting_value(session: AsyncSession, setting_key: str, value: any) -> str:
    """
    Format setting value for display.
    
    Converts technical values (IDs, enum keys) to human-readable format.
    """
    if value is None or value == "":
        return "—"
    
    # Convert staff IDs to names
    if setting_key in ["duty_support_account", "duty_manager_account", "backup_manager_slot_1", "backup_manager_slot_2"]:
        try:
            from sqlalchemy import select
            from database.models import Staff_Member
            
            staff_id = int(value)
            result = await session.execute(
                select(Staff_Member).where(Staff_Member.id == staff_id)
            )
            staff = result.scalar_one_or_none()
            if staff:
                return staff.full_name
            return f"ID: {staff_id}"
        except (ValueError, TypeError):
            return str(value)
    
    return str(value)


def _get_setting_display_name(setting_key: str) -> str:
    """
    Get human-readable name for setting key.
    """
    setting_names = {
        "duty_support_account": "Дежурный специалист поддержки",
        "duty_manager_account": "Дежурный менеджер",
        "backup_manager_slot_1": "Резервный менеджер (слот 1)",
        "backup_manager_slot_2": "Резервный менеджер (слот 2)",
        "working_hours_start": "Начало рабочего дня",
        "working_hours_end": "Конец рабочего дня",
        "auto_assignment_enabled": "Автоматическое назначение",
        "notification_enabled": "Уведомления",
    }
    return setting_names.get(setting_key, setting_key)


@router.callback_query(SettingsCallback.filter(F.action == "history"))
async def show_settings_history(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession
) -> None:
    """
    Display recent settings changes with pagination.
    
    Shows history of all configuration changes including:
    - Date and time
    - Administrator name
    - Parameter changed
    - Old and new values
    
    Requirements: 2.3, 8.1, 8.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        if not await verify_admin_access(session, user_id):
            await callback.answer(
                "❌ У вас нет доступа к настройкам системы.",
                show_alert=True
            )
            return
        
        # Get page from callback data (default to 0)
        page = callback_data.page if callback_data.page is not None else 0
        page_size = 10
        
        # Get settings history
        logs, total_count = await get_settings_history(
            session=session,
            limit=page_size,
            offset=page * page_size
        )
        
        # Calculate total pages
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        
        # Build history text
        if logs:
            history_lines = []
            
            for log in logs:
                # Format timestamp
                timestamp = log.action_timestamp.strftime("%d.%m.%Y %H:%M")
                
                # Get administrator name
                admin_name = log.staff.full_name if log.staff else "Неизвестно"
                
                # Get action type
                action_type_display = {
                    ActionType.SETTING_CHANGED: "Изменено",
                    ActionType.SETTING_RESET: "Сброшено"
                }
                action_text = action_type_display.get(log.action_type, str(log.action_type.value))
                
                # Get setting details
                details = log.action_details or {}
                setting_key = details.get("setting_key", "Неизвестно")
                old_value = details.get("old_value")
                new_value = details.get("new_value")
                
                # Format setting name and values for display
                setting_display = _get_setting_display_name(setting_key)
                old_display = await _format_setting_value(session, setting_key, old_value)
                new_display = await _format_setting_value(session, setting_key, new_value)
                
                # Build history entry
                entry = (
                    f"📅 <b>{timestamp}</b>\n"
                    f"👤 {admin_name}\n"
                    f"⚙️ {action_text}: <b>{setting_display}</b>\n"
                    f"📝 Было: {old_display}\n"
                    f"📝 Стало: {new_display}"
                )
                
                history_lines.append(entry)
            
            history_text = (
                "📜 <b>История изменений настроек</b>\n\n"
                f"Страница {page + 1} из {total_pages}\n"
                f"Всего записей: {total_count}\n\n"
                + "\n\n".join(history_lines)
            )
        else:
            history_text = (
                "📜 <b>История изменений настроек</b>\n\n"
                "История изменений пуста."
            )
        
        # Get keyboard with pagination
        keyboard = await get_settings_history_keyboard(page, total_pages)
        
        await callback.message.edit_text(
            history_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} viewed settings history (page {page + 1})")
        
    except Exception as e:
        logger.error(f"Error showing settings history: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке истории.",
            show_alert=True
        )


@router.callback_query(SettingsCallback.filter(F.action == "history_page"))
async def history_page_navigation(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession
) -> None:
    """
    Handle pagination for settings history.
    
    Navigates between pages of settings change history.
    
    Requirements: 2.3
    """
    # Reuse show_settings_history with the new page
    await show_settings_history(callback, callback_data, session)


# ========== Reset Handlers ==========


@router.callback_query(SettingsCallback.filter(F.action == "reset_setting"))
async def reset_setting_handler(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession
) -> None:
    """
    Reset a setting to its default value.
    
    Creates audit log entry and displays confirmation message.
    
    Requirements: 1.4, 8.1, 8.2, 8.3
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Verify user is administrator
        if not await verify_admin_access(session, user_id):
            await callback.answer(
                "❌ У вас нет доступа к настройкам системы.",
                show_alert=True
            )
            return
        
        # Get admin record for logging
        from sqlalchemy import select
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == user_id,
            Staff_Member.is_active == True,
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR
        )
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()
        
        if not admin:
            await callback.answer(
                "❌ Ошибка получения данных администратора.",
                show_alert=True
            )
            return
        
        # Get setting key from callback data
        setting_key = callback_data.setting_key
        
        if not setting_key:
            await callback.answer(
                "❌ Не указан параметр для сброса.",
                show_alert=True
            )
            return
        
        # Map category keys to individual setting keys
        category_to_settings = {
            "timeouts": ["manager_response_timeout", "duty_taken_timeout"],
            "escalation": ["escalation_manager_channel", "escalation_duty_channel"],
            "duty_support": ["duty_support_account", "duty_manager_account"],
            "nps": ["nps_frequency_days", "nps_trigger_after_payment", "nps_trigger_after_support"],
            "renewal_reminders": ["renewal_reminder_days"]
        }
        
        # Determine which settings to reset
        settings_to_reset = []
        
        if setting_key in category_to_settings:
            # Reset all settings in category
            settings_to_reset = category_to_settings[setting_key]
            category_name = setting_key
        else:
            # Reset single setting
            settings_to_reset = [setting_key]
            category_name = None
        
        # Reset each setting
        success_count = 0
        failed_settings = []
        
        for key in settings_to_reset:
            success, message = await reset_setting(
                session=session,
                key=key,
                admin_id=admin.id
            )
            
            if success:
                success_count += 1
            else:
                failed_settings.append(key)
                logger.warning(f"Failed to reset setting {key}: {message}")
        
        # Build response message
        if success_count == len(settings_to_reset):
            # All settings reset successfully
            if category_name:
                response_text = f"✅ Все настройки категории <b>{category_name}</b> сброшены на значения по умолчанию."
            else:
                response_text = f"✅ Настройка <code>{setting_key}</code> сброшена на значение по умолчанию."
            
            await callback.answer(response_text, show_alert=True)
            
            logger.info(f"Administrator {user_id} ({admin.full_name}) reset settings: {settings_to_reset}")
            
            # Refresh the current settings view
            # Determine which view to return to based on category
            if category_name == "timeouts":
                from bots.tg_bot.handlers.staff.settings import show_timeout_settings
                await show_timeout_settings(callback, session)
            elif category_name == "escalation":
                from bots.tg_bot.handlers.staff.settings import show_escalation_settings
                await show_escalation_settings(callback, session)
            elif category_name == "duty_support":
                from bots.tg_bot.handlers.staff.settings import show_duty_support_settings
                await show_duty_support_settings(callback, session)
            elif category_name == "nps":
                from bots.tg_bot.handlers.staff.settings import show_nps_settings
                await show_nps_settings(callback, session)
            elif category_name == "renewal_reminders":
                from bots.tg_bot.handlers.staff.settings import show_renewal_reminders_settings
                await show_renewal_reminders_settings(callback, session)
            else:
                # Unknown category, return to settings menu
                from bots.tg_bot.handlers.staff.settings import show_settings_menu
                await show_settings_menu(callback, session)
        
        elif success_count > 0:
            # Partial success
            response_text = (
                f"⚠️ Сброшено {success_count} из {len(settings_to_reset)} настроек.\n"
                f"Не удалось сбросить: {', '.join(failed_settings)}"
            )
            await callback.answer(response_text, show_alert=True)
        
        else:
            # All failed
            response_text = "❌ Не удалось сбросить настройки. Попробуйте позже."
            await callback.answer(response_text, show_alert=True)
        
    except Exception as e:
        logger.error(f"Error resetting setting: user={callback.from_user.id}, setting={callback_data.setting_key}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при сбросе настроек.",
            show_alert=True
        )
