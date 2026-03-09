"""
Pydantic schemas for bulk ticket reassignment webhook.

This module defines request and response schemas for the ticket reassignment
webhook endpoint that handles bulk ticket transfers between staff members.
"""

from pydantic import BaseModel, Field, field_validator


class TicketReassignmentWebhookPayload(BaseModel):
    """
    Payload for bulk ticket reassignment webhook.
    
    Attributes:
        from_staff_id: Messenger-specific ID of staff member currently assigned
        to_staff_id: Messenger-specific ID of staff member to reassign to
        ticket_ids: List of ticket IDs to reassign, or ["all"] to reassign all tickets
        messenger: Messenger platform ("telegram" or "max")
        reason: Optional reason for reassignment
    """
    
    from_staff_id: int = Field(..., description="Messenger-specific ID of current staff member")
    to_staff_id: int = Field(..., description="Messenger-specific ID of target staff member")
    ticket_ids: list[str] = Field(..., min_length=1, description="List of ticket IDs to reassign, or ['all'] for all tickets")
    messenger: str = Field(..., description="Messenger platform (telegram or max)")
    reason: str | None = Field(None, description="Optional reason for reassignment")
    
    @field_validator("from_staff_id", "to_staff_id")
    @classmethod
    def validate_positive_ids(cls, v: int) -> int:
        """Validate that staff IDs are positive integers."""
        if v <= 0:
            raise ValueError("Staff ID must be a positive integer")
        return v
    
    @field_validator("ticket_ids")
    @classmethod
    def validate_ticket_ids_non_empty(cls, v: list[str]) -> list[str]:
        """Validate that ticket_ids list is non-empty and contains valid IDs or 'all'."""
        if not v or len(v) == 0:
            raise ValueError("ticket_ids list must contain at least one ticket ID")
        
        # Check if it's the special "all" value
        if len(v) == 1 and v[0].strip().lower() == "all":
            return ["all"]
        
        # Validate each ticket ID is non-empty
        for ticket_id in v:
            if not ticket_id or not ticket_id.strip():
                raise ValueError("All ticket IDs must be non-empty strings")
        
        return [tid.strip() for tid in v]
    
    @field_validator("messenger")
    @classmethod
    def validate_messenger_type(cls, v: str) -> str:
        """Validate that messenger is either 'telegram' or 'max'."""
        if v.lower() not in ("telegram", "max"):
            raise ValueError("messenger must be 'telegram' or 'max'")
        return v.lower()


class TicketReassignmentWebhookResponse(BaseModel):
    """
    Response for bulk ticket reassignment webhook.
    
    Attributes:
        status: Operation status ("success" or "error")
        message: Human-readable status message
        from_staff_id: Staff member ID tickets were reassigned from
        to_staff_id: Staff member ID tickets were reassigned to
        tickets_reassigned: Number of tickets successfully reassigned
    """
    
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable status message")
    from_staff_id: int = Field(..., description="Staff member ID tickets were reassigned from")
    to_staff_id: int = Field(..., description="Staff member ID tickets were reassigned to")
    tickets_reassigned: int = Field(..., description="Number of tickets successfully reassigned")
