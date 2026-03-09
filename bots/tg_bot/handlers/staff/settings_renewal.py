"""
Renewal Reminder Configuration Handlers

Handles renewal reminder schedule configuration with add/remove functionality.

Requirements: 6.1, 6.2
"""

import json
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import SettingsCallback
from bots.tg_bot.keyboards.admin_kb import get_renewal_reminders_keyboard, get_cancel_keyboard
from bots.tg_bot.states import SettingsStates
from services.settings_service import get_setting, update_setting

logger = logging.getLogger(__name__)

router = Router(name="settings_renewal")


@router.callback_query(SettingsCallback.filter(F.action == "add_renewal_reminder"))
async def add_renewal_reminder(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """
    Start adding new renewal reminder flow.
    
    Prompts administrator to enter days before expiration.
    
    Requirements: 6.1
    """
    await callback.answer()
    
    try:
        # Set FSM state
        await state.set_state(SettingsStates.entering_renewal_reminder_days)
        
        # Get cancel keyboard
        keyboard = await get_cancel_keyboard(action="settings")
        
        # Prompt for new value
        await callback.message.edit_text(
            "🔔 <b>Добавление напоминания о продлении</b>\n\n"
            "Введите за сколько дней до истечения подписки отправлять напоминание (от 1 до 365):\n\n"
            "Например: 14",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"User {callback.from_user.id} started adding renewal reminder")
        
    except Exception as e:
        logger.error(f"Error starting add renewal reminder: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка.",
            show_alert=True
        )


@router.message(SettingsStates.entering_renewal_reminder_days)
async def process_renewal_reminder_days(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Process renewal reminder days input and add to schedule if valid.
    
    Validates input is integer between 1 and 365 days.
    Adds to existing reminder schedule.
    Creates audit log entry on successful save.
    
    Requirements: 6.1, 6.2
    """
    try:
        user_id = message.from_user.id
        
        # Get input value
        input_value = message.text.strip()
        
        # Validate input is integer
        try:
            new_days = int(input_value)
            if new_days < 1 or new_days > 365:
                await message.answer(
                    "❌ <b>Ошибка валидации</b>\n\n"
                    "Значение должно быть от 1 до 365 дней.\n\n"
                    "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                    parse_mode="HTML"
                )
                return
        except ValueError:
            await message.answer(
                "❌ <b>Ошибка валидации</b>\n\n"
                "Значение должно быть числом.\n\n"
                "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                parse_mode="HTML"
            )
            return
        
        # Get current reminder schedule
        current_reminders = await get_setting(session, "renewal_reminder_days")
        
        # Ensure it's a list
        if not isinstance(current_reminders, list):
            current_reminders = [30, 7]  # Default
        
        # Check if this value already exists
        if new_days in current_reminders:
            await message.answer(
                f"❌ <b>Ошибка</b>\n\n"
                f"Напоминание за {new_days} дней уже существует.\n\n"
                "Попробуйте другое значение или нажмите \"Назад\" для отмены.",
                parse_mode="HTML"
            )
            return
        
        # Add new reminder to schedule
        updated_reminders = current_reminders + [new_days]
        
        # Save updated schedule
        success, result_message = await update_setting(
            session=session,
            key="renewal_reminder_days",
            value=json.dumps(updated_reminders),
            admin_id=user_id
        )
        
        if success:
            # Clear FSM state
            await state.clear()
            
            # Get keyboard with updated values
            keyboard = await get_renewal_reminders_keyboard(updated_reminders)
            
            # Format reminder list
            reminder_list = ", ".join(str(d) for d in sorted(updated_reminders, reverse=True))
            
            # Display success message with updated settings
            renewal_text = (
                "✅ <b>Напоминание успешно добавлено</b>\n\n"
                "🔔 <b>Настройка напоминаний о продлении</b>\n\n"
                f"<b>Текущее расписание:</b> за {reminder_list} дней до истечения\n\n"
                "Используйте кнопки для добавления или удаления напоминаний."
            )
            
            await message.answer(
                renewal_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"User {user_id} added renewal reminder: {new_days} days")
        else:
            # Save failed - show error
            await message.answer(
                f"❌ <b>Ошибка сохранения</b>\n\n"
                f"{result_message}",
                parse_mode="HTML"
            )
            
            logger.error(f"Failed to save renewal reminder for user {user_id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing renewal reminder days: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при сохранении настройки."
        )
        await state.clear()


@router.callback_query(SettingsCallback.filter(F.action == "remove_renewal_reminder"))
async def remove_renewal_reminder(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession
) -> None:
    """
    Remove renewal reminder from schedule.
    
    Validates minimum constraint (at least one reminder must remain).
    Creates audit log entry on successful save.
    
    Requirements: 6.1, 6.2
    """
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        days_to_remove = callback_data.reminder_days
        
        if days_to_remove is None:
            await callback.answer(
                "❌ Ошибка: не указаны дни для удаления.",
                show_alert=True
            )
            return
        
        # Get current reminder schedule
        current_reminders = await get_setting(session, "renewal_reminder_days")
        
        # Ensure it's a list
        if not isinstance(current_reminders, list):
            current_reminders = [30, 7]  # Default
        
        # Check minimum constraint - at least one reminder must remain
        if len(current_reminders) <= 1:
            await callback.answer(
                "❌ Нельзя удалить последнее напоминание.\n"
                "Должно быть настроено минимум одно напоминание.",
                show_alert=True
            )
            logger.warning(f"User {user_id} attempted to remove last renewal reminder")
            return
        
        # Remove the specified reminder
        if days_to_remove in current_reminders:
            updated_reminders = [d for d in current_reminders if d != days_to_remove]
        else:
            await callback.answer(
                "❌ Напоминание не найдено в расписании.",
                show_alert=True
            )
            return
        
        # Save updated schedule
        success, result_message = await update_setting(
            session=session,
            key="renewal_reminder_days",
            value=json.dumps(updated_reminders),
            admin_id=user_id
        )
        
        if success:
            # Get keyboard with updated values
            keyboard = await get_renewal_reminders_keyboard(updated_reminders)
            
            # Format reminder list
            reminder_list = ", ".join(str(d) for d in sorted(updated_reminders, reverse=True))
            
            # Display success message with updated settings
            renewal_text = (
                "✅ <b>Напоминание успешно удалено</b>\n\n"
                "🔔 <b>Настройка напоминаний о продлении</b>\n\n"
                f"<b>Текущее расписание:</b> за {reminder_list} дней до истечения\n\n"
                "Используйте кнопки для добавления или удаления напоминаний."
            )
            
            await callback.message.edit_text(
                renewal_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            logger.info(f"User {user_id} removed renewal reminder: {days_to_remove} days")
        else:
            # Save failed - show error
            await callback.answer(
                f"❌ Ошибка сохранения: {result_message}",
                show_alert=True
            )
            
            logger.error(f"Failed to remove renewal reminder for user {user_id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error removing renewal reminder: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка при удалении напоминания.",
            show_alert=True
        )
