"""
Escalation Test API Endpoint

This module implements the API endpoint for testing ticket escalation functionality.
Allows administrators to manually trigger escalation for a specific ticket to test
the escalation flow, notifications, and manager reassignment logic.

Requirements: 6.1, 8 - Escalation testing functionality
"""

import logging
from typing import Annotated

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.schemas.escalation_test_schemas import (
    EscalationTestRequest,
    EscalationTestResponse,
    BackupManagerTestRequest,
    BackupManagerTestResponse,
)
from constants import get_session, WEBHOOK_API_KEY, TG_BOT_TOKEN, MAX_BOT_TOKEN
from database.models import (
    Escalation,
    EscalationType,
    Staff_Member,
    StaffRole,
    Ticket,
    TicketStatus,
    TicketType,
)
from services.escalation_service import create_escalation, get_active_admins
from services.settings_service import get_setting, get_escalation_channels

router = APIRouter()
logger = logging.getLogger(__name__)


def is_max_chat_id(chat_id: str) -> bool:
    """
    Determine if chat_id is for MAX messenger.
    
    MAX chat IDs are typically very long negative numbers (e.g., -71826453867944).
    Telegram chat IDs are shorter (e.g., -1001234567890 for supergroups).
    
    Args:
        chat_id: Chat ID string
        
    Returns:
        True if MAX chat ID, False if Telegram
    """
    try:
        chat_id_int = int(chat_id)
        # MAX chat IDs are typically < -10^13 (very long negative numbers)
        # Telegram supergroup IDs are typically > -10^13
        return chat_id_int < -10000000000000
    except (ValueError, TypeError):
        return False


async def verify_webhook_api_key(
    x_api_key: Annotated[str | None, Header()] = None
) -> str:
    """
    Verify webhook API key authentication.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        Validated API key
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    if not x_api_key:
        logger.warning("Escalation test API request received without API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    if not WEBHOOK_API_KEY:
        logger.error("WEBHOOK_API_KEY not configured in environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured on server",
        )
    
    if x_api_key != WEBHOOK_API_KEY:
        logger.warning(f"Invalid API key attempt: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return x_api_key


@router.post("/escalation/test", response_model=EscalationTestResponse)
async def test_ticket_escalation(
    request: EscalationTestRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> EscalationTestResponse:
    """
    Test escalation functionality for a specific ticket.
    
    This endpoint allows administrators to manually trigger escalation for testing purposes.
    It creates an escalation record and sends notifications to administrators, simulating
    the automatic escalation that would occur after timeout.
    
    Use cases:
    - Test escalation notifications
    - Verify escalation channel configuration
    - Test manager reassignment flow
    - Validate escalation UI in admin panel
    
    Example request:
    POST /api/escalation/test
    Headers:
        X-API-Key: your-api-key-here
        Content-Type: application/json
    Body:
        {
            "ticket_id": 123,
            "force_escalation": false
        }
    
    Example response:
    {
        "success": true,
        "message": "Escalation test completed successfully",
        "ticket_id": 123,
        "escalation_triggered": true,
        "escalation_id": 45,
        "current_status": "new",
        "assigned_staff_id": 789
    }
    
    Args:
        request: Escalation test request with ticket_id and options
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        Escalation test result with details
        
    Raises:
        HTTPException: 404 if ticket not found
        HTTPException: 400 if ticket is not eligible for escalation
        HTTPException: 500 if escalation creation fails
        
    Requirements:
        - 6.1: Test escalation for specific ticket
        - 8: Admin panel escalation testing
    """
    logger.info(
        f"Escalation test API request received: ticket_id={request.ticket_id}, "
        f"force={request.force_escalation}"
    )
    
    try:
        # Step 1: Query ticket with relationships
        stmt = (
            select(Ticket)
            .where(Ticket.id == request.ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.assigned_staff),
                selectinload(Ticket.organization)
            )
        )
        
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        # Check if ticket exists
        if not ticket:
            logger.error(f"Ticket not found: ticket_id={request.ticket_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket with ID {request.ticket_id} not found",
            )
        
        # Step 2: Check if ticket is eligible for escalation
        if not request.force_escalation:
            # Only NEW tickets should be escalated in normal flow
            if ticket.ticket_status != TicketStatus.NEW:
                logger.warning(
                    f"Ticket not eligible for escalation: ticket_id={request.ticket_id}, "
                    f"status={ticket.ticket_status.value}"
                )
                return EscalationTestResponse(
                    success=False,
                    message=f"Ticket is not in NEW status (current: {ticket.ticket_status.value}). "
                            f"Use force_escalation=true to override.",
                    ticket_id=ticket.id,
                    escalation_triggered=False,
                    escalation_id=None,
                    current_status=ticket.ticket_status.value,
                    assigned_staff_id=ticket.assigned_staff_id,
                )
            
            # Check if ticket is already escalated
            if ticket.is_escalated:
                logger.warning(
                    f"Ticket already escalated: ticket_id={request.ticket_id}"
                )
                return EscalationTestResponse(
                    success=False,
                    message="Ticket is already escalated. Use force_escalation=true to create another escalation.",
                    ticket_id=ticket.id,
                    escalation_triggered=False,
                    escalation_id=None,
                    current_status=ticket.ticket_status.value,
                    assigned_staff_id=ticket.assigned_staff_id,
                )
        
        # Step 3: Create escalation record
        escalation = await create_escalation(
            session=session,
            ticket_id=ticket.id,
            escalation_type=EscalationType.ESCALATION_20MIN
        )
        
        # Mark ticket as escalated
        ticket.is_escalated = True
        ticket.escalated_at = escalation.created_at
        
        await session.commit()
        await session.refresh(escalation)
        
        logger.info(
            f"Test escalation created: escalation_id={escalation.id}, "
            f"ticket_id={ticket.id}"
        )
        
        # Step 4: Send notifications to administrators and escalation channels
        admins = await get_active_admins(session)
        
        # Initialize bots
        tg_bot = None
        max_bot_instance = None
        
        if TG_BOT_TOKEN:
            tg_bot = Bot(
                token=TG_BOT_TOKEN,
                default=DefaultBotProperties(parse_mode="HTML")
            )
        
        if MAX_BOT_TOKEN:
            try:
                from maxapi import Bot as MAXBot
                from maxapi.types import ParseMode
                max_bot_instance = MAXBot(
                    token=MAX_BOT_TOKEN,
                    parse_mode=ParseMode.HTML
                )
            except ImportError as e:
                logger.warning(f"maxapi not available: {e}, MAX notifications will be skipped")
            except Exception as e:
                logger.error(f"Failed to initialize MAX bot: {e}", exc_info=True)
        
        # Ticket type display
        ticket_type_display = {
            "invoice": "Счет",
            "technical_support": "Техподдержка",
            "renewal": "Продление"
        }
        ticket_type_text = ticket_type_display.get(
            ticket.ticket_type.value,
            ticket.ticket_type.value
        )
        
        # Build notification message
        notification_text = (
            f"🔥 <b>ТЕСТОВАЯ ЭСКАЛАЦИЯ</b>\n\n"
            f"<b>Заявка:</b> #{ticket.id}\n"
            f"<b>Тип:</b> {ticket_type_text}\n"
            f"<b>Клиент:</b> {ticket.user.full_name}\n"
        )
        
        if ticket.organization:
            notification_text += f"<b>ИНН:</b> {ticket.organization.inn}\n"
        
        if ticket.assigned_staff:
            notification_text += f"<b>Ответственный:</b> {ticket.assigned_staff.full_name}\n"
        else:
            notification_text += f"<b>Ответственный:</b> Не назначен\n"
        
        notification_text += (
            f"\n<i>Это тестовая эскалация, созданная через API.</i>\n"
            f"<i>Используйте админ-панель для проверки функционала.</i>"
        )
        
        notifications_sent = 0
        channels_notified = []
        
        # Send to all admins (both Telegram and MAX)
        if admins:
            for admin in admins:
                # Try Telegram first
                if admin.tg_user_id and tg_bot:
                    try:
                        await tg_bot.send_message(
                            chat_id=admin.tg_user_id,
                            text=notification_text,
                            parse_mode="HTML"
                        )
                        notifications_sent += 1
                        logger.info(
                            f"Test escalation notification sent to admin via Telegram: "
                            f"admin_id={admin.id}, tg_user_id={admin.tg_user_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to send test escalation notification to admin {admin.id} via Telegram: {e}",
                            exc_info=True
                        )
                
                # Try MAX if available
                if admin.max_chat_id and max_bot_instance:
                    try:
                        await max_bot_instance.send_message(
                            chat_id=admin.max_chat_id,
                            text=notification_text
                        )
                        notifications_sent += 1
                        logger.info(
                            f"Test escalation notification sent to admin via MAX: "
                            f"admin_id={admin.id}, max_chat_id={admin.max_chat_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to send test escalation notification to admin {admin.id} via MAX: {e}",
                            exc_info=True
                        )
                
                # Log if admin has no messenger IDs
                if not admin.tg_user_id and not admin.max_chat_id:
                    logger.warning(
                        f"Admin {admin.id} has no messenger IDs (tg_user_id and max_chat_id are both None)"
                    )
        else:
            logger.warning("No active administrators found for escalation notification")
        
        # Send to escalation channels based on ticket type
        if ticket.ticket_type in [TicketType.INVOICE, TicketType.RENEWAL]:
            # For invoice/renewal tickets, send to manager escalation channels
            manager_channels = await get_escalation_channels(session, "escalation_manager_channel")
            for manager_channel in manager_channels:
                is_max = is_max_chat_id(manager_channel)
                if is_max and max_bot_instance:
                    try:
                        await max_bot_instance.send_message(
                            chat_id=int(manager_channel),
                            text=notification_text
                        )
                        channels_notified.append(f"escalation_manager_channel:{manager_channel} (MAX)")
                        logger.info(f"Test escalation notification sent to MAX manager channel: {manager_channel}")
                    except Exception as e:
                        logger.error(f"Failed to send test escalation to MAX manager channel {manager_channel}: {e}", exc_info=True)
                elif not is_max and tg_bot:
                    try:
                        await tg_bot.send_message(chat_id=manager_channel, text=notification_text, parse_mode="HTML")
                        channels_notified.append(f"escalation_manager_channel:{manager_channel} (Telegram)")
                        logger.info(f"Test escalation notification sent to Telegram manager channel: {manager_channel}")
                    except Exception as e:
                        logger.error(f"Failed to send test escalation to Telegram manager channel {manager_channel}: {e}", exc_info=True)
                else:
                    logger.warning(f"Cannot send to manager channel {manager_channel}: bot not available")
        elif ticket.ticket_type in (TicketType.TECHNICAL_SUPPORT, TicketType.CONSULTATION):
            # For technical support/consultation tickets, send to duty escalation channels
            duty_channels = await get_escalation_channels(session, "escalation_duty_channel")
            for duty_channel in duty_channels:
                is_max = is_max_chat_id(duty_channel)
                if is_max and max_bot_instance:
                    try:
                        await max_bot_instance.send_message(chat_id=int(duty_channel), text=notification_text)
                        channels_notified.append(f"escalation_duty_channel:{duty_channel} (MAX)")
                        logger.info(f"Test escalation notification sent to MAX duty channel: {duty_channel}")
                    except Exception as e:
                        logger.error(f"Failed to send test escalation to MAX duty channel {duty_channel}: {e}", exc_info=True)
                elif not is_max and tg_bot:
                    try:
                        await tg_bot.send_message(chat_id=duty_channel, text=notification_text, parse_mode="HTML")
                        channels_notified.append(f"escalation_duty_channel:{duty_channel} (Telegram)")
                        logger.info(f"Test escalation notification sent to Telegram duty channel: {duty_channel}")
                    except Exception as e:
                        logger.error(f"Failed to send test escalation to Telegram duty channel {duty_channel}: {e}", exc_info=True)
                else:
                    logger.warning(f"Cannot send to duty channel {duty_channel}: bot not available")
        
        # Close bot sessions
        if tg_bot:
            await tg_bot.session.close()
        if max_bot_instance:
            await max_bot_instance.session.close()
        
        logger.info(
            f"Test escalation notifications sent: {notifications_sent} admins, "
            f"{len(channels_notified)} channels ({', '.join(channels_notified)})"
        )
        
        # Step 5: Return success response
        message_parts = [f"Notifications sent to {notifications_sent} administrator(s)"]
        if channels_notified:
            message_parts.append(f"{len(channels_notified)} escalation channel(s)")
        
        return EscalationTestResponse(
            success=True,
            message=f"Escalation test completed successfully. {', '.join(message_parts)}.",
            ticket_id=ticket.id,
            escalation_triggered=True,
            escalation_id=escalation.id,
            current_status=ticket.ticket_status.value,
            assigned_staff_id=ticket.assigned_staff_id,
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        logger.error(
            f"Error testing escalation for ticket_id={request.ticket_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )



@router.post("/escalation/test-backup-reassignment", response_model=BackupManagerTestResponse)
async def test_backup_manager_reassignment(
    request: BackupManagerTestRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> BackupManagerTestResponse:
    """
    Test backup manager reassignment functionality for a specific ticket.
    
    This endpoint simulates the backup manager escalation flow by reassigning
    a ticket to one of the backup managers configured for the currently assigned staff.
    This allows testing the backup manager logic without waiting for timeout.
    
    Use cases:
    - Test backup manager configuration
    - Verify backup manager notifications
    - Test reassignment flow
    - Validate backup manager UI
    
    Example request:
    POST /api/escalation/test-backup-reassignment
    Headers:
        X-API-Key: your-api-key-here
        Content-Type: application/json
    Body:
        {
            "ticket_id": 123,
            "target_backup_slot": 1
        }
    
    Args:
        request: Backup manager test request with ticket_id and target slot
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        Backup manager test result with reassignment details
        
    Raises:
        HTTPException: 404 if ticket not found
        HTTPException: 400 if ticket has no assigned staff or no backup managers
        HTTPException: 500 if reassignment fails
        
    Requirements:
        - 8: Test backup manager reassignment (резервные менеджеры)
    """
    logger.info(
        f"Backup manager test API request received: ticket_id={request.ticket_id}, "
        f"target_slot={request.target_backup_slot}"
    )
    
    try:
        # Step 1: Query ticket with relationships
        stmt = (
            select(Ticket)
            .where(Ticket.id == request.ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.assigned_staff).selectinload(Staff_Member.backup_manager_1),
                selectinload(Ticket.assigned_staff).selectinload(Staff_Member.backup_manager_2),
                selectinload(Ticket.organization)
            )
        )
        
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        # Check if ticket exists
        if not ticket:
            logger.error(f"Ticket not found: ticket_id={request.ticket_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket with ID {request.ticket_id} not found",
            )
        
        # Check if ticket has assigned staff
        if not ticket.assigned_staff:
            logger.warning(
                f"Ticket has no assigned staff: ticket_id={request.ticket_id}"
            )
            return BackupManagerTestResponse(
                success=False,
                message="Ticket has no assigned staff. Cannot test backup manager reassignment.",
                ticket_id=ticket.id,
                original_staff_id=None,
                original_staff_name=None,
                backup_1_id=None,
                backup_1_name=None,
                backup_2_id=None,
                backup_2_name=None,
                reassigned_to_id=None,
                reassigned_to_name=None,
            )
        
        original_staff = ticket.assigned_staff
        backup_1 = original_staff.backup_manager_1
        backup_2 = original_staff.backup_manager_2
        
        # Check if backup managers are configured
        if not backup_1 and not backup_2:
            logger.warning(
                f"No backup managers configured for staff: staff_id={original_staff.id}"
            )
            return BackupManagerTestResponse(
                success=False,
                message=f"No backup managers configured for {original_staff.full_name}. "
                        f"Configure backup managers first.",
                ticket_id=ticket.id,
                original_staff_id=original_staff.id,
                original_staff_name=original_staff.full_name,
                backup_1_id=None,
                backup_1_name=None,
                backup_2_id=None,
                backup_2_name=None,
                reassigned_to_id=None,
                reassigned_to_name=None,
            )
        
        # Determine which backup manager to use
        target_backup = None
        target_slot_name = None
        
        if request.target_backup_slot == 1:
            if backup_1:
                target_backup = backup_1
                target_slot_name = "Backup Manager 1"
            else:
                return BackupManagerTestResponse(
                    success=False,
                    message="Backup manager 1 is not configured.",
                    ticket_id=ticket.id,
                    original_staff_id=original_staff.id,
                    original_staff_name=original_staff.full_name,
                    backup_1_id=None,
                    backup_1_name=None,
                    backup_2_id=backup_2.id if backup_2 else None,
                    backup_2_name=backup_2.full_name if backup_2 else None,
                    reassigned_to_id=None,
                    reassigned_to_name=None,
                )
        elif request.target_backup_slot == 2:
            if backup_2:
                target_backup = backup_2
                target_slot_name = "Backup Manager 2"
            else:
                return BackupManagerTestResponse(
                    success=False,
                    message="Backup manager 2 is not configured.",
                    ticket_id=ticket.id,
                    original_staff_id=original_staff.id,
                    original_staff_name=original_staff.full_name,
                    backup_1_id=backup_1.id if backup_1 else None,
                    backup_1_name=backup_1.full_name if backup_1 else None,
                    backup_2_id=None,
                    backup_2_name=None,
                    reassigned_to_id=None,
                    reassigned_to_name=None,
                )
        else:
            # No specific slot requested, use first available
            if backup_1:
                target_backup = backup_1
                target_slot_name = "Backup Manager 1"
            elif backup_2:
                target_backup = backup_2
                target_slot_name = "Backup Manager 2"
        
        if not target_backup:
            return BackupManagerTestResponse(
                success=False,
                message="No backup managers available for reassignment.",
                ticket_id=ticket.id,
                original_staff_id=original_staff.id,
                original_staff_name=original_staff.full_name,
                backup_1_id=backup_1.id if backup_1 else None,
                backup_1_name=backup_1.full_name if backup_1 else None,
                backup_2_id=backup_2.id if backup_2 else None,
                backup_2_name=backup_2.full_name if backup_2 else None,
                reassigned_to_id=None,
                reassigned_to_name=None,
            )
        
        # Step 2: Reassign ticket to backup manager
        old_staff_id = ticket.assigned_staff_id
        ticket.assigned_staff_id = target_backup.id
        ticket.ticket_status = TicketStatus.IN_PROGRESS
        
        await session.commit()
        
        # Step 3: Log the action
        from services.logging_service import log_ticket_action
        from database.models import ActionType
        
        await log_ticket_action(
            session=session,
            action_type=ActionType.TICKET_ASSIGNED,
            ticket_id=ticket.id,
            staff_id=target_backup.id,
            action_details={
                "from_staff_id": old_staff_id,
                "to_staff_id": target_backup.id,
                "backup_manager_test": True,
                "backup_slot": request.target_backup_slot or (1 if target_backup == backup_1 else 2),
                "reason": f"Test backup manager reassignment via API ({target_slot_name})"
            }
        )
        
        # Step 4: Send notification to backup manager
        tg_bot = None
        max_bot_instance = None
        
        if TG_BOT_TOKEN:
            tg_bot = Bot(
                token=TG_BOT_TOKEN,
                default=DefaultBotProperties(parse_mode="HTML")
            )
        
        if MAX_BOT_TOKEN:
            try:
                from maxapi import Bot as MAXBot
                from maxapi.types import ParseMode
                max_bot_instance = MAXBot(
                    token=MAX_BOT_TOKEN,
                    parse_mode=ParseMode.HTML
                )
            except ImportError as e:
                logger.warning(f"maxapi not available: {e}, MAX notifications will be skipped")
            except Exception as e:
                logger.error(f"Failed to initialize MAX bot: {e}", exc_info=True)
        
        ticket_type_display = {
            "invoice": "Счет",
            "technical_support": "Техподдержка",
            "renewal": "Продление"
        }
        ticket_type_text = ticket_type_display.get(
            ticket.ticket_type.value,
            ticket.ticket_type.value
        )
        
        notification_text = (
            f"🔄 <b>ТЕСТ: Заявка переназначена на резервного менеджера</b>\n\n"
            f"<b>Заявка:</b> #{ticket.id}\n"
            f"<b>Тип:</b> {ticket_type_text}\n"
            f"<b>Клиент:</b> {ticket.user.full_name}\n"
        )
        
        if ticket.organization:
            notification_text += f"<b>ИНН:</b> {ticket.organization.inn}\n"
        
        notification_text += (
            f"\n<b>Исходный менеджер:</b> {original_staff.full_name}\n"
            f"<b>Резервный менеджер:</b> {target_backup.full_name} ({target_slot_name})\n"
            f"\n<i>Это тестовое переназначение, созданное через API.</i>"
        )
        
        notification_sent = False
        
        # Try Telegram first
        if target_backup.tg_user_id and tg_bot:
            try:
                await tg_bot.send_message(
                    chat_id=target_backup.tg_user_id,
                    text=notification_text,
                    parse_mode="HTML"
                )
                notification_sent = True
                logger.info(
                    f"Test backup reassignment notification sent via Telegram: "
                    f"staff_id={target_backup.id}, tg_user_id={target_backup.tg_user_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to send test backup reassignment notification to staff {target_backup.id} via Telegram: {e}",
                    exc_info=True
                )
        
        # Try MAX if Telegram failed or not available
        if target_backup.max_chat_id and max_bot_instance:
            try:
                await max_bot_instance.send_message(
                    chat_id=target_backup.max_chat_id,
                    text=notification_text
                )
                notification_sent = True
                logger.info(
                    f"Test backup reassignment notification sent via MAX: "
                    f"staff_id={target_backup.id}, max_chat_id={target_backup.max_chat_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to send test backup reassignment notification to staff {target_backup.id} via MAX: {e}",
                    exc_info=True
                )
        
        if not notification_sent:
            logger.warning(
                f"Could not send notification to backup manager {target_backup.id}: "
                f"no valid messenger IDs found"
            )
        
        # Close bot sessions
        if tg_bot:
            await tg_bot.session.close()
        if max_bot_instance:
            await max_bot_instance.session.close()
        
        logger.info(
            f"Test backup manager reassignment completed: ticket_id={ticket.id}, "
            f"from_staff={old_staff_id}, to_staff={target_backup.id}"
        )
        
        # Step 5: Return success response
        return BackupManagerTestResponse(
            success=True,
            message=f"Ticket successfully reassigned to {target_slot_name}: {target_backup.full_name}",
            ticket_id=ticket.id,
            original_staff_id=original_staff.id,
            original_staff_name=original_staff.full_name,
            backup_1_id=backup_1.id if backup_1 else None,
            backup_1_name=backup_1.full_name if backup_1 else None,
            backup_2_id=backup_2.id if backup_2 else None,
            backup_2_name=backup_2.full_name if backup_2 else None,
            reassigned_to_id=target_backup.id,
            reassigned_to_name=target_backup.full_name,
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        logger.error(
            f"Error testing backup manager reassignment for ticket_id={request.ticket_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )
