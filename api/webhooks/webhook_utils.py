"""
Webhook Utilities

Common utilities for webhook handlers including deduplication checks.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def has_field_changed(old_value: Any, new_value: Any, field_name: str) -> bool:
    """
    Check if a field value has actually changed.
    
    This function compares old and new values to determine if an update
    is necessary. Used for webhook deduplication to avoid sending
    duplicate notifications when 1C CRM triggers multiple times.
    
    Args:
        old_value: Current value in database
        new_value: New value from webhook payload
        field_name: Name of field being checked (for logging)
        
    Returns:
        True if value has changed, False if unchanged
        
    Examples:
        >>> has_field_changed("active", "active", "status")
        False
        >>> has_field_changed("active", "expired", "status")
        True
        >>> has_field_changed(None, "test@example.com", "email")
        True
    """
    # Handle None values
    if old_value is None and new_value is None:
        return False
    
    if old_value is None or new_value is None:
        return True
    
    # For datetime objects, compare as strings to handle timezone differences
    if hasattr(old_value, 'isoformat') and hasattr(new_value, 'isoformat'):
        old_str = old_value.isoformat()
        new_str = new_value.isoformat()
        changed = old_str != new_str
        if not changed:
            logger.debug(f"Field '{field_name}' unchanged: {old_str}")
        return changed
    
    # For enum values, compare by value
    if hasattr(old_value, 'value'):
        old_value = old_value.value
    if hasattr(new_value, 'value'):
        new_value = new_value.value
    
    # Direct comparison
    changed = old_value != new_value
    if not changed:
        logger.debug(f"Field '{field_name}' unchanged: {old_value}")
    
    return changed


def check_updates_needed(
    current_data: dict[str, Any],
    new_data: dict[str, Any],
    fields_to_check: list[str]
) -> dict[str, Any]:
    """
    Check which fields have actually changed and need updating.
    
    This function compares current database values with incoming webhook
    payload values to determine which fields need updating. Used for
    webhook deduplication.
    
    Args:
        current_data: Dictionary of current values from database
        new_data: Dictionary of new values from webhook payload
        fields_to_check: List of field names to check
        
    Returns:
        Dictionary with only fields that have changed
        
    Examples:
        >>> current = {"status": "active", "email": "old@example.com"}
        >>> new = {"status": "active", "email": "new@example.com"}
        >>> check_updates_needed(current, new, ["status", "email"])
        {"email": "new@example.com"}
    """
    updates = {}
    
    for field in fields_to_check:
        if field not in new_data:
            continue
        
        new_value = new_data[field]
        old_value = current_data.get(field)
        
        if has_field_changed(old_value, new_value, field):
            updates[field] = new_value
            logger.debug(f"Field '{field}' changed: {old_value} -> {new_value}")
    
    return updates
