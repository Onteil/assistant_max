"""
Admin Panel - Settings Handlers for MAX Bot

Consolidated settings management for all system configuration:
- Navigation between settings categories
- Timeout configuration (manager response, duty support)
- Escalation channel configuration (manager, duty)
- Duty support account configuration
- NPS survey settings
- Renewal reminder scheduling
- Manager backup display (view only)
- Settings history

All settings handlers are consolidated in this single file for easier maintenance.

Migrated from Telegram bot to MAX messenger.
Uses replace_message pattern for all callback handlers.

Requirements: 1.1-1.4, 2.1-2.2, 3.1-3.2, 4.1-4.2, 5.1-5.2, 6.1-6.2, 7.1-7.3, 8.1-8.2
"""

import logging
from datetime import datetime

from maxapi.types import MessageCallback, MessageCreated
from maxapi.context import MemoryContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import AdminMenuPayload, SettingsPayload
from bots.max_bot.states import SettingsStates
from database.models import (
    Action_Log,
    ActionType,
    SettingCategory,
    Staff_Member,
    StaffRole,
)
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


# ========== Helper Functions ==========


async def is_admin(session: AsyncSession, max_user_id: int) -> Staff_Member | None:
    """
    Check if user is an administrator and return their record.
    
    Args:
        session: Database session
        max_user_id: MAX user ID
    
    Returns:
        Staff_Member object if user is admin, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == max_user_id,
            Staff_Member.is_active == True,
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking admin status for MAX user {max_user_id}: {e}", exc_info=True)
        return None


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


# ========== Main Settings Menu ==========


async def handle_settings_menu(
    event: MessageCallback,
    payload: AdminMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
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
    
    Uses replace_message pattern.
    
    Requirements: 1.1, 1.2, 1.3, 8.1, 8.2
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к настройкам системы.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Build settings menu keyboard
        buttons = [
            [
                KeyboardButton(
                    text="⏱ Таймауты",
                    payload=SettingsPayload(action="timeouts").pack()
                )
            ],
            [
                KeyboardButton(
                    text="📢 Эскалация",
                    payload=SettingsPayload(action="escalation").pack()
                )
            ],
            # [
            #     KeyboardButton(
            #         text="🌙 Дежурная поддержка",
            #         payload=SettingsPayload(action="duty_support").pack()
            #     )
            # ],
            [
                KeyboardButton(
                    text="📊 NPS настройки",
                    payload=SettingsPayload(action="nps").pack()
                )
            ],
            [
                KeyboardButton(
                    text="🔔 Напоминания",
                    payload=SettingsPayload(action="renewal_reminders").pack()
                )
            ],
            [
                KeyboardButton(
                    text="📜 История",
                    payload=SettingsPayload(action="history").pack()
                )
            ],
            [
                KeyboardButton(
                    text="◀️ Назад в главное меню",
                    payload=AdminMenuPayload(action="back").pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        settings_text = (
            "⚙️ <b>Настройки системы</b>\n\n"
            "Выберите категорию для настройки:\n\n"
            "⏱ <b>Таймауты</b> - время ожидания ответа и эскалации\n"
            "📢 <b>Эскалация</b> - каналы уведомлений об эскалации\n"
            "🌙 <b>Дежурная поддержка</b> - аккаунт для внерабочих часов\n"
            "📊 <b>NPS настройки</b> - частота и триггеры опросов\n"
            "🔔 <b>Напоминания</b> - расписание напоминаний о продлении\n"
            "📜 <b>История</b> - журнал изменений настроек"
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=settings_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} accessed settings menu")
        
    except Exception as e:
        logger.error(f"Error showing settings menu: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке настроек.",
            parse_mode="HTML"
        )


# ========== Timeout Settings ==========


async def handle_timeout_settings(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display timeout configuration screen.
    
    Shows current timeout values for manager response and duty support.
    Uses replace_message pattern.
    
    Requirements: 2.1, 2.2, 8.1, 8.2
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к настройкам системы.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get current timeout values
        timeout_settings = await get_settings_by_category(session, SettingCategory.TIMEOUTS)
        
        manager_timeout = timeout_settings.get('manager_response_timeout', 10)
        duty_timeout = timeout_settings.get('duty_taken_timeout', 10)
        
        # Build keyboard
        buttons = [
            [
                KeyboardButton(
                    text=f"⏱ Таймаут ответа менеджера: {manager_timeout} мин",
                    payload=SettingsPayload(
                        action="edit_timeout",
                        setting_key="manager_response_timeout"
                    ).pack()
                )
            ],
            [
                KeyboardButton(
                    text=f"⏱ Таймаут взятия в работу: {duty_timeout} мин",
                    payload=SettingsPayload(
                        action="edit_timeout",
                        setting_key="duty_taken_timeout"
                    ).pack()
                )
            ],
            [
                KeyboardButton(
                    text="🔄 Сбросить по умолчанию",
                    payload=SettingsPayload(action="reset_timeouts").pack()
                )
            ],
            [
                KeyboardButton(
                    text="◀️ Назад",
                    payload=SettingsPayload(action="menu").pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        timeout_text = (
            "⏱ <b>Настройка таймаутов</b>\n\n"
            "Настройте время ожидания для обработки заявок.\n\n"
            f"<b>Таймаут ответа менеджера:</b> {manager_timeout} мин\n"
            "Время после которого начнется процесс переключения на резервного менеджера 1, "
            "затем на резервного менеджера 2 (если установлены), и только потом эскалация.\n\n"
            f"<b>Таймаут взятия в работу дежурной:</b> {duty_timeout} мин\n"
            "Время ожидания взятия тикета в работу дежурной поддержкой.\n\n"
            "Нажмите на параметр для изменения значения."
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=timeout_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} accessed timeout settings")
        
    except Exception as e:
        logger.error(f"Error showing timeout settings: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке настроек.",
            parse_mode="HTML"
        )


async def handle_edit_timeout_start(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Start timeout value editing flow.
    
    Prompts administrator to enter new timeout value in minutes.
    Uses replace_message pattern.
    
    Requirements: 2.1
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к настройкам системы.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        setting_key = payload.setting_key
        
        # Store setting key in context
        await context.update_data(editing_setting_key=setting_key)
        
        # Set FSM state
        await context.set_state(SettingsStates.entering_timeout_value)
        
        # Map setting key to display name
        setting_names = {
            "manager_response_timeout": "таймаута ответа менеджера",
            "duty_taken_timeout": "таймаута взятия в работу дежурной"
        }
        
        setting_name = setting_names.get(setting_key, "таймаута")
        
        # Build cancel keyboard
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="❌ Отмена",
                        payload=SettingsPayload(action="timeouts").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"⏱ <b>Изменение {setting_name}</b>\n\n"
                "Введите новое значение в минутах (от 1 до 60):\n\n"
                "Например: 15"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started editing timeout: {setting_key}")
        
    except Exception as e:
        logger.error(f"Error starting timeout edit: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )


async def handle_timeout_value_input(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Process timeout value input and save if valid.
    
    Validates input is integer between 1 and 60 minutes.
    Creates audit log entry on successful save.
    
    Requirements: 2.1, 2.2
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к настройкам системы.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Get setting key from context
        data = await context.get_data()
        setting_key = data.get("editing_setting_key")
        
        if not setting_key:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка: не найден ключ настройки.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Get input value
        input_value = event.message.body.text.strip()
        
        # Validate and save
        success, result_message = await update_setting(
            session=session,
            key=setting_key,
            value=input_value,
            admin_id=admin.max_user_id
        )
        
        if success:
            # Clear FSM state
            await context.clear()
            
            # Get updated timeout settings
            timeout_settings = await get_settings_by_category(session, SettingCategory.TIMEOUTS)
            
            manager_timeout = timeout_settings.get('manager_response_timeout', 10)
            duty_timeout = timeout_settings.get('duty_taken_timeout', 10)
            
            # Build keyboard
            buttons = [
                [
                    KeyboardButton(
                        text=f"⏱ Таймаут ответа менеджера: {manager_timeout} мин",
                        payload=SettingsPayload(
                            action="edit_timeout",
                            setting_key="manager_response_timeout"
                        ).pack()
                    )
                ],
                [
                    KeyboardButton(
                        text=f"⏱ Таймаут взятия в работу: {duty_timeout} мин",
                        payload=SettingsPayload(
                            action="edit_timeout",
                            setting_key="duty_taken_timeout"
                        ).pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="🔄 Сбросить по умолчанию",
                        payload=SettingsPayload(action="reset_timeouts").pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="◀️ Назад",
                        payload=SettingsPayload(action="menu").pack()
                    )
                ]
            ]
            
            keyboard = Keyboard(buttons=buttons, inline=True)
            
            timeout_text = (
                "✅ <b>Таймаут успешно обновлен</b>\n\n"
                "⏱ <b>Настройка таймаутов</b>\n\n"
                f"<b>Таймаут ответа менеджера:</b> {manager_timeout} мин\n"
                "Время после которого начнется процесс переключения на резервных менеджеров, затем эскалация.\n\n"
                f"<b>Таймаут взятия в работу дежурной:</b> {duty_timeout} мин\n"
                "Время ожидания взятия тикета в работу дежурной поддержкой.\n\n"
                "Нажмите на параметр для изменения значения."
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=timeout_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Administrator {admin.id} updated timeout {setting_key} to {input_value}")
        else:
            # Validation failed - show error and prompt again
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    f"❌ <b>Ошибка валидации</b>\n\n"
                    f"{result_message}\n\n"
                    "Попробуйте еще раз или нажмите \"Отмена\"."
                ),
                parse_mode="HTML"
            )
            
            logger.warning(f"Timeout validation failed for admin {admin.id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing timeout value: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при сохранении настройки.",
            parse_mode="HTML"
        )
        await context.clear()


# ========== Escalation Channel Settings ==========


# ========== Escalation Channel Settings ==========


async def handle_escalation_settings(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display escalation channel configuration screen.
    
    Shows current escalation channels for manager and duty support.
    Uses replace_message pattern.
    
    Requirements: 3.1, 3.2, 8.1, 8.2
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к настройкам системы.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get current escalation channel values
        manager_channel = await get_setting(session, "escalation_manager_channel")
        duty_channel = await get_setting(session, "escalation_duty_channel")
        
        # Get chat titles from action logs
        manager_title = await _get_chat_title_from_logs(session, "escalation_manager_channel")
        duty_title = await _get_chat_title_from_logs(session, "escalation_duty_channel")
        
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
        
        # Build keyboard
        buttons = [
            [
                KeyboardButton(
                    text=f"📢 Канал менеджеров: {manager_status[:20]}...",
                    payload=SettingsPayload(
                        action="edit_escalation_channel",
                        setting_key="escalation_manager_channel"
                    ).pack()
                )
            ],
            [
                KeyboardButton(
                    text=f"📢 Канал дежурной: {duty_status[:20]}...",
                    payload=SettingsPayload(
                        action="edit_escalation_channel",
                        setting_key="escalation_duty_channel"
                    ).pack()
                )
            ],
            [
                KeyboardButton(
                    text="🔄 Сбросить по умолчанию",
                    payload=SettingsPayload(action="reset_escalation").pack()
                )
            ],
            [
                KeyboardButton(
                    text="◀️ Назад",
                    payload=SettingsPayload(action="menu").pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        escalation_text = (
            "📢 <b>Настройка каналов эскалации</b>\n\n"
            "Настройте MAX чаты для уведомлений об эскалации заявок.\n\n"
            f"<b>Канал эскалации менеджеров:</b> {manager_status}\n"
            "Чат для уведомлений об эскалации заявок менеджеров.\n\n"
            f"<b>Канал эскалации дежурной:</b> {duty_status}\n"
            "Чат для уведомлений об эскалации заявок дежурной поддержки.\n\n"
            "Нажмите на параметр для изменения значения.\n"
            "⚠️ Перед сохранением будет отправлено тестовое сообщение."
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=escalation_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} accessed escalation settings")
        
    except Exception as e:
        logger.error(f"Error showing escalation settings: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке настроек.",
            parse_mode="HTML"
        )


# ========== Duty Support Settings ==========


async def handle_duty_support_settings(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display duty support account configuration screen.
    
    Shows current duty support MAX account.
    Uses replace_message pattern.
    
    Requirements: 4.1, 4.2, 8.1, 8.2
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к настройкам системы.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get current duty support account
        duty_account = await get_setting(session, "duty_support_account")
        
        # Format account display
        account_status = duty_account if duty_account else "❌ Не настроен"
        
        # Build keyboard
        buttons = [
            [
                KeyboardButton(
                    text=f"🌙 Аккаунт дежурной: {account_status}",
                    payload=SettingsPayload(
                        action="edit_duty_account",
                        setting_key="duty_support_account"
                    ).pack()
                )
            ],
            [
                KeyboardButton(
                    text="🔄 Сбросить по умолчанию",
                    payload=SettingsPayload(action="reset_duty_support").pack()
                )
            ],
            [
                KeyboardButton(
                    text="◀️ Назад",
                    payload=SettingsPayload(action="menu").pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        duty_text = (
            "🌙 <b>Настройка дежурной поддержки</b>\n\n"
            "Настройте MAX аккаунт сотрудника дежурной поддержки.\n\n"
            f"<b>Текущий аккаунт:</b> {account_status}\n\n"
            "Заявки, поступающие в нерабочее время, будут направляться "
            "на этот аккаунт.\n\n"
            "Нажмите на параметр для изменения значения."
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=duty_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} accessed duty support settings")
        
    except Exception as e:
        logger.error(f"Error showing duty support settings: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке настроек.",
            parse_mode="HTML"
        )


# ========== NPS Settings ==========


async def handle_nps_settings(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display NPS survey configuration screen.
    
    Shows current NPS settings for frequency and triggers.
    Uses replace_message pattern.
    
    Requirements: 5.1, 5.2, 8.1, 8.2
    """
    chat_id = event.message.recipient.chat_id
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="📊 <b>Настройка NPS опросов</b>\n\nФункционал в разработке.",
        parse_mode="HTML"
    )


async def handle_renewal_reminders_settings(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Display renewal reminder schedule configuration screen. TODO: Implement"""
    chat_id = event.message.recipient.chat_id
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="🔔 <b>Настройка напоминаний о продлении</b>\n\nФункционал в разработке.",
        parse_mode="HTML"
    )


async def handle_settings_history(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Display settings change history. TODO: Implement"""
    chat_id = event.message.recipient.chat_id
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text="📜 <b>История изменений настроек</b>\n\nФункционал в разработке.",
        parse_mode="HTML"
    )
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к настройкам системы.",
                parse_mode="HTML"
            )
            return
        
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        nps_settings = await get_settings_by_category(session, SettingCategory.NPS)
        
        frequency_days = nps_settings.get("nps_frequency_days", 30)
        trigger_after_payment = nps_settings.get("nps_trigger_after_payment", 10)
        trigger_after_support = nps_settings.get("nps_trigger_after_support", 1)
        
        buttons = [
            [KeyboardButton(text=f"📊 Частота опросов: {frequency_days} дней", payload=SettingsPayload(action="edit_nps_frequency", setting_key="nps_frequency_days").pack())],
            [KeyboardButton(text=f"💳 После оплаты: {trigger_after_payment} дней", payload=SettingsPayload(action="edit_nps_trigger", setting_key="nps_trigger_after_payment").pack())],
            [KeyboardButton(text=f"🛠 После поддержки: {trigger_after_support} дней", payload=SettingsPayload(action="edit_nps_trigger", setting_key="nps_trigger_after_support").pack())],
            [KeyboardButton(text="🔄 Сбросить по умолчанию", payload=SettingsPayload(action="reset_nps").pack())],
            [KeyboardButton(text="◀️ Назад", payload=SettingsPayload(action="menu").pack())]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
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
        
        await messenger_adapter.send_message(chat_id=chat_id, text=nps_text, keyboard=keyboard, parse_mode="HTML")
        logger.info(f"Administrator {max_user_id} accessed NPS settings")
        
    except Exception as e:
        logger.error(f"Error showing NPS settings: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при загрузке настроек.", parse_mode="HTML")


# ========== Renewal Reminders Settings ==========


async def handle_renewal_reminders_settings(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Display renewal reminder schedule configuration screen."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            return
        
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        reminder_days = await get_setting(session, "renewal_reminder_days")
        if not isinstance(reminder_days, list):
            reminder_days = [30, 7]
        
        reminder_list = ", ".join(str(d) for d in sorted(reminder_days, reverse=True))
        
        buttons = [
            [KeyboardButton(text="➕ Добавить напоминание", payload=SettingsPayload(action="add_renewal_reminder").pack())]
        ]
        
        for days in sorted(reminder_days, reverse=True):
            buttons.append([KeyboardButton(text=f"❌ Удалить: за {days} дней", payload=SettingsPayload(action="remove_renewal_reminder", page=days).pack())])
        
        buttons.extend([
            [KeyboardButton(text="🔄 Сбросить по умолчанию", payload=SettingsPayload(action="reset_renewal_reminders").pack())],
            [KeyboardButton(text="◀️ Назад", payload=SettingsPayload(action="menu").pack())]
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        renewal_text = (
            "🔔 <b>Настройка напоминаний о продлении</b>\n\n"
            "Настройте расписание напоминаний о продлении подписки.\n\n"
            f"<b>Текущее расписание:</b> за {reminder_list} дней до истечения\n\n"
            "Пользователи будут получать напоминания о необходимости продления "
            "подписки за указанное количество дней до истечения срока.\n\n"
            "Используйте кнопки для добавления или удаления напоминаний.\n"
            "⚠️ Должно быть настроено минимум одно напоминание."
        )
        
        await messenger_adapter.send_message(chat_id=chat_id, text=renewal_text, keyboard=keyboard, parse_mode="HTML")
        logger.info(f"Administrator {max_user_id} accessed renewal reminder settings")
        
    except Exception as e:
        logger.error(f"Error showing renewal reminder settings: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при загрузке настроек.", parse_mode="HTML")


# ========== Settings History ==========


async def handle_settings_history(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Display recent settings changes with pagination."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            return
        
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        page = payload.page if payload.page is not None else 0
        page_size = 10
        
        logs, total_count = await get_settings_history(session=session, limit=page_size, offset=page * page_size)
        
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        
        if logs:
            history_lines = []
            for log in logs:
                timestamp = log.action_timestamp.strftime("%d.%m.%Y %H:%M")
                admin_name = log.staff.full_name if log.staff else "Неизвестно"
                details = log.action_details or {}
                setting_key = details.get("setting_key", "Неизвестно")
                old_value = details.get("old_value", "—")
                new_value = details.get("new_value", "—")
                
                entry = (
                    f"📅 <b>{timestamp}</b>\n"
                    f"👤 {admin_name}\n"
                    f"⚙️ Изменено: <b>{setting_key}</b>\n"
                    f"📝 Было: {old_value}\n"
                    f"📝 Стало: {new_value}"
                )
                history_lines.append(entry)
            
            history_text = (
                "📜 <b>История изменений настроек</b>\n\n"
                f"Страница {page + 1} из {total_pages}\n"
                f"Всего записей: {total_count}\n\n"
                + "\n\n".join(history_lines)
            )
        else:
            history_text = "📜 <b>История изменений настроек</b>\n\nИстория изменений пуста."
        
        buttons = []
        if total_pages > 1:
            nav_row = []
            if page > 0:
                nav_row.append(KeyboardButton(text="⬅️ Назад", payload=SettingsPayload(action="history", page=page - 1).pack()))
            if page < total_pages - 1:
                nav_row.append(KeyboardButton(text="Вперед ➡️", payload=SettingsPayload(action="history", page=page + 1).pack()))
            if nav_row:
                buttons.append(nav_row)
        
        buttons.append([KeyboardButton(text="◀️ Назад", payload=SettingsPayload(action="menu").pack())])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(chat_id=chat_id, text=history_text, keyboard=keyboard, parse_mode="HTML")
        logger.info(f"Administrator {max_user_id} viewed settings history (page {page + 1})")
        
    except Exception as e:
        logger.error(f"Error showing settings history: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при загрузке истории.", parse_mode="HTML")



# ========== NPS Input Handlers ==========


async def handle_edit_nps_frequency_start(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Start NPS frequency editing flow."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            return
        
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        await context.update_data(editing_setting_key=payload.setting_key)
        await context.set_state(SettingsStates.entering_nps_frequency)
        
        keyboard = Keyboard(buttons=[[KeyboardButton(text="❌ Отмена", payload=SettingsPayload(action="nps").pack())]], inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "📊 <b>Изменение частоты NPS опросов</b>\n\n"
                "Введите минимальный интервал между опросами в днях (от 1 до 365):\n\n"
                "Например: 30"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started editing NPS frequency")
        
    except Exception as e:
        logger.error(f"Error starting NPS frequency edit: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка.", parse_mode="HTML")


async def handle_nps_frequency_input(event: MessageCreated, context: MemoryContext, session: AsyncSession, messenger_adapter: MAXMessengerAdapter) -> None:
    """Process NPS frequency input (1-365 days)."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            await context.clear()
            return
        
        data = await context.get_data()
        setting_key = data.get("editing_setting_key")
        
        if not setting_key:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ Ошибка: не найден ключ настройки.", parse_mode="HTML")
            await context.clear()
            return
        
        input_value = event.message.body.text.strip()
        
        success, result_message = await update_setting(session=session, key=setting_key, value=input_value, admin_id=admin.max_user_id)
        
        if success:
            await context.clear()
            
            nps_settings = await get_settings_by_category(session, SettingCategory.NPS)
            frequency_days = nps_settings.get("nps_frequency_days", 30)
            trigger_after_payment = nps_settings.get("nps_trigger_after_payment", 10)
            trigger_after_support = nps_settings.get("nps_trigger_after_support", 1)
            
            buttons = [
                [KeyboardButton(text=f"📊 Частота опросов: {frequency_days} дней", payload=SettingsPayload(action="edit_nps_frequency", setting_key="nps_frequency_days").pack())],
                [KeyboardButton(text=f"💳 После оплаты: {trigger_after_payment} дней", payload=SettingsPayload(action="edit_nps_trigger", setting_key="nps_trigger_after_payment").pack())],
                [KeyboardButton(text=f"🛠 После поддержки: {trigger_after_support} дней", payload=SettingsPayload(action="edit_nps_trigger", setting_key="nps_trigger_after_support").pack())],
                [KeyboardButton(text="🔄 Сбросить по умолчанию", payload=SettingsPayload(action="reset_nps").pack())],
                [KeyboardButton(text="◀️ Назад", payload=SettingsPayload(action="menu").pack())]
            ]
            
            keyboard = Keyboard(buttons=buttons, inline=True)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "✅ <b>Настройка NPS успешно обновлена</b>\n\n"
                    "📊 <b>Настройка NPS опросов</b>\n\n"
                    f"<b>Частота опросов:</b> {frequency_days} дней\n"
                    f"<b>После оплаты:</b> {trigger_after_payment} дней\n"
                    f"<b>После поддержки:</b> {trigger_after_support} дней\n\n"
                    "Нажмите на параметр для изменения значения."
                ),
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Administrator {admin.id} updated NPS frequency to {input_value}")
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Ошибка валидации</b>\n\n{result_message}\n\nПопробуйте еще раз или нажмите \"Отмена\".",
                parse_mode="HTML"
            )
            logger.warning(f"NPS frequency validation failed for admin {admin.id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing NPS frequency: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при сохранении настройки.", parse_mode="HTML")
        await context.clear()


async def handle_edit_nps_trigger_start(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Start NPS trigger timing editing flow."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            return
        
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        setting_key = payload.setting_key
        await context.update_data(editing_setting_key=setting_key)
        await context.set_state(SettingsStates.entering_nps_trigger_timing)
        
        setting_names = {
            "nps_trigger_after_payment": "триггера NPS после оплаты",
            "nps_trigger_after_support": "триггера NPS после поддержки"
        }
        setting_name = setting_names.get(setting_key, "триггера NPS")
        
        keyboard = Keyboard(buttons=[[KeyboardButton(text="❌ Отмена", payload=SettingsPayload(action="nps").pack())]], inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=f"📊 <b>Изменение {setting_name}</b>\n\nВведите количество дней (от 0 до 90):\n\nНапример: 10",
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started editing NPS trigger: {setting_key}")
        
    except Exception as e:
        logger.error(f"Error starting NPS trigger edit: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка.", parse_mode="HTML")


async def handle_nps_trigger_input(event: MessageCreated, context: MemoryContext, session: AsyncSession, messenger_adapter: MAXMessengerAdapter) -> None:
    """Process NPS trigger timing input (0-90 days)."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            await context.clear()
            return
        
        data = await context.get_data()
        setting_key = data.get("editing_setting_key")
        
        if not setting_key:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ Ошибка: не найден ключ настройки.", parse_mode="HTML")
            await context.clear()
            return
        
        input_value = event.message.body.text.strip()
        
        success, result_message = await update_setting(session=session, key=setting_key, value=input_value, admin_id=admin.max_user_id)
        
        if success:
            await context.clear()
            
            nps_settings = await get_settings_by_category(session, SettingCategory.NPS)
            frequency_days = nps_settings.get("nps_frequency_days", 30)
            trigger_after_payment = nps_settings.get("nps_trigger_after_payment", 10)
            trigger_after_support = nps_settings.get("nps_trigger_after_support", 1)
            
            buttons = [
                [KeyboardButton(text=f"📊 Частота опросов: {frequency_days} дней", payload=SettingsPayload(action="edit_nps_frequency", setting_key="nps_frequency_days").pack())],
                [KeyboardButton(text=f"💳 После оплаты: {trigger_after_payment} дней", payload=SettingsPayload(action="edit_nps_trigger", setting_key="nps_trigger_after_payment").pack())],
                [KeyboardButton(text=f"🛠 После поддержки: {trigger_after_support} дней", payload=SettingsPayload(action="edit_nps_trigger", setting_key="nps_trigger_after_support").pack())],
                [KeyboardButton(text="🔄 Сбросить по умолчанию", payload=SettingsPayload(action="reset_nps").pack())],
                [KeyboardButton(text="◀️ Назад", payload=SettingsPayload(action="menu").pack())]
            ]
            
            keyboard = Keyboard(buttons=buttons, inline=True)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "✅ <b>Настройка NPS успешно обновлена</b>\n\n"
                    "📊 <b>Настройка NPS опросов</b>\n\n"
                    f"<b>Частота опросов:</b> {frequency_days} дней\n"
                    f"<b>После оплаты:</b> {trigger_after_payment} дней\n"
                    f"<b>После поддержки:</b> {trigger_after_support} дней\n\n"
                    "Нажмите на параметр для изменения значения."
                ),
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Administrator {admin.id} updated NPS trigger {setting_key} to {input_value}")
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Ошибка валидации</b>\n\n{result_message}\n\nПопробуйте еще раз или нажмите \"Отмена\".",
                parse_mode="HTML"
            )
            logger.warning(f"NPS trigger validation failed for admin {admin.id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing NPS trigger: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при сохранении настройки.", parse_mode="HTML")
        await context.clear()


# ========== Renewal Reminder Input Handlers ==========


async def handle_add_renewal_reminder_start(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Start adding new renewal reminder flow."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            return
        
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        await context.set_state(SettingsStates.entering_renewal_reminder_days)
        
        keyboard = Keyboard(buttons=[[KeyboardButton(text="❌ Отмена", payload=SettingsPayload(action="renewal_reminders").pack())]], inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "🔔 <b>Добавление напоминания о продлении</b>\n\n"
                "Введите за сколько дней до истечения подписки отправлять напоминание (от 1 до 365):\n\n"
                "Например: 14"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started adding renewal reminder")
        
    except Exception as e:
        logger.error(f"Error starting add renewal reminder: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка.", parse_mode="HTML")


async def handle_renewal_reminder_input(event: MessageCreated, context: MemoryContext, session: AsyncSession, messenger_adapter: MAXMessengerAdapter) -> None:
    """Process renewal reminder days input (1-365 days)."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            await context.clear()
            return
        
        input_value = event.message.body.text.strip()
        
        # Validate input is integer
        try:
            new_days = int(input_value)
            if new_days < 1 or new_days > 365:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ <b>Ошибка валидации</b>\n\nЗначение должно быть от 1 до 365 дней.\n\nПопробуйте еще раз или нажмите \"Отмена\".",
                    parse_mode="HTML"
                )
                return
        except ValueError:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ <b>Ошибка валидации</b>\n\nЗначение должно быть числом.\n\nПопробуйте еще раз или нажмите \"Отмена\".",
                parse_mode="HTML"
            )
            return
        
        # Get current reminder schedule
        current_reminders = await get_setting(session, "renewal_reminder_days")
        if not isinstance(current_reminders, list):
            current_reminders = [30, 7]
        
        # Check if this value already exists
        if new_days in current_reminders:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Ошибка</b>\n\nНапоминание за {new_days} дней уже существует.\n\nПопробуйте другое значение или нажмите \"Отмена\".",
                parse_mode="HTML"
            )
            return
        
        # Add new reminder to schedule
        import json
        updated_reminders = current_reminders + [new_days]
        
        success, result_message = await update_setting(
            session=session,
            key="renewal_reminder_days",
            value=json.dumps(updated_reminders),
            admin_id=admin.max_user_id
        )
        
        if success:
            await context.clear()
            
            reminder_list = ", ".join(str(d) for d in sorted(updated_reminders, reverse=True))
            
            buttons = [[KeyboardButton(text="➕ Добавить напоминание", payload=SettingsPayload(action="add_renewal_reminder").pack())]]
            
            for days in sorted(updated_reminders, reverse=True):
                buttons.append([KeyboardButton(text=f"❌ Удалить: за {days} дней", payload=SettingsPayload(action="remove_renewal_reminder", page=days).pack())])
            
            buttons.extend([
                [KeyboardButton(text="🔄 Сбросить по умолчанию", payload=SettingsPayload(action="reset_renewal_reminders").pack())],
                [KeyboardButton(text="◀️ Назад", payload=SettingsPayload(action="menu").pack())]
            ])
            
            keyboard = Keyboard(buttons=buttons, inline=True)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "✅ <b>Напоминание успешно добавлено</b>\n\n"
                    "🔔 <b>Настройка напоминаний о продлении</b>\n\n"
                    f"<b>Текущее расписание:</b> за {reminder_list} дней до истечения\n\n"
                    "Используйте кнопки для добавления или удаления напоминаний."
                ),
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Administrator {admin.id} added renewal reminder: {new_days} days")
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Ошибка сохранения</b>\n\n{result_message}",
                parse_mode="HTML"
            )
            logger.error(f"Failed to save renewal reminder for admin {admin.id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing renewal reminder days: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при сохранении настройки.", parse_mode="HTML")
        await context.clear()


async def handle_remove_renewal_reminder(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Remove renewal reminder from schedule."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            return
        
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        days_to_remove = payload.page  # Using page field to store days value
        
        if days_to_remove is None:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ Ошибка: не указаны дни для удаления.", parse_mode="HTML")
            return
        
        # Get current reminder schedule
        current_reminders = await get_setting(session, "renewal_reminder_days")
        if not isinstance(current_reminders, list):
            current_reminders = [30, 7]
        
        # Check minimum constraint
        if len(current_reminders) <= 1:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Нельзя удалить последнее напоминание.\nДолжно быть настроено минимум одно напоминание.",
                parse_mode="HTML"
            )
            logger.warning(f"Administrator {admin.id} attempted to remove last renewal reminder")
            return
        
        # Remove the specified reminder
        if days_to_remove in current_reminders:
            updated_reminders = [d for d in current_reminders if d != days_to_remove]
        else:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ Напоминание не найдено в расписании.", parse_mode="HTML")
            return
        
        # Save updated schedule
        import json
        success, result_message = await update_setting(
            session=session,
            key="renewal_reminder_days",
            value=json.dumps(updated_reminders),
            admin_id=admin.max_user_id
        )
        
        if success:
            reminder_list = ", ".join(str(d) for d in sorted(updated_reminders, reverse=True))
            
            buttons = [[KeyboardButton(text="➕ Добавить напоминание", payload=SettingsPayload(action="add_renewal_reminder").pack())]]
            
            for days in sorted(updated_reminders, reverse=True):
                buttons.append([KeyboardButton(text=f"❌ Удалить: за {days} дней", payload=SettingsPayload(action="remove_renewal_reminder", page=days).pack())])
            
            buttons.extend([
                [KeyboardButton(text="🔄 Сбросить по умолчанию", payload=SettingsPayload(action="reset_renewal_reminders").pack())],
                [KeyboardButton(text="◀️ Назад", payload=SettingsPayload(action="menu").pack())]
            ])
            
            keyboard = Keyboard(buttons=buttons, inline=True)
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "✅ <b>Напоминание успешно удалено</b>\n\n"
                    "🔔 <b>Настройка напоминаний о продлении</b>\n\n"
                    f"<b>Текущее расписание:</b> за {reminder_list} дней до истечения\n\n"
                    "Используйте кнопки для добавления или удаления напоминаний."
                ),
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Administrator {admin.id} removed renewal reminder: {days_to_remove} days")
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка сохранения: {result_message}",
                parse_mode="HTML"
            )
            logger.error(f"Failed to remove renewal reminder for admin {admin.id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error removing renewal reminder: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при удалении напоминания.", parse_mode="HTML")



# ========== Reset Handlers ==========


async def handle_reset_timeouts(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Reset timeout settings to default values."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            return
        
        # Reset both timeout settings
        for key in ["manager_response_timeout", "duty_taken_timeout"]:
            await reset_setting(session=session, key=key, admin_id=admin.max_user_id)
        
        # Show updated timeout settings
        await handle_timeout_settings(event, payload, context, session, messenger_adapter)
        
        logger.info(f"Administrator {admin.id} reset timeout settings")
        
    except Exception as e:
        logger.error(f"Error resetting timeouts: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при сбросе настроек.", parse_mode="HTML")


async def handle_reset_nps(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Reset NPS settings to default values."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            return
        
        # Reset all NPS settings
        for key in ["nps_frequency_days", "nps_trigger_after_payment", "nps_trigger_after_support"]:
            await reset_setting(session=session, key=key, admin_id=admin.max_user_id)
        
        # Show updated NPS settings
        await handle_nps_settings(event, payload, context, session, messenger_adapter)
        
        logger.info(f"Administrator {admin.id} reset NPS settings")
        
    except Exception as e:
        logger.error(f"Error resetting NPS: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при сбросе настроек.", parse_mode="HTML")


async def handle_reset_renewal_reminders(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Reset renewal reminder schedule to default values."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            return
        
        await reset_setting(session=session, key="renewal_reminder_days", admin_id=admin.max_user_id)
        
        # Show updated renewal reminders settings
        await handle_renewal_reminders_settings(event, payload, context, session, messenger_adapter)
        
        logger.info(f"Administrator {admin.id} reset renewal reminder settings")
        
    except Exception as e:
        logger.error(f"Error resetting renewal reminders: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при сбросе настроек.", parse_mode="HTML")


async def handle_reset_escalation(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Reset escalation channel settings to default values."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            return
        
        # Reset both escalation channels
        for key in ["escalation_manager_channel", "escalation_duty_channel"]:
            await reset_setting(session=session, key=key, admin_id=admin.max_user_id)
        
        # Show updated escalation settings
        await handle_escalation_settings(event, payload, context, session, messenger_adapter)
        
        logger.info(f"Administrator {admin.id} reset escalation settings")
        
    except Exception as e:
        logger.error(f"Error resetting escalation: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при сбросе настроек.", parse_mode="HTML")


async def handle_reset_duty_support(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Reset duty support account setting to default value."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            return
        
        await reset_setting(session=session, key="duty_support_account", admin_id=admin.max_user_id)
        
        # Show updated duty support settings
        await handle_duty_support_settings(event, payload, context, session, messenger_adapter)
        
        logger.info(f"Administrator {admin.id} reset duty support settings")
        
    except Exception as e:
        logger.error(f"Error resetting duty support: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при сбросе настроек.", parse_mode="HTML")


# ========== Escalation Channel Editing ==========


async def handle_edit_escalation_channel_start(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Start escalation channel editing flow."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            return
        
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        setting_key = payload.setting_key
        await context.update_data(editing_setting_key=setting_key)
        await context.set_state(SettingsStates.entering_escalation_chat_id)
        
        setting_info = {
            "escalation_manager_channel": {
                "name": "канала эскалации менеджеров",
                "description": "В этот чат будут приходить уведомления об эскалации обращений к менеджерам."
            },
            "escalation_duty_channel": {
                "name": "канала эскалации дежурной",
                "description": "В этот чат будут приходить уведомления об эскалации обращений к дежурной поддержке."
            }
        }
        
        info = setting_info.get(setting_key, {"name": "канала эскалации", "description": "В этот чат будут приходить уведомления об эскалации."})
        
        keyboard = Keyboard(buttons=[[KeyboardButton(text="❌ Отмена", payload=SettingsPayload(action="escalation").pack())]], inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"📢 <b>Изменение {info['name']}</b>\n\n"
                f"{info['description']}\n\n"
                "<b>Как узнать Chat ID:</b>\n"
                "1️⃣ Добавьте бота в групповой чат\n"
                "2️⃣ Отправьте команду <code>/get_chat_id</code> в этом чате\n"
                "3️⃣ Скопируйте Chat ID из ответного сообщения бота\n\n"
                "<b>Требования:</b>\n"
                "• Бот должен быть добавлен в этот чат\n"
                "• Бот должен иметь право на отправку сообщений\n\n"
                "<b>Формат:</b> <code>-71826453867944</code> (отрицательное число для групповых чатов)\n\n"
                "⚠️ После ввода будет отправлено тестовое сообщение для проверки доступа."
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started editing escalation channel: {setting_key}")
        
    except Exception as e:
        logger.error(f"Error starting escalation channel edit: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка.", parse_mode="HTML")


async def handle_escalation_channel_input(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Process escalation channel input, test, and save if valid."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            await context.clear()
            return
        
        data = await context.get_data()
        setting_key = data.get("editing_setting_key")
        
        if not setting_key:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ Ошибка: не найден ключ настройки.", parse_mode="HTML")
            await context.clear()
            return
        
        chat_id_input = event.message.body.text.strip()
        
        # Test the channel
        max_bot = messenger_adapter.bot
        test_success, test_message, chat_title = await test_escalation_channel(max_bot, chat_id_input)
        
        if not test_success:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    f"❌ <b>Ошибка тестирования канала</b>\n\n"
                    f"{test_message}\n\n"
                    "Убедитесь, что:\n"
                    "• Бот добавлен в чат\n"
                    "• Бот имеет права на отправку сообщений\n"
                    "• Chat ID указан правильно\n\n"
                    "Попробуйте еще раз или нажмите \"Отмена\"."
                ),
                parse_mode="HTML"
            )
            logger.warning(f"Escalation channel test failed for admin {admin.id}: {test_message}")
            return
        
        # Save the setting
        success, result_message = await update_setting(
            session=session,
            key=setting_key,
            value=chat_id_input,
            admin_id=admin.max_user_id,
            chat_title=chat_title
        )
        
        if success:
            await context.clear()
            
            # Get updated escalation channel values
            manager_channel = await get_setting(session, "escalation_manager_channel")
            duty_channel = await get_setting(session, "escalation_duty_channel")
            
            # Get chat titles from action logs
            manager_title = await _get_chat_title_from_logs(session, "escalation_manager_channel")
            duty_title = await _get_chat_title_from_logs(session, "escalation_duty_channel")
            
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
            
            # Build keyboard
            buttons = [
                [
                    KeyboardButton(
                        text=f"💼 Канал менеджеров: {manager_status[:30]}...",
                        payload=SettingsPayload(
                            action="edit_escalation_channel",
                            setting_key="escalation_manager_channel"
                        ).pack()
                    )
                ],
                [
                    KeyboardButton(
                        text=f"🛠 Канал дежурной: {duty_status[:30]}...",
                        payload=SettingsPayload(
                            action="edit_escalation_channel",
                            setting_key="escalation_duty_channel"
                        ).pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="🔄 Сбросить по умолчанию",
                        payload=SettingsPayload(action="reset_escalation").pack()
                    )
                ],
                [
                    KeyboardButton(
                        text="◀️ Назад",
                        payload=SettingsPayload(action="menu").pack()
                    )
                ]
            ]
            
            keyboard = Keyboard(buttons=buttons, inline=True)
            
            escalation_text = (
                "✅ <b>Канал эскалации успешно обновлен</b>\n\n"
                "📢 <b>Настройка каналов эскалации</b>\n\n"
                f"<b>Канал менеджеров:</b> {manager_status}\n"
                "Канал для эскалации заявок на счета и продления.\n\n"
                f"<b>Канал дежурной поддержки:</b> {duty_status}\n"
                "Канал для эскалации заявок техподдержки.\n\n"
                "Нажмите на канал для изменения или тестирования."
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=escalation_text,
                keyboard=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"Administrator {admin.id} updated escalation channel {setting_key} to {chat_id_input}")
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Ошибка валидации</b>\n\n{result_message}\n\nПопробуйте еще раз или нажмите \"Отмена\".",
                parse_mode="HTML"
            )
            logger.warning(f"Escalation channel validation failed for admin {admin.id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing escalation channel: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при сохранении настройки.", parse_mode="HTML")
        await context.clear()


# ========== Duty Support Account Editing ==========


async def handle_edit_duty_account_start(
    event: MessageCallback,
    payload: SettingsPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Start duty support account editing flow."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            return
        
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        await context.update_data(editing_setting_key=payload.setting_key)
        await context.set_state(SettingsStates.entering_duty_account_id)
        
        keyboard = Keyboard(buttons=[[KeyboardButton(text="❌ Отмена", payload=SettingsPayload(action="duty_support").pack())]], inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "🌙 <b>Изменение аккаунта дежурной поддержки</b>\n\n"
                "Введите MAX User ID сотрудника:\n\n"
                "Формат: 123456789\n\n"
                "⚠️ User ID должен соответствовать активному сотруднику в системе."
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started editing duty account")
        
    except Exception as e:
        logger.error(f"Error starting duty account edit: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка.", parse_mode="HTML")


async def handle_duty_account_input(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """Process duty account input and save if valid."""
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    try:
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ У вас нет доступа к настройкам системы.", parse_mode="HTML")
            await context.clear()
            return
        
        data = await context.get_data()
        setting_key = data.get("editing_setting_key")
        
        if not setting_key:
            await messenger_adapter.send_message(chat_id=chat_id, text="❌ Ошибка: не найден ключ настройки.", parse_mode="HTML")
            await context.clear()
            return
        
        duty_user_id = event.message.body.text.strip()
        
        # Validate user ID is a positive integer
        try:
            duty_user_id_int = int(duty_user_id)
            if duty_user_id_int <= 0:
                await messenger_adapter.send_message(
                    chat_id=chat_id,
                    text="❌ <b>Ошибка валидации</b>\n\nUser ID должен быть положительным числом.\n\nПопробуйте еще раз или нажмите \"Отмена\".",
                    parse_mode="HTML"
                )
                return
        except ValueError:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ <b>Ошибка валидации</b>\n\nUser ID должен быть числом.\n\nПопробуйте еще раз или нажмите \"Отмена\".",
                parse_mode="HTML"
            )
            return
        
        # Verify user ID corresponds to active staff member
        stmt = select(Staff_Member).where(
            Staff_Member.max_user_id == duty_user_id_int,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        staff_member = result.scalar_one_or_none()
        
        if not staff_member:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    "❌ <b>Ошибка валидации</b>\n\n"
                    "User ID не соответствует активному сотруднику в системе.\n\n"
                    "Убедитесь, что:\n"
                    "• Сотрудник добавлен в систему\n"
                    "• Сотрудник активен\n"
                    "• User ID указан правильно\n\n"
                    "Попробуйте еще раз или нажмите \"Отмена\"."
                ),
                parse_mode="HTML"
            )
            logger.warning(f"Duty account validation failed: user_id {duty_user_id} not found or inactive")
            return
        
        # Save the setting
        success, result_message = await update_setting(
            session=session,
            key=setting_key,
            value=duty_user_id,
            admin_id=admin.max_user_id
        )
        
        if success:
            await context.clear()
            
            # Show updated duty support settings
            await handle_duty_support_settings(
                event=event,
                payload=SettingsPayload(action="duty_support"),
                context=context,
                session=session,
                messenger_adapter=messenger_adapter
            )
            
            logger.info(f"Administrator {admin.id} updated duty account to {duty_user_id} ({staff_member.full_name})")
        else:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Ошибка валидации</b>\n\n{result_message}\n\nПопробуйте еще раз или нажмите \"Отмена\".",
                parse_mode="HTML"
            )
            logger.warning(f"Duty account validation failed for admin {admin.id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing duty account: {e}", exc_info=True)
        await messenger_adapter.send_message(chat_id=chat_id, text="❌ Произошла ошибка при сохранении настройки.", parse_mode="HTML")
        await context.clear()
