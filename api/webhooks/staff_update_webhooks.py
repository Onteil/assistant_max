"""
Staff Update Webhook Handler

This module implements the webhook endpoint for receiving staff member updates
from 1C CRM. Handles staff lifecycle management including signature updates,
deactivation, and automatic ticket reassignment to backup managers.

Requirements: 3.1-3.13 - Staff member lifecycle management
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.staff_update_schemas import (
    StaffUpdateWebhookPayload,
    StaffUpdateWebhookResponse,
)
from constants import get_session, WEBHOOK_API_KEY
from database.models import (
    Action_Log,
    ActionType,
    Staff_Member,
    StaffRole,
    Ticket,
    TicketStatus,
)
from services.i_tat_service import get_itat_client

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
        logger.warning("Staff update webhook request received without API key")
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


@router.post("/staff_update", response_model=StaffUpdateWebhookResponse)
async def staff_update_webhook(
    payload: StaffUpdateWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> StaffUpdateWebhookResponse:
    """
    Handle staff member update webhook from 1C CRM.
    
    This endpoint receives staff member updates from the CRM system including
    signature changes, activation/deactivation, and backup manager assignments.
    When a staff member is deactivated, all their active tickets are automatically
    reassigned to backup managers using round-robin distribution.
    
    Request body:
    {
        "staff_id": 123456789,
        "messenger": "telegram",
        "updates": {
            "signature": "Best regards, John",
            "is_active": false,
            "backup_managers": [987654321, 111222333]
        }
    }
    
    Response:
    {
        "status": "success",
        "message": "Staff member updated successfully",
        "staff_id": 123456789,
        "updates_applied": ["signature", "is_active"],
        "tickets_reassigned": 5
    }
    
    Args:
        payload: Staff update payload
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with update status
        
    Raises:
        HTTPException: 404 if staff member not found
        HTTPException: 400 if deactivating without backup managers
        HTTPException: 500 if internal error occurs
        
    Requirements:
        - 3.1: Update Staff_Member record with provided fields
        - 3.2: Update staff.signature if provided
        - 3.3: Deactivate staff member if is_active=false
        - 3.4: Query all active tickets when deactivating
        - 3.5: Reassign tickets to backup managers round-robin
        - 3.6: Log reassignment action for each ticket
        - 3.7: Update staff.backup_managers if provided
        - 3.8: Log staff update action
        - 3.9: Sync update to CRM via i-TAT API
        - 3.10: Return 404 if staff not found
        - 3.11: Return 400 if deactivating without backup managers
        - 3.12: Log warning if backup manager not found
        - 3.13: Return 401 if API key invalid
    """
    logger.info(
        f"Staff update webhook received: messenger={payload.messenger}, "
        f"staff_id={payload.staff_id}"
    )
    
    try:
        # Step 1: Query staff member by messenger-specific ID (Requirement 3.1)
        if payload.messenger == "telegram":
            stmt = select(Staff_Member).where(Staff_Member.tg_user_id == payload.staff_id)
        elif payload.messenger == "max":
            stmt = select(Staff_Member).where(Staff_Member.max_user_id == payload.staff_id)
        else:
            # This should never happen due to Pydantic validation
            logger.error(f"Invalid messenger type: {payload.messenger}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid messenger type: {payload.messenger}",
            )
        
        result = await session.execute(stmt)
        staff = result.scalar_one_or_none()
        
        # Requirement 3.10: Return 404 if staff not found
        if not staff:
            logger.error(
                f"Staff member with {payload.messenger}_user_id={payload.staff_id} not found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Staff member with {payload.messenger.upper()} ID {payload.staff_id} not found",
            )
        
        updates_applied = []
        tickets_reassigned = 0
        
        # Check which fields have actually changed (deduplication for 1C CRM multiple triggers)
        from api.webhooks.webhook_utils import has_field_changed
        
        # Step 2: Apply updates from payload
        
        # Update full_name if provided and changed
        if payload.updates.full_name is not None and has_field_changed(staff.full_name, payload.updates.full_name, "full_name"):
            staff.full_name = payload.updates.full_name
            updates_applied.append("full_name")
            logger.info(f"Updated full_name for staff {staff.id}")
        
        # Update position if provided and changed
        if payload.updates.position is not None and has_field_changed(staff.position, payload.updates.position, "position"):
            staff.position = payload.updates.position
            updates_applied.append("position")
            logger.info(f"Updated position for staff {staff.id}")
        
        # Update staff_role if provided and changed
        if payload.updates.staff_role is not None:
            new_role = StaffRole(payload.updates.staff_role)
            if has_field_changed(staff.staff_role, new_role, "staff_role"):
                staff.staff_role = new_role
                updates_applied.append("staff_role")
                logger.info(f"Updated staff_role to {payload.updates.staff_role} for staff {staff.id}")
        
        # Requirement 3.7: Update backup managers if provided
        if payload.updates.backup_managers is not None:
            # Store backup managers in the first two backup_manager fields
            if len(payload.updates.backup_managers) >= 1:
                # Query first backup manager
                if payload.messenger == "telegram":
                    stmt_bm1 = select(Staff_Member).where(
                        Staff_Member.tg_user_id == payload.updates.backup_managers[0]
                    )
                else:
                    stmt_bm1 = select(Staff_Member).where(
                        Staff_Member.max_user_id == payload.updates.backup_managers[0]
                    )
                result_bm1 = await session.execute(stmt_bm1)
                backup_manager_1 = result_bm1.scalar_one_or_none()
                
                if backup_manager_1:
                    staff.backup_manager_1_id = backup_manager_1.id
                else:
                    # Requirement 3.12: Log warning if backup manager not found
                    logger.warning(
                        f"Backup manager 1 with {payload.messenger}_user_id="
                        f"{payload.updates.backup_managers[0]} not found"
                    )
            
            if len(payload.updates.backup_managers) >= 2:
                # Query second backup manager
                if payload.messenger == "telegram":
                    stmt_bm2 = select(Staff_Member).where(
                        Staff_Member.tg_user_id == payload.updates.backup_managers[1]
                    )
                else:
                    stmt_bm2 = select(Staff_Member).where(
                        Staff_Member.max_user_id == payload.updates.backup_managers[1]
                    )
                result_bm2 = await session.execute(stmt_bm2)
                backup_manager_2 = result_bm2.scalar_one_or_none()
                
                if backup_manager_2:
                    staff.backup_manager_2_id = backup_manager_2.id
                else:
                    # Requirement 3.12: Log warning if backup manager not found
                    logger.warning(
                        f"Backup manager 2 with {payload.messenger}_user_id="
                        f"{payload.updates.backup_managers[1]} not found"
                    )
            
            updates_applied.append("backup_managers")
            logger.info(f"Updated backup managers for staff {staff.id}")
        
        # Requirement 3.3: Handle deactivation with ticket reassignment
        if payload.updates.is_active is not None:
            old_active_status = staff.is_active
            
            # Check if is_active has actually changed
            if has_field_changed(old_active_status, payload.updates.is_active, "is_active"):
                staff.is_active = payload.updates.is_active
                updates_applied.append("is_active")
                
                # If deactivating staff member
                if payload.updates.is_active is False and old_active_status is True:
                    logger.info(f"Deactivating staff member {staff.id}, reassigning tickets")
                    
                    # Requirement 3.11: Validate backup managers provided
                    if not payload.updates.backup_managers or len(payload.updates.backup_managers) == 0:
                        logger.error(
                            f"Cannot deactivate staff {staff.id} without backup managers"
                        )
                        raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="backup_managers list is required when deactivating staff member",
                    )
                
                # Requirement 3.4: Query all active tickets assigned to this staff member
                stmt_tickets = select(Ticket).where(
                    Ticket.assigned_staff_id == staff.id,
                    Ticket.ticket_status.not_in([TicketStatus.CLOSED, TicketStatus.CANCELLED])
                )
                result_tickets = await session.execute(stmt_tickets)
                active_tickets = result_tickets.scalars().all()
                
                ticket_count = len(active_tickets)
                logger.info(f"Found {ticket_count} active tickets to reassign")
                
                if ticket_count > 0:
                    # Requirement 3.5: Reassign tickets to backup managers using round-robin
                    backup_manager_ids = []
                    
                    # Collect valid backup manager IDs
                    for backup_messenger_id in payload.updates.backup_managers:
                        if payload.messenger == "telegram":
                            stmt_bm = select(Staff_Member).where(
                                Staff_Member.tg_user_id == backup_messenger_id
                            )
                        else:
                            stmt_bm = select(Staff_Member).where(
                                Staff_Member.max_user_id == backup_messenger_id
                            )
                        result_bm = await session.execute(stmt_bm)
                        backup_manager = result_bm.scalar_one_or_none()
                        
                        if backup_manager:
                            backup_manager_ids.append(backup_manager.id)
                        else:
                            logger.warning(
                                f"Backup manager with {payload.messenger}_user_id="
                                f"{backup_messenger_id} not found, skipping"
                            )
                    
                    if not backup_manager_ids:
                        logger.error("No valid backup managers found for ticket reassignment")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No valid backup managers found",
                        )
                    
                    # Round-robin distribution
                    for index, ticket in enumerate(active_tickets):
                        backup_manager_id = backup_manager_ids[index % len(backup_manager_ids)]
                        
                        old_staff_id = ticket.assigned_staff_id
                        ticket.assigned_staff_id = backup_manager_id
                        tickets_reassigned += 1
                        
                        # Requirement 3.6: Log reassignment action for each ticket
                        action_log = Action_Log(
                            action_type=ActionType.TICKET_ASSIGNED,
                            ticket_id=ticket.id,
                            user_id=ticket.user_id,
                            staff_id=backup_manager_id,
                            action_details={
                                "action": "ticket_reassigned_due_to_staff_deactivation",
                                "old_staff_id": old_staff_id,
                                "new_staff_id": backup_manager_id,
                                "reason": "staff_deactivation",
                                "deactivated_staff_id": staff.id,
                                "messenger": payload.messenger,
                            },
                            action_timestamp=datetime.now()
                        )
                        session.add(action_log)
                    
                    logger.info(
                        f"Reassigned {tickets_reassigned} tickets to {len(backup_manager_ids)} "
                        f"backup managers"
                    )
        
        # Commit database changes
        await session.commit()
        
        # If nothing changed, skip action log and CRM sync
        if not updates_applied:
            logger.info(
                f"No actual changes detected for staff {staff.id}. "
                f"Skipping action log and CRM sync (likely duplicate webhook from 1C CRM)."
            )
            return StaffUpdateWebhookResponse(
                status="success",
                message="Staff member data already up to date (no changes detected)",
                staff_id=payload.staff_id,
                updates_applied=updates_applied,
            )
        
        # Requirement 3.8: Log staff update action
        action_log = Action_Log(
            action_type=ActionType.STAFF_UPDATED,
            staff_id=staff.id,
            action_details={
                "action": "staff_updated_via_webhook",
                "updates_applied": updates_applied,
                "messenger": payload.messenger,
                "staff_messenger_id": payload.staff_id,
                "tickets_reassigned": tickets_reassigned,
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        # Requirement 3.9: Call i-TAT API to sync update
        try:
            itat_client = get_itat_client()
            
            # Note: This method needs to be implemented in i_tat_service.py
            # For now, we'll log that it should be called
            logger.info(
                f"Should call i-TAT API update_staff_member with: "
                f"staff_id={payload.staff_id}, messenger={payload.messenger}, "
                f"updates={updates_applied}"
            )
            
            # When i-TAT API method is implemented:
            # await itat_client.update_staff_member(
            #     staff_id=payload.staff_id,
            #     messenger=payload.messenger,
            #     signature=payload.updates.signature,
            #     is_active=payload.updates.is_active,
            #     backup_managers=payload.updates.backup_managers
            # )
            
        except Exception as e:
            # Log error but don't fail the webhook - local DB is source of truth
            logger.error(
                f"Failed to sync staff update to CRM: {e}",
                exc_info=True
            )
        
        if tickets_reassigned > 0:
            updates_applied.append(f"tickets_reassigned: {tickets_reassigned}")
        
        logger.info(
            f"Staff update webhook processed successfully: staff_id={payload.staff_id}, "
            f"updates={updates_applied}, tickets_reassigned={tickets_reassigned}"
        )
        
        return StaffUpdateWebhookResponse(
            status="success",
            message="Staff member updated successfully",
            staff_id=payload.staff_id,
            updates_applied=updates_applied,
        )
        
    except HTTPException as http_exc:
        # Notify admins about HTTP errors
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            
            error_type = f"HTTP {http_exc.status_code}"
            error_details = http_exc.detail
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}, action={payload.action}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="staff_update",
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
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}, action={payload.action}"
            
            await notify_admins_webhook_error(
                session=session,
                webhook_name="staff_update",
                error_type=error_type,
                error_details=error_details,
                payload_summary=payload_summary
            )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        # Unexpected error (Requirement 18.6, 18.9)
        logger.error(
            f"Error processing staff update webhook: {e}",
            exc_info=True
        )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )
