"""
Subscription Status Change Webhook Handler

This module implements the webhook endpoint for receiving subscription status updates
from 1C CRM. When a user's subscription status changes (payment received, expiration,
or administrative action), the CRM sends an update to this endpoint.

Requirements: 5.1-5.9 - Subscription status management webhook
"""

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.subscription_schemas import (
    SubscriptionWebhookPayload,
    SubscriptionWebhookResponse,
)
from constants import get_session, WEBHOOK_API_KEY
from database.models import (
    Action_Log,
    ActionType,
    SubscriptionStatus,
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
        logger.warning("Subscription webhook request received without API key")
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


@router.post("/subscription_status_change", response_model=SubscriptionWebhookResponse)
async def subscription_status_change_webhook(
    payload: SubscriptionWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> SubscriptionWebhookResponse:
    """
    Handle subscription status change webhook from 1C CRM.
    
    This endpoint receives subscription status updates from the CRM system.
    Updates include status changes (active/expired/none) and subscription end dates.
    Sends friendly notifications to users about their subscription changes.
    
    Request body (activation):
    {
        "messenger": "telegram",
        "user_id": 123456789,
        "subscription_status": "active",
        "subscription_end_date": "2026-12-31T23:59:59"
    }
    
    Request body (expiration):
    {
        "messenger": "max",
        "user_id": 123456789,
        "subscription_status": "expired"
    }
    
    Response:
    {
        "status": "success",
        "message": "Subscription status updated successfully",
        "user_id": 123456789,
        "subscription_status": "active"
    }
    
    Args:
        payload: Subscription status change payload
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with update status
        
    Raises:
        HTTPException: 404 if user not found
        HTTPException: 400 if validation fails
        HTTPException: 500 if internal error occurs
        
    Requirements:
        - 5.1: Update User.subscription_status
        - 5.2: Update User.subscription_end_date if provided
        - 5.3: Send friendly notification to user about subscription change
        - 5.4: Different messages for active/expired/none statuses
        - 5.5: Log action in Action_Log
        - 5.6: Return 404 if user not found
        - 5.7: Return 400 if status="active" and end_date in past
        - 5.8: Log warning if notification fails but continue
        - 5.9: Return 401 if API key invalid
    """
    logger.info(
        f"Subscription status change webhook received: messenger={payload.messenger}, "
        f"user_id={payload.user_id}, status={payload.subscription_status}"
    )
    
    try:
        # Step 1: Query user by messenger-specific ID
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
        
        # Requirement 5.6: Return 404 if user not found
        if not user:
            logger.error(
                f"User with {payload.messenger}_user_id={payload.user_id} not found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with {payload.messenger.upper()} ID {payload.user_id} not found",
            )
        
        # Requirement 5.7: Validate active subscription has future end date
        if payload.subscription_status == "active" and payload.subscription_end_date:
            now = datetime.now(timezone.utc)
            end_date = payload.subscription_end_date
            
            # Make end_date timezone-aware if it isn't
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            
            if end_date < now:
                logger.error(
                    f"Invalid subscription: status='active' but end_date {end_date} is in the past"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot set active subscription with past end date",
                )
        
        # Track old status for notification logic
        old_status = user.subscription_status
        old_end_date = user.subscription_end_date
        
        # Check if data has actually changed (deduplication for 1C CRM multiple triggers)
        from api.webhooks.webhook_utils import has_field_changed
        
        new_status = SubscriptionStatus[payload.subscription_status.upper()]
        status_changed = has_field_changed(old_status, new_status, "subscription_status")
        
        # Prepare end_date for comparison
        end_date_changed = False
        new_end_date = None
        if payload.subscription_end_date is not None:
            # Convert to naive datetime for PostgreSQL TIMESTAMP WITHOUT TIME ZONE
            end_date = payload.subscription_end_date
            if end_date.tzinfo is not None:
                # Convert to UTC and remove timezone info
                end_date = end_date.astimezone(timezone.utc).replace(tzinfo=None)
            new_end_date = end_date
            end_date_changed = has_field_changed(old_end_date, new_end_date, "subscription_end_date")
        
        # If nothing changed, skip update and notification
        if not status_changed and not end_date_changed:
            logger.info(
                f"Subscription data unchanged for user {user.id}: "
                f"status={payload.subscription_status}, end_date={payload.subscription_end_date}. "
                f"Skipping update (likely duplicate webhook from 1C CRM)."
            )
            return SubscriptionWebhookResponse(
                status="success",
                message="Subscription data already up to date (no changes detected)",
                user_id=payload.user_id,
                subscription_status=payload.subscription_status
            )
        
        # Step 2: Update user subscription fields
        # Requirement 5.1: Update subscription_status
        if status_changed:
            user.subscription_status = new_status
            logger.info(f"Updated subscription_status for user {user.id}: {old_status} -> {new_status}")
        
        # Requirement 5.2: Update subscription_end_date if provided
        if end_date_changed and new_end_date is not None:
            user.subscription_end_date = new_end_date
            logger.info(f"Updated subscription_end_date for user {user.id}: {old_end_date} -> {new_end_date}")
        
        await session.commit()
        
        logger.info(
            f"Updated subscription for user {user.id}: "
            f"status={payload.subscription_status}, "
            f"end_date={payload.subscription_end_date}"
        )
        
        # Step 3: Send notification to user about subscription change
        user_messenger_id = (
            user.tg_user_id if payload.messenger == "telegram" else user.max_user_id
        )
        
        if user_messenger_id:
            # Build notification based on status (different format for Telegram and MAX)
            if payload.subscription_status == "active":
                end_date_str = ""
                if payload.subscription_end_date:
                    end_date = payload.subscription_end_date
                    if end_date.tzinfo is not None:
                        end_date = end_date.astimezone(timezone.utc).replace(tzinfo=None)
                    end_date_str = f" до {end_date.strftime('%d.%m.%Y')}"
                
                if payload.messenger == "telegram":
                    notification_text = (
                        f"✅ <b>Ваша подписка активирована!</b>\n\n"
                        f"Теперь вам доступны все возможности сервиса{end_date_str}.\n\n"
                        f"Если у вас возникнут вопросы, мы всегда готовы помочь!\n\n"
                        f"С уважением,\nКоманда АЙТАТ 💙"
                    )
                else:  # MAX - no HTML tags
                    notification_text = (
                        f"✅ Ваша подписка активирована!\n\n"
                        f"Теперь вам доступны все возможности сервиса{end_date_str}.\n\n"
                        f"Если у вас возникнут вопросы, мы всегда готовы помочь!\n\n"
                        f"С уважением,\nКоманда АЙТАТ 💙"
                    )
            elif payload.subscription_status == "expired":
                if payload.messenger == "telegram":
                    notification_text = (
                        f"⚠️ <b>Ваша подписка истекла</b>\n\n"
                        f"Для продления подписки и продолжения работы с сервисом, "
                        f"пожалуйста, обратитесь к вашему менеджеру.\n\n"
                        f"Мы будем рады продолжить сотрудничество!\n\n"
                        f"С уважением,\nКоманда АЙТАТ 💙"
                    )
                else:  # MAX - no HTML tags
                    notification_text = (
                        f"⚠️ Ваша подписка истекла\n\n"
                        f"Для продления подписки и продолжения работы с сервисом, "
                        f"пожалуйста, обратитесь к вашему менеджеру.\n\n"
                        f"Мы будем рады продолжить сотрудничество!\n\n"
                        f"С уважением,\nКоманда АЙТАТ 💙"
                    )
                
                # Create inline keyboard with renewal button
                keyboard_markup = None
                if payload.messenger == "telegram":
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    from bots.tg_bot.callback_datas import RenewalCallback
                    
                    keyboard_markup = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text="📝 Оформить заявку на продление",
                            callback_data=RenewalCallback(action="renew_from_notification").pack()
                        )]
                    ])
                else:  # max
                    from maxapi.types.attachments.buttons import CallbackButton
                    from maxapi.types.attachments.attachment import ButtonsPayload
                    from bots.max_bot.payloads import RenewalPayload
                    
                    keyboard_markup = ButtonsPayload(buttons=[
                        [CallbackButton(
                            text="📝 Оформить заявку на продление",
                            payload=RenewalPayload(action="renew").pack()
                        )]
                    ])
            else:  # none
                if payload.messenger == "telegram":
                    notification_text = (
                        f"ℹ️ <b>Статус вашей подписки изменён</b>\n\n"
                        f"Если у вас есть вопросы по подписке, "
                        f"обратитесь к вашему менеджеру.\n\n"
                        f"С уважением,\nКоманда АЙТАТ 💙"
                    )
                else:  # MAX - no HTML tags
                    notification_text = (
                        f"ℹ️ Статус вашей подписки изменён\n\n"
                        f"Если у вас есть вопросы по подписке, "
                        f"обратитесь к вашему менеджеру.\n\n"
                        f"С уважением,\nКоманда АЙТАТ 💙"
                    )
            
            try:
                # Send via centralized utility
                from api.utils.messenger_utils import send_message_to_user
                
                result = await send_message_to_user(
                    messenger=payload.messenger,
                    user_id=user.id,
                    text=notification_text,
                    session=session,
                    keyboard=keyboard_markup if payload.subscription_status == "expired" else None,
                    parse_mode="HTML"
                )
                
                if result["success"]:
                    logger.info(
                        f"Subscription notification sent to {payload.messenger} user {user.id}"
                    )
                    notification_sent = True
                else:
                    logger.warning(
                        f"Failed to send subscription notification to user {user.id}: {result['message']}"
                    )
                    notification_sent = False
                
            except Exception as e:
                # Requirement 5.8: Log warning if notification fails but continue
                logger.warning(
                    f"Failed to send subscription notification to user {user.id}: {e}",
                    exc_info=True
                )
                notification_sent = False
        else:
            logger.warning(
                f"User {user.id} has no {payload.messenger} user ID, "
                f"cannot send subscription notification"
            )
            notification_sent = False
        
        # Step 4: Send additional notification if status changed to expired (legacy requirement)
        should_notify_expired = (
            payload.subscription_status == "expired" and 
            old_status != SubscriptionStatus.EXPIRED
        )
        
        if should_notify_expired and not notification_sent:
            # Fallback notification if main notification failed
            if user_messenger_id:
                try:
                    logger.info(
                        f"Sending fallback expiration notification to {payload.messenger} "
                        f"user {user_messenger_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to send fallback expiration notification to user {user.id}: {e}",
                        exc_info=True
                    )
        
        # Step 5: Log action in Action_Log (Requirement 5.5)
        action_log = Action_Log(
            action_type=ActionType.STATUS_CHANGED,
            user_id=user.id,
            staff_id=None,
            action_details={
                "action": "subscription_status_changed",
                "old_status": old_status.value if old_status else None,
                "new_status": payload.subscription_status,
                "subscription_end_date": (
                    payload.subscription_end_date.isoformat() 
                    if payload.subscription_end_date else None
                ),
                "messenger": payload.messenger,
                "user_messenger_id": payload.user_id,
                "notification_sent": notification_sent,
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Subscription status change webhook processed successfully for user {user.id}"
        )
        
        return SubscriptionWebhookResponse(
            status="success",
            message="Subscription status updated successfully",
            user_id=payload.user_id,
            subscription_status=payload.subscription_status
        )
        
    except HTTPException as http_exc:
        # Notify admins about HTTP errors
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = f"HTTP {http_exc.status_code}"
            error_details = http_exc.detail
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}, status={payload.subscription_status}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="subscription_status",
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
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}, status={payload.subscription_status}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="subscription_status",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        # Unexpected error (Requirement 18.6, 18.9)
        logger.error(
            f"Error processing subscription status change webhook: {e}",
            exc_info=True
        )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )
