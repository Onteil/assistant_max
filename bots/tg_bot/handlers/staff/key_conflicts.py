"""
Admin Panel - Key Conflict Resolution Handlers

Handles GS_Key ownership conflicts with transfer, rejection, and contact information workflows:
- Detect key conflicts when users register duplicate keys
- Send notifications to admins when conflicts are detected
- Transfer key ownership from old user to new user
- Reject key transfer requests
- Display contact information for both parties
- Display paginated list of unresolved key conflicts

Requirements: 24.2, 33.2, 6.1-6.8, 7.1-7.7, 8.1-8.9, 9.1-9.8, 10.1-10.6, 11.1-11.7
"""

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bots.tg_bot.callback_datas import KeyConflictCallback
from database.models import (
    Action_Log,
    ActionType,
    GS_Key,
    KeyConflictStatus,
    Organization,
    Staff_Member,
    StaffRole,
    User,
    ticket_keys,
)

logger = logging.getLogger(__name__)

router = Router(name="admin_key_conflicts")


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


# ========== Key Conflict Detection ==========


async def detect_key_conflict(
    session: AsyncSession,
    user_id: int,
    key_number: str
) -> tuple[bool, int | None]:
    """
    Detect if GS_Key is already owned by another user.
    
    Args:
        session: Database session
        user_id: ID of user attempting to add key
        key_number: GS_Key number to check
        
    Returns:
        Tuple of (is_conflict, existing_owner_id)
        - (False, None) if key not found or owned by same user
        - (True, owner_id) if owned by different user
        
    Raises:
        SQLAlchemyError: Database query failed
        
    Requirements: 6.1
    """
    try:
        # Query GS_Key table for existing key with same key_number
        stmt = select(GS_Key).where(GS_Key.key_number == key_number)
        result = await session.execute(stmt)
        existing_key = result.scalar_one_or_none()
        
        if existing_key is None:
            # No conflict - key is available
            logger.debug(f"Key {key_number} not found - no conflict")
            return False, None
        
        if existing_key.user_id == user_id:
            # No conflict - user already owns this key
            logger.debug(f"Key {key_number} already owned by user {user_id} - no conflict")
            return False, None
        
        # Conflict - key owned by different user
        logger.info(
            f"Key conflict detected: key {key_number} owned by user {existing_key.user_id}, "
            f"attempted by user {user_id}"
        )
        return True, existing_key.user_id
        
    except Exception as e:
        logger.error(f"Error detecting key conflict for key {key_number}: {e}", exc_info=True)
        raise


# ========== Conflict Notification ==========


async def create_key_conflict_notification(
    session: AsyncSession,
    new_user_id: int,
    existing_user_id: int,
    key_number: str
) -> None:
    """
    Create conflict record and notify all administrators.
    
    Workflow:
    1. Update GS_Key.conflict_status = PENDING_REVIEW
    2. Set GS_Key.conflict_reported_at = now()
    3. Send notifications to all admins with is_admin=True
    4. Log conflict in Action_Log
    
    Args:
        session: Database session
        new_user_id: ID of user attempting to add key
        existing_user_id: ID of current key owner
        key_number: Conflicted GS_Key number
        
    Raises:
        SQLAlchemyError: Database update failed
        
    Requirements: 6.2, 6.3, 6.4, 6.5, 6.8, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
    """
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from bots.tg_bot.keyboards.admin_kb import build_key_conflict_actions_keyboard
    from bots.tg_bot.texts import ADMIN_KEY_CONFLICT_NOTIFICATION
    from constants import TG_BOT_TOKEN
    
    try:
        # Query the GS_Key record
        stmt = select(GS_Key).where(GS_Key.key_number == key_number)
        result = await session.execute(stmt)
        gs_key = result.scalar_one_or_none()
        
        if not gs_key:
            logger.error(f"GS_Key {key_number} not found for conflict notification")
            return
        
        # Update GS_Key.conflict_status to PENDING_REVIEW
        gs_key.conflict_status = KeyConflictStatus.PENDING_REVIEW
        
        # Set GS_Key.conflict_reported_at to current timestamp
        gs_key.conflict_reported_at = datetime.now()
        
        await session.commit()
        
        logger.info(f"Updated GS_Key {key_number} conflict status to PENDING_REVIEW")
        
        # Query both users with eager loading of organizations and gs_keys
        stmt = select(User).where(User.id.in_([new_user_id, existing_user_id])).options(
            selectinload(User.organizations),
            selectinload(User.gs_keys)
        )
        result = await session.execute(stmt)
        users = {user.id: user for user in result.scalars().all()}
        
        new_user = users.get(new_user_id)
        existing_user = users.get(existing_user_id)
        
        if not new_user or not existing_user:
            logger.error(
                f"Users not found for conflict notification: "
                f"new_user_id={new_user_id}, existing_user_id={existing_user_id}"
            )
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
            logger.warning("No active administrators found to send key conflict notification")
            return
        
        # Format INN lists
        new_user_inn_list = ", ".join([org.inn for org in new_user.organizations]) if new_user.organizations else "Не указано"
        existing_user_inn_list = ", ".join([org.inn for org in existing_user.organizations]) if existing_user.organizations else "Не указано"
        
        # Format conflict timestamp
        conflict_timestamp = gs_key.conflict_reported_at.strftime("%d.%m.%Y %H:%M")
        
        # Format notification message
        message_text = ADMIN_KEY_CONFLICT_NOTIFICATION.format(
            key_number=key_number,
            current_owner_name=existing_user.full_name or "Не указано",
            current_owner_phone=existing_user.phone_number or "Не указано",
            new_user_name=new_user.full_name or "Не указано",
            new_user_phone=new_user.phone_number or "Не указано",
            conflict_date=conflict_timestamp
        )
        
        # Build keyboard with action buttons
        keyboard = await build_key_conflict_actions_keyboard(
            key_id=gs_key.id,
            new_user_id=new_user_id
        )
        
        # Send notification to all administrators
        bot = Bot(token=TG_BOT_TOKEN)
        
        sent_count = 0
        for admin in admins:
            try:
                await bot.send_message(
                    chat_id=admin.tg_user_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
                sent_count += 1
                logger.info(f"Sent key conflict notification to admin {admin.tg_user_id}")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send key conflict notification to admin {admin.tg_user_id}: {send_error}",
                    exc_info=True
                )
        
        # Log conflict event in Action_Log
        action_log = Action_Log(
            action_type=ActionType.KEY_CONFLICT_DETECTED,
            user_id=new_user_id,
            action_details={
                "key_number": key_number,
                "new_user_id": new_user_id,
                "new_user_name": new_user.full_name,
                "existing_user_id": existing_user_id,
                "existing_user_name": existing_user.full_name,
                "admins_notified": sent_count,
                "total_admins": len(admins)
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Key conflict notification sent to {sent_count}/{len(admins)} administrators "
            f"for key {key_number}"
        )
        
    except Exception as e:
        logger.error(
            f"Error creating key conflict notification for key {key_number}: {e}",
            exc_info=True
        )
        raise


# ========== Handler Registration ==========


# Key transfer handler
@router.callback_query(KeyConflictCallback.filter(F.action == "transfer"))
async def _handle_key_transfer(
    callback_query: CallbackQuery,
    callback_data: KeyConflictCallback,
    session: AsyncSession
) -> None:
    """Router wrapper for key transfer handler."""
    await handle_key_transfer(callback_query, callback_data, session)


# Key rejection handler
@router.callback_query(KeyConflictCallback.filter(F.action == "reject"))
async def _handle_key_rejection(
    callback_query: CallbackQuery,
    callback_data: KeyConflictCallback,
    session: AsyncSession
) -> None:
    """Router wrapper for key rejection handler."""
    await handle_key_rejection(callback_query, callback_data, session)


# Contact information display handler
@router.callback_query(KeyConflictCallback.filter(F.action == "contact"))
async def _handle_key_conflict_contact(
    callback_query: CallbackQuery,
    callback_data: KeyConflictCallback,
    session: AsyncSession
) -> None:
    """Router wrapper for contact information display handler."""
    await handle_key_conflict_contact(callback_query, callback_data, session)


# Conflict list handler
@router.callback_query(KeyConflictCallback.filter(F.action == "list"))
async def _handle_key_conflict_list(
    callback_query: CallbackQuery,
    callback_data: KeyConflictCallback,
    session: AsyncSession
) -> None:
    """Router wrapper for conflict list handler."""
    page = callback_data.page if callback_data.page is not None else 0
    await handle_key_conflict_list(callback_query, session, page)


# Conflict detail view handler
@router.callback_query(KeyConflictCallback.filter(F.action == "view"))
async def _handle_key_conflict_view(
    callback_query: CallbackQuery,
    callback_data: KeyConflictCallback,
    session: AsyncSession
) -> None:
    """Router wrapper for conflict detail view handler."""
    await handle_key_conflict_view(callback_query, callback_data, session)





# ========== Conflict Detail View Handler ==========


async def handle_key_conflict_view(
    callback_query: CallbackQuery,
    callback_data: KeyConflictCallback,
    session: AsyncSession
) -> None:
    """
    Display detailed view of a specific key conflict with action buttons.
    
    Shows:
    - Key number
    - Current owner name
    - New user name
    - Conflict date
    - Action buttons (Transfer, Reject, Contact)
    
    Args:
        callback_query: Telegram callback query
        callback_data: Parsed callback data with conflict details
        session: Database session
        
    Raises:
        SQLAlchemyError: Database query failed
    """
    from aiogram.enums import ParseMode
    from bots.tg_bot.keyboards.admin_kb import build_key_conflict_actions_keyboard
    from bots.tg_bot.texts import ADMIN_KEY_CONFLICT_NOTIFICATION
    
    key_id = callback_data.key_id
    new_user_id = callback_data.new_user_id
    admin_tg_id = callback_query.from_user.id
    
    try:
        # Verify admin authorization
        admin = await is_admin(session, admin_tg_id)
        if not admin:
            await callback_query.answer("❌ Доступ запрещен", show_alert=True)
            logger.warning(f"Unauthorized conflict view attempt by user {admin_tg_id}")
            return
        
        # Query GS_Key with user relationship
        stmt = select(GS_Key).where(GS_Key.id == key_id).options(
            selectinload(GS_Key.user)
        )
        result = await session.execute(stmt)
        gs_key = result.scalar_one_or_none()
        
        if not gs_key:
            await callback_query.answer("❌ Ключ не найден", show_alert=True)
            logger.error(f"GS_Key {key_id} not found for conflict view")
            return
        
        # Get both users
        stmt = select(User).where(User.id.in_([new_user_id, gs_key.user_id])).options(
            selectinload(User.organizations)
        )
        result = await session.execute(stmt)
        users = {user.id: user for user in result.scalars().all()}
        
        new_user = users.get(new_user_id)
        existing_user = users.get(gs_key.user_id)
        
        if not new_user or not existing_user:
            await callback_query.answer("❌ Пользователи не найдены", show_alert=True)
            logger.error(
                f"Users not found for conflict view: "
                f"new_user_id={new_user_id}, existing_user_id={gs_key.user_id}"
            )
            return
        
        # Format conflict timestamp
        conflict_timestamp = gs_key.conflict_reported_at.strftime("%d.%m.%Y %H:%M") if gs_key.conflict_reported_at else "Не указано"
        
        # Format Telegram usernames
        new_user_telegram = f"@{new_user.username}" if new_user.username else "Не указано"
        existing_user_telegram = f"@{existing_user.username}" if existing_user.username else "Не указано"
        
        # Format notification message
        message_text = ADMIN_KEY_CONFLICT_NOTIFICATION.format(
            key_number=gs_key.key_number,
            current_owner_name=existing_user.full_name or "Не указано",
            current_owner_phone=existing_user.phone_number or "Не указано",
            current_owner_telegram=existing_user_telegram,
            new_user_name=new_user.full_name or "Не указано",
            new_user_phone=new_user.phone_number or "Не указано",
            new_user_telegram=new_user_telegram,
            conflict_date=conflict_timestamp
        )
        
        # Build keyboard with action buttons
        keyboard = await build_key_conflict_actions_keyboard(
            key_id=gs_key.id,
            new_user_id=new_user_id
        )
        
        # Update message
        await callback_query.message.edit_text(
            text=message_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        
        await callback_query.answer()
        logger.info(f"Admin {admin_tg_id} viewed conflict detail for key {gs_key.key_number}")
        
    except Exception as e:
        logger.error(f"Error displaying conflict view for key {key_id}: {e}", exc_info=True)
        await callback_query.answer(
            "❌ Ошибка при загрузке конфликта",
            show_alert=True
        )


# ========== Key Transfer Handler ==========


async def handle_key_transfer(
    callback_query: CallbackQuery,
    callback_data: KeyConflictCallback,
    session: AsyncSession
) -> None:
    """
    Transfer GS_Key ownership to new user.
    
    Workflow:
    1. Call i-TAT API POST /assets/transfer_key
    2. Update GS_Key.user_id = new_user_id
    3. Update GS_Key.conflict_status = RESOLVED
    4. Set GS_Key.conflict_resolved_at = now()
    5. Send notification to new user (KEY_TRANSFERRED_TO_YOU)
    6. Send notification to old user (KEY_TRANSFERRED_AWAY)
    7. Update admin notification message
    8. Log action in Action_Log
    
    Args:
        callback_query: Telegram callback query
        callback_data: Parsed callback data with conflict details
        session: Database session
        
    Raises:
        HTTPError: i-TAT API call failed
        SQLAlchemyError: Database update failed
        
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9
    """
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from bots.tg_bot.texts import (
        ADMIN_KEY_TRANSFERRED,
        KEY_TRANSFERRED_TO_YOU,
        KEY_TRANSFERRED_AWAY
    )
    from constants import TG_BOT_TOKEN
    from services.i_tat_service import get_itat_client
    import httpx
    
    key_id = callback_data.key_id
    new_user_id = callback_data.new_user_id
    admin_tg_id = callback_query.from_user.id
    
    try:
        # Verify admin authorization
        admin = await is_admin(session, admin_tg_id)
        if not admin:
            await callback_query.answer("❌ Доступ запрещен", show_alert=True)
            logger.warning(f"Unauthorized key transfer attempt by user {admin_tg_id}")
            return
        
        # Query GS_Key with eager loading of user relationship
        stmt = select(GS_Key).where(GS_Key.id == key_id).options(
            selectinload(GS_Key.user)
        )
        result = await session.execute(stmt)
        gs_key = result.scalar_one_or_none()
        
        if not gs_key:
            await callback_query.answer("❌ Ключ не найден", show_alert=True)
            logger.error(f"GS_Key {key_id} not found for transfer")
            return
        
        # Check if already resolved
        if gs_key.conflict_status == KeyConflictStatus.RESOLVED:
            await callback_query.answer("✅ Конфликт уже разрешен", show_alert=True)
            return
        
        old_user_id = gs_key.user_id
        key_number = gs_key.key_number
        
        # Query both users
        stmt = select(User).where(User.id.in_([new_user_id, old_user_id]))
        result = await session.execute(stmt)
        users = {user.id: user for user in result.scalars().all()}
        
        new_user = users.get(new_user_id)
        old_user = users.get(old_user_id)
        
        if not new_user or not old_user:
            await callback_query.answer("❌ Пользователи не найдены", show_alert=True)
            logger.error(
                f"Users not found for key transfer: "
                f"new_user_id={new_user_id}, old_user_id={old_user_id}"
            )
            return
        
        # Call i-TAT API POST /assets/transfer_key
        api_client = get_itat_client()
        api_success = False
        api_error_message = None
        
        try:
            logger.info(
                f"Calling i-TAT API to transfer key {key_number} "
                f"from user {old_user_id} to user {new_user_id}"
            )
            api_response = await api_client.transfer_gs_key(
                old_user_id=old_user_id,
                new_user_id=new_user_id,
                key_number=key_number
            )
            api_success = True
            logger.info(f"i-TAT API key transfer successful: {api_response}")
            
        except httpx.TimeoutException as e:
            api_error_message = "Превышено время ожидания ответа от CRM"
            logger.error(f"i-TAT API timeout for key transfer: {e}", exc_info=True)
            
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 400:
                api_error_message = "Неверные параметры запроса"
            elif status_code == 404:
                api_error_message = "Ключ не найден в CRM"
            elif status_code >= 500:
                api_error_message = "Ошибка сервера CRM"
            else:
                api_error_message = f"Ошибка API (код {status_code})"
            
            logger.error(
                f"i-TAT API HTTP error for key transfer: {status_code} - {e.response.text}",
                exc_info=True
            )
            
        except httpx.ConnectError as e:
            api_error_message = "Не удалось подключиться к CRM"
            logger.error(f"i-TAT API connection error for key transfer: {e}", exc_info=True)
            
        except Exception as e:
            api_error_message = "Неизвестная ошибка при обращении к CRM"
            logger.error(f"Unexpected error calling i-TAT API for key transfer: {e}", exc_info=True)
        
        # If API call failed, rollback and show error
        if not api_success:
            await callback_query.answer(
                f"❌ Ошибка: {api_error_message}\n\nПопробуйте позже или обратитесь к администратору.",
                show_alert=True
            )
            
            # Log failed transfer attempt
            action_log = Action_Log(
                action_type=ActionType.API_RETRY_FAILED,
                user_id=new_user_id,
                staff_id=admin.id,
                action_details={
                    "action": "key_transfer",
                    "error": api_error_message,
                    "key_number": key_number,
                    "old_user_id": old_user_id,
                    "new_user_id": new_user_id,
                    "admin_name": admin.full_name
                },
                action_timestamp=datetime.now()
            )
            session.add(action_log)
            await session.commit()
            
            return
        
        # Update GS_Key.user_id to new_user_id
        gs_key.user_id = new_user_id
        
        # Update GS_Key.conflict_status to RESOLVED
        gs_key.conflict_status = KeyConflictStatus.RESOLVED
        
        # Set GS_Key.conflict_resolved_at to current timestamp
        gs_key.conflict_resolved_at = datetime.now()
        
        await session.commit()
        
        logger.info(
            f"Updated GS_Key {key_number} ownership: "
            f"old_user={old_user_id} -> new_user={new_user_id}"
        )
        
        # Send notifications
        bot = Bot(token=TG_BOT_TOKEN)
        
        # Send KEY_TRANSFERRED_TO_YOU notification to new user
        if new_user.tg_user_id:
            try:
                new_user_text = KEY_TRANSFERRED_TO_YOU.format(key_number=key_number)
                await bot.send_message(
                    chat_id=new_user.tg_user_id,
                    text=new_user_text,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent key transfer notification to new user {new_user.tg_user_id}")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send key transfer notification to new user {new_user.tg_user_id}: {send_error}",
                    exc_info=True
                )
        
        # Send KEY_TRANSFERRED_AWAY notification to old user
        if old_user.tg_user_id:
            try:
                old_user_text = KEY_TRANSFERRED_AWAY.format(key_number=key_number)
                await bot.send_message(
                    chat_id=old_user.tg_user_id,
                    text=old_user_text,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent key transfer notification to old user {old_user.tg_user_id}")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send key transfer notification to old user {old_user.tg_user_id}: {send_error}",
                    exc_info=True
                )
        
        # Update admin notification message
        try:
            admin_message_text = ADMIN_KEY_TRANSFERRED.format(
                key_number=key_number,
                new_owner_name=new_user.full_name or "Не указано"
            )
            
            await callback_query.message.edit_text(
                text=admin_message_text,
                parse_mode=ParseMode.HTML
            )
            
            await callback_query.answer("✅ Ключ передан новому пользователю", show_alert=False)
            
        except Exception as edit_error:
            logger.error(
                f"Failed to update admin notification message: {edit_error}",
                exc_info=True
            )
            await callback_query.answer("✅ Ключ передан новому пользователю", show_alert=True)
        
        # Log transfer action in Action_Log
        action_log = Action_Log(
            action_type=ActionType.KEY_CONFLICT_DETECTED,  # Using existing type
            user_id=new_user_id,
            staff_id=admin.id,
            action_details={
                "action": "key_transferred",
                "key_number": key_number,
                "old_user_id": old_user_id,
                "old_user_name": old_user.full_name,
                "new_user_id": new_user_id,
                "new_user_name": new_user.full_name,
                "admin_name": admin.full_name,
                "admin_tg_id": admin_tg_id
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Key {key_number} transferred from user {old_user_id} to user {new_user_id} "
            f"by admin {admin.full_name} (ID: {admin.id})"
        )
        
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Error transferring key {key_id}: {e}",
            exc_info=True
        )
        await callback_query.answer(
            "❌ Произошла ошибка при передаче ключа",
            show_alert=True
        )



# ========== Key Rejection Handler ==========


async def handle_key_rejection(
    callback_query: CallbackQuery,
    callback_data: KeyConflictCallback,
    session: AsyncSession
) -> None:
    """
    Reject key transfer request.
    
    Workflow:
    1. Update GS_Key.conflict_status = REJECTED
    2. Set GS_Key.conflict_resolved_at = now()
    3. Send notification to new user (KEY_CONFLICT_REJECTED)
    4. Update admin notification message
    5. Log action in Action_Log
    
    Args:
        callback_query: Telegram callback query
        callback_data: Parsed callback data with conflict details
        session: Database session
        
    Raises:
        SQLAlchemyError: Database update failed
        
    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8
    """
    from aiogram import Bot
    from aiogram.enums import ParseMode
    from bots.tg_bot.texts import ADMIN_KEY_CLAIM_REJECTED, KEY_CONFLICT_REJECTED
    from constants import TG_BOT_TOKEN
    
    key_id = callback_data.key_id
    new_user_id = callback_data.new_user_id
    admin_tg_id = callback_query.from_user.id
    
    try:
        # Verify admin authorization
        admin = await is_admin(session, admin_tg_id)
        if not admin:
            await callback_query.answer("❌ Доступ запрещен", show_alert=True)
            logger.warning(f"Unauthorized key rejection attempt by user {admin_tg_id}")
            return
        
        # Query GS_Key
        stmt = select(GS_Key).where(GS_Key.id == key_id)
        result = await session.execute(stmt)
        gs_key = result.scalar_one_or_none()
        
        if not gs_key:
            await callback_query.answer("❌ Ключ не найден", show_alert=True)
            logger.error(f"GS_Key {key_id} not found for rejection")
            return
        
        # Check if already resolved
        if gs_key.conflict_status == KeyConflictStatus.RESOLVED:
            await callback_query.answer("✅ Конфликт уже разрешен", show_alert=True)
            return
        
        key_number = gs_key.key_number
        
        # Query new user
        stmt = select(User).where(User.id == new_user_id)
        result = await session.execute(stmt)
        new_user = result.scalar_one_or_none()
        
        if not new_user:
            await callback_query.answer("❌ Пользователь не найден", show_alert=True)
            logger.error(f"User {new_user_id} not found for key rejection")
            return
        
        # Find all GS_Key records for this key_number from new user
        from sqlalchemy import delete
        keys_to_delete_stmt = select(GS_Key).where(
            GS_Key.user_id == new_user_id,
            GS_Key.key_number == key_number
        )
        keys_to_delete_result = await session.execute(keys_to_delete_stmt)
        keys_to_delete = keys_to_delete_result.scalars().all()
        
        if keys_to_delete:
            # Delete related ticket_keys entries first to avoid foreign key constraint
            key_ids_to_delete = [key.id for key in keys_to_delete]
            
            delete_ticket_keys_stmt = delete(ticket_keys).where(
                ticket_keys.c.key_id.in_(key_ids_to_delete)
            )
            await session.execute(delete_ticket_keys_stmt)
            
            # Now delete the GS_Key records
            delete_keys_stmt = delete(GS_Key).where(
                GS_Key.user_id == new_user_id,
                GS_Key.key_number == key_number
            )
            delete_result = await session.execute(delete_keys_stmt)
            deleted_count = delete_result.rowcount
            
            logger.info(
                f"Deleted {deleted_count} GS_Key record(s) with key_number={key_number} "
                f"from user {new_user_id} (and related ticket_keys entries)"
            )
        else:
            logger.warning(
                f"No GS_Key records found with key_number={key_number} for user {new_user_id}"
            )
        
        # Update GS_Key.conflict_status to RESOLVED
        gs_key.conflict_status = KeyConflictStatus.RESOLVED
        
        # Set GS_Key.conflict_resolved_at to current timestamp
        gs_key.conflict_resolved_at = datetime.now()
        
        await session.commit()
        
        logger.info(f"Updated GS_Key {key_number} conflict status to REJECTED")
        
        # Send KEY_CONFLICT_REJECTED notification to new user
        bot = Bot(token=TG_BOT_TOKEN)
        
        if new_user.tg_user_id:
            try:
                user_notification_text = KEY_CONFLICT_REJECTED.format(key_number=key_number)
                await bot.send_message(
                    chat_id=new_user.tg_user_id,
                    text=user_notification_text,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent key rejection notification to user {new_user.tg_user_id}")
                
            except Exception as send_error:
                logger.error(
                    f"Failed to send key rejection notification to user {new_user.tg_user_id}: {send_error}",
                    exc_info=True
                )
        
        # Update admin notification message
        try:
            admin_message_text = ADMIN_KEY_CLAIM_REJECTED.format(
                key_number=key_number,
                rejected_user_name=new_user.full_name or "Не указано"
            )
            
            await callback_query.message.edit_text(
                text=admin_message_text,
                parse_mode=ParseMode.HTML
            )
            
            await callback_query.answer("✅ Претензия на ключ отклонена", show_alert=False)
            
        except Exception as edit_error:
            logger.error(
                f"Failed to update admin notification message: {edit_error}",
                exc_info=True
            )
            await callback_query.answer("✅ Претензия на ключ отклонена", show_alert=True)
        
        # Log rejection action in Action_Log
        action_log = Action_Log(
            action_type=ActionType.KEY_CONFLICT_DETECTED,  # Using existing type
            user_id=new_user_id,
            staff_id=admin.id,
            action_details={
                "action": "key_conflict_rejected",
                "key_number": key_number,
                "rejected_user_id": new_user_id,
                "rejected_user_name": new_user.full_name,
                "admin_name": admin.full_name,
                "admin_tg_id": admin_tg_id
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Key conflict rejected for key {key_number}, user {new_user_id} "
            f"by admin {admin.full_name} (ID: {admin.id})"
        )
        
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Error rejecting key conflict for key {key_id}: {e}",
            exc_info=True
        )
        await callback_query.answer(
            "❌ Произошла ошибка при отклонении претензии",
            show_alert=True
        )



# ========== Contact Information Display Handler ==========


async def handle_key_conflict_contact(
    callback_query: CallbackQuery,
    callback_data: KeyConflictCallback,
    session: AsyncSession
) -> None:
    """
    Display contact information for both parties in conflict.
    
    Shows:
    - Full name, phone, Telegram username
    - Registration date
    - All GS_Keys for each user
    - All INN organizations for each user
    
    Args:
        callback_query: Telegram callback query
        callback_data: Parsed callback data with conflict details
        session: Database session
        
    Raises:
        SQLAlchemyError: Database query failed
        
    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
    """
    from aiogram.enums import ParseMode
    from bots.tg_bot.texts import ADMIN_KEY_CONFLICT_CONTACT
    
    key_id = callback_data.key_id
    new_user_id = callback_data.new_user_id
    admin_tg_id = callback_query.from_user.id
    
    try:
        # Verify admin authorization
        admin = await is_admin(session, admin_tg_id)
        if not admin:
            await callback_query.answer("❌ Доступ запрещен", show_alert=True)
            logger.warning(f"Unauthorized contact info access attempt by user {admin_tg_id}")
            return
        
        # Query GS_Key to get old user ID
        stmt = select(GS_Key).where(GS_Key.id == key_id)
        result = await session.execute(stmt)
        gs_key = result.scalar_one_or_none()
        
        if not gs_key:
            await callback_query.answer("❌ Ключ не найден", show_alert=True)
            logger.error(f"GS_Key {key_id} not found for contact info")
            return
        
        old_user_id = gs_key.user_id
        
        # Query both users with eager loading of organizations and gs_keys
        stmt = select(User).where(User.id.in_([new_user_id, old_user_id])).options(
            selectinload(User.organizations),
            selectinload(User.gs_keys)
        )
        result = await session.execute(stmt)
        users = {user.id: user for user in result.scalars().all()}
        
        new_user = users.get(new_user_id)
        old_user = users.get(old_user_id)
        
        if not new_user or not old_user:
            await callback_query.answer("❌ Пользователи не найдены", show_alert=True)
            logger.error(
                f"Users not found for contact info: "
                f"new_user_id={new_user_id}, old_user_id={old_user_id}"
            )
            return
        
        # Format contact information
        def format_user_info(user: User, label: str) -> str:
            """Format user information block."""
            info = f"<b>{label}:</b>\n"
            info += f"👤 ФИО: {user.full_name or 'Не указано'}\n"
            
            # Format phone number in international format (+7XXXXXXXXXX)
            phone = user.phone_number or "Не указано"
            if phone != "Не указано" and not phone.startswith("+"):
                phone = f"+{phone}"
            info += f"📱 Телефон: {phone}\n"
            
            # Telegram username
            username = f"@{user.username}" if user.username else "Не указано"
            info += f"💬 Telegram: {username}\n"
            
            # Registration date
            reg_date = user.created_at.strftime("%d.%m.%Y") if user.created_at else "Не указано"
            info += f"📅 Регистрация: {reg_date}\n"
            
            # GS_Keys
            if user.gs_keys:
                keys_list = ", ".join([key.key_number for key in user.gs_keys])
                info += f"🔑 Ключи ГС: {keys_list}\n"
            else:
                info += "🔑 Ключи ГС: Не указано\n"
            
            # INN organizations
            if user.organizations:
                inn_list = ", ".join([org.inn for org in user.organizations])
                info += f"🏢 ИНН: {inn_list}\n"
            else:
                info += "🏢 ИНН: Не указано\n"
            
            return info
        
        # Build contact information message
        current_owner_info = format_user_info(old_user, "Текущий владелец")
        new_user_info = format_user_info(new_user, "Новый претендент")
        
        contact_text = f"📞 <b>Контактная информация</b>\n\n{current_owner_info}\n{new_user_info}"
        
        # Create back button to return to conflict notification
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🔙 Назад к конфликту",
            callback_data=KeyConflictCallback(
                action="view",
                key_id=key_id,
                new_user_id=new_user_id
            )
        )
        keyboard = builder.as_markup()
        
        # Update message
        await callback_query.message.edit_text(
            text=contact_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        
        await callback_query.answer()
        logger.info(f"Admin {admin_tg_id} viewed contact info for key conflict {key_id}")
        
    except Exception as e:
        logger.error(f"Error displaying contact info for key {key_id}: {e}", exc_info=True)
        await callback_query.answer(
            "❌ Ошибка при загрузке контактной информации",
            show_alert=True
        )



# ========== Conflict List Handler ==========


async def handle_key_conflict_list(
    callback_query: CallbackQuery,
    session: AsyncSession,
    page: int = 0
) -> None:
    """
    Display paginated list of unresolved key conflicts.
    
    Shows conflicts with status PENDING_REVIEW.
    
    Args:
        callback_query: Telegram callback query
        session: Database session
        page: Page number for pagination (default 0)
        
    Raises:
        SQLAlchemyError: Database query failed
        
    Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7
    """
    from aiogram.enums import ParseMode
    from bots.tg_bot.keyboards.admin_kb import build_conflict_list_keyboard
    from bots.tg_bot.texts import ADMIN_NO_KEY_CONFLICTS
    
    admin_tg_id = callback_query.from_user.id
    
    try:
        # Verify admin authorization
        admin = await is_admin(session, admin_tg_id)
        if not admin:
            await callback_query.answer("❌ Доступ запрещен", show_alert=True)
            logger.warning(f"Unauthorized access attempt to conflict list by user {admin_tg_id}")
            return
        
        # Query GS_Keys with conflict_status=PENDING_REVIEW
        # Requirement 11.2: Filter by PENDING_REVIEW status
        query = (
            select(GS_Key)
            .where(GS_Key.conflict_status == KeyConflictStatus.PENDING_REVIEW)
            # Requirement 11.4: Order by conflict_reported_at descending (newest first)
            .order_by(GS_Key.conflict_reported_at.desc())
            # Eager load user relationship for display
            .options(selectinload(GS_Key.user))
        )
        
        result = await session.execute(query)
        all_conflicts = result.scalars().all()
        
        # Requirement 11.7: Display ADMIN_NO_KEY_CONFLICTS when list is empty
        if not all_conflicts:
            await callback_query.message.edit_text(
                text=ADMIN_NO_KEY_CONFLICTS,
                parse_mode=ParseMode.HTML
            )
            
            await callback_query.answer()
            logger.info(f"Admin {admin_tg_id} viewed empty conflict list")
            return
        
        # Requirement 11.5: Implement pagination with 10 entries per page
        ENTRIES_PER_PAGE = 10
        total_conflicts = len(all_conflicts)
        total_pages = (total_conflicts + ENTRIES_PER_PAGE - 1) // ENTRIES_PER_PAGE
        
        # Validate page number
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1
        
        # Get conflicts for current page
        start_idx = page * ENTRIES_PER_PAGE
        end_idx = start_idx + ENTRIES_PER_PAGE
        page_conflicts = all_conflicts[start_idx:end_idx]
        
        # Requirement 11.3: Format each entry with key_number, new user name, existing user name, conflict date
        conflict_list_text = "🔑 <b>Конфликты ключей</b>\n\n"
        
        for idx, conflict in enumerate(page_conflicts, start=start_idx + 1):
            conflict_date = conflict.conflict_reported_at.strftime("%d.%m.%Y %H:%M") if conflict.conflict_reported_at else "Не указано"
            
            # Get user info (this is the current owner)
            current_owner = conflict.user.full_name if conflict.user else "Не указано"
            
            conflict_list_text += (
                f"{idx}. ⚠️ <b>Ключ: {conflict.key_number}</b>\n"
                f"   👤 Текущий владелец: {current_owner}\n"
                f"   📅 Дата конфликта: {conflict_date}\n\n"
            )
        
        conflict_list_text += f"<i>Страница {page + 1} из {total_pages} • Всего: {total_conflicts}</i>"
        
        # Build keyboard with pagination
        keyboard = await build_conflict_list_keyboard(
            conflicts=page_conflicts,
            page=page,
            total_pages=total_pages
        )
        
        # Update message
        await callback_query.message.edit_text(
            text=conflict_list_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        
        await callback_query.answer()
        logger.info(
            f"Admin {admin_tg_id} viewed conflict list page {page + 1}/{total_pages} "
            f"({len(page_conflicts)} conflicts)"
        )
        
    except Exception as e:
        logger.error(f"Error displaying conflict list: {e}", exc_info=True)
        await callback_query.answer(
            "❌ Ошибка при загрузке списка конфликтов",
            show_alert=True
        )
        raise
