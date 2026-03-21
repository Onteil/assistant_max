"""
Admin Panel - Operations Handlers for MAX Bot

Handles administrative operational activities:
- Broadcast creation and delivery
- Key conflict resolution
- Escalations management

Migrated from Telegram bot to MAX messenger.
Uses replace_message pattern for all callback handlers.

Requirements: 9.x, 10.x, 11.x
"""

import logging
from datetime import datetime

from maxapi.types import MessageCallback, MessageCreated
from maxapi.context import MemoryContext
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter, Keyboard, KeyboardButton
from bots.max_bot.payloads import (
    AdminMenuPayload,
    OperationsMenuPayload,
    BroadcastPayload,
)
from bots.max_bot.states import OperationsStates
from database.models import (
    Action_Log,
    ActionType,
    Staff_Member,
    StaffRole,
    User,
    Broadcast,
)
from services.broadcast_service import (
    create_broadcast,
    get_target_users,
    create_delivery_records,
    send_broadcast,
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


# ========== Operations Menu ==========


async def handle_operations_menu(
    event: MessageCallback,
    payload: AdminMenuPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Operations" menu button in admin panel.
    
    Shows operations submenu with broadcast, key conflicts, and escalations.
    Uses replace_message pattern.
    
    Requirements: 1.3, 10.1, 24.3, 24.6
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
                text="❌ У вас нет доступа к административной панели.",
                parse_mode="HTML"
            )
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get operation counts for display
        from bots.max_bot.utils.operations_counter import count_all_operations, format_operation_counter
        
        try:
            operations_counts = await count_all_operations(session)
            key_conflicts_counter = format_operation_counter(operations_counts['key_conflicts'])
            phone_changes_counter = format_operation_counter(operations_counts['phone_changes'])
            escalations_counter = format_operation_counter(operations_counts['escalations'])
        except Exception as e:
            logger.error(f"Error getting operation counts for operations menu: {e}")
            key_conflicts_counter = ""
            phone_changes_counter = ""
            escalations_counter = ""
        
        # Build operations menu keyboard
        buttons = [
            [
                KeyboardButton(
                    text=f"🔑 Конфликты ключей{key_conflicts_counter}",
                    payload=OperationsMenuPayload(action="key_conflicts").pack()
                )
            ],
            # [
            #     KeyboardButton(
            #         text=f"📱 Смена номеров{phone_changes_counter}",
            #         payload=OperationsMenuPayload(action="phone_changes").pack()
            #     )
            # ],
            [
                KeyboardButton(
                    text="📢 Рассылка",
                    payload=BroadcastPayload(action="create").pack()
                )
            ],
            [
                KeyboardButton(
                    text=f"⚠️ Эскалации{escalations_counter}",
                    payload=OperationsMenuPayload(action="escalations").pack()
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
        
        # Build operations menu text with counts
        operations_text = (
            "📋 <b>Операции</b>\n\n"
            "Раздел для управления операционными процессами и мониторинга системы.\n\n"
            "<b>Доступные функции:</b>\n\n"
        )
        
        # Add key conflicts section
        if operations_counts['key_conflicts'] > 0:
            operations_text += f"🔑 <b>Конфликты ключей</b> ({operations_counts['key_conflicts']})\n"
        else:
            operations_text += "🔑 <b>Конфликты ключей</b>\n"
        operations_text += ("Разрешение конфликтов при дублировании ключей GS_Key между пользователями. "
                           "Передача ключа новому владельцу или отклонение претензии.\n\n")
        
        # Add phone changes section
        # if operations_counts['phone_changes'] > 0:
        #     operations_text += f"📱 <b>Смена номеров</b> ({operations_counts['phone_changes']})\n"
        # else:
        #     operations_text += "📱 <b>Смена номеров</b>\n"
        # operations_text += ("Обработка запросов на смену номера телефона. "
        #                    "Проверка и подтверждение изменений контактных данных.\n\n")
        
        # Add broadcast section (no counter needed)
        operations_text += ("📢 <b>Рассылка</b>\n"
                           "Создание и отправка массовых уведомлений пользователям. "
                           "Выбор целевой аудитории, предпросмотр и отправка сообщений.\n\n")
        
        # Add escalations section
        if operations_counts['escalations'] > 0:
            operations_text += f"⚠️ <b>Эскалации</b> ({operations_counts['escalations']})\n"
        else:
            operations_text += "⚠️ <b>Эскалации</b>\n"
        operations_text += ("Мониторинг и управление эскалированными заявками. "
                           "Просмотр заявок, требующих внимания администратора, переназначение и контроль.")
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=operations_text,
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} accessed operations menu")
        
    except Exception as e:
        logger.error(f"Error showing operations menu: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при загрузке меню.",
            parse_mode="HTML"
        )


# ========== Broadcast System ==========


async def handle_broadcast_create(
    event: MessageCallback,
    payload: BroadcastPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Broadcast" menu button - start broadcast creation flow.
    
    Prompts administrator to enter broadcast message content.
    Uses replace_message pattern.
    
    Requirements: 10.1
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
        
        # Set state to wait for broadcast content
        await context.set_state(OperationsStates.creating_broadcast_content)
        
        # Show prompt with cancel button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="❌ Отмена",
                        payload=AdminMenuPayload(action="operations").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "📢 <b>Создание рассылки</b>\n\n"
                "Введите текст сообщения для рассылки.\n\n"
                "Отправьте текст сообщения:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Administrator {max_user_id} started broadcast creation")
        
    except Exception as e:
        logger.error(f"Error starting broadcast creation: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )



async def handle_broadcast_content_input(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle broadcast content input from administrator.
    
    Creates broadcast record and prompts for targeting selection.
    Uses replace_message pattern.
    
    Requirements: 10.1, 10.2
    """
    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    
    try:
        # Verify user is administrator
        admin = await is_admin(session, max_user_id)
        if not admin:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ У вас нет доступа к этой функции.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        message_text = event.message.body.text
        
        # Create broadcast in DRAFT status
        broadcast = await create_broadcast(
            session=session,
            created_by_staff_id=admin.id,
            message_text=message_text
        )
        
        # Store broadcast ID in context
        await context.update_data(broadcast_id=broadcast.id)
        
        # Set state to wait for targeting selection
        await context.set_state(OperationsStates.selecting_broadcast_target)
        
        # Build targeting keyboard
        buttons = [
            [
                KeyboardButton(
                    text="👥 Всем пользователям",
                    payload=BroadcastPayload(action="target", broadcast_id=broadcast.id, target_type="all").pack()
                )
            ],
            [
                KeyboardButton(
                    text="✅ С активной подпиской",
                    payload=BroadcastPayload(action="target", broadcast_id=broadcast.id, target_type="active_subscription").pack()
                )
            ],
            [
                KeyboardButton(
                    text="📧 Согласившимся на уведомление",
                    payload=BroadcastPayload(action="target", broadcast_id=broadcast.id, target_type="marketing_consent").pack()
                )
            ],
            [
                KeyboardButton(
                    text="❌ Отмена",
                    payload=BroadcastPayload(action="cancel", broadcast_id=broadcast.id).pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        # Show targeting options
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "📊 <b>Выбор целевой аудитории</b>\n\n"
                "Выберите, кому отправить рассылку:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Admin {admin.id} entered broadcast content, broadcast {broadcast.id} created")
        
    except Exception as e:
        logger.error(f"Error handling broadcast content: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при создании рассылки. Попробуйте позже.",
            parse_mode="HTML"
        )
        await context.clear()


async def handle_broadcast_targeting(
    event: MessageCallback,
    payload: BroadcastPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle targeting selection for broadcast.
    
    Gets target users, creates delivery records, and shows preview.
    Uses replace_message pattern.
    
    Requirements: 10.2, 10.3, 10.4
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
            await context.clear()
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Get broadcast ID from payload
        broadcast_id = payload.broadcast_id
        target = payload.target_type
        
        if not broadcast_id or not target:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка: рассылка не найдена.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Get target users for MAX messenger
        target_users = await get_target_users(session, target, messenger="max")
        
        if not target_users:
            # No users found - show message with back button
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
                text="⚠️ Не найдено пользователей для выбранной целевой аудитории.",
                keyboard=keyboard,
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Create delivery records
        user_ids = [user.id for user in target_users]
        await create_delivery_records(session, broadcast_id, user_ids)
        
        # Update broadcast target count
        result = await session.execute(
            select(Broadcast).where(Broadcast.id == broadcast_id)
        )
        broadcast = result.scalar_one()
        broadcast.target_user_count = len(user_ids)
        await session.commit()
        
        # Store target info in context
        await context.update_data(target=target, target_count=len(user_ids))
        
        # Set state to confirming
        await context.set_state(OperationsStates.confirming_broadcast)
        
        # Build preview keyboard
        buttons = [
            [
                KeyboardButton(
                    text="🚀 Запустить рассылку",
                    payload=BroadcastPayload(action="send", broadcast_id=broadcast_id).pack()
                )
            ],
            [
                KeyboardButton(
                    text="❌ Отмена",
                    payload=BroadcastPayload(action="cancel", broadcast_id=broadcast_id).pack()
                )
            ]
        ]
        
        keyboard = Keyboard(buttons=buttons, inline=True)
        
        # Target display names
        target_display = {
            "all": "Всем пользователям",
            "active_subscription": "Пользователям с активной подпиской",
            "marketing_consent": "Пользователям, согласившимся на маркетинг"
        }
        
        target_text = target_display.get(target, target)
        
        # Show preview
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"📋 <b>Превью рассылки</b>\n\n"
                f"<b>Целевая аудитория:</b> {target_text}\n"
                f"<b>Количество получателей:</b> {len(user_ids)}\n\n"
                f"<b>Текст сообщения:</b>\n"
                f"{broadcast.message_text}\n\n"
                f"Подтвердите запуск рассылки:"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(
            f"Admin {admin.id} selected target '{target}' for broadcast {broadcast_id}, "
            f"{len(user_ids)} recipients"
        )
        
    except Exception as e:
        logger.error(f"Error handling broadcast targeting: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при подготовке рассылки. Попробуйте позже.",
            parse_mode="HTML"
        )
        await context.clear()


async def handle_broadcast_send(
    event: MessageCallback,
    payload: BroadcastPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle "Launch" button - send broadcast to all target users.
    
    Sends messages to all users and provides delivery report.
    Uses replace_message pattern.
    
    Requirements: 10.5, 10.6, 10.7
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
            await context.clear()
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        broadcast_id = payload.broadcast_id
        
        if not broadcast_id:
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="❌ Ошибка: рассылка не найдена.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Show "sending" message
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                "🚀 <b>Запуск рассылки...</b>\n\n"
                "Отправка сообщений пользователям. Это может занять некоторое время."
            ),
            parse_mode="HTML"
        )
        
        # Send broadcast via MAX messenger
        delivered_count, error_count = await send_broadcast(
            session=session,
            broadcast_id=broadcast_id,
            messenger_adapter=messenger_adapter
        )
        
        # Log action
        action_log = Action_Log(
            action_type=ActionType.BROADCAST_SENT,
            staff_id=admin.id,
            action_details={
                "broadcast_id": broadcast_id,
                "delivered_count": delivered_count,
                "error_count": error_count
            }
        )
        session.add(action_log)
        await session.commit()
        
        # Show delivery report
        total_count = delivered_count + error_count
        success_rate = (delivered_count / total_count * 100) if total_count > 0 else 0
        
        # Build back button
        keyboard = Keyboard(
            buttons=[
                [
                    KeyboardButton(
                        text="◀️ В меню операций",
                        payload=AdminMenuPayload(action="operations").pack()
                    )
                ]
            ],
            inline=True
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=(
                f"✅ <b>Рассылка завершена</b>\n\n"
                f"<b>Всего получателей:</b> {total_count}\n"
                f"<b>Доставлено:</b> {delivered_count}\n"
                f"<b>Ошибок:</b> {error_count}\n"
                f"<b>Успешность:</b> {success_rate:.1f}%"
            ),
            keyboard=keyboard,
            parse_mode="HTML"
        )
        
        # Clear FSM state
        await context.clear()
        
        logger.info(
            f"Admin {admin.id} sent broadcast {broadcast_id}: "
            f"delivered={delivered_count}, errors={error_count}"
        )
        
    except Exception as e:
        logger.error(f"Error sending broadcast: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при отправке рассылки. Попробуйте позже.",
            parse_mode="HTML"
        )
        await context.clear()


async def handle_broadcast_cancel(
    event: MessageCallback,
    payload: BroadcastPayload,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle broadcast cancellation.
    
    Deletes broadcast and returns to operations menu.
    Uses replace_message pattern.
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
            await context.clear()
            return
        
        # Delete old message
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Clear FSM state
        await context.clear()
        
        # Return to operations menu
        operations_payload = AdminMenuPayload(action="operations")
        await handle_operations_menu(
            event=event,
            payload=operations_payload,
            context=context,
            session=session,
            messenger_adapter=messenger_adapter
        )
        
        logger.info(f"Admin {admin.id} cancelled broadcast creation")
        
    except Exception as e:
        logger.error(f"Error cancelling broadcast: {e}", exc_info=True)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка.",
            parse_mode="HTML"
        )
