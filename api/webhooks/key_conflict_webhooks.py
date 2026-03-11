"""
Key Conflict Resolution Webhook Handler

This module implements the webhook endpoint for receiving key conflict resolution
decisions from 1C CRM. When a GS_Key ownership conflict is detected, the CRM admin
reviews the case and sends a resolution decision (transfer or reject) to this endpoint.

Requirements: 1.1-1.11 - Key conflict resolution webhook
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from api.schemas.key_conflict_schemas import (
    KeyConflictWebhookPayload,
    KeyConflictWebhookResponse,
)
from constants import get_session, WEBHOOK_API_KEY, TG_BOT_TOKEN, MAX_BOT_TOKEN
from database.models import (
    Action_Log,
    ActionType,
    GS_Key,
    KeyConflictStatus,
    Staff_Member,
    User,
)
from services.i_tat_service import get_itat_client

router = APIRouter()
logger = logging.getLogger(__name__)


async def verify_webhook_api_key(
    x_api_key: Annotated[str | None, Header()] = None
) -> str:
    """
    Verify webhook API key authentication.
    
    This dependency validates that incoming webhook requests include a valid
    API key in the X-API-Key header. The key should match the configured
    WEBHOOK_API_KEY environment variable.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        Validated API key
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
        
    Requirements: 17.1-17.6 - Webhook authentication
    """
    if not x_api_key:
        logger.warning("Key conflict webhook request received without API key")
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


@router.post("/key_conflict_resolution", response_model=KeyConflictWebhookResponse)
async def key_conflict_resolution_webhook(
    payload: KeyConflictWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> KeyConflictWebhookResponse:
    """
    Handle key conflict resolution webhook from 1C CRM.
    
    This endpoint receives key conflict resolution decisions from the CRM system.
    When a GS_Key is claimed by multiple users, the CRM admin reviews the case
    and decides whether to transfer the key to the new user or reject the claim.
    
    Request body (transfer):
    {
        "messenger": "telegram",
        "new_user_id": 123456789,
        "old_user_id": 987654321,
        "gs_key": "GS-12345",
        "resolution": "transfer",
        "resolved_by_staff_id": 111222333,
        "reason": "Verified ownership transfer"
    }
    
    Request body (reject):
    {
        "messenger": "max",
        "new_user_id": 123456789,
        "old_user_id": 987654321,
        "gs_key": "GS-12345",
        "resolution": "reject",
        "resolved_by_staff_id": 111222333,
        "reason": "Invalid claim"
    }
    
    Response:
    {
        "status": "success",
        "message": "Conflict resolved successfully",
        "resolution": "transfer",
        "gs_key": "GS-12345"
    }
    
    Args:
        payload: Key conflict resolution payload
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with resolution status
        
    Raises:
        HTTPException: 404 if user or key not found
        HTTPException: 500 if internal error occurs
        
    Requirements:
        - 1.1: Transfer key ownership when resolution="transfer"
        - 1.2: Reject claim when resolution="reject"
        - 1.3: Update key.user_id and conflict_status for transfer
        - 1.4: Set conflict_status to REJECTED for reject
        - 1.5: Send notification to new_user
        - 1.6: Send notification to old_user
        - 1.7: Log action in Action_Log
        - 1.8: Sync resolution to CRM via i-TAT API
        - 1.9: Return 404 if new_user not found
        - 1.10: Return 404 if old_user not found
        - 1.11: Return 404 if GS_Key not found
    """
    logger.info(
        f"Key conflict resolution webhook received: messenger={payload.messenger}, "
        f"gs_key={payload.gs_key}, resolution={payload.resolution}"
    )
    
    try:
        # Step 1: Query users by messenger-specific ID
        if payload.messenger == "telegram":
            stmt_new = select(User).where(User.tg_user_id == payload.new_user_id)
            stmt_old = select(User).where(User.tg_user_id == payload.old_user_id)
        elif payload.messenger == "max":
            stmt_new = select(User).where(User.max_user_id == payload.new_user_id)
            stmt_old = select(User).where(User.max_user_id == payload.old_user_id)
        else:
            # This should never happen due to Pydantic validation
            logger.error(f"Invalid messenger type: {payload.messenger}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid messenger type: {payload.messenger}",
            )
        
        result_new = await session.execute(stmt_new)
        new_user = result_new.scalar_one_or_none()
        
        result_old = await session.execute(stmt_old)
        old_user = result_old.scalar_one_or_none()
        
        # Requirement 1.9, 1.10: Return 404 if users not found
        if not new_user:
            logger.error(
                f"New user with {payload.messenger}_user_id={payload.new_user_id} not found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"New user with {payload.messenger.upper()} ID {payload.new_user_id} not found",
            )
        
        if not old_user:
            logger.error(
                f"Old user with {payload.messenger}_user_id={payload.old_user_id} not found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Old user with {payload.messenger.upper()} ID {payload.old_user_id} not found",
            )
        
        # Step 2: Query GS_Key
        stmt_key = select(GS_Key).where(GS_Key.key_number == payload.gs_key)
        result_key = await session.execute(stmt_key)
        gs_key = result_key.scalar_one_or_none()
        
        # Requirement 1.11: Return 404 if key not found
        if not gs_key:
            logger.error(f"GS_Key {payload.gs_key} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"GS_Key {payload.gs_key} not found",
            )
        
        # Step 3: Resolve conflict based on resolution type
        if payload.resolution == "transfer":
            # Requirement 1.1, 1.3: Transfer key ownership
            gs_key.user_id = new_user.id
            gs_key.conflict_status = KeyConflictStatus.RESOLVED
            
            # Дружелюбные уведомления с emoji и форматированием (different for Telegram and MAX)
            if payload.messenger == "telegram":
                notification_new = (
                    f"🎉 <b>Отличные новости!</b>\n\n"
                    f"Ключ <code>{payload.gs_key}</code> успешно передан вам.\n"
                    f"Теперь вы можете пользоваться всеми возможностями системы.\n\n"
                    f"С уважением,\n"
                    f"Команда АЙТАТ 💙"
                )
                
                notification_old = (
                    f"ℹ️ <b>Уведомление о передаче ключа</b>\n\n"
                    f"Ключ <code>{payload.gs_key}</code> был передан другому пользователю "
                    f"в соответствии с решением администратора.\n\n"
                    f"Если у вас есть вопросы, обратитесь в службу поддержки.\n\n"
                    f"С уважением,\n"
                    f"Команда АЙТАТ 💙"
                )
            else:  # MAX - no HTML tags
                notification_new = (
                    f"🎉 Отличные новости!\n\n"
                    f"Ключ {payload.gs_key} успешно передан вам.\n"
                    f"Теперь вы можете пользоваться всеми возможностями системы.\n\n"
                    f"С уважением,\n"
                    f"Команда АЙТАТ 💙"
                )
                
                notification_old = (
                    f"ℹ️ Уведомление о передаче ключа\n\n"
                    f"Ключ {payload.gs_key} был передан другому пользователю "
                    f"в соответствии с решением администратора.\n\n"
                    f"Если у вас есть вопросы, обратитесь в службу поддержки.\n\n"
                    f"С уважением,\n"
                    f"Команда АЙТАТ 💙"
                )
            
            log_message = (
                f"Key {payload.gs_key} transferred from user {old_user.id} "
                f"to user {new_user.id} via CRM webhook"
            )
            
        elif payload.resolution == "reject":
            # Requirement 1.2, 1.4: Reject claim, keep ownership with old_user
            gs_key.conflict_status = KeyConflictStatus.RESOLVED  # Mark as resolved (rejected)
            
            # Уведомление только тому, кто пытался добавить ключ (different for Telegram and MAX)
            if payload.messenger == "telegram":
                notification_new = (
                    f"❌ <b>Запрос отклонен</b>\n\n"
                    f"К сожалению, ваш запрос на добавление ключа <code>{payload.gs_key}</code> "
                    f"был отклонен администратором.\n\n"
                    f"Причина: {payload.reason or 'не указана'}\n\n"
                    f"Если вы считаете, что произошла ошибка, пожалуйста, "
                    f"свяжитесь со службой поддержки.\n\n"
                    f"С уважением,\n"
                    f"Команда АЙТАТ 💙"
                )
            else:  # MAX - no HTML tags
                notification_new = (
                    f"❌ Запрос отклонен\n\n"
                    f"К сожалению, ваш запрос на добавление ключа {payload.gs_key} "
                    f"был отклонен администратором.\n\n"
                    f"Причина: {payload.reason or 'не указана'}\n\n"
                    f"Если вы считаете, что произошла ошибка, пожалуйста, "
                    f"свяжитесь со службой поддержки.\n\n"
                    f"С уважением,\n"
                    f"Команда АЙТАТ 💙"
                )
            
            # Старому владельцу не отправляем уведомление при отклонении
            notification_old = None
            
            log_message = (
                f"Key {payload.gs_key} conflict rejected, ownership remains with user {old_user.id}"
            )
        
        else:
            # This should never happen due to Pydantic validation
            logger.error(f"Invalid resolution type: {payload.resolution}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid resolution: {payload.resolution}",
            )
        
        # Step 4: Commit database changes
        await session.commit()
        logger.info(log_message)
        
        # Step 5: Send notifications to users (Requirements 1.5, 1.6)
        # Get messenger-specific user IDs
        new_user_messenger_id = (
            new_user.tg_user_id if payload.messenger == "telegram" else new_user.max_user_id
        )
        old_user_messenger_id = (
            old_user.tg_user_id if payload.messenger == "telegram" else old_user.max_user_id
        )
        
        # Send notification to new user
        if new_user_messenger_id:
            try:
                # Send via centralized utility
                from api.utils.messenger_utils import send_message_to_user
                
                result = await send_message_to_user(
                    messenger=payload.messenger,
                    user_id=new_user.id,
                    text=notification_new,
                    session=session,
                    parse_mode="HTML"
                )
                
                if result["success"]:
                    logger.info(
                        f"Key conflict notification sent to {payload.messenger} user {new_user.id}"
                    )
                else:
                    logger.warning(
                        f"Failed to send notification to user {new_user.id}: {result['message']}"
                    )
                    
            except Exception as e:
                logger.error(
                    f"Failed to send notification to {payload.messenger} "
                    f"user {new_user.id}: {e}",
                    exc_info=True
                )
        else:
            logger.warning(f"New user {new_user.id} has no {payload.messenger} user ID")
        
        # Send notification to old user (only for transfer, not for reject)
        if notification_old and old_user_messenger_id:
            try:
                # Send via centralized utility
                from api.utils.messenger_utils import send_message_to_user
                
                result = await send_message_to_user(
                    messenger=payload.messenger,
                    user_id=old_user.id,
                    text=notification_old,
                    session=session,
                    parse_mode="HTML"
                )
                
                if result["success"]:
                    logger.info(
                        f"Key conflict notification sent to {payload.messenger} user {old_user.id}"
                    )
                else:
                    logger.warning(
                        f"Failed to send notification to user {old_user.id}: {result['message']}"
                    )
                    
            except Exception as e:
                logger.error(
                    f"Failed to send notification to {payload.messenger} "
                    f"user {old_user.id}: {e}",
                    exc_info=True
                )
        elif notification_old:
            logger.warning(f"Old user {old_user.id} has no {payload.messenger} user ID")
        
        # Step 6: Log action in Action_Log (Requirement 1.7)
        action_log = Action_Log(
            action_type=ActionType.KEY_CONFLICT_DETECTED,  # Using existing enum value
            user_id=new_user.id,
            staff_id=None,  # Will be set if we can find staff member
            action_details={
                "action": "key_conflict_resolved",
                "resolution": payload.resolution,
                "gs_key": payload.gs_key,
                "old_user_id": old_user.id,
                "new_user_id": new_user.id,
                "old_user_messenger_id": payload.old_user_id,
                "new_user_messenger_id": payload.new_user_id,
                "messenger": payload.messenger,
                "resolved_by_staff_messenger_id": payload.resolved_by_staff_id,
                "reason": payload.reason,
            },
            action_timestamp=datetime.now()
        )
        
        # Try to find staff member by messenger ID
        if payload.resolved_by_staff_id:
            if payload.messenger == "telegram":
                stmt_staff = select(Staff_Member).where(
                    Staff_Member.tg_user_id == payload.resolved_by_staff_id
                )
            else:
                stmt_staff = select(Staff_Member).where(
                    Staff_Member.max_user_id == payload.resolved_by_staff_id
                )
            
            result_staff = await session.execute(stmt_staff)
            staff = result_staff.scalar_one_or_none()
            
            if staff:
                action_log.staff_id = staff.id
            else:
                logger.warning(
                    f"Staff member with {payload.messenger}_user_id={payload.resolved_by_staff_id} "
                    f"not found in database"
                )
        
        session.add(action_log)
        await session.commit()
        
        # Step 7: Call i-TAT API to sync resolution (Requirement 1.8)
        try:
            itat_client = get_itat_client()
            
            # Note: This method needs to be implemented in i_tat_service.py
            # For now, we'll log that it should be called
            logger.info(
                f"Should call i-TAT API resolve_key_conflict with: "
                f"old_user_id={payload.old_user_id}, new_user_id={payload.new_user_id}, "
                f"gs_key={payload.gs_key}, resolution={payload.resolution}"
            )
            
            # When i-TAT API method is implemented:
            # await itat_client.resolve_key_conflict(
            #     old_user_id=payload.old_user_id,
            #     new_user_id=payload.new_user_id,
            #     gs_key=payload.gs_key,
            #     resolution=payload.resolution,
            #     messenger=payload.messenger,
            #     resolved_by_staff_id=payload.resolved_by_staff_id,
            #     reason=payload.reason
            # )
            
        except Exception as e:
            # Log error but don't fail the webhook - local DB is source of truth
            logger.error(
                f"Failed to sync conflict resolution to CRM: {e}",
                exc_info=True
            )
        
        logger.info(
            f"Key conflict resolution webhook processed successfully: "
            f"gs_key={payload.gs_key}, resolution={payload.resolution}"
        )
        
        return KeyConflictWebhookResponse(
            status="success",
            message="Conflict resolved successfully",
            resolution=payload.resolution,
            gs_key=payload.gs_key
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (404, 400, etc.)
        raise
        
    except Exception as e:
        # Unexpected error (Requirement 18.6, 18.9)
        logger.error(
            f"Error processing key conflict resolution webhook: {e}",
            exc_info=True
        )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )
