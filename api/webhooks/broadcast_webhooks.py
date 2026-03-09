"""
Broadcast Campaign Webhook Handler

This module implements the webhook endpoint for receiving broadcast campaign
requests from 1C CRM. When the CRM wants to send a mass message to users,
it sends a request to this endpoint with targeting criteria and message content.

Requirements: 6.1-6.15 - Broadcast campaign management webhook
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.broadcast_schemas import (
    BroadcastWebhookPayload,
    BroadcastWebhookResponse,
)
from constants import get_session, WEBHOOK_API_KEY
from database.models import (
    Action_Log,
    ActionType,
    Broadcast,
    BroadcastStatus,
    Broadcast_Delivery,
    DeliveryStatus,
    Staff_Member,
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
        logger.warning("Broadcast webhook request received without API key")
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


@router.post("/broadcast_campaign", response_model=BroadcastWebhookResponse)
async def broadcast_campaign_webhook(
    payload: BroadcastWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> BroadcastWebhookResponse:
    """
    Handle broadcast campaign webhook from 1C CRM.
    
    This endpoint receives broadcast campaign requests from the CRM system.
    It calculates target users based on audience type, creates broadcast
    and delivery records, and schedules a Celery task for message delivery.
    
    Request body (all users):
    {
        "campaign_id": "promo_2026_q1",
        "message_text": "Новая версия ГРАНД-Смета доступна!",
        "target_audience": "all_users",
        "schedule_time": "2026-03-01T10:00:00",
        "messenger": "telegram"
    }
    
    Request body (subscribed users):
    {
        "campaign_id": "renewal_reminder_march",
        "message_text": "Ваша подписка истекает через 30 дней",
        "target_audience": "subscribed_users",
        "schedule_time": "2026-03-01T09:00:00",
        "messenger": "max"
    }
    
    Request body (users with notifications allowed):
    {
        "campaign_id": "news_update_q1",
        "message_text": "Новости и обновления",
        "target_audience": "allow_notification_users",
        "schedule_time": "2026-03-01T12:00:00",
        "messenger": "telegram"
    }
    
    Response:
    {
        "status": "success",
        "message": "Broadcast campaign scheduled successfully",
        "campaign_id": "promo_2026_q1",
        "target_count": 1523,
        "schedule_time": "2026-03-01T10:00:00"
    }
    
    Args:
        payload: Broadcast campaign payload
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with campaign status
        
    Raises:
        HTTPException: 400 if campaign_id already exists
        HTTPException: 500 if Celery task scheduling fails
        
    Requirements:
        - 6.1: Create Broadcast record with status=SCHEDULED
        - 6.2: Select all users when target_audience="all_users"
        - 6.3: Filter by active subscription when target_audience="subscribed_users"
        - 6.5: Filter by notification consent when target_audience="allow_notification_users"
        - 6.9: Create Broadcast_Delivery record for each target user
        - 6.10: Schedule Celery task for delivery
        - 6.11: Log action in Action_Log
        - 6.12: Return 400 if campaign_id already exists
        - 6.14: Return 500 if Celery task fails
        - 6.15: Return 401 if API key invalid
    """
    logger.info(
        f"Broadcast campaign webhook received: campaign_id={payload.campaign_id}, "
        f"target_audience={payload.target_audience}, messenger={payload.messenger}, "
        f"send_now={payload.send_now}"
    )
    
    try:
        # Step 1: Find staff member by messenger ID
        if payload.messenger == "telegram":
            stmt_staff = select(Staff_Member).where(
                Staff_Member.tg_user_id == payload.manager_messenger_id
            )
        else:  # max
            stmt_staff = select(Staff_Member).where(
                Staff_Member.max_user_id == payload.manager_messenger_id
            )
        
        result_staff = await session.execute(stmt_staff)
        staff_member = result_staff.scalar_one_or_none()
        
        if not staff_member:
            logger.error(
                f"Staff member not found: messenger={payload.messenger}, "
                f"messenger_id={payload.manager_messenger_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Staff member with {payload.messenger} ID {payload.manager_messenger_id} not found",
            )
        
        # Step 2: Check if campaign_id already exists (Requirement 6.12)
        # Note: We'll store campaign_id in action_details for tracking
        # The database uses auto-increment ID, so we check by querying all broadcasts
        # and looking for matching campaign_id in action logs
        stmt = select(Action_Log).where(
            and_(
                Action_Log.action_type == ActionType.BROADCAST_SENT,
                Action_Log.action_details["campaign_id"].astext == payload.campaign_id
            )
        )
        result = await session.execute(stmt)
        existing_campaign = result.scalar_one_or_none()
        
        if existing_campaign:
            logger.error(f"Duplicate campaign_id: {payload.campaign_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Campaign with ID '{payload.campaign_id}' already exists",
            )
        
        # Step 2: Calculate target users based on target_audience
        target_users = await _calculate_target_users(
            session=session,
            target_audience=payload.target_audience,
            filters=None,  # Not used anymore
            messenger=payload.messenger
        )
        
        target_count = len(target_users)
        
        logger.info(
            f"Calculated target users: campaign_id={payload.campaign_id}, "
            f"target_count={target_count}"
        )
        
        # Step 3: Create Broadcast record (Requirement 6.1)
        broadcast = Broadcast(
            # id will be auto-generated
            created_by_staff_id=staff_member.id,
            message_text=payload.message_text,
            broadcast_status=BroadcastStatus.DRAFT,  # Will be updated to SENDING by Celery task
            target_user_count=target_count,
            delivered_count=0,
            created_at=datetime.now(),
            sent_at=None
        )
        session.add(broadcast)
        await session.flush()  # Flush to get broadcast.id for deliveries
        
        # Step 4: Create Broadcast_Delivery records (Requirement 6.9)
        delivery_records = []
        for user in target_users:
            delivery = Broadcast_Delivery(
                broadcast_id=broadcast.id,
                user_id=user.id,
                delivery_status=DeliveryStatus.PENDING,
                delivered_at=None,
                error_message=None
            )
            delivery_records.append(delivery)
        
        if delivery_records:
            session.add_all(delivery_records)
        
        await session.commit()
        
        logger.info(
            f"Created broadcast and delivery records: campaign_id={payload.campaign_id}, "
            f"delivery_count={len(delivery_records)}"
        )
        
        # Step 5: Schedule Celery task for delivery (Requirement 6.10)
        try:
            from celery_app.broadcast_tasks import send_broadcast_campaign
            
            # Schedule task with eta (execution time) or immediately
            if payload.send_now:
                # Send immediately
                task = send_broadcast_campaign.apply_async(
                    args=[broadcast.id, payload.messenger],
                    queue="broadcasts"
                )
                logger.info(
                    f"Scheduled immediate broadcast task: campaign_id={payload.campaign_id}, "
                    f"task_id={task.id}"
                )
            else:
                # Schedule for later
                task = send_broadcast_campaign.apply_async(
                    args=[broadcast.id, payload.messenger],
                    eta=payload.schedule_time,
                    queue="broadcasts"
                )
                logger.info(
                    f"Scheduled broadcast task: campaign_id={payload.campaign_id}, "
                    f"task_id={task.id}, eta={payload.schedule_time}"
                )
            
        except Exception as e:
            # Requirement 6.14: Return 500 if Celery task fails
            logger.error(
                f"Failed to schedule Celery task: campaign_id={payload.campaign_id}, "
                f"error={e}",
                exc_info=True
            )
            
            # Update broadcast status to FAILED
            broadcast.broadcast_status = BroadcastStatus.FAILED
            await session.commit()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to schedule broadcast task: {str(e)}",
            )
        
        # Step 6: Log action in Action_Log (Requirement 6.11)
        action_log = Action_Log(
            action_type=ActionType.BROADCAST_SENT,
            user_id=None,
            staff_id=None,  # TODO: Get from payload
            action_details={
                "action": "broadcast_campaign_scheduled",
                "campaign_id": payload.campaign_id,
                "target_audience": payload.target_audience,
                "target_count": target_count,
                "schedule_time": payload.schedule_time.isoformat(),
                "messenger": payload.messenger,
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Broadcast campaign webhook processed successfully: "
            f"campaign_id={payload.campaign_id}"
        )
        
        return BroadcastWebhookResponse(
            status="success",
            message="Broadcast campaign scheduled successfully",
            campaign_id=payload.campaign_id,
            target_count=target_count,
            schedule_time=payload.schedule_time
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (400, 500, etc.)
        raise
        
    except Exception as e:
        # Unexpected error (Requirement 18.6, 18.9)
        logger.error(
            f"Error processing broadcast campaign webhook: {e}",
            exc_info=True
        )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )


async def _calculate_target_users(
    session: AsyncSession,
    target_audience: str,
    filters: any,
    messenger: str
) -> list[User]:
    """
    Calculate target users based on audience type.
    
    This helper function implements the audience targeting logic:
    - "all_users": All users with messenger ID
    - "subscribed_users": Users with active subscriptions
    - "allow_notification_users": Users who allowed notifications
    
    Args:
        session: Database session
        target_audience: Audience type ("all_users", "subscribed_users", "allow_notification_users")
        filters: Not used anymore (kept for backward compatibility)
        messenger: Messenger platform ("telegram" or "max")
        
    Returns:
        List of User objects matching criteria
        
    Requirements:
        - 6.2: Select all users when target_audience="all_users"
        - 6.3: Filter by active subscription when target_audience="subscribed_users"
        - 6.5: Filter by notification consent when target_audience="allow_notification_users"
    """
    # Base query: Select users with messenger ID
    if messenger == "telegram":
        base_stmt = select(User).where(User.tg_user_id.isnot(None))
    elif messenger == "max":
        base_stmt = select(User).where(User.max_user_id.isnot(None))
    else:
        # This should never happen due to Pydantic validation
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid messenger type: {messenger}",
        )
    
    # Requirement 6.2: All users
    if target_audience == "all_users":
        # Select all users with messenger ID (already in base query)
        stmt = base_stmt
    
    # Requirement 6.3: Subscribed users
    elif target_audience == "subscribed_users":
        stmt = base_stmt.where(
            User.subscription_status == SubscriptionStatus.ACTIVE
        )
    
    # Requirement 6.5: Users who allowed notifications
    elif target_audience == "allow_notification_users":
        stmt = base_stmt.where(
            User.notification_preferences == True
        )
    
    else:
        # This should never happen due to Pydantic validation
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid target_audience: {target_audience}",
        )
    
    # Execute query
    result = await session.execute(stmt)
    users = result.scalars().all()
    
    return list(users)
