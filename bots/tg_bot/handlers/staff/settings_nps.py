"""
NPS Configuration Handlers

Handles NPS survey frequency and trigger timing configuration.

Requirements: 5.1, 5.2
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import SettingsCallback
from bots.tg_bot.keyboards.admin_kb import get_nps_settings_keyboard, get_cancel_keyboard
from bots.tg_bot.states import SettingsStates
from database.models import SettingCategory
from services.settings_service import get_settings_by_category, update_setting

logger = logging.getLogger(__name__)

router = Router(name="settings_nps")


@router.callback_query(SettingsCallback.filter(F.action == "edit_nps_frequency"))
async def start_nps_frequency_edit(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    state: FSMContext
) -> None:
    """
    Start NPS frequency editing flow.
    
    Prompts administrator to enter new frequency value in days.
    
    Requirements: 5.1
    """
    await callback.answer()
    
    try:
        setting_key = callback_data.setting_key
        
        # Store setting key in FSM state
        await state.update_data(editing_setting_key=setting_key)
        
        # Set FSM state
        await state.set_state(SettingsStates.entering_nps_frequency)
        
        # Get cancel keyboard
        keyboard = await get_cancel_keyboard(action="settings")
        
        # Prompt for new value
        await callback.message.edit_text(
            "📊 <b>Изменение частоты NPS опросов</b>\n\n"
            "Введите минимальный интервал между опросами в днях (от 1 до 365):\n\n"
            "Например: 30",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"User {callback.from_user.id} started editing NPS frequency: {setting_key}")
        
    except Exception as e:
        logger.error(f"Error starting NPS frequency edit: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка.",
            show_alert=True
        )


@router.message(SettingsStates.entering_nps_frequency)
async def process_nps_frequency(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Process NPS frequency input and save if valid.
    
    Validates input is integer between 1 and 365 days.
    Creates audit log entry on successful save.
    
    Requirements: 5.1, 5.2
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
            
            # Get updated NPS settings
            nps_settings = await get_settings_by_category(session, SettingCategory.NPS)
            
            frequency_days = nps_settings.get("nps_frequency_days", 30)
            trigger_after_payment = nps_settings.get("nps_trigger_after_payment", 10)
            trigger_after_support = nps_settings.get("nps_trigger_after_support", 1)
            
            # Get keyboard with updated values
            keyboard = await get_nps_settings_keyboard(
                frequency_days,
                trigger_after_payment,
                trigger_after_support
            )
            
            # Display success message with updated settings
            nps_text = (
                "✅ <b>Настройка NPS успешно обновлена</b>\n\n"
                "📊 <b>Настройка NPS опросов</b>\n\n"
                f"<b>Частота опросов:</b> {frequency_days} дней\n"
                f"<b>После оплаты:</b> {trigger_after_payment} дней\n"
                f"<b>После поддержки:</b> {trigger_after_support} дней\n\n"
                "Нажмите на параметр для изменения значения."
            )
            
            await message.answer(
                nps_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"User {user_id} updated NPS setting {setting_key} to {input_value}")
        else:
            # Validation failed - show error and prompt again
            await message.answer(
                f"❌ <b>Ошибка валидации</b>\n\n"
                f"{result_message}\n\n"
                "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                parse_mode="HTML"
            )
            
            logger.warning(f"NPS frequency validation failed for user {user_id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing NPS frequency: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при сохранении настройки."
        )
        await state.clear()


@router.callback_query(SettingsCallback.filter(F.action == "edit_nps_trigger"))
async def start_nps_trigger_edit(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    state: FSMContext
) -> None:
    """
    Start NPS trigger timing editing flow.
    
    Prompts administrator to enter new trigger timing value in days.
    
    Requirements: 5.1
    """
    await callback.answer()
    
    try:
        setting_key = callback_data.setting_key
        
        # Store setting key in FSM state
        await state.update_data(editing_setting_key=setting_key)
        
        # Set FSM state
        await state.set_state(SettingsStates.entering_nps_trigger_timing)
        
        # Get cancel keyboard
        keyboard = await get_cancel_keyboard(action="settings")
        
        # Map setting key to display name
        setting_names = {
            "nps_trigger_after_payment": "триггера NPS после оплаты",
            "nps_trigger_after_support": "триггера NPS после поддержки"
        }
        
        setting_name = setting_names.get(setting_key, "триггера NPS")
        
        # Prompt for new value
        await callback.message.edit_text(
            f"📊 <b>Изменение {setting_name}</b>\n\n"
            "Введите количество дней (от 0 до 90):\n\n"
            "Например: 10",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"User {callback.from_user.id} started editing NPS trigger: {setting_key}")
        
    except Exception as e:
        logger.error(f"Error starting NPS trigger edit: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка.",
            show_alert=True
        )


@router.message(SettingsStates.entering_nps_trigger_timing)
async def process_nps_trigger(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Process NPS trigger timing input and save if valid.
    
    Validates input is integer between 0 and 90 days.
    Creates audit log entry on successful save.
    
    Requirements: 5.1, 5.2
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
            
            # Get updated NPS settings
            nps_settings = await get_settings_by_category(session, SettingCategory.NPS)
            
            frequency_days = nps_settings.get("nps_frequency_days", 30)
            trigger_after_payment = nps_settings.get("nps_trigger_after_payment", 10)
            trigger_after_support = nps_settings.get("nps_trigger_after_support", 1)
            
            # Get keyboard with updated values
            keyboard = await get_nps_settings_keyboard(
                frequency_days,
                trigger_after_payment,
                trigger_after_support
            )
            
            # Display success message with updated settings
            nps_text = (
                "✅ <b>Настройка NPS успешно обновлена</b>\n\n"
                "📊 <b>Настройка NPS опросов</b>\n\n"
                f"<b>Частота опросов:</b> {frequency_days} дней\n"
                f"<b>После оплаты:</b> {trigger_after_payment} дней\n"
                f"<b>После поддержки:</b> {trigger_after_support} дней\n\n"
                "Нажмите на параметр для изменения значения."
            )
            
            await message.answer(
                nps_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"User {user_id} updated NPS trigger {setting_key} to {input_value}")
        else:
            # Validation failed - show error and prompt again
            await message.answer(
                f"❌ <b>Ошибка валидации</b>\n\n"
                f"{result_message}\n\n"
                "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                parse_mode="HTML"
            )
            
            logger.warning(f"NPS trigger validation failed for user {user_id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing NPS trigger: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при сохранении настройки."
        )
        await state.clear()
