"""
NPS Survey System - Payment Webhook Handler

This module implements the webhook endpoint for receiving payment confirmation
events from 1C CRM. When a payment is confirmed, it triggers the NPS survey
scheduling process with frequency limiting.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.nps_schemas import PaymentWebhookPayload
from constants import get_session, WEBHOOK_API_KEY
from database.models import SurveyType, User
from services.nps_service import schedule_survey

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
        
    Requirements: 7.3 - Webhook authentication
    """
    if not x_api_key:
        logger.warning("NPS webhook request received without API key")
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


@router.post("/payment_confirmed")
async def payment_confirmed_webhook(
    payload: PaymentWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> dict:
    """
    Handle payment confirmation webhook from 1C CRM.
    
    This endpoint receives payment confirmation events and triggers NPS survey
    scheduling with LOYALTY survey type. The survey is scheduled for delivery
    N days after the payment date, where N is configured in system settings.
    
    Frequency limiting is automatically applied - if the user has received
    any NPS survey within the configured frequency limit period, the survey
    will be suppressed.
    
    Supports both Telegram and MAX messengers.
    
    Request body (Telegram):
    {
        "messenger": "telegram",
        "user_id": 123456789,
        "payment_date": "2024-02-15T10:30:00Z"
    }
    
    Request body (MAX):
    {
        "messenger": "max",
        "user_id": 987654321,
        "payment_date": "2024-02-15T10:30:00Z"
    }
    
    Response:
    {
        "status": "scheduled" | "suppressed" | "error",
        "reason": "Survey scheduled for delivery" | "Frequency limit active" | "Error message",
        "messenger": "telegram" | "max",
        "user_id": 123456789
    }
    
    Args:
        payload: Payment webhook payload with messenger, user_id, payment_date
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with status, reason, messenger, and user_id
        
    Raises:
        HTTPException: 400 if payload validation fails
        HTTPException: 404 if user not found
        HTTPException: 500 if internal error occurs
        
    Requirements:
        - 7.1: Webhook endpoint /api/webhooks/payment_confirmed
        - 7.2: Validate messenger, user_id, payment_date fields
        - 7.3: API key authentication
        - 7.4: Schedule survey with LOYALTY type
        - 7.5: Return appropriate HTTP status codes
        - 7.6: Log all webhook receipts
        - Support both Telegram and MAX messengers
    """
    logger.info(
        f"Payment webhook received: messenger={payload.messenger}, "
        f"user_id={payload.user_id}, "
        f"payment_date={payload.payment_date}"
    )
    
    try:
        # Query user by messenger-specific ID to get internal database ID
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
                f"User with {payload.messenger}_user_id={payload.user_id} not found for NPS webhook"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with {payload.messenger.upper()} ID {payload.user_id} not found",
            )
        
        # Schedule NPS survey with LOYALTY type
        # The schedule_survey function handles:
        # - Frequency limit checking
        # - User lookup by internal database ID
        # - Celery task creation with appropriate delay
        # - Timestamp updates
        scheduled, reason = await schedule_survey(
            session=session,
            user_id=user.id,  # Use internal database ID
            survey_type=SurveyType.LOYALTY,
            trigger_event_id=0,
            event_date=payload.payment_date,
        )
        
        if scheduled:
            logger.info(
                f"NPS survey scheduled for user {user.id} "
                f"({payload.messenger}_user_id={payload.user_id}): {reason}"
            )
            return {
                "status": "scheduled",
                "reason": reason,
                "messenger": payload.messenger,
                "user_id": payload.user_id,
            }
        else:
            logger.info(
                f"NPS survey suppressed for user {user.id} "
                f"({payload.messenger}_user_id={payload.user_id}): {reason}"
            )
            return {
                "status": "suppressed",
                "reason": reason,
                "messenger": payload.messenger,
                "user_id": payload.user_id,
            }
            
    except HTTPException as http_exc:
        # Notify admins about HTTP errors
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = f"HTTP {http_exc.status_code}"
            error_details = http_exc.detail
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="payment_confirmed",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        # Re-raise HTTP exceptions (404, 400, etc.)
        raise
        
    except ValueError as e:
        # User not found or validation error - notify admins
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = "ValueError"
            error_details = str(e)
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="payment_confirmed",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        logger.error(
            f"Validation error processing payment webhook: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
        
    except Exception as e:
        # Unexpected error - notify admins
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = type(e).__name__
            error_details = str(e)
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="payment_confirmed",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        # Unexpected error
        logger.error(
            f"Error processing payment webhook for user {payload.user_id}: {e}",
            exc_info=True
        )
        return {
            "status": "error",
            "reason": f"Internal error: {str(e)}",
            "messenger": payload.messenger,
            "user_id": payload.user_id,
        }



@router.post("/test_nps_survey")
async def test_nps_survey_webhook(
    payload: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> dict:
    """
    Test NPS survey delivery - sends survey immediately without delay.
    
    This endpoint is for testing purposes only. It bypasses the normal
    scheduling delay and frequency limits, sending the NPS survey immediately.
    
    Request body:
    {
        "messenger": "telegram" | "max",
        "user_id": 123456789,
        "survey_type": "loyalty" | "service_quality",
        "trigger_event_id": 0,
        "event_date": "2024-02-15T10:30:00Z"
    }
    
    Response:
    {
        "status": "success" | "error",
        "message": "Survey sent successfully" | "Error message",
        "details": {...}
    }
    
    Args:
        payload: Test survey payload
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with status and details
        
    Raises:
        HTTPException: 400 if validation fails
        HTTPException: 404 if user not found
    """
    logger.info(
        f"Test NPS survey request: messenger={payload.get('messenger')}, "
        f"user_id={payload.get('user_id')}"
    )
    
    try:
        # Validate required fields
        messenger = payload.get("messenger")
        user_id = payload.get("user_id")
        survey_type = payload.get("survey_type", "loyalty")
        trigger_event_id = payload.get("trigger_event_id", 0)
        event_date_str = payload.get("event_date")
        
        if not messenger or not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: messenger, user_id",
            )
        
        if messenger not in ["telegram", "max"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid messenger: {messenger}",
            )
        
        # Parse event_date - handle both ISO formats (with and without 'Z')
        from datetime import datetime
        if event_date_str:
            # Replace 'Z' with '+00:00' for Python compatibility
            if event_date_str.endswith('Z'):
                event_date_str = event_date_str[:-1] + '+00:00'
            try:
                event_date = datetime.fromisoformat(event_date_str)
                # Remove timezone info to make it naive (for compatibility with format_relative_time)
                if event_date.tzinfo is not None:
                    event_date = event_date.replace(tzinfo=None)
            except ValueError as e:
                logger.warning(f"Invalid date format: {event_date_str}, using current time")
                event_date = datetime.now()
        else:
            event_date = datetime.now()
        
        # Query user by messenger-specific ID
        if messenger == "telegram":
            stmt = select(User).where(User.tg_user_id == user_id)
        else:
            stmt = select(User).where(User.max_user_id == user_id)
        
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(
                f"User with {messenger}_user_id={user_id} not found for test NPS"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with {messenger.upper()} ID {user_id} not found",
            )
        
        # Reset last_nps_sent_at to bypass frequency limit for testing
        user.last_nps_sent_at = None
        await session.commit()
        
        logger.info(
            f"Reset frequency limit for test: user_id={user.id}, "
            f"messenger={messenger}"
        )
        
        # Import and execute the async survey function directly
        from celery_app.nps_tasks import _send_survey_async
        
        # Send survey immediately (bypassing frequency limits)
        result = await _send_survey_async(
            user_id=user.id,  # Use internal database ID
            survey_type=survey_type,
            trigger_event_id=trigger_event_id,
            event_date=event_date.isoformat(),
        )
        
        if result.get("status") == "success":
            logger.info(
                f"Test NPS survey sent successfully: user_id={user.id}, "
                f"messenger={result.get('messenger')}"
            )
            return {
                "status": "success",
                "message": "Survey sent successfully",
                "details": {
                    "user_id": user_id,
                    "internal_user_id": user.id,
                    "messenger": result.get("messenger"),
                    "messenger_id": result.get("messenger_id"),
                    "survey_type": survey_type,
                }
            }
        else:
            logger.warning(
                f"Test NPS survey failed: user_id={user.id}, "
                f"status={result.get('status')}, reason={result.get('reason')}"
            )
            return {
                "status": result.get("status"),
                "message": result.get("reason", "Survey delivery failed"),
                "details": {
                    "user_id": user_id,
                    "internal_user_id": user.id,
                    "error": result.get("error"),
                }
            }
            
    except HTTPException as http_exc:
        # Notify admins about HTTP errors
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = f"HTTP {http_exc.status_code}"
            error_details = http_exc.detail
            payload_summary = f"messenger={payload.get('messenger')}, user_id={payload.get('user_id')}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="test_nps_survey",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        raise
        
    except Exception as e:
        # Unexpected error - notify admins
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = type(e).__name__
            error_details = str(e)
            payload_summary = f"messenger={payload.get('messenger')}, user_id={payload.get('user_id')}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="test_nps_survey",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        logger.error(
            f"Error in test NPS survey: user_id={payload.get('user_id')}, error={e}",
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Internal error: {str(e)}",
            "details": {
                "user_id": payload.get("user_id"),
            }
        }
