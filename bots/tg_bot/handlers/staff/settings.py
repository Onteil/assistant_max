"""
Settings Handlers

Handles administrative settings configuration:
- Navigation between settings categories
- Timeout configuration
- Escalation channel configuration
- Duty support account configuration
- NPS survey settings
- Renewal reminder scheduling
- Manager backup display (view only)

Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 5.1, 5.2, 6.1, 6.2, 7.1
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import SettingsCallback
from bots.tg_bot.keyboards.admin_kb import (
    get_settings_menu_keyboard,
    get_timeout_settings_keyboard,
    get_escalation_settings_keyboard,
    get_nps_settings_keyboard,
    get_renewal_reminders_keyboard,
    get_settings_history_keyboard,
)
from bots.tg_bot.states import SettingsStates
from database.models import SettingCategory, Staff_Member, StaffRole
from services.settings_service import (
    get_setting,
    get_settings_by_category,
    update_setting,
    reset_setting,
    test_escalation_channel,
    get_settings_history,
    verify_admin_access,
)

logger = logging.getLogger(__name__)

router = Router(name="admin_settings")


# ========== Helper Functions ==========


async def _get_chat_title_from_logs(session: AsyncSession, setting_key: str) -> str | None:
    """
    Get chat title from the most recent action log for a setting.
    
    Args:
        session: Database session
        setting_key: Setting key to look up
    
    Returns:
        Chat title if found in logs, None otherwise
    """
    try:
        from database.models import Action_Log, ActionType
        
        # Get the most recent SETTING_CHANGED log for this key
        stmt = (
            select(Action_Log.action_details)
            .where(
                Action_Log.action_type == ActionType.SETTING_CHANGED,
                Action_Log.action_details["setting_key"].astext == setting_key
            )
            .order_by(Action_Log.action_timestamp.desc())
            .limit(1)
        )
        
        result = await session.execute(stmt)
        action_details = result.scalar_one_or_none()
        
        if action_details and "chat_title" in action_details:
            return action_details["chat_title"]
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting chat title from logs for {setting_key}: {e}", exc_info=True)
        return None


# ========== Navigation Handlers ==========


@router.callback_query(SettingsCallback.filter(F.action == "menu"))
async def show_settings_menu(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Display main settings menu with all categories.
    
    Entry point to settings configuration. Shows categories:
    - Timeouts
    - Escalation channels
    - Duty support
    - NPS settings
    - Renewal reminders
    - Manager backups (view only)
    - History
    
    Requirements: 1.1, 1.2, 1.3, 8.1, 8.2
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
        
        # Get settings menu keyboard
        keyboard = await get_settings_menu_keyboard()
        
        # Display settings menu
        settings_text = (
            "⚙️ <b>Настройки системы</b>\n\n"
            "Выберите категорию для настройки:\n\n"
            "⏱ <b>Таймауты</b> - время ожидания ответа и эскалации\n"
            "📢 <b>Эскалация</b> - каналы уведомлений об эскалации\n"
            "🌙 <b>Дежурная поддержка</b> - аккаунт для внерабочих часов\n"
            "📊 <b>NPS настройки</b> - частота и триггеры опросов\n"
            "🔔 <b>Напоминания</b> - расписание напоминаний о продлении\n"
            # "👥 <b>Резервы менеджеров</b> - просмотр назначений резервов\n"
            "📜 <b>История</b> - журнал изменений настроек"
        )
        
        await callback.message.edit_text(
            settings_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} accessed settings menu")
        
    except SQLAlchemyError as e:
        logger.error(f"Database error showing settings menu: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке настроек.",
            show_alert=True
        )
    except Exception as e:
        logger.error(f"Error showing settings menu: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке настроек.",
            show_alert=True
        )


@router.callback_query(SettingsCallback.filter(F.action == "timeouts"))
async def show_timeout_settings(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Display timeout configuration screen.
    
    Shows current timeout values for:
    - Manager response timeout
    - Duty support "taken to work" timeout
    
    Requirements: 2.1, 2.2, 8.1, 8.2
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
        
        # Get current timeout values
        timeout_settings = await get_settings_by_category(session, SettingCategory.TIMEOUTS)
        
        # Get keyboard with current values
        keyboard = await get_timeout_settings_keyboard(timeout_settings)
        
        # Display timeout settings
        timeout_text = (
            "⏱ <b>Настройка таймаутов</b>\n\n"
            "Настройте время ожидания перед эскалацией заявок.\n\n"
            f"<b>Таймаут ответа менеджера:</b> {timeout_settings.get('manager_response_timeout', 10)} мин\n"
            "Время ожидания ответа менеджера перед эскалацией заявки.\n\n"
            f"<b>Таймаут взятия в работу дежурной:</b> {timeout_settings.get('duty_taken_timeout', 10)} мин\n"
            "Время ожидания взятия тикета в работу дежурной поддержкой.\n\n"
            "Нажмите на параметр для изменения значения."
        )
        
        await callback.message.edit_text(
            timeout_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} accessed timeout settings")
        
    except Exception as e:
        logger.error(f"Error showing timeout settings: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке настроек.",
            show_alert=True
        )


@router.callback_query(SettingsCallback.filter(F.action == "escalation"))
async def show_escalation_settings(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Display escalation channel configuration screen.
    
    Shows current escalation channels for:
    - Manager escalations
    - Duty support escalations
    
    Requirements: 3.1, 3.2, 8.1, 8.2
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
        
        # Get current escalation channel values
        manager_channel = await get_setting(session, "escalation_manager_channel")
        duty_channel = await get_setting(session, "escalation_duty_channel")
        
        # Get chat titles from action logs
        manager_title = await _get_chat_title_from_logs(session, "escalation_manager_channel")
        duty_title = await _get_chat_title_from_logs(session, "escalation_duty_channel")
        
        # Get keyboard with current values
        keyboard = await get_escalation_settings_keyboard(manager_channel, duty_channel)
        
        # Format channel display with titles
        if manager_channel:
            manager_status = f"{manager_channel}"
            if manager_title:
                manager_status += f" ({manager_title})"
        else:
            manager_status = "❌ Не настроен"
            
        if duty_channel:
            duty_status = f"{duty_channel}"
            if duty_title:
                duty_status += f" ({duty_title})"
        else:
            duty_status = "❌ Не настроен"
        
        # Display escalation settings
        escalation_text = (
            "📢 <b>Настройка каналов эскалации</b>\n\n"
            "Настройте Telegram чаты для уведомлений об эскалации заявок.\n\n"
            f"<b>Канал эскалации менеджеров:</b> {manager_status}\n"
            "Чат для уведомлений об эскалации заявок менеджеров.\n\n"
            f"<b>Канал эскалации дежурной:</b> {duty_status}\n"
            "Чат для уведомлений об эскалации заявок дежурной поддержки.\n\n"
            "Нажмите на параметр для изменения значения.\n"
            "⚠️ Перед сохранением будет отправлено тестовое сообщение."
        )
        
        await callback.message.edit_text(
            escalation_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} accessed escalation settings")
        
    except Exception as e:
        logger.error(f"Error showing escalation settings: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке настроек.",
            show_alert=True
        )


@router.callback_query(SettingsCallback.filter(F.action == "duty_support"))
async def show_duty_support_settings(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Display duty support account configuration screen.
    
    Shows current duty support Telegram account.
    
    Requirements: 4.1, 4.2, 8.1, 8.2
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
        
        # Get current duty support account
        duty_account = await get_setting(session, "duty_support_account")
        
        # Format account display
        account_status = duty_account if duty_account else "❌ Не настроен"
        
        # Build keyboard
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        
        builder.button(
            text=f"🌙 Аккаунт дежурной: {account_status}",
            callback_data=SettingsCallback(
                action="edit_duty_account",
                setting_key="duty_support_account"
            )
        )
        
        builder.button(
            text="🔄 Сбросить по умолчанию",
            callback_data=SettingsCallback(
                action="reset_setting",
                setting_key="duty_support"
            )
        )
        
        builder.button(
            text="◀️ Назад",
            callback_data=SettingsCallback(action="menu")
        )
        
        builder.adjust(1)
        
        # Display duty support settings
        duty_text = (
            "🌙 <b>Настройка дежурной поддержки</b>\n\n"
            "Настройте Telegram аккаунт сотрудника дежурной поддержки.\n\n"
            f"<b>Текущий аккаунт:</b> {account_status}\n\n"
            "Заявки, поступающие в нерабочее время, будут направляться "
            "на этот аккаунт.\n\n"
            "Нажмите на параметр для изменения значения."
        )
        
        await callback.message.edit_text(
            duty_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} accessed duty support settings")
        
    except Exception as e:
        logger.error(f"Error showing duty support settings: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке настроек.",
            show_alert=True
        )


@router.callback_query(SettingsCallback.filter(F.action == "nps"))
async def show_nps_settings(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Display NPS survey configuration screen.
    
    Shows current NPS settings:
    - Survey frequency limit
    - Trigger timing after payment
    - Trigger timing after support ticket
    
    Requirements: 5.1, 5.2, 8.1, 8.2
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
        
        # Get current NPS settings
        nps_settings = await get_settings_by_category(session, SettingCategory.NPS)
        
        frequency_days = nps_settings.get("nps_frequency_days", 30)
        trigger_after_payment = nps_settings.get("nps_trigger_after_payment", 10)
        trigger_after_support = nps_settings.get("nps_trigger_after_support", 1)
        
        # Get keyboard with current values
        keyboard = await get_nps_settings_keyboard(
            frequency_days,
            trigger_after_payment,
            trigger_after_support
        )
        
        # Display NPS settings
        nps_text = (
            "📊 <b>Настройка NPS опросов</b>\n\n"
            "Настройте частоту и условия отправки NPS опросов пользователям.\n\n"
            f"<b>Частота опросов:</b> {frequency_days} дней\n"
            "Минимальный интервал между опросами для одного пользователя.\n\n"
            f"<b>После оплаты:</b> {trigger_after_payment} дней\n"
            "Через сколько дней после оплаты отправлять опрос.\n\n"
            f"<b>После поддержки:</b> {trigger_after_support} дней\n"
            "Через сколько дней после закрытия тикета отправлять опрос.\n\n"
            "Нажмите на параметр для изменения значения."
        )
        
        await callback.message.edit_text(
            nps_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} accessed NPS settings")
        
    except Exception as e:
        logger.error(f"Error showing NPS settings: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке настроек.",
            show_alert=True
        )


@router.callback_query(SettingsCallback.filter(F.action == "renewal_reminders"))
async def show_renewal_reminders_settings(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Display renewal reminder schedule configuration screen.
    
    Shows current renewal reminder schedule with ability to add/remove reminders.
    
    Requirements: 6.1, 6.2, 8.1, 8.2
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
        
        # Get current renewal reminder schedule
        reminder_days = await get_setting(session, "renewal_reminder_days")
        
        # Ensure it's a list
        if not isinstance(reminder_days, list):
            reminder_days = [30, 7]  # Default
        
        # Get keyboard with current values
        keyboard = await get_renewal_reminders_keyboard(reminder_days)
        
        # Format reminder list
        reminder_list = ", ".join(str(d) for d in sorted(reminder_days, reverse=True))
        
        # Display renewal reminder settings
        renewal_text = (
            "🔔 <b>Настройка напоминаний о продлении</b>\n\n"
            "Настройте расписание напоминаний о продлении подписки.\n\n"
            f"<b>Текущее расписание:</b> за {reminder_list} дней до истечения\n\n"
            "Пользователи будут получать напоминания о необходимости продления "
            "подписки за указанное количество дней до истечения срока.\n\n"
            "Используйте кнопки для добавления или удаления напоминаний.\n"
            "⚠️ Должно быть настроено минимум одно напоминание."
        )
        
        await callback.message.edit_text(
            renewal_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} accessed renewal reminder settings")
        
    except Exception as e:
        logger.error(f"Error showing renewal reminder settings: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке настроек.",
            show_alert=True
        )


@router.callback_query(SettingsCallback.filter(F.action == "manager_backups"))
async def show_manager_backups_settings(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Display manager backup assignments (view only).
    
    Shows all managers with their backup assignments.
    Displays warning for managers without configured backups.
    
    Note: Configuration is done in employee management, this is view only.
    
    Requirements: 7.1, 7.2, 7.3, 8.1, 8.2
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
        
        # Get all active managers
        stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.MANAGER,
            Staff_Member.is_active == True
        ).order_by(Staff_Member.full_name)
        
        result = await session.execute(stmt)
        managers = result.scalars().all()
        
        # Build manager backup list
        backup_lines = []
        
        for manager in managers:
            # Get backup manager names
            backup_1_name = None
            backup_2_name = None
            
            if manager.backup_manager_1_id:
                backup_1_stmt = select(Staff_Member).where(Staff_Member.id == manager.backup_manager_1_id)
                backup_1_result = await session.execute(backup_1_stmt)
                backup_1 = backup_1_result.scalar_one_or_none()
                backup_1_name = backup_1.full_name if backup_1 else "Неизвестно"
            
            if manager.backup_manager_2_id:
                backup_2_stmt = select(Staff_Member).where(Staff_Member.id == manager.backup_manager_2_id)
                backup_2_result = await session.execute(backup_2_stmt)
                backup_2 = backup_2_result.scalar_one_or_none()
                backup_2_name = backup_2.full_name if backup_2 else "Неизвестно"
            
            # Format manager line
            if backup_1_name and backup_2_name:
                # Both backups configured
                line = f"✅ <b>{manager.full_name}</b>\n   Резерв 1: {backup_1_name}\n   Резерв 2: {backup_2_name}"
            elif backup_1_name or backup_2_name:
                # Only one backup configured
                backup_name = backup_1_name or backup_2_name
                line = f"⚠️ <b>{manager.full_name}</b>\n   Резерв: {backup_name}\n   ⚠️ Настроен только один резерв"
            else:
                # No backups configured
                line = f"❌ <b>{manager.full_name}</b>\n   ⚠️ Резервы не настроены"
            
            backup_lines.append(line)
        
        # Build keyboard
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        
        builder.button(
            text="◀️ Назад",
            callback_data=SettingsCallback(action="menu")
        )
        
        # Display manager backups
        if backup_lines:
            backups_list = "\n\n".join(backup_lines)
            backups_text = (
                "👥 <b>Резервы менеджеров</b>\n\n"
                "Просмотр назначений резервных менеджеров.\n\n"
                f"{backups_list}\n\n"
                "ℹ️ Для настройки резервов используйте раздел \"Сотрудники\" → "
                "выберите менеджера → \"Настроить резервы\"."
            )
        else:
            backups_text = (
                "👥 <b>Резервы менеджеров</b>\n\n"
                "В системе нет активных менеджеров.\n\n"
                "ℹ️ Для настройки резервов используйте раздел \"Сотрудники\"."
            )
        
        await callback.message.edit_text(
            backups_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {user_id} accessed manager backup settings")
        
    except Exception as e:
        logger.error(f"Error showing manager backup settings: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при загрузке настроек.",
            show_alert=True
        )
