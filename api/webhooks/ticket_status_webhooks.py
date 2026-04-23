"""
Ticket Status Update Webhook Handler

This module implements the webhook endpoint for receiving ticket status updates
from 1C CRM. Synchronizes ticket status changes from CRM to bot and notifies
users via messenger.

Requirements: 4.1-4.9 - Ticket status synchronization
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.ticket_status_schemas import (
    TicketStatusWebhookPayload,
    TicketStatusWebhookResponse,
)
from constants import get_session, WEBHOOK_API_KEY
from database.models import (
    Action_Log,
    ActionType,
    Staff_Member,
    Ticket,
    TicketStatus,
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
        logger.warning("Ticket status webhook request received without API key")
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


@router.post("/ticket_status_update", response_model=TicketStatusWebhookResponse)
async def ticket_status_update_webhook(
    payload: TicketStatusWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> TicketStatusWebhookResponse:
    """
    Handle ticket status update webhook from 1C CRM.
    
    This endpoint receives ticket status updates from the CRM system and
    synchronizes them to the bot database. When a ticket is closed, it sets
    the closed_at timestamp and closed_by_staff_id. Users are notified of
    status changes via messenger.
    
    Request body:
    {
        "ticket_id": "12345",
        "status": "closed",
        "closed_by_staff_id": 123456789,
        "messenger": "telegram"
    }
    
    Response:
    {
        "status": "success",
        "message": "Ticket status updated successfully",
        "ticket_id": "12345",
        "new_status": "closed"
    }
    
    Args:
        payload: Ticket status update payload
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with update status
        
    Raises:
        HTTPException: 404 if ticket not found
        HTTPException: 400 if status="closed" without closed_by_staff_id
        HTTPException: 500 if internal error occurs
        
    Requirements:
        - 4.1: Update Ticket.status to new status
        - 4.2: Set Ticket.closed_at when status="closed"
        - 4.3: Set Ticket.closed_by_staff_id when status="closed"
        - 4.4: Send notification to user via messenger
        - 4.5: Log status change in Action_Log
        - 4.6: Return 404 if ticket not found
        - 4.7: Return 400 if status="closed" without closed_by_staff_id
        - 4.8: Log warning if notification fails
        - 4.9: Return 401 if API key invalid
    """
    logger.info(
        f"Ticket status update webhook received: ticket_id={payload.ticket_id}, "
        f"status={payload.status}, messenger={payload.messenger}, "
        f"closed_by_staff_id={payload.closed_by_staff_id}"
    )
    logger.debug(f"Full webhook payload: {payload.model_dump()}")
    
    try:
        # Step 1: Query ticket by ticket_id with eager loading of user relationship
        # Convert ticket_id to integer if it's numeric
        try:
            ticket_id_int = int(payload.ticket_id)
            from sqlalchemy.orm import selectinload
            stmt = select(Ticket).options(selectinload(Ticket.user)).where(Ticket.id == ticket_id_int)
        except ValueError:
            # If ticket_id is not numeric, treat as string (shouldn't happen with current schema)
            logger.error(f"Invalid ticket_id format: {payload.ticket_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid ticket_id format: {payload.ticket_id}",
            )
        
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        # Requirement 4.6: Return 404 if ticket not found
        if not ticket:
            logger.error(f"Ticket with id={payload.ticket_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket with ID {payload.ticket_id} not found",
            )
        
        # Map string status to TicketStatus enum
        # Supports both English keys and Russian values sent by 1C CRM triggers
        status_mapping = {
            # English keys (our internal format)
            "new": TicketStatus.NEW,
            "in_progress": TicketStatus.IN_PROGRESS,
            "waiting_client": TicketStatus.WAITING_CLIENT,
            "closed": TicketStatus.CLOSED,
            "cancelled": TicketStatus.CANCELLED,
            # Russian values from 1C CRM (ай_СтатусыОбращений enum)
            "новое": TicketStatus.NEW,
            "в работе": TicketStatus.IN_PROGRESS,
            "ожидание клиента": TicketStatus.WAITING_CLIENT,
            "закрыто": TicketStatus.CLOSED,
            "отменено": TicketStatus.CANCELLED,
        }
        
        new_status_enum = status_mapping.get(payload.status.lower())
        if not new_status_enum:
            logger.error(f"Invalid status value: {payload.status}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {payload.status}. Expected one of: new, in_progress, waiting_client, closed, cancelled (or Russian equivalents: Новое, В работе, Ожидание клиента, Закрыто, Отменено)",
            )
        
        old_status = ticket.ticket_status
        
        # Idempotency: skip update if status already matches (CRM trigger race condition)
        if old_status == new_status_enum:
            logger.info(
                f"Ticket {payload.ticket_id} already has status={new_status_enum.value}, "
                f"skipping update (likely CRM trigger echo)"
            )
            return TicketStatusWebhookResponse(
                status="success",
                message="Ticket status already up to date",
                ticket_id=payload.ticket_id,
                new_status=payload.status
            )
        
        # Requirement 4.1: Update Ticket.status to new status
        ticket.ticket_status = new_status_enum
        
        # Requirement 4.2, 4.3: Handle ticket closure
        if new_status_enum == TicketStatus.CLOSED:
            # Requirement 4.7: Validate closed_by_staff_id provided
            if not payload.closed_by_staff_id:
                logger.error(
                    f"Cannot close ticket {payload.ticket_id} without closed_by_staff_id"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="closed_by_staff_id is required when status='closed'",
                )
            
            # Requirement 4.2: Set closed_at timestamp
            ticket.closed_at = datetime.now()
            
            # Requirement 4.3: Set closed_by_staff_id
            # Query staff member by messenger-specific ID
            if payload.messenger == "telegram":
                stmt_staff = select(Staff_Member).where(
                    Staff_Member.tg_user_id == payload.closed_by_staff_id
                )
            else:
                stmt_staff = select(Staff_Member).where(
                    Staff_Member.max_user_id == payload.closed_by_staff_id
                )
            
            result_staff = await session.execute(stmt_staff)
            staff = result_staff.scalar_one_or_none()
            
            if staff:
                ticket.closed_by_staff_id = staff.id
            else:
                logger.warning(
                    f"Staff member with {payload.messenger}_user_id="
                    f"{payload.closed_by_staff_id} not found, setting closed_by_staff_id to None"
                )
                ticket.closed_by_staff_id = None
        
        # Commit database changes
        await session.commit()
        
        # Requirement 4.4: Send notification to user via messenger
        # Get user's messenger-specific ID
        user = ticket.user
        
        # For MAX messenger, check if chat_id exists in max_messenger_data
        if payload.messenger == "max":
            from api.utils.messenger_utils import get_max_chat_id
            user_messenger_id = await get_max_chat_id(session, user.id)
        else:
            user_messenger_id = user.tg_user_id
        
        if user_messenger_id and new_status_enum in (TicketStatus.CLOSED, TicketStatus.CANCELLED):
            # Build notification text for closed/cancelled statuses only
            if new_status_enum == TicketStatus.CLOSED:
                if payload.messenger == "telegram":
                    from bots.tg_bot.texts import SUPPORT_TICKET_CLOSED
                else:
                    from bots.max_bot.texts import SUPPORT_TICKET_CLOSED
                comment = ticket.resolution_comment or "Не указан"
                notification_text = SUPPORT_TICKET_CLOSED.format(
                    ticket_id=payload.ticket_id,
                    comment=comment,
                )
            else:  # CANCELLED
                if payload.messenger == "telegram":
                    from bots.tg_bot.texts import SUPPORT_TICKET_CANCELLED
                else:
                    from bots.max_bot.texts import SUPPORT_TICKET_CANCELLED
                notification_text = SUPPORT_TICKET_CANCELLED.format(
                    ticket_id=payload.ticket_id,
                )

            try:
                from api.utils.messenger_utils import send_message_to_user
                result = await send_message_to_user(
                    messenger=payload.messenger,
                    user_id=user.id,
                    text=notification_text,
                    session=session,
                    parse_mode="HTML",
                )
                if result["success"]:
                    logger.info(
                        f"Ticket {new_status_enum.value} notification sent to "
                        f"{payload.messenger} user {user.id}"
                    )
                else:
                    logger.warning(
                        f"Failed to send ticket notification to user {user.id}: {result['message']}"
                    )
            except Exception as e:
                # Requirement 4.8: Log warning if notification fails, but continue
                logger.warning(
                    f"Failed to send notification to user {user.id}: {e}",
                    exc_info=True
                )
        elif not user_messenger_id:
            logger.warning(
                f"User {user.id} has no MAX chat_id in max_messenger_data, cannot send notification"
                if payload.messenger == "max"
                else f"User {user.id} has no telegram user ID, cannot send notification"
            )
        
        # Requirement 4.5: Log status change in Action_Log
        action_log = Action_Log(
            action_type=ActionType.STATUS_CHANGED,
            ticket_id=ticket.id,
            user_id=ticket.user_id,
            staff_id=ticket.closed_by_staff_id if new_status_enum == TicketStatus.CLOSED else None,
            action_details={
                "action": "ticket_status_updated_via_webhook",
                "old_status": old_status.value if old_status else None,
                "new_status": new_status_enum.value,
                "messenger": payload.messenger,
                "closed_by_staff_messenger_id": payload.closed_by_staff_id if new_status_enum == TicketStatus.CLOSED else None,
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        logger.info(
            f"Ticket status update webhook processed successfully: ticket_id={payload.ticket_id}, "
            f"old_status={old_status.value if old_status else None}, new_status={new_status_enum.value}"
        )
        
        return TicketStatusWebhookResponse(
            status="success",
            message="Ticket status updated successfully",
            ticket_id=payload.ticket_id,
            new_status=payload.status
        )
        
    except HTTPException as http_exc:
        # Notify admins about HTTP errors
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = f"HTTP {http_exc.status_code}"
            error_details = http_exc.detail
            payload_summary = f"ticket_id={payload.ticket_id}, status={payload.status}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="ticket_status",
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
            payload_summary = f"ticket_id={payload.ticket_id}, status={payload.status}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="ticket_status",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        # Unexpected error (Requirement 18.6, 18.9)
        logger.error(
            f"Error processing ticket status update webhook: {e}",
            exc_info=True
        )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )
