"""
Escalation Channel Configuration Handlers

Handles escalation channel configuration with test-before-save validation.

Requirements: 3.1, 3.2
"""

import logging

from aiogram import F, Router, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import SettingsCallback
from bots.tg_bot.keyboards.admin_kb import get_escalation_settings_keyboard, get_cancel_keyboard
from bots.tg_bot.states import SettingsStates
from services.settings_service import get_setting, update_setting, test_escalation_channel

logger = logging.getLogger(__name__)

router = Router(name="settings_escalation")


@router.callback_query(SettingsCallback.filter(F.action == "edit_escalation_channel"))
async def start_escalation_channel_edit(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    state: FSMContext
) -> None:
    """
    Start escalation channel editing flow.
    
    Prompts administrator to enter Telegram chat ID.
    
    Requirements: 3.1
    """
    await callback.answer()
    
    try:
        setting_key = callback_data.setting_key
        
        # Store setting key in FSM state
        await state.update_data(editing_setting_key=setting_key)
        
        # Set FSM state
        await state.set_state(SettingsStates.entering_escalation_chat_id)
        
        # Get cancel keyboard
        keyboard = await get_cancel_keyboard(action="settings")
        
        # Map setting key to display name and description
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
        
        info = setting_info.get(setting_key, {
            "name": "канала эскалации",
            "description": "В этот чат будут приходить уведомления об эскалации."
        })
        
        # Prompt for new value
        await callback.message.edit_text(
            f"📢 <b>Изменение {info['name']}</b>\n\n"
            f"{info['description']}\n\n"
            "<b>Как узнать Chat ID:</b>\n"
            "• Перейдите в бота @UserInfoToBot, и поделитесь с ним чатом\n"
            "• Скопируйте Chat ID из ответного сообщения бота\n\n"
            "<b>Требования:</b>\n"
            "• Бот <b>Ассистент сметчика АЙТАТ</b> должен быть добавлен в этот чат\n"
            "• Бот должен иметь право на отправку сообщений\n\n"
            "<b>Формат:</b> -1001234567890\n\n"
            "⚠️ После ввода будет отправлено тестовое сообщение для проверки доступа.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"User {callback.from_user.id} started editing escalation channel: {setting_key}")
        
    except Exception as e:
        logger.error(f"Error starting escalation channel edit: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка.",
            show_alert=True
        )


@router.message(SettingsStates.entering_escalation_chat_id, F.text)
async def process_escalation_channel(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
) -> None:
    """
    Process escalation channel input, test, and save if valid.
    
    Validates chat ID format, sends test message, and saves only if test succeeds.
    Creates audit log entry on successful save.
    
    Requirements: 3.1, 3.2
    """
    try:
        user_id = message.from_user.id
        
        # Get setting key from FSM state
        data = await state.get_data()
        setting_key = data.get("editing_setting_key")
        
        if not setting_key:
            await message.answer("❌ Ошибка: не найден ключ настройки.")
            await state.clear()
            return
        
        # Get input value
        chat_id = message.text.strip()
        
        # First, validate format (will be done by settings_service)
        # Then test the channel and get chat title
        test_success, test_message, chat_title = await test_escalation_channel(bot, chat_id)
        
        if not test_success:
            # Test failed - show error and prompt again
            await message.answer(
                f"❌ <b>Ошибка тестирования канала</b>\n\n"
                f"{test_message}\n\n"
                "Убедитесь, что:\n"
                "• Бот добавлен в чат\n"
                "• Бот имеет права на отправку сообщений\n"
                "• Chat ID указан правильно\n\n"
                "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                parse_mode="HTML"
            )
            
            logger.warning(f"Escalation channel test failed for user {user_id}: {test_message}")
            return
        
        # Store chat title in FSM state for later use
        await state.update_data(chat_title=chat_title)
        
        # Test succeeded - now save the setting with chat title
        success, result_message = await update_setting(
            session=session,
            key=setting_key,
            value=chat_id,
            admin_id=user_id,
            chat_title=chat_title
        )
        
        if success:
            # Clear FSM state
            await state.clear()
            
            # Get updated escalation settings
            manager_channel = await get_setting(session, "escalation_manager_channel")
            duty_channel = await get_setting(session, "escalation_duty_channel")
            
            # Get chat titles from action logs
            from bots.tg_bot.handlers.staff.settings import _get_chat_title_from_logs
            manager_title = await _get_chat_title_from_logs(session, "escalation_manager_channel")
            duty_title = await _get_chat_title_from_logs(session, "escalation_duty_channel")
            
            # Get keyboard with updated values
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
            
            # Display success message with updated settings
            escalation_text = (
                "✅ <b>Канал эскалации успешно обновлен</b>\n\n"
                "📢 <b>Настройка каналов эскалации</b>\n\n"
                f"<b>Канал эскалации менеджеров:</b> {manager_status}\n"
                f"<b>Канал эскалации дежурной:</b> {duty_status}\n\n"
                "Нажмите на параметр для изменения значения."
            )
            
            await message.answer(
                escalation_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"User {user_id} updated escalation channel {setting_key} to {chat_id}")
        else:
            # Validation failed - show error and prompt again
            await message.answer(
                f"❌ <b>Ошибка валидации</b>\n\n"
                f"{result_message}\n\n"
                "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                parse_mode="HTML"
            )
            
            logger.warning(f"Escalation channel validation failed for user {user_id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing escalation channel: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при сохранении настройки."
        )
        await state.clear()
