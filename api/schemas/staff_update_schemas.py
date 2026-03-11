"""
Pydantic schemas for staff member update webhook.

This module defines request and response schemas for the staff update webhook
endpoint that handles staff member lifecycle management including deactivation
and ticket reassignment.
"""

from pydantic import BaseModel, Field, field_validator, model_validator


class StaffUpdates(BaseModel):
    """
    Staff member update fields.
    
    Attributes:
        full_name: Updated staff member full name
        position: Updated staff member position
        is_active: Active status (false triggers ticket reassignment)
        backup_managers: List of backup manager IDs for ticket reassignment
    """
    
    full_name: str | None = Field(None, description="Updated staff member full name")
    position: str | None = Field(None, description="Updated staff member position")
    is_active: bool | None = Field(None, description="Active status")
    backup_managers: list[int] | None = Field(None, description="List of backup manager IDs")
    
    @model_validator(mode="after")
    def validate_backup_managers_required(self) -> "StaffUpdates":
        """Validate that backup_managers is provided when is_active=false."""
        if self.is_active is False:
            if not self.backup_managers or len(self.backup_managers) == 0:
                raise ValueError("backup_managers list is required when is_active=false")
        return self


class StaffUpdateWebhookPayload(BaseModel):
    """
    Payload for staff member update webhook.
    
    Attributes:
        staff_id: Messenger-specific ID of staff member to update
        messenger: Messenger platform ("telegram" or "max")
        updates: Staff member fields to update
    """
    
    staff_id: int = Field(..., description="Messenger-specific ID of staff member")
    messenger: str = Field(..., description="Messenger platform (telegram or max)")
    updates: StaffUpdates = Field(..., description="Staff member fields to update")
    
    @field_validator("staff_id")
    @classmethod
    def validate_positive_id(cls, v: int) -> int:
        """Validate that staff_id is a positive integer."""
        if v <= 0:
            raise ValueError("staff_id must be a positive integer")
        return v
    
    @field_validator("messenger")
    @classmethod
    def validate_messenger_type(cls, v: str) -> str:
        """Validate that messenger is either 'telegram' or 'max'."""
        if v.lower() not in ("telegram", "max"):
            raise ValueError("messenger must be 'telegram' or 'max'")
        return v.lower()


class StaffUpdateWebhookResponse(BaseModel):
    """
    Response for staff member update webhook.
    
    Attributes:
        status: Operation status ("success" or "error")
        message: Human-readable status message
        staff_id: Staff member ID that was updated
        updates_applied: List of field names that were updated
        tickets_reassigned: Number of tickets reassigned (if deactivated)
    """
    
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable status message")
    staff_id: int = Field(..., description="Staff member ID that was updated")
    updates_applied: list[str] = Field(..., description="List of field names that were updated")
    tickets_reassigned: int | None = Field(None, description="Number of tickets reassigned")
