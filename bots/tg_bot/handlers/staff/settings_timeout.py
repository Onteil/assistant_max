"""
Timeout Configuration Handlers

Handles timeout value configuration for escalation triggers.

Requirements: 2.1, 2.2
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import SettingsCallback
from bots.tg_bot.keyboards.admin_kb import get_timeout_settings_keyboard, get_cancel_keyboard
from bots.tg_bot.states import SettingsStates
from database.models import SettingCategory
from services.settings_service import get_settings_by_category, update_setting

logger = logging.getLogger(__name__)

router = Router(name="settings_timeout")


@router.callback_query(SettingsCallback.filter(F.action == "edit_timeout"))
async def start_timeout_edit(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    state: FSMContext
) -> None:
    """
    Start timeout value editing flow.
    
    Prompts administrator to enter new timeout value in minutes.
    
    Requirements: 2.1
    """
    await callback.answer()
    
    try:
        setting_key = callback_data.setting_key
        
        # Store setting key in FSM state
        await state.update_data(editing_setting_key=setting_key)
        
        # Set FSM state
        await state.set_state(SettingsStates.entering_timeout_value)
        
        # Get cancel keyboard
        keyboard = await get_cancel_keyboard(action="settings")
        
        # Map setting key to display name
        setting_names = {
            "manager_response_timeout": "таймаута ответа менеджера",
            "duty_taken_timeout": "таймаута взятия в работу дежурной"
        }
        
        setting_name = setting_names.get(setting_key, "таймаута")
        
        # Prompt for new value
        await callback.message.edit_text(
            f"⏱ <b>Изменение {setting_name}</b>\n\n"
            "Введите новое значение в минутах (от 1 до 60):\n\n"
            "Например: 15",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"User {callback.from_user.id} started editing timeout: {setting_key}")
        
    except Exception as e:
        logger.error(f"Error starting timeout edit: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка.",
            show_alert=True
        )


@router.message(SettingsStates.entering_timeout_value)
async def process_timeout_value(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Process timeout value input and save if valid.
    
    Validates input is integer between 1 and 60 minutes.
    Creates audit log entry on successful save.
    
    Requirements: 2.1, 2.2
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
        input_value = message.text.strip()
        
        # Validate and save
        success, result_message = await update_setting(
            session=session,
            key=setting_key,
            value=input_value,
            admin_id=user_id
        )
        
        if success:
            # Clear FSM state
            await state.clear()
            
            # Get updated timeout settings
            timeout_settings = await get_settings_by_category(session, SettingCategory.TIMEOUTS)
            
            # Get keyboard with updated values
            keyboard = await get_timeout_settings_keyboard(timeout_settings)
            
            # Display success message with updated settings
            timeout_text = (
                "✅ <b>Таймаут успешно обновлен</b>\n\n"
                "⏱ <b>Настройка таймаутов</b>\n\n"
                f"<b>Таймаут ответа менеджера:</b> {timeout_settings.get('manager_response_timeout', 10)} мин\n"
                f"<b>Таймаут взятия в работу дежурной:</b> {timeout_settings.get('duty_taken_timeout', 10)} мин\n\n"
                "Нажмите на параметр для изменения значения."
            )
            
            await message.answer(
                timeout_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"User {user_id} updated timeout {setting_key} to {input_value}")
        else:
            # Validation failed - show error and prompt again
            await message.answer(
                f"❌ <b>Ошибка валидации</b>\n\n"
                f"{result_message}\n\n"
                "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                parse_mode="HTML"
            )
            
            logger.warning(f"Timeout validation failed for user {user_id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing timeout value: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при сохранении настройки."
        )
        await state.clear()
