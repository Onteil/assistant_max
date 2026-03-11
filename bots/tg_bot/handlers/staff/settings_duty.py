"""
Duty Support Configuration Handlers

Handles duty support account configuration with staff member validation.

Requirements: 4.1, 4.2
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.callback_datas import SettingsCallback
from bots.tg_bot.keyboards.admin_kb import get_cancel_keyboard
from bots.tg_bot.states import SettingsStates
from database.models import Staff_Member
from services.settings_service import get_setting, update_setting

logger = logging.getLogger(__name__)

router = Router(name="settings_duty")


@router.callback_query(SettingsCallback.filter(F.action == "edit_duty_account"))
async def start_duty_account_edit(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    state: FSMContext
) -> None:
    """
    Start duty support account editing flow.
    
    Prompts administrator to enter Telegram user ID.
    
    Requirements: 4.1
    """
    await callback.answer()
    
    try:
        setting_key = callback_data.setting_key
        
        # Store setting key in FSM state
        await state.update_data(editing_setting_key=setting_key)
        
        # Set FSM state
        await state.set_state(SettingsStates.entering_duty_account_id)
        
        # Get cancel keyboard
        keyboard = await get_cancel_keyboard(action="settings")
        
        # Prompt for new value
        await callback.message.edit_text(
            "🌙 <b>Изменение аккаунта дежурной поддержки</b>\n\n"
            "Введите Telegram User ID сотрудника:\n\n"
            "Формат: 123456789\n\n"
            "⚠️ User ID должен соответствовать активному сотруднику в системе.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"User {callback.from_user.id} started editing duty account: {setting_key}")
        
    except Exception as e:
        logger.error(f"Error starting duty account edit: user={callback.from_user.id}, error={e}", exc_info=True)
        await callback.answer(
            "❌ Произошла ошибка.",
            show_alert=True
        )


@router.message(SettingsStates.entering_duty_account_id)
async def process_duty_account(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Process duty account input and save if valid.
    
    Validates user ID corresponds to active staff member.
    Creates audit log entry on successful save.
    
    Requirements: 4.1, 4.2
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
        duty_user_id = message.text.strip()
        
        # Validate user ID is a positive integer
        try:
            duty_user_id_int = int(duty_user_id)
            if duty_user_id_int <= 0:
                await message.answer(
                    "❌ <b>Ошибка валидации</b>\n\n"
                    "User ID должен быть положительным числом.\n\n"
                    "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                    parse_mode="HTML"
                )
                return
        except ValueError:
            await message.answer(
                "❌ <b>Ошибка валидации</b>\n\n"
                "User ID должен быть числом.\n\n"
                "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                parse_mode="HTML"
            )
            return
        
        # Verify user ID corresponds to active staff member
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == duty_user_id_int,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        staff_member = result.scalar_one_or_none()
        
        if not staff_member:
            await message.answer(
                "❌ <b>Ошибка валидации</b>\n\n"
                "User ID не соответствует активному сотруднику в системе.\n\n"
                "Убедитесь, что:\n"
                "• Сотрудник добавлен в систему\n"
                "• Сотрудник активен\n"
                "• User ID указан правильно\n\n"
                "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                parse_mode="HTML"
            )
            logger.warning(f"Duty account validation failed: user_id {duty_user_id} not found or inactive")
            return
        
        # Save the setting
        success, result_message = await update_setting(
            session=session,
            key=setting_key,
            value=duty_user_id,
            admin_id=user_id
        )
        
        if success:
            # Clear FSM state
            await state.clear()
            
            # Get updated duty support setting
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
            
            # Display success message with updated settings
            duty_text = (
                f"✅ <b>Аккаунт дежурной поддержки успешно обновлен</b>\n\n"
                f"Назначен сотрудник: {staff_member.full_name}\n\n"
                "🌙 <b>Настройка дежурной поддержки</b>\n\n"
                f"<b>Текущий аккаунт:</b> {account_status}\n\n"
                "Нажмите на параметр для изменения значения."
            )
            
            await message.answer(
                duty_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
            
            logger.info(f"User {user_id} updated duty account to {duty_user_id} ({staff_member.full_name})")
        else:
            # Validation failed - show error and prompt again
            await message.answer(
                f"❌ <b>Ошибка валидации</b>\n\n"
                f"{result_message}\n\n"
                "Попробуйте еще раз или нажмите \"Назад\" для отмены.",
                parse_mode="HTML"
            )
            
            logger.warning(f"Duty account validation failed for user {user_id}: {result_message}")
    
    except Exception as e:
        logger.error(f"Error processing duty account: user={message.from_user.id}, error={e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при сохранении настройки."
        )
        await state.clear()
