"""
Renewal Reminder Webhooks

Webhook endpoints for testing renewal reminder functionality.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from constants import get_session, WEBHOOK_API_KEY
from database.models import User

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.post("/test_renewal_reminder")
async def test_renewal_reminder_webhook(
    payload: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> dict:
    """
    Test renewal reminder delivery - sends reminder immediately without delay.
    
    This endpoint is for testing purposes only. It bypasses the normal
    scheduling and sends the renewal reminder immediately.
    
    Request body:
    {
        "messenger": "telegram" | "max",
        "user_id": 123456789,
        "reminder_type": "30" | "7"  # days before expiration
    }
    
    Response:
    {
        "status": "success" | "error",
        "message": "Reminder sent successfully" | "Error message",
        "details": {...}
    }
    
    Args:
        payload: Test reminder payload
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with status and details
        
    Raises:
        HTTPException: 400 if validation fails
        HTTPException: 404 if user not found
    """
    logger.info(
        f"Test renewal reminder request: messenger={payload.get('messenger')}, "
        f"user_id={payload.get('user_id')}, reminder_type={payload.get('reminder_type')}"
    )
    
    try:
        # Validate required fields
        messenger = payload.get("messenger")
        user_id = payload.get("user_id")
        reminder_type = payload.get("reminder_type", "30")
        
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
        
        if reminder_type not in ["30", "7"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid reminder_type: {reminder_type}. Must be '30' or '7'",
            )
        
        # Query user by messenger-specific ID
        if messenger == "telegram":
            stmt = select(User).where(User.tg_user_id == user_id)
        else:
            stmt = select(User).where(User.max_user_id == user_id)
        
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(
                f"User with {messenger}_user_id={user_id} not found for test renewal reminder"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with {messenger.upper()} ID {user_id} not found",
            )
        
        # Check if user has subscription_end_date
        if not user.subscription_end_date:
            logger.warning(
                f"User {user.id} has no subscription_end_date for test renewal reminder"
            )
            return {
                "status": "error",
                "message": "User has no subscription_end_date",
                "details": {
                    "user_id": user_id,
                    "internal_user_id": user.id,
                    "messenger": messenger,
                }
            }
        
        # Import bot and send message directly
        from datetime import datetime, timezone
        
        # Check if subscription has already expired
        now = datetime.now(timezone.utc)
        if user.subscription_end_date <= now:
            logger.warning(
                f"User {user.id} subscription already expired: "
                f"end_date={user.subscription_end_date}, now={now}"
            )
            return {
                "status": "error",
                "message": "Subscription has already expired",
                "details": {
                    "user_id": user_id,
                    "internal_user_id": user.id,
                    "messenger": messenger,
                    "subscription_end_date": user.subscription_end_date.strftime("%d.%m.%Y %H:%M:%S"),
                    "current_date": now.strftime("%d.%m.%Y %H:%M:%S"),
                }
            }
        
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
        
        from bots.tg_bot.keyboards.renewal_kb import get_subscription_status_keyboard
        from bots.tg_bot.texts import RENEWAL_REMINDER_30_DAYS, RENEWAL_REMINDER_7_DAYS
        from constants import TG_BOT_TOKEN
        
        # Format expiration date
        expiry_date = user.subscription_end_date.strftime("%d.%m.%Y")
        
        # Select message text based on reminder type
        if reminder_type == "30":
            message_text = RENEWAL_REMINDER_30_DAYS.format(expiry_date=expiry_date)
        else:
            message_text = RENEWAL_REMINDER_7_DAYS.format(expiry_date=expiry_date)
        
        # Get renewal keyboard
        keyboard = await get_subscription_status_keyboard(user.subscription_status)
        
        # Send message based on messenger
        if messenger == "telegram":
            if not user.tg_user_id:
                return {
                    "status": "error",
                    "message": "User has no Telegram ID",
                    "details": {
                        "user_id": user_id,
                        "internal_user_id": user.id,
                    }
                }
            
            # Initialize bot
            bot = Bot(
                token=TG_BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
            
            try:
                # Send Telegram message
                await bot.send_message(
                    chat_id=user.tg_user_id,
                    text=message_text,
                    reply_markup=keyboard
                )
                
                logger.info(
                    f"Test renewal reminder sent successfully: "
                    f"user_id={user.id}, tg_user_id={user.tg_user_id}, "
                    f"reminder_type={reminder_type}"
                )
                
                return {
                    "status": "success",
                    "message": "Reminder sent successfully",
                    "details": {
                        "user_id": user_id,
                        "internal_user_id": user.id,
                        "messenger": "telegram",
                        "messenger_id": user.tg_user_id,
                        "reminder_type": f"{reminder_type} days",
                        "expiry_date": expiry_date,
                    }
                }
            
            except TelegramForbiddenError as e:
                logger.warning(
                    f"Bot blocked by user: user_id={user.id}, "
                    f"tg_user_id={user.tg_user_id}, error={e}"
                )
                return {
                    "status": "bot_blocked",
                    "message": "Bot is blocked by user",
                    "details": {
                        "user_id": user_id,
                        "internal_user_id": user.id,
                        "error": str(e),
                    }
                }
            
            except TelegramBadRequest as e:
                logger.error(
                    f"Telegram bad request: user_id={user.id}, "
                    f"tg_user_id={user.tg_user_id}, error={e}",
                    exc_info=True
                )
                return {
                    "status": "failed",
                    "message": f"Telegram error: {str(e)}",
                    "details": {
                        "user_id": user_id,
                        "internal_user_id": user.id,
                        "error": str(e),
                    }
                }
            
            finally:
                # Close bot session
                await bot.session.close()
        
        else:  # MAX messenger
            if not user.max_user_id:
                return {
                    "status": "error",
                    "message": "User has no MAX ID",
                    "details": {
                        "user_id": user_id,
                        "internal_user_id": user.id,
                    }
                }
            
            # Import MAX texts and keyboard
            from bots.max_bot.texts import RENEWAL_REMINDER_30_DAYS as MAX_RENEWAL_30
            from bots.max_bot.texts import RENEWAL_REMINDER_7_DAYS as MAX_RENEWAL_7
            from bots.max_bot.keyboards.user.renewal_kb import get_subscription_status_keyboard as get_max_keyboard
            
            # Select message text based on reminder type
            if reminder_type == "30":
                message_text = MAX_RENEWAL_30.format(expiry_date=expiry_date)
            else:
                message_text = MAX_RENEWAL_7.format(expiry_date=expiry_date)
            
            # Get MAX keyboard
            max_keyboard = await get_max_keyboard(user.subscription_status)
            
            # Send message via utility function
            from api.utils.messenger_utils import send_message_to_user
            
            result = await send_message_to_user(
                messenger="max",
                user_id=user.id,  # Internal user ID, not max_user_id
                text=message_text,
                session=session,  # Required for MAX to get chat_id
                keyboard=max_keyboard
            )
            
            if result["success"]:
                logger.info(
                    f"Test renewal reminder sent successfully: "
                    f"user_id={user.id}, max_user_id={user.max_user_id}, "
                    f"reminder_type={reminder_type}"
                )
                
                return {
                    "status": "success",
                    "message": "Reminder sent successfully",
                    "details": {
                        "user_id": user_id,
                        "internal_user_id": user.id,
                        "messenger": "max",
                        "messenger_id": user.max_user_id,
                        "reminder_type": f"{reminder_type} days",
                        "expiry_date": expiry_date,
                    }
                }
            else:
                return {
                    "status": result["status"],
                    "message": result["message"],
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
                webhook_name="test_renewal_reminder",
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
                webhook_name="test_renewal_reminder",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        logger.error(
            f"Error in test renewal reminder: user_id={payload.get('user_id')}, error={e}",
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Internal error: {str(e)}",
            "details": {
                "user_id": payload.get("user_id"),
            }
        }
