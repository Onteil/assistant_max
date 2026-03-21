"""
NPS Survey Response Handler Service

Handles user rating responses, CRM integration, and thank you messages.
Processes NPS survey responses and sends data to 1C CRM.

Requirements: 4.4, 4.5, 5.2, 5.3, 5.4, 5.5, 5.6, 11.5, 13.3
"""

import logging
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import NPS_Response, SurveyType, User, Staff_Member, StaffRole, MAX_Messenger_Data
from services.i_tat_service import get_itat_client

logger = logging.getLogger(__name__)


async def handle_rating_response(
    session: AsyncSession,
    user_id: int,
    rating: int,
    survey_type: SurveyType,
    trigger_event_id: int
) -> tuple[bool, str]:
    """
    Process and store user rating response.
    
    Validates rating, creates NPS_Response record, and updates user's
    last_nps_sent_at timestamp.
    
    Args:
        session: Database session
        user_id: User's internal database ID
        rating: User's rating (0-10)
        survey_type: Type of survey (LOYALTY or SERVICE_QUALITY)
        trigger_event_id: ID of triggering event (invoice_id or ticket_id)
    
    Returns:
        Tuple of (success: bool, message: str)
    
    Requirements: 4.4, 5.2, 3.4, 13.4
    """
    logger.info(
        f"Processing NPS rating response: user_id={user_id}, "
        f"rating={rating}, survey_type={survey_type.value}, "
        f"trigger_event_id={trigger_event_id}"
    )
    
    try:
        # Validate rating is 0-10
        if not isinstance(rating, int) or rating < 0 or rating > 10:
            logger.warning(
                f"Invalid rating value rejected: user_id={user_id}, "
                f"rating={rating}, survey_type={survey_type.value}"
            )
            return (False, "Invalid rating: must be between 0 and 10")
        
        # Get current timestamp
        current_time = datetime.utcnow()
        
        # Create NPS_Response record
        nps_response = NPS_Response(
            user_id=user_id,
            survey_type=survey_type,
            rating=rating,
            trigger_event_id=trigger_event_id,
            sent_at=current_time,
            responded_at=current_time
        )
        session.add(nps_response)
        
        # Update user's last_nps_sent_at timestamp
        result = await session.execute(
            User.__table__.update()
            .where(User.id == user_id)
            .values(last_nps_sent_at=current_time)
        )
        
        await session.commit()
        
        logger.info(
            f"NPS response stored successfully: user_id={user_id}, "
            f"survey_type={survey_type.value}, rating={rating}, "
            f"trigger_event_id={trigger_event_id}, action=response_stored, "
            f"result=success"
        )
        
        return (True, "success")
    
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Failed to store NPS response: user_id={user_id}, "
            f"rating={rating}, survey_type={survey_type.value}, "
            f"trigger_event_id={trigger_event_id}, action=response_storage, "
            f"result=error, error={e}",
            exc_info=True
        )
        return (False, f"Database error: {str(e)}")


async def send_to_crm(
    user_id: int,
    rating: int,
    survey_type: SurveyType,
    event_date: datetime,
    response_timestamp: datetime
) -> bool:
    """
    Send NPS data to 1C CRM with retry logic and comprehensive error handling.
    
    Builds CRMNPSPayload and sends to 1C CRM endpoint using i_tat_service.
    Implements retry logic: 3 attempts with exponential backoff (1s, 2s, 4s).
    
    Handles:
    - Network errors (connection timeout, DNS failures)
    - HTTP errors (4xx, 5xx responses)
    - Unexpected exceptions
    
    Failed requests are logged with full context for manual review.
    
    Args:
        user_id: User's internal database ID
        rating: User's rating (0-10)
        survey_type: Type of survey (LOYALTY or SERVICE_QUALITY)
        event_date: Date of triggering event
        response_timestamp: When user responded
    
    Returns:
        bool: True if successful, False otherwise
    
    Requirements: 5.3, 5.4, 5.5, 5.6, 13.3, 13.4, 13.5
    """
    # Build CRM payload
    payload = {
        "telegram_id": user_id,
        "rating": rating,
        "survey_type": survey_type.value,
        "event_date": event_date.isoformat(),
        "response_timestamp": response_timestamp.isoformat()
    }
    
    # Retry configuration: 3 attempts with exponential backoff
    max_attempts = 3
    backoff_delays = [1, 2, 4]  # seconds
    
    try:
        client = get_itat_client()
    except Exception as e:
        logger.error(
            f"Failed to initialize i-TAT client for CRM integration: "
            f"user_id={user_id}, error={e}",
            exc_info=True
        )
        return False
    
    last_error = None
    
    for attempt in range(max_attempts):
        try:
            # Send to 1C CRM endpoint
            endpoint = f"{client.base_url}/nps/response"
            
            logger.info(
                f"Sending NPS data to CRM (attempt {attempt + 1}/{max_attempts}): "
                f"user_id={user_id}, rating={rating}, survey_type={survey_type.value}"
            )
            
            response = await client._make_request(
                method="POST",
                endpoint=endpoint,
                json=payload
            )
            
            logger.info(
                f"NPS data sent to CRM successfully: user_id={user_id}, "
                f"rating={rating}, survey_type={survey_type.value}, "
                f"attempt={attempt + 1}"
            )
            return True
        
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(
                f"CRM integration timeout (attempt {attempt + 1}/{max_attempts}): "
                f"user_id={user_id}, rating={rating}, survey_type={survey_type.value}, "
                f"error={e}"
            )
        
        except httpx.ConnectError as e:
            last_error = e
            logger.warning(
                f"CRM integration connection error (attempt {attempt + 1}/{max_attempts}): "
                f"user_id={user_id}, rating={rating}, survey_type={survey_type.value}, "
                f"error={e}"
            )
        
        except httpx.HTTPStatusError as e:
            last_error = e
            logger.warning(
                f"CRM integration HTTP error (attempt {attempt + 1}/{max_attempts}): "
                f"user_id={user_id}, rating={rating}, survey_type={survey_type.value}, "
                f"status_code={e.response.status_code}, error={e}"
            )
            
            # Don't retry on 4xx client errors (except 429 Too Many Requests)
            if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                logger.error(
                    f"CRM integration failed with client error (no retry): "
                    f"user_id={user_id}, rating={rating}, survey_type={survey_type.value}, "
                    f"status_code={e.response.status_code}, response={e.response.text}"
                )
                # Queue for manual review
                _queue_failed_crm_request(user_id, rating, survey_type, payload, str(e))
                return False
        
        except Exception as e:
            last_error = e
            logger.warning(
                f"CRM integration unexpected error (attempt {attempt + 1}/{max_attempts}): "
                f"user_id={user_id}, rating={rating}, survey_type={survey_type.value}, "
                f"error={e}",
                exc_info=True
            )
        
        # If not the last attempt, wait before retrying
        if attempt < max_attempts - 1:
            import asyncio
            delay = backoff_delays[attempt]
            logger.info(
                f"Retrying CRM integration in {delay}s: "
                f"user_id={user_id}, attempt={attempt + 2}/{max_attempts}"
            )
            await asyncio.sleep(delay)
    
    # All retries exhausted
    logger.error(
        f"CRM integration failed after {max_attempts} attempts: "
        f"user_id={user_id}, rating={rating}, survey_type={survey_type.value}, "
        f"last_error={last_error}",
        exc_info=True
    )
    
    # Queue for manual review
    _queue_failed_crm_request(user_id, rating, survey_type, payload, str(last_error))
    
    return False


def _queue_failed_crm_request(
    user_id: int,
    rating: int,
    survey_type: SurveyType,
    payload: dict,
    error: str
) -> None:
    """
    Queue failed CRM request for manual review.
    
    Logs the failed request with full context to enable manual retry
    or investigation. In production, this could write to a dedicated
    retry queue table or external queue system.
    
    Args:
        user_id: User's internal database ID
        rating: User's rating
        survey_type: Survey type
        payload: Full CRM payload that failed
        error: Error message
    
    Requirements: 13.3, 13.5
    """
    logger.error(
        f"MANUAL_REVIEW_REQUIRED: CRM integration failed permanently: "
        f"user_id={user_id}, rating={rating}, survey_type={survey_type.value}, "
        f"payload={payload}, error={error}"
    )
    
    # TODO: In production, write to api_retry_queue table or external queue
    # For now, logging with MANUAL_REVIEW_REQUIRED prefix enables grep/search


def format_thank_you_message() -> str:
    """
    Generate localized thank you message.
    
    Returns Russian thank you text for NPS survey responses.
    
    Returns:
        str: Russian thank you message
    
    Requirements: 4.5, 11.5
    """
    return "Ваше мнение помогает нам становиться лучше."


async def notify_staff_about_low_rating(
    session: AsyncSession,
    user: User,
    rating: int,
    survey_type: SurveyType,
    feedback_comment: str | None = None,
    trigger_event_id: int | None = None
) -> bool:
    """
    Send notification to all administrators about low NPS rating (0-7).
    
    Notifies all active administrators about negative feedback.
    For MAX messenger: includes action buttons (call, write in MAX).
    For Telegram: includes contact info and MAX profile link in text.
    
    Args:
        session: Database session
        user: User who provided the rating
        rating: User's rating (0-7)
        survey_type: Type of survey (LOYALTY or SERVICE_QUALITY)
        feedback_comment: Optional feedback comment from user
        trigger_event_id: Optional ID of the triggering event (ticket/invoice)
    
    Returns:
        bool: True if at least one notification sent successfully, False otherwise
    """
    try:
        # Get all active administrators
        stmt = select(Staff_Member).where(
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR,
            Staff_Member.is_active == True
        )
        result = await session.execute(stmt)
        administrators = result.scalars().all()
        
        if not administrators:
            logger.warning(
                f"No active administrators found for low NPS notification: "
                f"user_id={user.id}, rating={rating}"
            )
            return False
        
        logger.info(
            f"Found {len(administrators)} active administrators for low NPS notification"
        )
        
        # Build notification message
        survey_type_text = "оценка услуги" if survey_type == SurveyType.LOYALTY else "качество поддержки"
        user_name = user.full_name or user.first_name or f"ID {user.id}"
        
        # Collect client contact information
        contact_info = []
        if user.phone_number:
            contact_info.append(f"📱 {user.phone_number}")
        if user.email:
            contact_info.append(f"📧 {user.email}")
        
        contact_text = "\n".join(contact_info) if contact_info else "Контакты не указаны"
        
        # Add manager info if available
        manager_info = ""
        if user.default_manager_id:
            manager_stmt = select(Staff_Member).where(Staff_Member.id == user.default_manager_id)
            manager_result = await session.execute(manager_stmt)
            manager = manager_result.scalar_one_or_none()
            if manager:
                manager_info = f"<b>Менеджер:</b> {manager.full_name}\n"
        
        # Build ticket/invoice reference line
        event_ref = ""
        if trigger_event_id and trigger_event_id > 0:
            event_ref = f"<b>Заявка:</b> #{trigger_event_id}\n"
        
        # MAX profile link — works only via username, not numeric ID
        max_profile_url = None
        if user.username:
            max_profile_url = f"https://max.ru/{user.username}"
        
        notification_text = (
            f"⚠️ <b>Низкая оценка NPS</b>\n\n"
            f"<b>Клиент:</b> {user_name}\n"
            f"<b>Контакты:</b>\n{contact_text}\n\n"
            f"{manager_info}"
            f"{event_ref}"
            f"<b>Тип опроса:</b> {survey_type_text}\n"
            f"<b>Оценка:</b> {rating}/10\n"
        )
        
        if feedback_comment:
            notification_text += f"\n<b>Комментарий:</b>\n{feedback_comment}\n"
        
        notification_text += (
            f"\n💡 Пожалуйста, свяжитесь с клиентом для выяснения причин "
            f"и улучшения качества обслуживания."
        )
        
        # For Telegram: append MAX profile link in text (no buttons)
        tg_notification_text = notification_text
        if max_profile_url:
            tg_notification_text += f"\n\n🔗 Профиль в MAX: {max_profile_url}"
        
        # Send notification to all administrators
        success_count = 0
        for admin in administrators:
            # Determine which messenger to use (Telegram or MAX)
            messenger_type = None
            messenger_id = None
            
            if admin.tg_user_id:
                messenger_type = "telegram"
                messenger_id = admin.tg_user_id
            elif admin.max_user_id:
                # For MAX, get chat_id from max_messenger_data table
                stmt_chat = select(MAX_Messenger_Data.max_chat_id).where(
                    MAX_Messenger_Data.max_user_id == admin.max_user_id
                )
                result_chat = await session.execute(stmt_chat)
                max_chat_id = result_chat.scalar_one_or_none()
                
                if max_chat_id:
                    messenger_type = "max"
                    messenger_id = max_chat_id
                else:
                    logger.warning(
                        f"Administrator {admin.id} ({admin.full_name}) has max_user_id={admin.max_user_id} "
                        f"but no chat_id found in max_messenger_data table, skipping"
                    )
                    continue
            else:
                logger.warning(
                    f"Administrator {admin.id} ({admin.full_name}) has no messenger ID, skipping"
                )
                continue
            
            # Send notification via appropriate messenger
            if messenger_type == "telegram":
                success = await _send_telegram_notification(
                    messenger_id=messenger_id,
                    text=tg_notification_text
                )
            else:  # max
                # Get client's max_chat_id for the profile link test
                user_max_chat_id = None
                if user.max_user_id:
                    stmt_user_chat = select(MAX_Messenger_Data.max_chat_id).where(
                        MAX_Messenger_Data.max_user_id == user.max_user_id
                    )
                    result_user_chat = await session.execute(stmt_user_chat)
                    user_max_chat_id = result_user_chat.scalar_one_or_none()

                success = await _send_max_notification(
                    messenger_id=messenger_id,
                    text=notification_text,
                    phone_number=user.phone_number,
                    max_user_id=user.max_user_id,
                    max_chat_id=user_max_chat_id,
                    user_username=user.username,
                    user_full_name=user.full_name or user.first_name
                )
            
            if success:
                success_count += 1
                logger.info(
                    f"Low NPS notification sent to administrator: "
                    f"admin_id={admin.id}, admin_name={admin.full_name}, "
                    f"user_id={user.id}, rating={rating}, messenger={messenger_type}"
                )
            else:
                logger.warning(
                    f"Failed to send low NPS notification to administrator: "
                    f"admin_id={admin.id}, admin_name={admin.full_name}, "
                    f"user_id={user.id}, rating={rating}"
                )
        
        if success_count > 0:
            logger.info(
                f"Low NPS notifications sent successfully: "
                f"user_id={user.id}, rating={rating}, "
                f"sent_to={success_count}/{len(administrators)} administrators"
            )
            return True
        else:
            logger.error(
                f"Failed to send low NPS notification to any administrator: "
                f"user_id={user.id}, rating={rating}"
            )
            return False
        
    except Exception as e:
        logger.error(
            f"Error sending low NPS notification: user_id={user.id}, "
            f"rating={rating}, error={e}",
            exc_info=True
        )
        return False


async def _send_telegram_notification(
    messenger_id: int,
    text: str
) -> bool:
    """
    Send notification via Telegram bot.
    
    Args:
        messenger_id: Telegram user ID
        text: Notification text (HTML formatted)
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
        from constants import TG_BOT_TOKEN
        
        bot = Bot(
            token=TG_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode="HTML")
        )
        
        try:
            await bot.send_message(
                chat_id=messenger_id,
                text=text
            )
            return True
            
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logger.warning(
                f"Failed to send Telegram notification: messenger_id={messenger_id}, "
                f"error={e}"
            )
            return False
            
        finally:
            await bot.session.close()
            
    except Exception as e:
        logger.error(
            f"Error sending Telegram notification: messenger_id={messenger_id}, "
            f"error={e}",
            exc_info=True
        )
        return False


async def _send_max_notification(
    messenger_id: int,
    text: str,
    phone_number: str | None = None,
    max_user_id: int | None = None,
    max_chat_id: int | None = None,
    user_username: str | None = None,
    user_full_name: str | None = None
) -> bool:
    """
    Send notification via MAX bot, optionally with a contact attachment.
    
    If phone_number is provided, sends a contact card (VCF) as attachment
    so the admin can tap to call directly from the notification.
    
    Args:
        messenger_id: MAX chat ID of the admin
        text: Notification text (HTML formatted)
        phone_number: Optional client phone number for contact card
        max_user_id: Optional client MAX user ID
        max_chat_id: Optional client MAX chat ID
        user_username: Optional client username
        user_full_name: Optional client full name for contact card
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    try:
        from maxapi import Bot as MAXBot
        from maxapi.enums.parse_mode import ParseMode
        from maxapi.exceptions import MaxApiError
        from maxapi.types.attachments.attachment import Attachment, ContactAttachmentPayload
        from maxapi.enums.attachment import AttachmentType
        from constants import MAX_BOT_TOKEN
        
        bot = MAXBot(
            token=MAX_BOT_TOKEN,
            parse_mode=ParseMode.HTML
        )
        
        # Build contact attachment if phone number is available
        attachments = []
        if phone_number:
            name = user_full_name or "Клиент"
            vcf = f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL:{phone_number}\nEND:VCARD"
            contact_attachment = Attachment(
                type=AttachmentType.CONTACT,
                payload=ContactAttachmentPayload(vcf_info=vcf)
            )
            attachments = [contact_attachment]
        
        try:
            await bot.send_message(
                chat_id=messenger_id,
                text=text,
                attachments=attachments if attachments else None
            )
            return True
            
        except MaxApiError as e:
            logger.warning(
                f"Failed to send MAX notification: messenger_id={messenger_id}, "
                f"error={e}"
            )
            return False
            
        finally:
            await bot.session.close()
            
    except Exception as e:
        logger.error(
            f"Error sending MAX notification: messenger_id={messenger_id}, "
            f"error={e}",
            exc_info=True
        )
        return False
