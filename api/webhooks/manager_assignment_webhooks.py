"""
Manager Assignment System - CRM Webhook Handler

This module implements the webhook endpoint for assigning or updating managers
for users from 1C CRM. This webhook is called when:
- Manager is assigned to a new client
- Manager is changed for an existing client
- Manager assignment needs to be updated in the bot

Requirements: CRM integration for manager assignment synchronization
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from api.schemas.manager_assignment_schemas import (
    ManagerAssignmentWebhookPayload,
    ManagerAssignmentWebhookResponse,
)
from constants import get_session, WEBHOOK_API_KEY, TG_BOT_TOKEN, MAX_BOT_TOKEN
from database.models import (
    Action_Log,
    ActionType,
    Staff_Member,
    User,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def verify_webhook_api_key(
    x_api_key: Annotated[str | None, Header()] = None
) -> str:
    """
    Verify webhook API key authentication.
    
    This dependency validates that incoming webhook requests include a valid
    API key in the X-API-Key header.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        Validated API key
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    if not x_api_key:
        logger.warning("Manager assignment webhook request received without API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    if not WEBHOOK_API_KEY:
        logger.error("WEBHOOK_API_KEY not configured in environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook API key not configured on server",
        )
    
    if x_api_key != WEBHOOK_API_KEY:
        logger.warning(f"Invalid API key attempt: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return x_api_key


@router.post("/manager_assignment", response_model=ManagerAssignmentWebhookResponse)
async def manager_assignment_webhook(
    payload: ManagerAssignmentWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> ManagerAssignmentWebhookResponse:
    """
    Handle manager assignment/update webhook from 1C CRM.
    
    This endpoint receives manager assignment updates from the CRM system when:
    - Manager is assigned to a new client
    - Manager is changed for an existing client
    
    Request body example:
    {
        "messenger": "max",
        "user_id": 123456789,
        "phone": "+79991234567",
        "manager_id": 987654321,
        "manager_name": "Иван Иванов",
        "send_notification": true
    }
    
    Response:
    {
        "status": "success",
        "message": "Manager assigned successfully",
        "messenger": "max",
        "user_id": 123456789,
        "manager_id": 5,
        "manager_name": "Иван Иванов",
        "notification_sent": true
    }
    
    Args:
        payload: Manager assignment webhook payload
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with status and assignment details
        
    Raises:
        HTTPException: 400 if payload validation fails
        HTTPException: 404 if user or manager not found
        HTTPException: 500 if internal error occurs
    """
    logger.info(
        f"Manager assignment webhook received: messenger={payload.messenger}, "
        f"user_id={payload.user_id}, manager_id={payload.manager_id}"
    )
    
    try:
        # Query user by messenger-specific ID
        if payload.messenger == "telegram":
            stmt_user = select(User).where(User.tg_user_id == payload.user_id)
        elif payload.messenger == "max":
            stmt_user = select(User).where(User.max_user_id == payload.user_id)
        else:
            logger.error(f"Invalid messenger type: {payload.messenger}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid messenger type: {payload.messenger}",
            )
        
        result_user = await session.execute(stmt_user)
        user = result_user.scalar_one_or_none()
        
        if not user:
            logger.error(
                f"User with {payload.messenger}_user_id={payload.user_id} not found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with {payload.messenger.upper()} ID {payload.user_id} not found",
            )
        
        # Verify phone number matches (log warning but continue)
        if user.phone_number != payload.phone:
            logger.warning(
                f"Phone number mismatch for {payload.messenger}_user_id={payload.user_id}: "
                f"expected {user.phone_number}, got {payload.phone}"
            )
        
        # Find staff member by messenger-specific ID
        if payload.messenger == "telegram":
            stmt_staff = select(Staff_Member).where(Staff_Member.tg_user_id == payload.manager_id)
        else:  # max
            stmt_staff = select(Staff_Member).where(Staff_Member.max_user_id == payload.manager_id)
        
        result_staff = await session.execute(stmt_staff)
        manager = result_staff.scalar_one_or_none()
        
        if not manager:
            logger.error(
                f"Manager with {payload.messenger}_user_id={payload.manager_id} not found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Manager with {payload.messenger.upper()} ID {payload.manager_id} not found",
            )
        
        # Store previous manager for logging
        previous_manager_id = user.default_manager_id
        
        # Check if manager has actually changed (deduplication for 1C CRM multiple triggers)
        from api.webhooks.webhook_utils import has_field_changed
        
        manager_changed = has_field_changed(previous_manager_id, manager.id, "default_manager_id")
        
        # If manager hasn't changed, skip update and notification
        if not manager_changed:
            logger.info(
                f"Manager unchanged for user {user.id}: manager_id={manager.id}. "
                f"Skipping update (likely duplicate webhook from 1C CRM)."
            )
            return ManagerAssignmentWebhookResponse(
                status="success",
                message="Manager assignment already up to date (no changes detected)",
                messenger=payload.messenger,
                user_id=payload.user_id,
                manager_id=manager.id,
                manager_name=manager.full_name,
                notification_sent=False
            )
        
        # Assign manager to user
        user.default_manager_id = manager.id
        await session.commit()
        
        logger.info(
            f"Assigned manager {manager.full_name} (id={manager.id}) to user {user.id}. "
            f"Previous manager: {previous_manager_id}"
        )
        
        # Send notification to user if requested
        notification_sent = False
        if payload.send_notification:
            messenger_user_id = user.tg_user_id if payload.messenger == "telegram" else user.max_user_id
            
            if messenger_user_id:
                # Build informative notification message (different format for Telegram and MAX)
                if payload.messenger == "telegram":
                    if previous_manager_id is None:
                        # New manager assignment
                        notification_text = (
                            f"👤 <b>Вам назначен персональный менеджер</b>\n\n"
                            f"<b>ФИО:</b> {manager.full_name}\n"
                        )
                    else:
                        # Manager reassignment
                        notification_text = (
                            f"🔄 <b>Ваш менеджер изменён</b>\n\n"
                            f"<b>Новый менеджер:</b>\n"
                            f"<b>ФИО:</b> {manager.full_name}\n"
                        )
                    
                    # Add position if available
                    if manager.position:
                        notification_text += f"<b>Должность:</b> {manager.position}\n"
                else:  # MAX - no HTML tags
                    if previous_manager_id is None:
                        # New manager assignment
                        notification_text = (
                            f"👤 Вам назначен персональный менеджер\n\n"
                            f"ФИО: {manager.full_name}\n"
                        )
                    else:
                        # Manager reassignment
                        notification_text = (
                            f"🔄 Ваш менеджер изменён\n\n"
                            f"Новый менеджер:\n"
                            f"ФИО: {manager.full_name}\n"
                        )
                    
                    # Add position if available
                    if manager.position:
                        notification_text += f"Должность: {manager.position}\n"
                
                # # Add contact info if available
                # if manager.phone_number:
                #     notification_text += f"<b>Телефон:</b> {manager.phone_number}\n"
                
                try:
                    # Send via centralized utility
                    from api.utils.messenger_utils import send_message_to_user
                    
                    result = await send_message_to_user(
                        messenger=payload.messenger,
                        user_id=user.id,
                        text=notification_text,
                        session=session,
                        parse_mode="HTML"
                    )
                    
                    if result["success"]:
                        notification_sent = True
                        logger.info(
                            f"Manager assignment notification sent to {payload.messenger} user {user.id}"
                        )
                    else:
                        logger.warning(
                            f"Failed to send manager assignment notification to user {user.id}: {result['message']}"
                        )
                        
                except Exception as e:
                    logger.error(
                        f"Failed to send manager assignment notification to {payload.messenger} "
                        f"user {user.id}: {e}",
                        exc_info=True
                    )
            else:
                logger.warning(
                    f"User {user.id} has no {payload.messenger} user ID, cannot send notification"
                )
        
        # Log action in Action_Log
        action_log = Action_Log(
            action_type=ActionType.SETTING_CHANGED,  # Could add MANAGER_ASSIGNED enum value
            user_id=user.id,
            staff_id=manager.id,
            action_details={
                "action": "manager_assigned_via_crm",
                "messenger": payload.messenger,
                "messenger_user_id": payload.user_id,
                "manager_messenger_id": payload.manager_id,
                "manager_full_name": manager.full_name,
                "manager_position": manager.position,
                "previous_manager_id": previous_manager_id,
                "notification_requested": payload.send_notification,
                "notification_sent": notification_sent,
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Manager assignment webhook processed successfully for {payload.messenger}_user_id={payload.user_id}"
        )
        
        return ManagerAssignmentWebhookResponse(
            status="success",
            message="Manager assigned successfully",
            messenger=payload.messenger,
            user_id=payload.user_id,
            manager_id=manager.id,
            manager_name=manager.full_name,
            notification_sent=notification_sent
        )
        
    except HTTPException as http_exc:
        # Notify admins about HTTP errors
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = f"HTTP {http_exc.status_code}"
            error_details = http_exc.detail
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}, staff_id={payload.staff_id}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="manager_assignment",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        # Re-raise HTTP exceptions (404, 400, etc.)
        raise
        
    except Exception as e:
        # Unexpected error - notify admins
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = type(e).__name__
            error_details = str(e)
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}, staff_id={payload.staff_id}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="manager_assignment",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        # Unexpected error
        logger.error(
            f"Error processing manager assignment webhook for {payload.messenger}_user_id={payload.user_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )
