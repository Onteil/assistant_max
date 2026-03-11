"""
Test script to send registration rejection webhook
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.registration_schemas import RegistrationWebhookPayload
from bots.tg_bot.texts import REGISTRATION_REJECTED
from constants import AsyncSessionLocal, TG_BOT_TOKEN
from database.models import Action_Log, ActionType, RegistrationStatus, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_rejection_webhook():
    """
    Test registration rejection webhook logic locally
    """
    # Create payload
    payload = RegistrationWebhookPayload(
        user_id=24,
        phone="+79956877974",
        status="rejected",
        reason="Недостаточно данных для подтверждения личности"
    )
    
    logger.info(
        f"Testing registration rejection webhook: user_id={payload.user_id}, "
        f"phone={payload.phone}, status={payload.status}, reason={payload.reason}"
    )
    
    async with AsyncSessionLocal() as session:
        try:
            # Query user
            stmt = select(User).where(User.id == payload.user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"User {payload.user_id} not found")
                return
            
            logger.info(f"Found user: {user.full_name}, current status: {user.registration_status}")
            
            # Verify phone number matches
            if user.phone_number != payload.phone:
                logger.warning(
                    f"Phone number mismatch: expected {user.phone_number}, got {payload.phone}"
                )
            
            # Update registration status
            user.registration_status = RegistrationStatus.REJECTED
            notification_text = REGISTRATION_REJECTED.format(
                reason=payload.reason or "Не указано"
            )
            action_type = "registration_rejected_via_crm"
            log_message = (
                f"User {payload.user_id} registration rejected via CRM webhook. "
                f"Reason: {payload.reason}"
            )
            
            await session.commit()
            logger.info(f"✅ {log_message}")
            logger.info(f"New status: {user.registration_status}")
            
            # Send notification to user via Telegram
            if user.tg_user_id:
                from aiogram import Bot
                from aiogram.enums import ParseMode
                
                bot = Bot(token=TG_BOT_TOKEN)
                try:
                    await bot.send_message(
                        chat_id=user.tg_user_id,
                        text=notification_text,
                        parse_mode=ParseMode.HTML
                    )
                    logger.info(f"✅ Sent rejection notification to Telegram user {user.tg_user_id}")
                    logger.info(f"Message text:\n{notification_text}")
                except Exception as send_error:
                    logger.error(f"❌ Failed to send notification: {send_error}")
                finally:
                    await bot.session.close()
            else:
                logger.warning(f"⚠️ User has no Telegram ID, cannot send notification")
            
            # Log action
            action_log = Action_Log(
                action_type=ActionType.USER_REGISTERED,
                user_id=user.id,
                action_details={
                    "action": action_type,
                    "approval_method": "crm",
                    "status": payload.status,
                    "rejection_reason": payload.reason,
                    "phone": payload.phone,
                    "user_name": user.full_name
                },
                action_timestamp=datetime.now()
            )
            session.add(action_log)
            await session.commit()
            
            logger.info("✅ Registration rejection webhook processed successfully")
            
        except Exception as e:
            logger.error(f"❌ Error: {e}", exc_info=True)
            await session.rollback()


if __name__ == "__main__":
    asyncio.run(test_rejection_webhook())
