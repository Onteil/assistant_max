"""
Registration Approval System - CRM Webhook Handler

This module implements the webhook endpoint for receiving registration approval/rejection
events from 1C CRM. When REGISTRATION_APPROVE_METHOD is set to "crm", the CRM system
sends approval decisions to this endpoint instead of admins handling it in the bot.

Requirements: 4.19 - CRM webhook integration for registration approval
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.registration_schemas import (
    RegistrationWebhookPayload,
    RegistrationWebhookResponse,
)
from constants import get_session, WEBHOOK_API_KEY
from database.models import Action_Log, ActionType, RegistrationStatus, Staff_Member, SubscriptionStatus, User

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
        
    Requirements: Security - Webhook authentication
    """
    if not x_api_key:
        logger.warning("Registration webhook request received without API key")
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


@router.post("/registration_status", response_model=RegistrationWebhookResponse)
async def registration_status_webhook(
    payload: RegistrationWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> RegistrationWebhookResponse:
    """
    Handle registration approval/rejection webhook from 1C CRM.
    
    This endpoint receives registration status updates from the CRM system
    when REGISTRATION_APPROVE_METHOD is set to "crm". It updates the user's
    registration status in the database and sends a notification to the user.
    
    Request body (approved - MAX):
    {
        "messenger": "max",
        "user_id": 123456789,
        "phone": "+79991234567",
        "status": "approved",
        "manager_name": "Иван Иванов",
        "manager_id": 987654321,
        "subscription_status": "active",
        "support_expires_at": "2026-12-31T23:59:59"
    }
    
    Request body (approved - Telegram):
    {
        "messenger": "telegram",
        "user_id": 123456789,
        "phone": "+79991234567",
        "status": "approved",
        "manager_name": "Иван Иванов",
        "manager_id": 987654321,
        "subscription_status": "active",
        "support_expires_at": "2026-12-31T23:59:59"
    }
    
    Request body (approved - no subscription):
    {
        "messenger": "max",
        "user_id": 123456789,
        "phone": "+79991234567",
        "status": "approved",
        "manager_name": "Иван Иванов",
        "manager_id": 987654321,
        "subscription_status": "none"
    }
    
    Request body (rejected):
    {
        "messenger": "max",
        "user_id": 123456789,
        "phone": "+79991234567",
        "status": "rejected",
        "reason": "Неверные данные"
    }
    
    Response:
    {
        "status": "success" | "error",
        "message": "Human-readable message",
        "messenger": "max" | "telegram",
        "user_id": 123456789
    }
    
    Args:
        payload: Registration webhook payload with messenger, user_id, phone, status, and conditional fields
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with status and message
        
    Raises:
        HTTPException: 400 if payload validation fails
        HTTPException: 404 if user not found
        HTTPException: 500 if internal error occurs
        
    Requirements:
        - 4.2: CRM manual registration confirmation with manager assignment
        - 4.19: CRM webhook integration for registration approval
        - Support both Telegram and MAX messengers
        - Validate messenger, user_id, phone, status, and conditional fields
        - API key authentication
        - Update user registration status, manager, and support expiration
        - Send notification to user
        - Log all webhook receipts
    """
    logger.info(
        f"Registration webhook received: messenger={payload.messenger}, "
        f"user_id={payload.user_id}, phone={payload.phone}, status={payload.status}"
    )
    
    try:
        # Query user by messenger-specific ID
        if payload.messenger == "telegram":
            stmt = select(User).where(User.tg_user_id == payload.user_id)
        elif payload.messenger == "max":
            stmt = select(User).where(User.max_user_id == payload.user_id)
        else:
            # This should never happen due to Pydantic validation
            logger.error(f"Invalid messenger type: {payload.messenger}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid messenger type: {payload.messenger}",
            )
        
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(
                f"User with {payload.messenger}_user_id={payload.user_id} not found for registration webhook"
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
        
        # Update registration status based on payload
        if payload.status == "approved":
            user.registration_status = RegistrationStatus.ACTIVE
            
            # Update manager assignment (requirement 4.2)
            if payload.manager_id:
                # Find staff member by messenger-specific ID
                if payload.messenger == "telegram":
                    stmt_staff = select(Staff_Member).where(Staff_Member.tg_user_id == payload.manager_id)
                else:  # max
                    stmt_staff = select(Staff_Member).where(Staff_Member.max_user_id == payload.manager_id)
                
                result_staff = await session.execute(stmt_staff)
                manager = result_staff.scalar_one_or_none()
                
                if manager:
                    user.default_manager_id = manager.id
                    logger.info(f"Assigned manager {manager.full_name} (id={manager.id}) to user {user.id}")
                else:
                    logger.warning(
                        f"Manager with {payload.messenger}_user_id={payload.manager_id} not found in database. "
                        f"User {user.id} will not have default_manager_id set."
                    )
            
            # Handle subscription status and expiration date
            # Priority: explicit subscription_status from payload, then auto-detect from date
            if payload.subscription_status:
                # Use explicit subscription_status from webhook
                subscription_status_map = {
                    "active": SubscriptionStatus.ACTIVE,
                    "expired": SubscriptionStatus.EXPIRED,
                    "none": SubscriptionStatus.NONE
                }
                user.subscription_status = subscription_status_map[payload.subscription_status]
                logger.info(f"Set subscription_status to {payload.subscription_status} for user {user.id}")
                
                # Set expiration date only if provided (required for 'active', optional for others)
                if payload.support_expires_at:
                    # Strip timezone info to match database column (TIMESTAMP WITHOUT TIME ZONE)
                    expiration_date = payload.support_expires_at
                    if expiration_date.tzinfo is not None:
                        expiration_date = expiration_date.replace(tzinfo=None)
                    user.subscription_end_date = expiration_date
                    logger.info(f"Set subscription_end_date to {expiration_date} for user {user.id}")
                else:
                    # Clear expiration date if not provided (for 'none' or 'expired' status)
                    user.subscription_end_date = None
                    logger.info(f"Cleared subscription_end_date for user {user.id}")
            
            elif payload.support_expires_at:
                # Backward compatibility: auto-detect status from expiration date
                from utils.timezone_helpers import get_moscow_now_naive
                now_moscow = get_moscow_now_naive()
                
                # Strip timezone info to match database column
                expiration_date = payload.support_expires_at
                if expiration_date.tzinfo is not None:
                    expiration_date_aware = expiration_date
                    expiration_date = expiration_date.replace(tzinfo=None)
                else:
                    expiration_date_aware = expiration_date.replace(tzinfo=tz.utc)
                
                user.subscription_end_date = expiration_date
                
                if expiration_date_aware < now_utc:
                    user.subscription_status = SubscriptionStatus.EXPIRED
                    logger.warning(
                        f"Support expiration date {expiration_date} is in the past. "
                        f"Setting subscription_status to EXPIRED for user {user.id}"
                    )
                else:
                    user.subscription_status = SubscriptionStatus.ACTIVE
                    logger.info(
                        f"Set support expiration for user {user.id} to {expiration_date} "
                        f"with status ACTIVE"
                    )
            else:
                # No subscription info provided - set to NONE
                user.subscription_status = SubscriptionStatus.NONE
                user.subscription_end_date = None
                logger.info(f"No subscription info provided, set status to NONE for user {user.id}")
            
            # Build notification text with manager name
            # Import appropriate texts based on messenger
            if payload.messenger == "telegram":
                from bots.tg_bot.texts import REGISTRATION_APPROVED
            else:  # max
                from bots.max_bot.texts import REGISTRATION_APPROVED
            
            notification_text = REGISTRATION_APPROVED
            
            # Add manager info if manager was assigned
            if payload.manager_id and manager:
                if payload.messenger == "telegram":
                    manager_info = f"\n\n👤 <b>Вам назначен сотрудник:</b>\n{manager.full_name}"
                    if manager.position:
                        manager_info += f", {manager.position}"
                else:  # MAX - no HTML tags
                    manager_info = f"\n\n👤 Вам назначен сотрудник:\n{manager.full_name}"
                    if manager.position:
                        manager_info += f", {manager.position}"
                notification_text += manager_info
            
            # Add signature
            notification_text += "\n\nС уважением,\nКоманда АЙТАТ"
            
            action_type = "registration_approved_via_crm"
            log_message = (
                f"User {user.id} ({payload.messenger}_user_id={payload.user_id}) registration approved via CRM webhook. "
                f"Manager: {payload.manager_name} ({payload.messenger}_id={payload.manager_id}), "
                f"Support expires: {payload.support_expires_at}"
            )
            
        elif payload.status == "rejected":
            user.registration_status = RegistrationStatus.REJECTED
            
            # Import appropriate texts based on messenger
            if payload.messenger == "telegram":
                from bots.tg_bot.texts import REGISTRATION_REJECTED
            else:  # max
                from bots.max_bot.texts import REGISTRATION_REJECTED
            
            notification_text = REGISTRATION_REJECTED.format(
                reason=payload.reason or "Не указано"
            )
            action_type = "registration_rejected_via_crm"
            log_message = (
                f"User {user.id} ({payload.messenger}_user_id={payload.user_id}) registration rejected via CRM webhook. "
                f"Reason: {payload.reason}"
            )
        
        else:
            # This should never happen due to Pydantic validation
            logger.error(f"Invalid approval status: {payload.status}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {payload.status}",
            )
        
        await session.commit()
        logger.info(log_message)
        
        # Send notification to user via appropriate messenger
        try:
            from api.utils.messenger_utils import send_message_to_user
            
            result = await send_message_to_user(
                messenger=payload.messenger,
                user_id=user.id,  # Internal user ID
                text=notification_text,
                session=session,
                parse_mode="HTML"
            )
            
            if result["success"]:
                logger.info(f"Registration notification sent to {payload.messenger} user {user.id}")
            else:
                logger.warning(
                    f"Failed to send registration notification to {payload.messenger} user {user.id}: "
                    f"{result['message']}"
                )
        except Exception as e:
            logger.error(
                f"Failed to send registration notification to {payload.messenger} user {user.id}: {e}",
                exc_info=True
            )
        
        # Log action in Action_Log
        action_log = Action_Log(
            action_type=ActionType.USER_REGISTERED,
            user_id=user.id,
            action_details={
                "action": action_type,
                "approval_method": "crm",
                "messenger": payload.messenger,
                "status": payload.status,
                "rejection_reason": payload.reason,
                "phone": payload.phone,
                "messenger_user_id": payload.user_id,
                "user_name": user.full_name,
                "manager_name": payload.manager_name,
                "manager_messenger_id": payload.manager_id,
                "subscription_status": payload.subscription_status,
                "support_expires_at": payload.support_expires_at.isoformat() if payload.support_expires_at else None
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Registration webhook processed successfully for {payload.messenger}_user_id={payload.user_id}: {payload.status}"
        )
        
        return RegistrationWebhookResponse(
            status="success",
            message=f"Registration {payload.status} processed successfully",
            messenger=payload.messenger,
            user_id=payload.user_id
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (404, 400, etc.)
        raise
        
    except Exception as e:
        # Unexpected error
        logger.error(
            f"Error processing registration webhook for user {payload.user_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )
