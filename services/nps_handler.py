"""
NPS Survey Response Handler Service

Handles user rating responses, CRM integration, and thank you messages.
Processes NPS survey responses and sends data to 1C CRM.

Requirements: 4.4, 4.5, 5.2, 5.3, 5.4, 5.5, 5.6, 11.5, 13.3
"""

import logging
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import NPS_Response, SurveyType, User
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
    return "🙏 Спасибо за ваш отзыв! Ваше мнение помогает нам становиться лучше."
