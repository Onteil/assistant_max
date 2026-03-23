"""
Ticket Reassignment Webhook Handler

This module implements the webhook endpoint for receiving bulk ticket reassignment
requests from 1C CRM. Handles transferring multiple tickets from one staff member
to another in a single atomic operation.

Requirements: 7.1-7.10 - Bulk ticket reassignment
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.ticket_reassignment_schemas import (
    TicketReassignmentWebhookPayload,
    TicketReassignmentWebhookResponse,
)
from constants import get_session, WEBHOOK_API_KEY
from database.models import (
    Action_Log,
    ActionType,
    Staff_Member,
    Ticket,
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
        logger.warning("Ticket reassignment webhook request received without API key")
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


@router.post("/ticket_reassignment", response_model=TicketReassignmentWebhookResponse)
async def ticket_reassignment_webhook(
    payload: TicketReassignmentWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> TicketReassignmentWebhookResponse:
    """
    Handle bulk ticket reassignment webhook from 1C CRM.
    
    This endpoint receives bulk ticket reassignment requests from the CRM system.
    It transfers multiple tickets from one staff member to another in a single
    atomic transaction. All tickets must be currently assigned to the from_staff
    member, otherwise the entire operation is rolled back.
    
    Special feature: Pass ticket_ids=["all"] to reassign ALL tickets from from_staff
    to to_staff without specifying individual ticket IDs.
    
    Request body (specific tickets):
    {
        "from_staff_id": 123456789,
        "to_staff_id": 987654321,
        "ticket_ids": ["12345", "12346", "12347"],
        "messenger": "telegram",
        "reason": "Workload rebalancing"
    }
    
    Request body (all tickets):
    {
        "from_staff_id": 123456789,
        "to_staff_id": 987654321,
        "ticket_ids": ["all"],
        "messenger": "telegram",
        "reason": "Employee departure"
    }
    
    Response:
    {
        "status": "success",
        "message": "Tickets reassigned successfully",
        "from_staff_id": 123456789,
        "to_staff_id": 987654321,
        "tickets_reassigned": 3
    }
    
    Args:
        payload: Ticket reassignment payload
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with reassignment status
        
    Raises:
        HTTPException: 404 if staff member or ticket not found
        HTTPException: 400 if ticket not assigned to from_staff
        HTTPException: 500 if database transaction fails
        
    Requirements:
        - 7.1: Reassign all specified tickets from from_staff to to_staff
        - 7.2: Update Ticket.assigned_staff_id for each ticket
        - 7.3: Log reassignment action for each ticket
        - 7.4: Return success response with reassignment count
        - 7.5: Return 404 if from_staff not found
        - 7.6: Return 404 if to_staff not found
        - 7.7: Return 404 if any ticket not found
        - 7.8: Return 400 if ticket not assigned to from_staff
        - 7.9: Rollback all changes if transaction fails
        - 7.10: Return 401 if API key invalid
    """
    logger.info(
        f"Ticket reassignment webhook received: from_staff={payload.from_staff_id}, "
        f"to_staff={payload.to_staff_id}, ticket_count={len(payload.ticket_ids)}, "
        f"messenger={payload.messenger}"
    )
    
    try:
        # Step 1: Query from_staff by messenger-specific ID
        if payload.messenger == "telegram":
            stmt_from = select(Staff_Member).where(
                Staff_Member.tg_user_id == payload.from_staff_id
            )
        elif payload.messenger == "max":
            stmt_from = select(Staff_Member).where(
                Staff_Member.max_user_id == payload.from_staff_id
            )
        else:
            # This should never happen due to Pydantic validation
            logger.error(f"Invalid messenger type: {payload.messenger}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid messenger type: {payload.messenger}",
            )
        
        result_from = await session.execute(stmt_from)
        from_staff = result_from.scalar_one_or_none()
        
        # Requirement 7.5: Return 404 if from_staff not found
        if not from_staff:
            logger.error(
                f"From staff member with {payload.messenger}_user_id={payload.from_staff_id} "
                f"not found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"From staff member with {payload.messenger.upper()} ID "
                       f"{payload.from_staff_id} not found",
            )
        
        # Step 2: Query to_staff by messenger-specific ID
        if payload.messenger == "telegram":
            stmt_to = select(Staff_Member).where(
                Staff_Member.tg_user_id == payload.to_staff_id
            )
        else:
            stmt_to = select(Staff_Member).where(
                Staff_Member.max_user_id == payload.to_staff_id
            )
        
        result_to = await session.execute(stmt_to)
        to_staff = result_to.scalar_one_or_none()
        
        # Requirement 7.6: Return 404 if to_staff not found
        if not to_staff:
            logger.error(
                f"To staff member with {payload.messenger}_user_id={payload.to_staff_id} "
                f"not found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"To staff member with {payload.messenger.upper()} ID "
                       f"{payload.to_staff_id} not found",
            )
        
        # Step 3: Query tickets - either specific IDs or all tickets from from_staff
        tickets_reassigned = 0
        
        # Check if we should reassign all tickets
        if len(payload.ticket_ids) == 1 and payload.ticket_ids[0].lower() == "all":
            # Query all tickets assigned to from_staff
            stmt_all_tickets = select(Ticket).where(
                Ticket.assigned_staff_id == from_staff.id
            )
            result_all_tickets = await session.execute(stmt_all_tickets)
            tickets_to_reassign = result_all_tickets.scalars().all()
            
            logger.info(
                f"Reassigning all tickets from staff {from_staff.id}: "
                f"found {len(tickets_to_reassign)} tickets"
            )
            
            # Reassign each ticket
            for ticket in tickets_to_reassign:
                old_staff_id = ticket.assigned_staff_id
                ticket.assigned_staff_id = to_staff.id
                tickets_reassigned += 1
                
                # Requirement 7.3: Log reassignment action for each ticket
                action_log = Action_Log(
                    action_type=ActionType.TICKET_ASSIGNED,
                    ticket_id=ticket.id,
                    user_id=ticket.user_id,
                    staff_id=to_staff.id,
                    action_details={
                        "action": "ticket_reassigned_via_webhook",
                        "old_staff_id": old_staff_id,
                        "new_staff_id": to_staff.id,
                        "from_staff_messenger_id": payload.from_staff_id,
                        "to_staff_messenger_id": payload.to_staff_id,
                        "messenger": payload.messenger,
                        "reason": payload.reason,
                        "reassign_all": True,
                    },
                    action_timestamp=datetime.now()
                )
                session.add(action_log)
        else:
            # Reassign specific tickets by ID
            for ticket_id_str in payload.ticket_ids:
                # Convert ticket_id to integer
                try:
                    ticket_id_int = int(ticket_id_str)
                except ValueError:
                    logger.error(f"Invalid ticket_id format: {ticket_id_str}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid ticket_id format: {ticket_id_str}",
                    )
                
                # Query ticket
                stmt_ticket = select(Ticket).where(Ticket.id == ticket_id_int)
                result_ticket = await session.execute(stmt_ticket)
                ticket = result_ticket.scalar_one_or_none()
                
                # Requirement 7.7: Return 404 if ticket not found
                if not ticket:
                    logger.error(f"Ticket with id={ticket_id_str} not found")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Ticket with ID {ticket_id_str} not found",
                    )
                
                # Requirement 7.8: Validate ticket is assigned to from_staff
                if ticket.assigned_staff_id != from_staff.id:
                    logger.error(
                        f"Ticket {ticket_id_str} is not assigned to from_staff {from_staff.id}, "
                        f"currently assigned to {ticket.assigned_staff_id}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Ticket {ticket_id_str} is not assigned to from_staff "
                               f"{payload.from_staff_id}",
                    )
                
                # Requirement 7.1, 7.2: Reassign ticket to to_staff
                old_staff_id = ticket.assigned_staff_id
                ticket.assigned_staff_id = to_staff.id
                tickets_reassigned += 1
                
                # Requirement 7.3: Log reassignment action for each ticket
                action_log = Action_Log(
                    action_type=ActionType.TICKET_ASSIGNED,
                    ticket_id=ticket.id,
                    user_id=ticket.user_id,
                    staff_id=to_staff.id,
                    action_details={
                        "action": "ticket_reassigned_via_webhook",
                        "old_staff_id": old_staff_id,
                        "new_staff_id": to_staff.id,
                        "from_staff_messenger_id": payload.from_staff_id,
                        "to_staff_messenger_id": payload.to_staff_id,
                        "messenger": payload.messenger,
                        "reason": payload.reason,
                    },
                    action_timestamp=datetime.now()
                )
                session.add(action_log)
        
        # Requirement 7.9: Commit all changes atomically
        await session.commit()
        
        logger.info(
            f"Ticket reassignment webhook processed successfully: "
            f"from_staff={from_staff.id}, to_staff={to_staff.id}, "
            f"tickets_reassigned={tickets_reassigned}"
        )
        
        # Requirement 7.4: Return success response with reassignment count
        return TicketReassignmentWebhookResponse(
            status="success",
            message="Tickets reassigned successfully",
            from_staff_id=payload.from_staff_id,
            to_staff_id=payload.to_staff_id,
            tickets_reassigned=tickets_reassigned
        )
        
    except HTTPException as http_exc:
        # Notify admins about HTTP errors
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = f"HTTP {http_exc.status_code}"
            error_details = http_exc.detail
            payload_summary = f"messenger={payload.messenger}, from_staff={payload.from_staff_id}, to_staff={payload.to_staff_id}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="ticket_reassignment",
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
            payload_summary = f"messenger={payload.messenger}, from_staff={payload.from_staff_id}, to_staff={payload.to_staff_id}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="ticket_reassignment",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        # Requirement 7.9: Rollback on failure (Requirement 18.1, 18.6, 18.9)
        logger.error(
            f"Error processing ticket reassignment webhook: {e}",
            exc_info=True
        )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )
