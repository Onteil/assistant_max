"""
Ticket History API Endpoint

This module implements the API endpoint for retrieving complete ticket history
including all messages, status changes, and staff assignments. This endpoint is
used by the CRM system to query ticket data from the bot.

Requirements: 8.1-8.10 - Ticket history query API
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.schemas.ticket_history_schemas import (
    AssignmentDTO,
    MessageDTO,
    StatusChangeDTO,
    TicketHistoryResponse,
)
from constants import get_session, WEBHOOK_API_KEY
from database.models import (
    Action_Log,
    ActionType,
    File_Attachment,
    Message,
    SenderType,
    Staff_Member,
    Ticket,
    User,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def verify_webhook_api_key(
    x_api_key: Annotated[str | None, Header()] = None
) -> str:
    """
    Verify webhook API key authentication.
    
    This dependency validates that incoming API requests include a valid
    API key in the X-API-Key header.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        Validated API key
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
        
    Requirements: 8.10 - API authentication
    """
    if not x_api_key:
        logger.warning("Ticket history API request received without API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    if not WEBHOOK_API_KEY:
        logger.error("WEBHOOK_API_KEY not configured in environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured on server",
        )
    
    if x_api_key != WEBHOOK_API_KEY:
        logger.warning(f"Invalid API key attempt: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return x_api_key


@router.get("/tickets/{ticket_id}/history", response_model=TicketHistoryResponse)
async def get_ticket_history(
    ticket_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> TicketHistoryResponse:
    """
    Retrieve complete ticket history including messages, status changes, and assignments.
    
    This endpoint returns all historical data for a ticket, including:
    - All messages exchanged between user and staff
    - All status changes with timestamps and staff who made changes
    - All staff assignments with timestamps and assignment reasons
    - Ticket metadata (type, status, timestamps)
    
    Example request:
    GET /api/tickets/123/history
    Headers:
        X-API-Key: your-api-key-here
    
    Example response:
    {
        "ticket_id": "123",
        "ticket_type": "support",
        "current_status": "closed",
        "created_at": "2024-01-15T10:30:00",
        "updated_at": "2024-01-16T14:20:00",
        "closed_at": "2024-01-16T14:20:00",
        "messages": [
            {
                "message_id": 1,
                "sender_type": "user",
                "sender_id": 123456,
                "sender_name": "John Doe",
                "message_text": "I need help with...",
                "created_at": "2024-01-15T10:30:00",
                "attachments": ["https://example.com/file1.pdf"]
            }
        ],
        "status_changes": [
            {
                "change_id": 1,
                "old_status": "new",
                "new_status": "in_progress",
                "changed_by_staff_id": 789,
                "changed_by_staff_name": "Support Agent",
                "changed_at": "2024-01-15T11:00:00",
                "reason": "Started working on ticket"
            }
        ],
        "assignments": [
            {
                "assignment_id": 1,
                "assigned_to_staff_id": 789,
                "assigned_to_staff_name": "Support Agent",
                "assigned_by_staff_id": null,
                "assigned_by_staff_name": null,
                "assigned_at": "2024-01-15T10:35:00",
                "assignment_type": "initial",
                "reason": "Auto-assigned"
            }
        ]
    }
    
    Args:
        ticket_id: Unique ticket identifier
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        Complete ticket history with all messages, status changes, and assignments
        
    Raises:
        HTTPException: 404 if ticket not found
        HTTPException: 500 if database query fails
        
    Requirements:
        - 8.1: Return complete ticket history
        - 8.2: Include all messages ordered by timestamp ascending
        - 8.3: Include sender type, sender ID, and sender name for each message
        - 8.4: Include all file attachments for each message
        - 8.5: Include all status changes with timestamps and staff
        - 8.6: Include all staff assignments with timestamps
        - 8.7: Include ticket metadata
        - 8.8: Return 404 if ticket not found
        - 8.9: Return 500 if database query fails
        - 8.10: Require API key authentication
    """
    logger.info(f"Ticket history API request received for ticket_id={ticket_id}")
    
    try:
        # Step 1: Query Ticket by ticket_id with eager loading (Requirement 8.1, 8.7)
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.user),
                selectinload(Ticket.assigned_staff),
                selectinload(Ticket.messages).selectinload(Message.file_attachments),
            )
        )
        
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        # Requirement 8.8: Return 404 if ticket not found
        if not ticket:
            logger.error(f"Ticket with id={ticket_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket with ID {ticket_id} not found",
            )
        
        # Step 2: Query all Messages for ticket ordered by created_at ascending (Requirement 8.2)
        messages_stmt = (
            select(Message)
            .where(Message.ticket_id == ticket_id)
            .order_by(Message.sent_at.asc())
            .options(selectinload(Message.file_attachments))
        )
        
        messages_result = await session.execute(messages_stmt)
        messages = messages_result.scalars().all()
        
        # Step 3: Build MessageDTO list with sender info and attachments (Requirements 8.3, 8.4)
        message_dtos = []
        
        for msg in messages:
            # Determine sender name based on sender type
            sender_name = "Unknown"
            
            if msg.sender_type == SenderType.USER:
                # Query user by sender_id
                user_stmt = select(User).where(User.id == msg.sender_id)
                user_result = await session.execute(user_stmt)
                user = user_result.scalar_one_or_none()
                
                if user:
                    sender_name = user.full_name or user.first_name or user.username or f"User {user.id}"
                else:
                    sender_name = f"User {msg.sender_id}"
                    
            elif msg.sender_type == SenderType.STAFF:
                # Query staff by sender_id
                staff_stmt = select(Staff_Member).where(Staff_Member.id == msg.sender_id)
                staff_result = await session.execute(staff_stmt)
                staff = staff_result.scalar_one_or_none()
                
                if staff:
                    sender_name = staff.full_name
                else:
                    sender_name = f"Staff {msg.sender_id}"
            
            # Build attachments list (file URLs or identifiers)
            attachments = []
            if msg.file_attachments:
                for attachment in msg.file_attachments:
                    # Use telegram_file_id as the attachment reference
                    # In production, this could be converted to a download URL
                    attachments.append(attachment.telegram_file_id)
            
            message_dto = MessageDTO(
                message_id=msg.id,
                sender_type=msg.sender_type.value,
                sender_id=msg.sender_id or 0,
                sender_name=sender_name,
                message_text=msg.message_text,
                created_at=msg.sent_at,
                attachments=attachments,
            )
            message_dtos.append(message_dto)
        
        # Step 4: Query all status changes from Action_Log (Requirement 8.5)
        status_changes_stmt = (
            select(Action_Log)
            .where(
                Action_Log.ticket_id == ticket_id,
                Action_Log.action_type == ActionType.STATUS_CHANGED
            )
            .order_by(Action_Log.action_timestamp.asc())
        )
        
        status_changes_result = await session.execute(status_changes_stmt)
        status_changes = status_changes_result.scalars().all()
        
        # Step 5: Build StatusChangeDTO list with staff info (Requirement 8.5)
        status_change_dtos = []
        
        for change in status_changes:
            # Query staff member who made the change
            staff_name = "System"
            
            if change.staff_id:
                staff_stmt = select(Staff_Member).where(Staff_Member.id == change.staff_id)
                staff_result = await session.execute(staff_stmt)
                staff = staff_result.scalar_one_or_none()
                
                if staff:
                    staff_name = staff.full_name
                else:
                    staff_name = f"Staff {change.staff_id}"
            
            # Extract old_status and new_status from action_details
            action_details = change.action_details or {}
            old_status = action_details.get("old_status", "unknown")
            new_status = action_details.get("new_status", "unknown")
            reason = action_details.get("reason")
            
            status_change_dto = StatusChangeDTO(
                change_id=change.id,
                old_status=old_status,
                new_status=new_status,
                changed_by_staff_id=change.staff_id or 0,
                changed_by_staff_name=staff_name,
                changed_at=change.action_timestamp,
                reason=reason,
            )
            status_change_dtos.append(status_change_dto)
        
        # Step 6: Query all assignments from Action_Log (Requirement 8.6)
        assignments_stmt = (
            select(Action_Log)
            .where(
                Action_Log.ticket_id == ticket_id,
                Action_Log.action_type.in_([
                    ActionType.TICKET_ASSIGNED,
                    ActionType.TICKET_ESCALATED
                ])
            )
            .order_by(Action_Log.action_timestamp.asc())
        )
        
        assignments_result = await session.execute(assignments_stmt)
        assignments = assignments_result.scalars().all()
        
        # Step 7: Build AssignmentDTO list with staff info (Requirement 8.6)
        assignment_dtos = []
        
        for assignment in assignments:
            action_details = assignment.action_details or {}
            
            # Get assigned_to staff info
            assigned_to_staff_id = action_details.get("assigned_to_staff_id")
            assigned_to_staff_name = "Unknown"
            
            if assigned_to_staff_id:
                staff_stmt = select(Staff_Member).where(Staff_Member.id == assigned_to_staff_id)
                staff_result = await session.execute(staff_stmt)
                staff = staff_result.scalar_one_or_none()
                
                if staff:
                    assigned_to_staff_name = staff.full_name
                else:
                    assigned_to_staff_name = f"Staff {assigned_to_staff_id}"
            
            # Get assigned_by staff info (may be null for auto-assignments)
            assigned_by_staff_id = action_details.get("assigned_by_staff_id") or assignment.staff_id
            assigned_by_staff_name = None
            
            if assigned_by_staff_id:
                staff_stmt = select(Staff_Member).where(Staff_Member.id == assigned_by_staff_id)
                staff_result = await session.execute(staff_stmt)
                staff = staff_result.scalar_one_or_none()
                
                if staff:
                    assigned_by_staff_name = staff.full_name
                else:
                    assigned_by_staff_name = f"Staff {assigned_by_staff_id}"
            
            # Determine assignment type
            assignment_type = "initial" if assignment.action_type == ActionType.TICKET_ASSIGNED else "escalation"
            if action_details.get("is_escalation"):
                assignment_type = "escalation"
            
            assignment_dto = AssignmentDTO(
                assignment_id=assignment.id,
                assigned_to_staff_id=assigned_to_staff_id or 0,
                assigned_to_staff_name=assigned_to_staff_name,
                assigned_by_staff_id=assigned_by_staff_id,
                assigned_by_staff_name=assigned_by_staff_name,
                assigned_at=assignment.action_timestamp,
                assignment_type=assignment_type,
                reason=action_details.get("reason"),
            )
            assignment_dtos.append(assignment_dto)
        
        # Step 8: Return TicketHistoryResponse with all data (Requirement 8.1, 8.7)
        response = TicketHistoryResponse(
            ticket_id=str(ticket.id),
            ticket_type=ticket.ticket_type.value,
            current_status=ticket.ticket_status.value,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            closed_at=ticket.closed_at,
            messages=message_dtos,
            status_changes=status_change_dtos,
            assignments=assignment_dtos,
        )
        
        logger.info(
            f"Ticket history retrieved successfully: ticket_id={ticket_id}, "
            f"messages={len(message_dtos)}, status_changes={len(status_change_dtos)}, "
            f"assignments={len(assignment_dtos)}"
        )
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions (404, 401, etc.)
        raise
        
    except Exception as e:
        # Requirement 8.9: Return 500 if database query fails
        logger.error(
            f"Error retrieving ticket history for ticket_id={ticket_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )
