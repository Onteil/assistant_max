"""
Admin Panel - Registration Approval Handlers

Handles registration approval workflows in the administrative panel:
- Send notifications to admins when users complete registration
- Approve user registrations with i-TAT API integration
- Reject user registrations with reason collection via FSM
- Mark registrations for manual review
- Display paginated list of pending registrations

Requirements: 24.1, 33.1, 1.1-1.7, 2.1-2.9, 3.1-3.9, 4.1-4.7, 5.1-5.7
"""

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bots.tg_bot.callback_datas import RegistrationCallback
from bots.tg_bot.states import AdminStates
from database.models import (
    Action_Log,
    ActionType,
    KeyConflictStatus,
    Organization,
    RegistrationStatus,
    Staff_Member,
    StaffRole,
    User,
    GS_Key,
)

logger = logging.getLogger(__name__)

router = Router(name="admin_registrations")


# ========== Helper Functions ==========


async def is_admin(session: AsyncSession, user_id: int) -> Staff_Member | None:
    """
    Check if user is an administrator and return their record.
    
    Args:
        session: Database session
        user_id: Telegram user ID
    
    Returns:
        Staff_Member object if user is admin, None otherwise
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == user_id,
            Staff_Member.is_active == True,
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}", exc_info=True)
        return None


# ========== Registration Notification ==========


async def handle_registration_notification(
    session: AsyncSession,
    user_id: int
) -> None:
    """
    Send registration notification to all administrators.
    
    Called when user completes registration flow.
    Queries all admins and sends notification with user details and action buttons.
    
    Behavior depends on REGISTRATION_APPROVE_METHOD environment variable:
    - "bot": Sends notification to admins with approval buttons (default)
    - "crm": Skips admin notification, registration handled by 1C/CRM webhook
    
    Args:
        session: Database session
        user_id: ID of user who completed registration
        
    Raises:
        SQLAlchemyError: Database query failed
        
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 27.1
    """
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from bots.tg_bot.keyboards.admin_kb import build_registration_actions_keyboard
    from bots.tg_bot.texts import ADMIN_REGISTRATION_PENDING
    from constants import TG_BOT_TOKEN, REGISTRATION_APPROVE_METHOD
    
    try:
        # Check registration approval method
        if REGISTRATION_APPROVE_METHOD == "crm":
            logger.info(
                f"Registration approval method is 'crm'. Skipping admin notification for user {user_id}. "
                f"Registration will be handled by 1C/CRM webhook."
            )
            
            # Log notification skip in Action_Log
            action_log = Action_Log(
                action_type=ActionType.USER_REGISTERED,
                user_id=user_id,
                action_details={
                    "approval_method": "crm",
                    "admin_notification": "skipped",
                    "note": "Registration handled by 1C/CRM webhook"
                },
                action_timestamp=datetime.now()
            )
            session.add(action_log)
            await session.commit()
            
            return
        
        # Query user with eager loading of organizations and gs_keys
        stmt = select(User).where(User.id == user_id).options(
            selectinload(User.organizations),
            selectinload(User.gs_keys)
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User {user_id} not found for registration notification")
            return
        
        # Query all administrators
        stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
            Staff_Member.is_active == True,
            Staff_Member.tg_user_id.isnot(None)
        )
        result = await session.execute(stmt)
        admins = result.scalars().all()
        
        if not admins:
            logger.warning("No active administrators found to send registration notification")
            return
        
        # Format INN list
        inn_list = ", ".join([org.inn for org in user.organizations]) if user.organizations else "Не указано"
        
        # Format GS_Key list
        gs_key_list = ", ".join([key.key_number for key in user.gs_keys]) if user.gs_keys else "Не указано"
        
        # Format registration date in Moscow timezone
        from datetime import timezone, timedelta
        moscow_tz = timezone(timedelta(hours=3))
        registration_date_moscow = user.created_at.astimezone(moscow_tz)
        registration_date = registration_date_moscow.strftime("%d.%m.%Y %H:%M")
        
        # Format Telegram username
        telegram_username = f"@{user.username}" if user.username else "Не указан"
        
        # Check if any key has conflict status
        has_key_conflict = any(
            key.conflict_status == KeyConflictStatus.PENDING_REVIEW 
            for key in user.gs_keys
        ) if user.gs_keys else False
        
        # Format notification message based on conflict status
        if has_key_conflict:
            from bots.tg_bot.texts import ADMIN_REGISTRATION_WITH_CONFLICT
            message_text = ADMIN_REGISTRATION_WITH_CONFLICT.format(
                full_name=user.full_name or "Не указано",
                phone=user.phone_number,
                telegram_username=telegram_username,
                inn_list=inn_list,
                gs_key_list=gs_key_list,
                registration_date=registration_date
            )
        else:
            message_text = ADMIN_REGISTRATION_PENDING.format(
                full_name=user.full_name or "Не указано",
                phone=user.phone_number,
                telegram_username=telegram_username,
                inn_list=inn_list,
                gs_key_list=gs_key_list,
                registration_date=registration_date
            )
        
        # Send notification to all administrators (without keyboard - registration confirmed in CRM)
        bot = Bot(token=TG_BOT_TOKEN)
        
        sent_count = 0
        for admin in admins:
            try:
                await bot.send_message(
                    chat_id=admin.tg_user_id,
                    text=message_text,
                    parse_mode=ParseMode.HTML
                )
                sent_count += 1
                logger.info(f"Sent registration notification to admin {admin.tg_user_id}")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send registration notification to admin {admin.tg_user_id}: {send_error}",
                    exc_info=True
                )
        
        # Log notification event in Action_Log
        action_log = Action_Log(
            action_type=ActionType.USER_REGISTERED,
            user_id=user.id,
            action_details={
                "approval_method": "bot",
                "admins_notified": sent_count,
                "total_admins": len(admins),
                "full_name": user.full_name,
                "phone": user.phone_number,
                "inn_count": len(user.organizations),
                "gs_key_count": len(user.gs_keys)
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Registration notification sent to {sent_count}/{len(admins)} administrators for user {user_id}"
        )
        
    except Exception as e:
        logger.error(
            f"Error sending registration notification for user {user_id}: {e}",
            exc_info=True
        )
        raise


# ========== Registration Approval Handler ==========


async def handle_registration_approve(
    callback_query: CallbackQuery,
    callback_data: RegistrationCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle registration approval action.
    
    Workflow:
    1. Call i-TAT API POST /user/approve
    2. Update User.registration_status = APPROVED
    3. Send notification to user
    4. Update admin notification message
    5. Log action in Action_Log
    
    Args:
        callback_query: Telegram callback query
        callback_data: Parsed callback data with user_id
        state: FSM context (not used, for consistency)
        session: Database session
        
    Raises:
        HTTPError: i-TAT API call failed
        SQLAlchemyError: Database update failed
        
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9
    """
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from bots.tg_bot.texts import ADMIN_REGISTRATION_APPROVED, REGISTRATION_APPROVED
    from constants import TG_BOT_TOKEN
    from services.i_tat_service import get_itat_client
    import httpx
    
    user_id = callback_data.user_id
    admin_tg_id = callback_query.from_user.id
    
    try:
        # Verify admin authorization
        admin = await is_admin(session, admin_tg_id)
        if not admin:
            await callback_query.answer("❌ Доступ запрещен", show_alert=True)
            logger.warning(f"Unauthorized approval attempt by user {admin_tg_id}")
            return
        
        # Query user with eager loading of organizations and gs_keys
        stmt = select(User).where(User.id == user_id).options(
            selectinload(User.organizations),
            selectinload(User.gs_keys)
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            await callback_query.answer("❌ Пользователь не найден", show_alert=True)
            logger.error(f"User {user_id} not found for approval")
            return
        
        # Check if already approved
        if user.registration_status == RegistrationStatus.APPROVED:
            await callback_query.answer("✅ Регистрация уже одобрена", show_alert=True)
            return
        
        # Prepare data for i-TAT API
        phone = user.phone_number
        inn_list = [org.inn for org in user.organizations] if user.organizations else []
        gs_key_list = [key.key_number for key in user.gs_keys] if user.gs_keys else []
        
        # Call i-TAT API POST /user/approve
        api_client = get_itat_client()
        api_success = False
        api_error_message = None
        
        try:
            logger.info(f"Calling i-TAT API to approve user {user_id}")
            api_response = await api_client.approve_user_registration(
                user_id=user.id,
                phone=phone,
                inn_list=inn_list,
                gs_key_list=gs_key_list
            )
            api_success = True
            logger.info(f"i-TAT API approval successful for user {user_id}: {api_response}")
            
        except httpx.TimeoutException as e:
            api_error_message = "Превышено время ожидания ответа от CRM"
            logger.error(f"i-TAT API timeout for user {user_id}: {e}", exc_info=True)
            
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 400:
                api_error_message = "Неверные параметры запроса"
            elif status_code == 404:
                api_error_message = "Пользователь не найден в CRM"
            elif status_code >= 500:
                api_error_message = "Ошибка сервера CRM"
            else:
                api_error_message = f"Ошибка API (код {status_code})"
            
            logger.error(
                f"i-TAT API HTTP error for user {user_id}: {status_code} - {e.response.text}",
                exc_info=True
            )
            
        except httpx.ConnectError as e:
            api_error_message = "Не удалось подключиться к CRM"
            logger.error(f"i-TAT API connection error for user {user_id}: {e}", exc_info=True)
            
        except Exception as e:
            api_error_message = "Неизвестная ошибка при обращении к CRM"
            logger.error(f"Unexpected error calling i-TAT API for user {user_id}: {e}", exc_info=True)
        
        # If API call failed, show error and return
        if not api_success:
            await callback_query.answer(
                f"❌ Ошибка: {api_error_message}\n\nПопробуйте позже или обратитесь к администратору.",
                show_alert=True
            )
            
            # Log failed approval attempt
            action_log = Action_Log(
                action_type=ActionType.API_RETRY_FAILED,
                user_id=user.id,
                staff_id=admin.id,
                action_details={
                    "action": "registration_approval",
                    "error": api_error_message,
                    "admin_name": admin.full_name,
                    "user_name": user.full_name,
                    "phone": phone
                },
                action_timestamp=datetime.now()
            )
            session.add(action_log)
            await session.commit()
            
            return
        
        # Update User.registration_status to APPROVED
        user.registration_status = RegistrationStatus.APPROVED
        await session.commit()
        
        logger.info(f"Updated user {user_id} registration status to APPROVED")
        
        # Send REGISTRATION_APPROVED notification to user
        bot = Bot(token=TG_BOT_TOKEN)
        
        if user.tg_user_id:
            try:
                await bot.send_message(
                    chat_id=user.tg_user_id,
                    text=REGISTRATION_APPROVED,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent approval notification to user {user.tg_user_id}")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send approval notification to user {user.tg_user_id}: {send_error}",
                    exc_info=True
                )
        
        # Update admin notification message with approval status
        try:
            admin_message_text = ADMIN_REGISTRATION_APPROVED.format(
                full_name=user.full_name or "Не указано"
            )
            
            await callback_query.message.edit_text(
                text=admin_message_text,
                parse_mode=ParseMode.HTML
            )
            
            await callback_query.answer("✅ Регистрация одобрена", show_alert=False)
            
        except Exception as edit_error:
            logger.error(
                f"Failed to update admin notification message: {edit_error}",
                exc_info=True
            )
            await callback_query.answer("✅ Регистрация одобрена", show_alert=True)
        
        # Log approval action in Action_Log
        action_log = Action_Log(
            action_type=ActionType.USER_REGISTERED,  # Using existing type, could add REGISTRATION_APPROVED
            user_id=user.id,
            staff_id=admin.id,
            action_details={
                "action": "registration_approved",
                "admin_name": admin.full_name,
                "admin_tg_id": admin_tg_id,
                "user_name": user.full_name,
                "phone": phone,
                "inn_count": len(inn_list),
                "gs_key_count": len(gs_key_list)
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Registration approved for user {user_id} by admin {admin.full_name} (ID: {admin.id})"
        )
        
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Error approving registration for user {user_id}: {e}",
            exc_info=True
        )
        await callback_query.answer(
            "❌ Произошла ошибка при одобрении регистрации",
            show_alert=True
        )


# ========== Registration Rejection Handlers ==========


async def handle_registration_reject_start(
    callback_query: CallbackQuery,
    callback_data: RegistrationCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Start registration rejection workflow.
    
    Prompts admin for rejection reason and sets FSM state.
    
    Args:
        callback_query: Telegram callback query
        callback_data: Parsed callback data with user_id
        state: FSM context for storing user_id
        session: Database session
        
    Requirements: 3.1, 26.3, 26.5
    """
    from bots.tg_bot.texts import ADMIN_REGISTRATION_REJECT_REASON
    
    user_id = callback_data.user_id
    admin_tg_id = callback_query.from_user.id
    
    try:
        # Verify admin authorization
        admin = await is_admin(session, admin_tg_id)
        if not admin:
            await callback_query.answer("❌ Доступ запрещен", show_alert=True)
            logger.warning(f"Unauthorized rejection attempt by user {admin_tg_id}")
            return
        
        # Query user to get details for prompt
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            await callback_query.answer("❌ Пользователь не найден", show_alert=True)
            logger.error(f"User {user_id} not found for rejection")
            return
        
        # Check if already rejected or approved
        if user.registration_status == RegistrationStatus.REJECTED:
            await callback_query.answer("✅ Регистрация уже отклонена", show_alert=True)
            return
        
        if user.registration_status == RegistrationStatus.APPROVED:
            await callback_query.answer("⚠️ Регистрация уже одобрена", show_alert=True)
            return
        
        # Store user_id and phone in FSM state data
        await state.update_data(
            user_id=user.id,
            phone=user.phone_number,
            admin_message_id=callback_query.message.message_id
        )
        
        # Set FSM state to WAITING_REJECTION_REASON
        await state.set_state(AdminStates.WAITING_REJECTION_REASON)
        
        # Prompt admin for rejection reason
        prompt_text = ADMIN_REGISTRATION_REJECT_REASON.format(
            full_name=user.full_name or f"{user.first_name} {user.last_name or ''}".strip()
        )
        
        await callback_query.message.answer(prompt_text)
        await callback_query.answer()
        
        logger.info(f"Admin {admin_tg_id} started rejection workflow for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error starting rejection workflow for user {user_id}: {e}", exc_info=True)
        await callback_query.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)


async def handle_registration_reject_reason(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle rejection reason input and complete rejection.
    
    Workflow:
    1. Get user_id from FSM state
    2. Call i-TAT API POST /user/reject with reason
    3. Update User.registration_status = REJECTED
    4. Send notification to user with reason
    5. Update admin notification message
    6. Log action in Action_Log
    7. Clear FSM state
    
    Args:
        message: Telegram message with rejection reason
        state: FSM context with stored user_id
        session: Database session
        
    Raises:
        HTTPError: i-TAT API call failed
        SQLAlchemyError: Database update failed
        
    Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 26.4, 26.6
    """
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from bots.tg_bot.texts import ADMIN_REGISTRATION_REJECTED, REGISTRATION_REJECTED
    from constants import TG_BOT_TOKEN
    from services.i_tat_service import get_itat_client
    import httpx
    
    admin_tg_id = message.from_user.id
    rejection_reason = message.text.strip()
    
    try:
        # Get user_id and phone from FSM state data
        state_data = await state.get_data()
        
        # Validate FSM state contains required keys
        if not state_data or "user_id" not in state_data or "phone" not in state_data:
            await message.answer(
                "❌ Ошибка: данные сессии утеряны. Попробуйте начать процесс отклонения заново."
            )
            await state.clear()
            logger.error(f"Missing required keys in FSM state for admin {admin_tg_id}")
            return
        
        user_id = state_data["user_id"]
        phone = state_data["phone"]
        admin_message_id = state_data.get("admin_message_id")
        
        # Verify admin authorization
        admin = await is_admin(session, admin_tg_id)
        if not admin:
            await message.answer("❌ Доступ запрещен")
            await state.clear()
            logger.warning(f"Unauthorized rejection attempt by user {admin_tg_id}")
            return
        
        # Query user to verify existence and current status
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            await state.clear()
            logger.error(f"User {user_id} not found for rejection")
            return
        
        # Check if already rejected or approved
        if user.registration_status == RegistrationStatus.REJECTED:
            await message.answer("✅ Регистрация уже отклонена")
            await state.clear()
            return
        
        if user.registration_status == RegistrationStatus.APPROVED:
            await message.answer("⚠️ Регистрация уже одобрена. Отклонение невозможно.")
            await state.clear()
            return
        
        # Call i-TAT API POST /user/reject with user_id, phone, rejection_reason
        api_client = get_itat_client()
        api_success = False
        api_error_message = None
        
        try:
            logger.info(f"Calling i-TAT API to reject user {user_id} with reason: {rejection_reason}")
            api_response = await api_client.reject_user_registration(
                user_id=user.id,
                phone=phone,
                rejection_reason=rejection_reason
            )
            api_success = True
            logger.info(f"i-TAT API rejection successful for user {user_id}: {api_response}")
            
        except httpx.TimeoutException as e:
            api_error_message = "Превышено время ожидания ответа от CRM"
            logger.error(f"i-TAT API timeout for user {user_id}: {e}", exc_info=True)
            
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 400:
                api_error_message = "Неверные параметры запроса"
            elif status_code == 404:
                api_error_message = "Пользователь не найден в CRM"
            elif status_code >= 500:
                api_error_message = "Ошибка сервера CRM"
            else:
                api_error_message = f"Ошибка API (код {status_code})"
            
            logger.error(
                f"i-TAT API HTTP error for user {user_id}: {status_code} - {e.response.text}",
                exc_info=True
            )
            
        except httpx.ConnectError as e:
            api_error_message = "Не удалось подключиться к CRM"
            logger.error(f"i-TAT API connection error for user {user_id}: {e}", exc_info=True)
            
        except Exception as e:
            api_error_message = "Неизвестная ошибка при обращении к CRM"
            logger.error(f"Unexpected error calling i-TAT API for user {user_id}: {e}", exc_info=True)
        
        # If API call failed, show error and allow retry
        if not api_success:
            await message.answer(
                f"❌ Ошибка: {api_error_message}\n\nПопробуйте позже или обратитесь к администратору."
            )
            
            # Log failed rejection attempt
            action_log = Action_Log(
                action_type=ActionType.API_RETRY_FAILED,
                user_id=user.id,
                staff_id=admin.id,
                action_details={
                    "action": "registration_rejection",
                    "error": api_error_message,
                    "admin_name": admin.full_name,
                    "user_name": user.full_name,
                    "phone": phone,
                    "rejection_reason": rejection_reason
                },
                action_timestamp=datetime.now()
            )
            session.add(action_log)
            await session.commit()
            
            # Don't clear state - allow admin to retry
            return
        
        # Update User.registration_status to REJECTED on success
        user.registration_status = RegistrationStatus.REJECTED
        await session.commit()
        
        logger.info(f"Updated user {user_id} registration status to REJECTED")
        
        # Send REGISTRATION_REJECTED notification to user with reason
        bot = Bot(token=TG_BOT_TOKEN)
        
        if user.tg_user_id:
            try:
                user_notification_text = REGISTRATION_REJECTED.format(reason=rejection_reason)
                await bot.send_message(
                    chat_id=user.tg_user_id,
                    text=user_notification_text,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent rejection notification to user {user.tg_user_id}")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send rejection notification to user {user.tg_user_id}: {send_error}",
                    exc_info=True
                )
        
        # Update admin notification message
        try:
            admin_message_text = ADMIN_REGISTRATION_REJECTED.format(
                full_name=user.full_name or "Не указано",
                reason=rejection_reason
            )
            
            # Try to edit the original admin notification message if we have the message_id
            if admin_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=admin_tg_id,
                        message_id=admin_message_id,
                        text=admin_message_text,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as edit_error:
                    logger.warning(
                        f"Failed to edit admin notification message {admin_message_id}: {edit_error}"
                    )
            
            # Send confirmation to admin
            await message.answer(
                "✅ Регистрация отклонена. Уведомление отправлено пользователю.",
                parse_mode=ParseMode.HTML
            )
            
        except Exception as notify_error:
            logger.error(
                f"Failed to update admin notification: {notify_error}",
                exc_info=True
            )
            await message.answer("✅ Регистрация отклонена")
        
        # Log rejection action in Action_Log
        action_log = Action_Log(
            action_type=ActionType.USER_REGISTERED,  # Using existing type, could add REGISTRATION_REJECTED
            user_id=user.id,
            staff_id=admin.id,
            action_details={
                "action": "registration_rejected",
                "admin_name": admin.full_name,
                "admin_tg_id": admin_tg_id,
                "user_name": user.full_name,
                "phone": phone,
                "rejection_reason": rejection_reason
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Registration rejected for user {user_id} by admin {admin.full_name} (ID: {admin.id}). "
            f"Reason: {rejection_reason}"
        )
        
        # Clear FSM state
        await state.clear()
        
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Error rejecting registration for user: {e}",
            exc_info=True
        )
        await message.answer(
            "❌ Произошла ошибка при отклонении регистрации"
        )
        await state.clear()


# ========== Registration Review Handler ==========


async def handle_registration_review(
    callback_query: CallbackQuery,
    callback_data: RegistrationCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Mark registration for manual review.
    
    Workflow:
    1. Update User.registration_status = UNDER_REVIEW
    2. Update admin notification message
    3. Send notification to user
    4. Log action in Action_Log
    
    Args:
        callback_query: Telegram callback query
        callback_data: Parsed callback data with user_id
        state: FSM context (not used)
        session: Database session
        
    Raises:
        SQLAlchemyError: Database update failed
        
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
    """
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from bots.tg_bot.texts import ADMIN_REGISTRATION_UNDER_REVIEW, REGISTRATION_UNDER_REVIEW
    from constants import TG_BOT_TOKEN
    
    user_id = callback_data.user_id
    admin_tg_id = callback_query.from_user.id
    
    try:
        # Verify admin authorization
        admin = await is_admin(session, admin_tg_id)
        if not admin:
            await callback_query.answer("❌ Доступ запрещен", show_alert=True)
            logger.warning(f"Unauthorized review attempt by user {admin_tg_id}")
            return
        
        # Query user
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            await callback_query.answer("❌ Пользователь не найден", show_alert=True)
            logger.error(f"User {user_id} not found for review")
            return
        
        # Check if already under review
        if user.registration_status == RegistrationStatus.UNDER_REVIEW:
            await callback_query.answer("🔍 Регистрация уже на проверке", show_alert=True)
            return
        
        # Check if already approved
        if user.registration_status == RegistrationStatus.APPROVED:
            await callback_query.answer("✅ Регистрация уже одобрена", show_alert=True)
            return
        
        # Update User.registration_status to UNDER_REVIEW
        user.registration_status = RegistrationStatus.UNDER_REVIEW
        await session.commit()
        
        logger.info(f"Updated user {user_id} registration status to UNDER_REVIEW")
        
        # Send REGISTRATION_UNDER_REVIEW notification to user
        bot = Bot(token=TG_BOT_TOKEN)
        
        if user.tg_user_id:
            try:
                await bot.send_message(
                    chat_id=user.tg_user_id,
                    text=REGISTRATION_UNDER_REVIEW,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent under review notification to user {user.tg_user_id}")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send under review notification to user {user.tg_user_id}: {send_error}",
                    exc_info=True
                )
        
        # Update admin notification message
        try:
            admin_message_text = ADMIN_REGISTRATION_UNDER_REVIEW.format(
                full_name=user.full_name or "Не указано"
            )
            
            await callback_query.message.edit_text(
                text=admin_message_text,
                parse_mode=ParseMode.HTML
            )
            
            await callback_query.answer("🔍 Регистрация отмечена на проверку", show_alert=False)
            
        except Exception as edit_error:
            logger.error(
                f"Failed to update admin notification message: {edit_error}",
                exc_info=True
            )
            await callback_query.answer("🔍 Регистрация отмечена на проверку", show_alert=True)
        
        # Log review action in Action_Log
        action_log = Action_Log(
            action_type=ActionType.USER_REGISTERED,  # Using existing type
            user_id=user.id,
            staff_id=admin.id,
            action_details={
                "action": "registration_under_review",
                "admin_name": admin.full_name,
                "admin_tg_id": admin_tg_id,
                "user_name": user.full_name,
                "phone": user.phone_number
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Registration marked for review for user {user_id} by admin {admin.full_name} (ID: {admin.id})"
        )
        
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Error marking registration for review for user {user_id}: {e}",
            exc_info=True
        )
        await callback_query.answer(
            "❌ Произошла ошибка при отметке регистрации на проверку",
            show_alert=True
        )



# ========== Registration List Handler ==========


async def handle_registration_list(
    callback_query: CallbackQuery,
    session: AsyncSession,
    page: int = 0
) -> None:
    """
    Display paginated list of pending registrations.
    
    Shows users with status PENDING or UNDER_REVIEW.
    
    Args:
        callback_query: Telegram callback query
        session: Database session
        page: Page number for pagination (default 0)
        
    Raises:
        SQLAlchemyError: Database query failed
        
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
    """
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from bots.tg_bot.keyboards.admin_kb import build_registration_list_keyboard
    from bots.tg_bot.texts import ADMIN_NO_PENDING_REGISTRATIONS
    from constants import TG_BOT_TOKEN
    
    admin_tg_id = callback_query.from_user.id
    
    try:
        # Verify admin authorization
        admin = await is_admin(session, admin_tg_id)
        if not admin:
            await callback_query.answer("❌ Доступ запрещен", show_alert=True)
            logger.warning(f"Unauthorized access attempt to registration list by user {admin_tg_id}")
            return
        
        # Query users with registration_status in (PENDING, UNDER_REVIEW)
        # Requirement 5.2: Filter by PENDING and UNDER_REVIEW statuses
        query = (
            select(User)
            .where(
                User.registration_status.in_([
                    RegistrationStatus.PENDING,
                    RegistrationStatus.UNDER_REVIEW
                ])
            )
            # Requirement 5.4: Order by created_at descending (newest first)
            .order_by(User.created_at.desc())
            # Eager load relationships for display
            .options(
                selectinload(User.organizations),
                selectinload(User.gs_keys)
            )
        )
        
        result = await session.execute(query)
        all_registrations = result.scalars().all()
        
        # Requirement 5.7: Display ADMIN_NO_PENDING_REGISTRATIONS when list is empty
        if not all_registrations:
            bot = Bot(token=TG_BOT_TOKEN)
            try:
                await bot.edit_message_text(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    text=ADMIN_NO_PENDING_REGISTRATIONS,
                    parse_mode=ParseMode.HTML
                )
            finally:
                await bot.session.close()
            
            await callback_query.answer()
            logger.info(f"Admin {admin_tg_id} viewed empty registration list")
            return
        
        # Requirement 5.5: Implement pagination with 10 entries per page
        ENTRIES_PER_PAGE = 10
        total_registrations = len(all_registrations)
        total_pages = (total_registrations + ENTRIES_PER_PAGE - 1) // ENTRIES_PER_PAGE
        
        # Validate page number
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1
        
        # Get registrations for current page
        start_idx = page * ENTRIES_PER_PAGE
        end_idx = start_idx + ENTRIES_PER_PAGE
        page_registrations = all_registrations[start_idx:end_idx]
        
        # Requirement 5.3: Format each entry with name, phone, registration date, and status
        registration_list_text = "📋 <b>Ожидающие регистрации</b>\n\n"
        
        for idx, user in enumerate(page_registrations, start=start_idx + 1):
            status_emoji = "🔍" if user.registration_status == RegistrationStatus.UNDER_REVIEW else "⏳"
            status_text = "На проверке" if user.registration_status == RegistrationStatus.UNDER_REVIEW else "Ожидает"
            
            registration_date = user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "Не указано"
            
            registration_list_text += (
                f"{idx}. {status_emoji} <b>{user.full_name or 'Не указано'}</b>\n"
                f"   📱 {user.phone_number or 'Не указано'}\n"
                f"   📅 {registration_date}\n"
                f"   📊 Статус: {status_text}\n\n"
            )
        
        registration_list_text += f"<i>Страница {page + 1} из {total_pages} • Всего: {total_registrations}</i>"
        
        # Build keyboard with pagination
        keyboard = await build_registration_list_keyboard(
            registrations=page_registrations,
            page=page,
            total_pages=total_pages
        )
        
        # Send or update message
        bot = Bot(token=TG_BOT_TOKEN)
        try:
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=registration_list_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
        finally:
            await bot.session.close()
        
        await callback_query.answer()
        logger.info(
            f"Admin {admin_tg_id} viewed registration list page {page + 1}/{total_pages} "
            f"({len(page_registrations)} registrations)"
        )
        
    except Exception as e:
        logger.error(f"Error displaying registration list: {e}", exc_info=True)
        await callback_query.answer(
            "❌ Ошибка при загрузке списка регистраций",
            show_alert=True
        )
        raise


# ========== Handler Registration ==========


# Registration approval handler
@router.callback_query(RegistrationCallback.filter(F.action == "approve"))
async def _handle_registration_approve(
    callback_query: CallbackQuery,
    callback_data: RegistrationCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Router wrapper for registration approval handler."""
    await handle_registration_approve(callback_query, callback_data, state, session)


# Registration rejection start handler
@router.callback_query(RegistrationCallback.filter(F.action == "reject"))
async def _handle_registration_reject_start(
    callback_query: CallbackQuery,
    callback_data: RegistrationCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Router wrapper for registration rejection start handler."""
    await handle_registration_reject_start(callback_query, callback_data, state, session)


# Registration rejection reason handler (FSM state)
@router.message(AdminStates.WAITING_REJECTION_REASON, F.text)
async def _handle_registration_reject_reason(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Router wrapper for registration rejection reason handler."""
    await handle_registration_reject_reason(message, state, session)


# Registration review handler
@router.callback_query(RegistrationCallback.filter(F.action == "review"))
async def _handle_registration_review(
    callback_query: CallbackQuery,
    callback_data: RegistrationCallback,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Router wrapper for registration review handler."""
    await handle_registration_review(callback_query, callback_data, state, session)


# Registration list handler
@router.callback_query(RegistrationCallback.filter(F.action == "list"))
async def _handle_registration_list(
    callback_query: CallbackQuery,
    callback_data: RegistrationCallback,
    session: AsyncSession
) -> None:
    """Router wrapper for registration list handler."""
    page = callback_data.page if callback_data.page is not None else 0
    await handle_registration_list(callback_query, session, page)
