"""
Centralized audit logging utility for MAX bot.

This module provides helper functions to log significant events to i-TAT API
for audit trail and compliance tracking.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from services.i_tat_service import get_itat_client

logger = logging.getLogger(__name__)


async def log_audit_event(
    action_type: str,
    user_id: Optional[int] = None,
    staff_id: Optional[int] = None,
    ticket_id: Optional[str] = None,
    action_details: Optional[Dict[str, Any]] = None,
    action_timestamp: Optional[str] = None
) -> bool:
    """
    Log an audit event to i-TAT API.
    
    Args:
        action_type: Type of action performed (e.g., "user_registered", "staff_updated")
        user_id: User ID involved in the action (optional)
        staff_id: Staff ID who performed the action (optional)
        ticket_id: Ticket ID involved in the action (optional)
        action_details: Additional details as JSON (optional)
        action_timestamp: When the action occurred (ISO format, defaults to now)
    
    Returns:
        bool: True if logging was successful, False otherwise
    """
    try:
        itat_client = get_itat_client()
        
        # Use current timestamp if not provided
        if not action_timestamp:
            action_timestamp = datetime.utcnow().isoformat()
        
        await itat_client.audit_log(
            messenger="max",
            action_type=action_type,
            action_timestamp=action_timestamp,
            user_id=user_id,
            staff_id=staff_id,
            ticket_id=ticket_id,
            action_details=action_details
        )
        
        logger.info(f"Audit event logged: {action_type}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to log audit event {action_type}: {e}", exc_info=True)
        return False


# User Registration Events
async def log_user_registration_started(user_id: int, max_user_id: int) -> bool:
    """Log when user starts registration process."""
    return await log_audit_event(
        action_type="user_registration_started",
        user_id=user_id,
        action_details={
            "max_user_id": max_user_id,
            "step": "registration_started"
        }
    )


async def log_user_registration_completed(user_id: int, max_user_id: int) -> bool:
    """Log when user completes registration form."""
    return await log_audit_event(
        action_type="user_registration_completed",
        user_id=user_id,
        action_details={
            "max_user_id": max_user_id,
            "step": "registration_completed"
        }
    )


async def log_user_registration_approved(user_id: int, staff_id: int, admin_name: str, admin_max_id: int) -> bool:
    """Log when staff approves user registration."""
    return await log_audit_event(
        action_type="user_registration_approved",
        user_id=user_id,
        staff_id=staff_id,
        action_details={
            "admin_name": admin_name,
            "admin_max_id": admin_max_id,
            "action": "registration_approved"
        }
    )


async def log_user_registration_rejected(user_id: int, staff_id: int, admin_name: str, admin_max_id: int, reason: str) -> bool:
    """Log when staff rejects user registration."""
    return await log_audit_event(
        action_type="user_registration_rejected",
        user_id=user_id,
        staff_id=staff_id,
        action_details={
            "admin_name": admin_name,
            "admin_max_id": admin_max_id,
            "reason": reason,
            "action": "registration_rejected"
        }
    )


# Staff Management Events
async def log_staff_created(staff_id: int, admin_id: int, admin_name: str, admin_max_id: int, staff_name: str) -> bool:
    """Log when new staff member is created."""
    return await log_audit_event(
        action_type="staff_created",
        staff_id=admin_id,
        action_details={
            "admin_name": admin_name,
            "admin_max_id": admin_max_id,
            "new_staff_id": staff_id,
            "new_staff_name": staff_name,
            "action": "staff_created"
        }
    )


async def log_staff_activated(staff_id: int, admin_id: int, admin_name: str, admin_max_id: int) -> bool:
    """Log when staff member is activated."""
    return await log_audit_event(
        action_type="staff_activated",
        staff_id=admin_id,
        action_details={
            "admin_name": admin_name,
            "admin_max_id": admin_max_id,
            "target_staff_id": staff_id,
            "old_value": "inactive",
            "new_value": "active",
            "action": "staff_activated"
        }
    )


async def log_staff_deactivated(staff_id: int, admin_id: int, admin_name: str, admin_max_id: int, reason: str = None) -> bool:
    """Log when staff member is deactivated."""
    return await log_audit_event(
        action_type="staff_deactivated",
        staff_id=admin_id,
        action_details={
            "admin_name": admin_name,
            "admin_max_id": admin_max_id,
            "target_staff_id": staff_id,
            "old_value": "active",
            "new_value": "inactive",
            "reason": reason,
            "action": "staff_deactivated"
        }
    )


# Ticket Events
async def log_ticket_created(ticket_id: str, user_id: int, ticket_type: str, max_user_id: int) -> bool:
    """Log when ticket is created."""
    return await log_audit_event(
        action_type="ticket_created",
        user_id=user_id,
        ticket_id=ticket_id,
        action_details={
            "max_user_id": max_user_id,
            "ticket_type": ticket_type,
            "action": "ticket_created"
        }
    )


async def log_ticket_status_changed(
    ticket_id: str, 
    user_id: int, 
    staff_id: Optional[int], 
    old_status: str, 
    new_status: str,
    admin_name: str = None,
    admin_max_id: int = None
) -> bool:
    """Log when ticket status changes."""
    action_details = {
        "old_status": old_status,
        "new_status": new_status,
        "action": "ticket_status_changed"
    }
    
    if admin_name and admin_max_id:
        action_details.update({
            "admin_name": admin_name,
            "admin_max_id": admin_max_id
        })
    
    return await log_audit_event(
        action_type="ticket_status_changed",
        user_id=user_id,
        staff_id=staff_id,
        ticket_id=ticket_id,
        action_details=action_details
    )


async def log_ticket_assigned(
    ticket_id: str, 
    user_id: int, 
    staff_id: int, 
    admin_id: int,
    admin_name: str,
    admin_max_id: int
) -> bool:
    """Log when ticket is assigned to staff."""
    return await log_audit_event(
        action_type="ticket_assigned",
        user_id=user_id,
        staff_id=admin_id,
        ticket_id=ticket_id,
        action_details={
            "assigned_to_staff_id": staff_id,
            "admin_name": admin_name,
            "admin_max_id": admin_max_id,
            "action": "ticket_assigned"
        }
    )


# Profile/Asset Events
async def log_user_profile_updated(user_id: int, field: str, old_value: str, new_value: str, max_user_id: int) -> bool:
    """Log when user profile is updated."""
    return await log_audit_event(
        action_type="user_profile_updated",
        user_id=user_id,
        action_details={
            "max_user_id": max_user_id,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "action": "profile_updated"
        }
    )


async def log_user_assets_updated(user_id: int, max_user_id: int, changes: Dict[str, Any]) -> bool:
    """Log when user assets are updated."""
    return await log_audit_event(
        action_type="user_assets_updated",
        user_id=user_id,
        action_details={
            "max_user_id": max_user_id,
            "changes": changes,
            "action": "assets_updated"
        }
    )


# Key Conflict Events
async def log_key_conflict_detected(user_id: int, max_user_id: int, key: str, conflict_details: Dict[str, Any]) -> bool:
    """Log when key conflict is detected."""
    return await log_audit_event(
        action_type="key_conflict_detected",
        user_id=user_id,
        action_details={
            "max_user_id": max_user_id,
            "key": key,
            "conflict_details": conflict_details,
            "action": "key_conflict_detected"
        }
    )


async def log_key_conflict_resolved(
    user_id: int, 
    staff_id: int, 
    key: str, 
    resolution: str,
    admin_name: str,
    admin_max_id: int
) -> bool:
    """Log when key conflict is resolved."""
    return await log_audit_event(
        action_type="key_conflict_resolved",
        user_id=user_id,
        staff_id=staff_id,
        action_details={
            "key": key,
            "resolution": resolution,
            "admin_name": admin_name,
            "admin_max_id": admin_max_id,
            "action": "key_conflict_resolved"
        }
    )


# Calendar Events
async def log_calendar_rule_added(staff_id: int, admin_name: str, admin_max_id: int, rule_details: Dict[str, Any]) -> bool:
    """Log when calendar rule is added."""
    return await log_audit_event(
        action_type="calendar_rule_added",
        staff_id=staff_id,
        action_details={
            "admin_name": admin_name,
            "admin_max_id": admin_max_id,
            "rule_details": rule_details,
            "action": "calendar_rule_added"
        }
    )


async def log_calendar_rule_deleted(staff_id: int, admin_name: str, admin_max_id: int, rule_id: int) -> bool:
    """Log when calendar rule is deleted."""
    return await log_audit_event(
        action_type="calendar_rule_deleted",
        staff_id=staff_id,
        action_details={
            "admin_name": admin_name,
            "admin_max_id": admin_max_id,
            "rule_id": rule_id,
            "action": "calendar_rule_deleted"
        }
    )


# Phone Change Events
async def log_phone_change_requested(user_id: int, max_user_id: int, old_phone: str, new_phone: str, ticket_id: str) -> bool:
    """Log when user requests phone change."""
    return await log_audit_event(
        action_type="phone_change_requested",
        user_id=user_id,
        ticket_id=ticket_id,
        action_details={
            "max_user_id": max_user_id,
            "old_phone": old_phone,
            "new_phone": new_phone,
            "action": "phone_change_requested"
        }
    )