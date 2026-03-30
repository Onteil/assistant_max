"""
Pydantic schemas for ticket status update webhook.

This module defines request and response schemas for the ticket status update
webhook endpoint that synchronizes ticket status changes from CRM to bot.
"""

from pydantic import BaseModel, Field, field_validator, model_validator


class TicketStatusWebhookPayload(BaseModel):
    """
    Payload for ticket status update webhook.
    
    Attributes:
        ticket_id: Unique ticket identifier
        status: New ticket status
        closed_by_staff_id: Staff member ID who closed the ticket (required if status="closed")
        messenger: Messenger platform ("telegram" or "max")
        comment: Optional comment about the status change
    """
    
    ticket_id: str = Field(..., min_length=1, description="Unique ticket identifier")
    status: str = Field(..., description="New ticket status")
    closed_by_staff_id: int | None = Field(None, description="Staff member ID who closed the ticket")
    messenger: str = Field(default="telegram", description="Messenger platform (telegram or max)")
    comment: str | None = Field(None, description="Optional comment about the status change")
    
    @field_validator("ticket_id")
    @classmethod
    def validate_ticket_id(cls, v: str) -> str:
        """Validate and normalize ticket_id.
        
        Strips non-numeric prefixes like 'TKT_' sent by 1C/CRM systems.
        Examples: 'TKT_36' -> '36', 'TKT_37' -> '37', '36' -> '36'
        """
        if not v or not v.strip():
            raise ValueError("ticket_id must be a non-empty string")
        v = v.strip()
        # Strip common CRM prefixes (e.g. TKT_36 -> 36)
        import re
        match = re.search(r'\d+$', v)
        if match:
            return match.group()
        return v
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate that status is non-empty."""
        if not v or not v.strip():
            raise ValueError("status must be a non-empty string")
        return v.strip()
    
    @field_validator("messenger")
    @classmethod
    def validate_messenger_type(cls, v: str) -> str:
        """Validate that messenger is either 'telegram' or 'max'."""
        if v.lower() not in ("telegram", "max"):
            raise ValueError("messenger must be 'telegram' or 'max'")
        return v.lower()
    
    @field_validator("closed_by_staff_id")
    @classmethod
    def validate_positive_id(cls, v: int | None) -> int | None:
        """Validate that closed_by_staff_id is a positive integer if provided."""
        if v is not None and v <= 0:
            raise ValueError("closed_by_staff_id must be a positive integer")
        return v
    
    @model_validator(mode="after")
    def validate_closed_by_staff_id_required(self) -> "TicketStatusWebhookPayload":
        """Validate that closed_by_staff_id is provided when status='closed' or 'Закрыто'."""
        closed_statuses = {"closed", "закрыто"}
        if self.status.lower() in closed_statuses and self.closed_by_staff_id is None:
            raise ValueError("closed_by_staff_id is required when status='closed'")
        return self


class TicketStatusWebhookResponse(BaseModel):
    """
    Response for ticket status update webhook.
    
    Attributes:
        status: Operation status ("success" or "error")
        message: Human-readable status message
        ticket_id: Ticket ID that was updated
        new_status: Status that was applied
    """
    
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable status message")
    ticket_id: str = Field(..., description="Ticket ID that was updated")
    new_status: str = Field(..., description="Status that was applied")
