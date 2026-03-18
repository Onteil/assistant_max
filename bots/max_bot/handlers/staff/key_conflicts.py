"""
Admin Panel - Key Conflict Resolution Handlers for MAX Bot

Handles GS_Key ownership conflicts with transfer, rejection, and contact information workflows:
- Display paginated list of unresolved key conflicts
- View conflict details with user information
- Transfer key ownership from old user to new user
- Reject key transfer requests
- Display contact information for both parties

Migrated from Telegram bot to MAX messenger.
Uses replace_message pattern for all callback handlers.

Requirements: 24.2, 33.2, 6.1-6.8, 7.1-7.7, 8.1-8.9, 9.1-9.8, 10.1-10.6, 11.1-11.7
"""

import logging
from datetime import datetime

from maxapi.types import MessageCallback
from maxapi.context import MemoryContext
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    OperationsMenuPayload,
    KeyConflictPayload,
    AdminMenuPayload,
)
from database.models import (
    Action_Log,
    ActionType,
    GS_Key,
    KeyConflictStatus,
    MAX_Messenger_Data,
    Organization,
    Staff_Member,
    StaffRole,
    User,
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
            and_(
                Staff_Member.max_user_id == max_user_id,
                Staff_Member.is_active == True,
                Staff_Member.staff_role == StaffRole.ADMINISTRATOR
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking admin status for user {max_user_id}: {e}", exc_info=True)
        return None


# ========== Key Conflict List ==========


async def handle_key_conflict_list(
    event: MessageCallback,
    payload: OperationsMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    page: int = 0
) -> None:
    """
    Display paginated list of unresolved key conflicts.
    
    Shows conflicts with PENDING status, 5 per page.
    Uses replace_message pattern.
    
    Requirements: 11.1, 11.2
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
                text="❌ У вас нет доступа к этой функции.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get unresolved conflicts
        stmt = (
            select(GS_Key)
            .where(GS_Key.conflict_status == KeyConflictStatus.PENDING_REVIEW)
            .options(
                selectinload(GS_Key.user)
            )
            .order_by(GS_Key.conflict_reported_at.desc())
        )
        result = await session.execute(stmt)
        all_conflicts = list(result.scalars().all())
        
        if not all_conflicts:
            # No conflicts - show message with back button
            keyboard = Keyboard(
                buttons=[
                    [
                        KeyboardButton(
                            text="◀️ Назад",
                            payload=AdminMenuPayload(action="operations").pack()
                        )
                    ]
                ],
                inline=True
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="✅ <b>Конфликты ключей</b>\n\nНет неразрешенных конфликтов.",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            return
        
        # Pagination
        page_size = 5
        total_pages = (len(all_conflicts) + page_size - 1) // page_size
        page = max(0, min(page, total_pages - 1))
        
        start_idx = page * page_size
        end_idx = start_idx + page_size
        page_conflicts = all_conflicts[start_idx:end_idx]
        
        # Build conflict list text
        lines = [
            f"🔑 <b>Конфликты ключей</b> (стр. {page + 1}/{total_pages})\n",
            f"Всего неразрешенных: {len(all_conflicts)}\n"
        ]
        
        for conflict in page_conflicts:
            user_name = conflict.user.full_name if conflict.user else "Неизвестно"
            detected_date = conflict.conflict_reported_at.strftime('%d.%m.%Y') if conflict.conflict_reported_at else "Неизвестно"
            
            lines.append(
                f"\n🔸 <b>{conflict.key_number}</b>\n"
                f"   Пользователь: {user_name}\n"
                f"   Обнаружен: {detected_date}"
            )
        
        list_text = "\n".join(lines)
        
        # Build keyboard with conflict buttons and pagination
        buttons = []
        
        # Conflict buttons
        for conflict in page_conflicts:
            user_name = conflict.user.full_name if conflict.user else "Неизвестно"
            buttons.append([
                KeyboardButton(
                    text=f"🔸 {conflict.key_number} - {user_name}",
                    payload=KeyConflictPayload(action="view", key_id=conflict.id).pack()
                )
            ])
        
        # Pagination row
        if total_pages > 1:
            nav_row = []
            if page > 0:
                nav_row.append(
                    KeyboardButton(
                        text="⬅️ Назад",
                        payload=KeyConflictPayload(action="list", page=page - 1).pack()
                    )
                )
            if page < total_pages - 1:
                nav_row.append(
                    KeyboardButton(
                        text="Вперед ➡️",
                        payload=KeyConflictPayload(action="list", page=page + 1).pack()
                    )
                )
            if nav_row:
                buttons.append(nav_row)
        
        # Back button
        buttons.append([
            KeyboardButton(
                text="◀️ В меню операций",
                payload=AdminMenuPayload(action="operations").pack()
            )
        ])
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=list_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} viewed key conflicts list, page {page}")
        
    except Exception as e:
        logger.error(f"Error listing key conflicts: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке списка конфликтов.",
            parse_mode="HTML"
        )



# ========== Key Conflict View ==========


async def handle_key_conflict_view(
    event: MessageCallback,
    payload: KeyConflictPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display detailed view of a specific key conflict with action buttons.
    
    Shows key details, current owner, new user, and action buttons.
    Uses replace_message pattern.
    
    Requirements: 11.3, 11.4
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
                text="❌ У вас нет доступа к этой функции.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        key_id = payload.key_id
        
        if not key_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ключ не найден.",
                parse_mode="HTML"
            )
            return
        
        # Query GS_Key with relationships
        stmt = (
            select(GS_Key)
            .where(GS_Key.id == key_id)
            .options(
                selectinload(GS_Key.user)
            )
        )
        result = await session.execute(stmt)
        gs_key = result.scalar_one_or_none()
        
        if not gs_key:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ключ не найден.",
                parse_mode="HTML"
            )
            return
        
        # Get new_user_id from Action_Log (most recent conflict for this key)
        stmt = (
            select(Action_Log)
            .where(Action_Log.action_type == ActionType.KEY_CONFLICT_DETECTED)
            .where(Action_Log.action_details['key_number'].astext == gs_key.key_number)
            .order_by(Action_Log.action_timestamp.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        conflict_log = result.scalar_one_or_none()
        
        new_user_id = None
        new_user = None
        new_user_name = "Неизвестно"
        new_user_phone = "Не указано"
        
        if conflict_log and conflict_log.action_details:
            new_user_id = conflict_log.action_details.get('new_user_id')
            if new_user_id:
                # Get new user details
                stmt = select(User).where(User.id == new_user_id)
                result = await session.execute(stmt)
                new_user = result.scalar_one_or_none()
                if new_user:
                    new_user_name = new_user.full_name or "Неизвестно"
                    new_user_phone = new_user.phone_number or "Не указано"
        
        existing_user = gs_key.user
        
        # Format conflict details
        conflict_date = gs_key.conflict_reported_at.strftime("%d.%m.%Y %H:%M") if gs_key.conflict_reported_at else "Не указано"
        
        existing_user_name = existing_user.full_name if existing_user else "Неизвестно"
        existing_user_phone = existing_user.phone_number if existing_user else "Не указано"
        
        # Build message text
        message_text = (
            f"🔑 <b>Конфликт ключа</b>\n\n"
            f"<b>Ключ:</b> {gs_key.key_number}\n"
            f"<b>Обнаружен:</b> {conflict_date}\n\n"
            f"👤 <b>Текущий владелец:</b>\n"
            f"   Имя: {existing_user_name}\n"
            f"   Телефон: {existing_user_phone}\n\n"
            f"👤 <b>Новый пользователь:</b>\n"
            f"   Имя: {new_user_name}\n"
            f"   Телефон: {new_user_phone}\n\n"
            f"Выберите действие:"
        )
        
        # Build action buttons with new_user_id
        buttons = [
            [
                KeyboardButton(
                    text="✅ Передать ключ",
                    payload=KeyConflictPayload(action="transfer", key_id=key_id, new_user_id=new_user_id).pack()
                )
            ],
            [
                KeyboardButton(
                    text="❌ Отклонить запрос",
                    payload=KeyConflictPayload(action="reject", key_id=key_id, new_user_id=new_user_id).pack()
                )
            ],
            [
                KeyboardButton(
                    text="📞 Контакты сторон",
                    payload=KeyConflictPayload(action="contact", key_id=key_id, new_user_id=new_user_id).pack()
                )
            ],
            [
                KeyboardButton(
                    text="◀️ К списку конфликтов",
                    payload=KeyConflictPayload(action="list").pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=message_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} viewed conflict detail for key {gs_key.key_number}")
        
    except Exception as e:
        logger.error(f"Error displaying conflict view: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке конфликта.",
            parse_mode="HTML"
        )


# ========== Key Transfer ==========


async def handle_key_transfer(
    event: MessageCallback,
    payload: KeyConflictPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Transfer key ownership from existing user to new user.
    
    Workflow:
    1. Call i-TAT API POST /assets/transfer_key
    2. Update GS_Key.user_id = new_user_id
    3. Update GS_Key.conflict_status = RESOLVED
    4. Send notifications to both users via MAX messenger
    5. Log action in Action_Log
    
    Uses replace_message pattern.
    
    Requirements: 8.1-8.9
    """
    from services.i_tat_service import get_itat_client
    import httpx
    
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой функции.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        key_id = payload.key_id
        new_user_id = payload.new_user_id
        
        if not key_id or not new_user_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Недостаточно данных для передачи ключа.",
                parse_mode="HTML"
            )
            return
        
        # Get key with relationships
        stmt = (
            select(GS_Key)
            .where(GS_Key.id == key_id)
            .options(selectinload(GS_Key.user))
        )
        result = await session.execute(stmt)
        gs_key = result.scalar_one_or_none()
        
        if not gs_key:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ключ не найден.",
                parse_mode="HTML"
            )
            return
        
        # Check if already resolved
        if gs_key.conflict_status == KeyConflictStatus.RESOLVED:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="✅ Конфликт уже разрешен.",
                parse_mode="HTML"
            )
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
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователи не найдены.",
                parse_mode="HTML"
            )
            return
        
        # Call i-TAT API POST /assets/resolve_conflict
        api_client = get_itat_client()
        api_success = False
        api_error_message = None
        
        try:
            logger.info(
                f"Calling i-TAT API to resolve key conflict {key_number} "
                f"from user {old_user.phone_number} to user {new_user.phone_number}"
            )
            api_response = await api_client.resolve_conflict(
                key_number=key_number,
                action="transfer",
                new_user_phone=new_user.phone_number,
                old_user_phone=old_user.phone_number,
                user_id=max_user_id,
                messenger="max",
                reason=f"Одобрено администратором {admin.full_name}"
            )
            api_success = True
            logger.info(f"i-TAT API key conflict resolution successful: {api_response}")
            
        except httpx.TimeoutException as e:
            api_error_message = "Превышено время ожидания ответа от CRM"
            logger.error(f"i-TAT API timeout for key conflict resolution: {e}", exc_info=True)
            
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
                f"i-TAT API HTTP error for key conflict resolution: {status_code} - {e.response.text}",
                exc_info=True
            )
            
        except httpx.ConnectError as e:
            api_error_message = "Не удалось подключиться к CRM"
            logger.error(f"i-TAT API connection error for key conflict resolution: {e}", exc_info=True)
            
        except Exception as e:
            api_error_message = "Неизвестная ошибка при обращении к CRM"
            logger.error(f"Unexpected error calling i-TAT API for key conflict resolution: {e}", exc_info=True)
        
        # If API call failed, show error and log
        if not api_success:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка: {api_error_message}\n\nПопробуйте позже или обратитесь к администратору.",
                parse_mode="HTML"
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
                action_timestamp=datetime.utcnow()
            )
            session.add(action_log)
            await session.commit()
            
            return
        
        # Update GS_Key.user_id to new_user_id
        gs_key.user_id = new_user_id
        
        # Update GS_Key.conflict_status to RESOLVED
        gs_key.conflict_status = KeyConflictStatus.RESOLVED
        
        await session.commit()
        
        logger.info(
            f"Updated GS_Key {key_number} ownership: "
            f"old_user={old_user_id} -> new_user={new_user_id}"
        )
        
        # Send notifications to both users via MAX messenger
        # Send to new user
        if new_user.max_user_id:
            try:
                # Get MAX chat_id for new user
                stmt = select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == new_user.id)
                result = await session.execute(stmt)
                max_data = result.scalar_one_or_none()
                
                if max_data:
                    await messenger_adapter.send_message(
                        chat_id=max_data.max_chat_id,
                        text=f"✅ <b>Ключ передан вам</b>\n\nКлюч <code>{key_number}</code> теперь принадлежит вам.",
                        parse_mode="HTML"
                    )
                    logger.info(f"Sent key transfer notification to new user {new_user.id}")
            except Exception as send_error:
                logger.error(
                    f"Failed to send key transfer notification to new user {new_user.id}: {send_error}",
                    exc_info=True
                )
        
        # Send to old user
        if old_user.max_user_id:
            try:
                # Get MAX chat_id for old user
                stmt = select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == old_user.id)
                result = await session.execute(stmt)
                max_data = result.scalar_one_or_none()
                
                if max_data:
                    await messenger_adapter.send_message(
                        chat_id=max_data.max_chat_id,
                        text=f"ℹ️ <b>Ключ передан</b>\n\nКлюч <code>{key_number}</code> был передан другому пользователю.",
                        parse_mode="HTML"
                    )
                    logger.info(f"Sent key transfer notification to old user {old_user.id}")
            except Exception as send_error:
                logger.error(
                    f"Failed to send key transfer notification to old user {old_user.id}: {send_error}",
                    exc_info=True
                )
        
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
                "admin_max_id": max_user_id
            },
            action_timestamp=datetime.utcnow()
        )
        session.add(action_log)
        await session.commit()
        
        # Show success message with back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ К списку конфликтов",
                        payload=KeyConflictPayload(action="list").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ <b>Ключ передан</b>\n\n"
                f"Ключ <code>{key_number}</code> успешно передан пользователю {new_user.full_name or 'Не указано'}.\n\n"
                f"Конфликт разрешен."
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Key {key_number} transferred from user {old_user_id} to user {new_user_id} "
            f"by admin {admin.full_name} (ID: {admin.id})"
        )
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error transferring key: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при передаче ключа.",
            parse_mode="HTML"
        )


# ========== Key Rejection ==========


async def handle_key_rejection(
    event: MessageCallback,
    payload: KeyConflictPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Reject key transfer request.
    
    Workflow:
    1. Delete any GS_Key records for new user with this key_number
    2. Update GS_Key.conflict_status = RESOLVED
    3. Send notification to new user (KEY_CONFLICT_REJECTED)
    4. Log action in Action_Log
    
    Uses replace_message pattern.
    
    Requirements: 9.1-9.8
    """
    from sqlalchemy import delete
    from database.models import ticket_keys
    
    chat_id = event.message.recipient.chat_id
    max_user_id = event.callback.user.user_id
    message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой функции.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        key_id = payload.key_id
        new_user_id = payload.new_user_id
        
        if not key_id or not new_user_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Недостаточно данных для отклонения запроса.",
                parse_mode="HTML"
            )
            return
        
        # Get key
        stmt = select(GS_Key).where(GS_Key.id == key_id)
        result = await session.execute(stmt)
        gs_key = result.scalar_one_or_none()
        
        if not gs_key:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ключ не найден.",
                parse_mode="HTML"
            )
            return
        
        # Check if already resolved
        if gs_key.conflict_status == KeyConflictStatus.RESOLVED:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="✅ Конфликт уже разрешен.",
                parse_mode="HTML"
            )
            return
        
        key_number = gs_key.key_number
        
        # Query new user and old user (current owner)
        stmt = select(User).where(User.id == new_user_id)
        result = await session.execute(stmt)
        new_user = result.scalar_one_or_none()
        
        # Get current owner
        stmt = select(User).where(User.id == gs_key.user_id)
        result = await session.execute(stmt)
        old_user = result.scalar_one_or_none()
        
        if not new_user or not old_user:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Пользователи не найдены.",
                parse_mode="HTML"
            )
            return
        
        # Call i-TAT API POST /assets/resolve_conflict with reject action
        api_client = get_itat_client()
        try:
            logger.info(
                f"Calling i-TAT API to reject key conflict {key_number} "
                f"from user {old_user.phone_number} to user {new_user.phone_number}"
            )
            api_response = await api_client.resolve_conflict(
                key_number=key_number,
                action="reject",
                new_user_phone=new_user.phone_number,
                old_user_phone=old_user.phone_number,
                user_id=max_user_id,
                messenger="max",
                reason=f"Отклонено администратором {admin.full_name}"
            )
            logger.info(f"i-TAT API key conflict rejection successful: {api_response}")
            
        except Exception as api_error:
            logger.error(f"i-TAT API error for key conflict rejection: {api_error}")
            # Continue with local processing even if API fails
        
        # Find all GS_Key records for this key_number from new user
        keys_to_delete_stmt = select(GS_Key).where(
            GS_Key.user_id == new_user_id,
            GS_Key.key_number == key_number
        )
        keys_to_delete_result = await session.execute(keys_to_delete_stmt)
        keys_to_delete = keys_to_delete_result.scalars().all()
        
        if keys_to_delete:
            # Delete related ticket_keys entries first
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
        
        await session.commit()
        
        logger.info(f"Updated GS_Key {key_number} conflict status to RESOLVED (rejected)")
        
        # Send KEY_CONFLICT_REJECTED notification to new user
        if new_user.max_user_id:
            try:
                # Get MAX chat_id for new user
                stmt = select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == new_user.id)
                result = await session.execute(stmt)
                max_data = result.scalar_one_or_none()
                
                if max_data:
                    await messenger_adapter.send_message(
                        chat_id=max_data.max_chat_id,
                        text=f"❌ <b>Запрос отклонен</b>\n\nВаш запрос на ключ <code>{key_number}</code> был отклонен администратором.",
                        parse_mode="HTML"
                    )
                    logger.info(f"Sent key rejection notification to user {new_user.id}")
            except Exception as send_error:
                logger.error(
                    f"Failed to send key rejection notification to user {new_user.id}: {send_error}",
                    exc_info=True
                )
        
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
                "admin_max_id": max_user_id
            },
            action_timestamp=datetime.utcnow()
        )
        session.add(action_log)
        await session.commit()
        
        # Show success message with back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ К списку конфликтов",
                        payload=KeyConflictPayload(action="list").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"❌ <b>Запрос отклонен</b>\n\n"
                f"Запрос на передачу ключа <code>{key_number}</code> от пользователя {new_user.full_name or 'Не указано'} отклонен.\n\n"
                f"Ключ остается у текущего владельца."
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Key conflict rejected for key {key_number}, user {new_user_id} "
            f"by admin {admin.full_name} (ID: {admin.id})"
        )
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error rejecting key transfer: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при отклонении запроса.",
            parse_mode="HTML"
        )


# ========== Contact Information ==========


async def handle_key_conflict_contact(
    event: MessageCallback,
    payload: KeyConflictPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Display contact information for both parties in key conflict.
    
    Shows detailed contact info for current owner and new user.
    Uses replace_message pattern.
    
    Requirements: 11.8
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
                text="❌ У вас нет доступа к этой функции.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        key_id = payload.key_id
        
        if not key_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ключ не найден.",
                parse_mode="HTML"
            )
            return
        
        # Get key with relationships
        stmt = (
            select(GS_Key)
            .where(GS_Key.id == key_id)
            .options(
                selectinload(GS_Key.user).selectinload(User.organizations),
                selectinload(GS_Key.user).selectinload(User.gs_keys)
            )
        )
        result = await session.execute(stmt)
        gs_key = result.scalar_one_or_none()
        
        if not gs_key:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ключ не найден.",
                parse_mode="HTML"
            )
            return
        
        # Get new_user_id from Action_Log or payload
        new_user_id = payload.new_user_id
        
        if not new_user_id:
            # Try to get from Action_Log if not in payload
            stmt = (
                select(Action_Log)
                .where(Action_Log.action_type == ActionType.KEY_CONFLICT_DETECTED)
                .where(Action_Log.action_details['key_number'].astext == gs_key.key_number)
                .order_by(Action_Log.action_timestamp.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            conflict_log = result.scalar_one_or_none()
            
            if conflict_log and conflict_log.action_details:
                new_user_id = conflict_log.action_details.get('new_user_id')
        
        # Get new user details
        new_user = None
        if new_user_id:
            stmt = (
                select(User)
                .where(User.id == new_user_id)
                .options(
                    selectinload(User.organizations),
                    selectinload(User.gs_keys)
                )
            )
            result = await session.execute(stmt)
            new_user = result.scalar_one_or_none()
        
        existing_user = gs_key.user
        
        # Format user information helper
        def format_user_info(user: User, label: str) -> str:
            """Format user information block."""
            info = f"<b>{label}:</b>\n"
            info += f"👤 ФИО: {user.full_name or 'Не указано'}\n"
            
            # Format phone number
            phone = user.phone_number or "Не указано"
            if phone != "Не указано" and not phone.startswith("+"):
                phone = f"+{phone}"
            info += f"📱 Телефон: {phone}\n"
            
            # Email
            info += f"📧 Email: {user.email or 'Не указано'}\n"
            
            # MAX ID
            if user.max_user_id:
                info += f"💬 MAX ID: <code>{user.max_user_id}</code>\n"
            
            # Registration date
            reg_date = user.created_at.strftime("%d.%m.%Y") if user.created_at else "Не указано"
            info += f"📅 Регистрация: {reg_date}\n"
            
            # GS_Keys
            if user.gs_keys:
                keys_list = ", ".join([key.key_number for key in user.gs_keys])
                info += f"🔑 Ключи ГС: {keys_list}\n"
            else:
                info += "🔑 Ключи ГС: Не указано\n"
            
            # Organizations (INN and name if available)
            if user.organizations:
                orgs = ", ".join([
                    f"{org.inn} ({org.organization_name})" if org.organization_name else org.inn
                    for org in user.organizations
                ])
                info += f"🏢 Организации: {orgs}\n"
            else:
                info += "🏢 Организации: Не указано\n"
            
            return info
        
        # Build contact information message
        message_text = f"📞 <b>Контактная информация</b>\n\n"
        message_text += f"<b>Ключ:</b> {gs_key.key_number}\n\n"
        
        # Current owner
        if existing_user:
            message_text += format_user_info(existing_user, "Текущий владелец")
        else:
            message_text += "<b>Текущий владелец:</b>\n   Информация недоступна\n"
        
        message_text += "\n"
        
        # New user
        if new_user:
            message_text += format_user_info(new_user, "Новый пользователь")
        else:
            message_text += "<b>Новый пользователь:</b>\n   Информация недоступна\n"
        
        # Build back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ К деталям конфликта",
                        payload=KeyConflictPayload(action="view", key_id=key_id, new_user_id=new_user_id).pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=message_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} viewed contact info for key conflict {key_id}")
        
    except Exception as e:
        logger.error(f"Error displaying contact info: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке контактов.",
            parse_mode="HTML"
        )
