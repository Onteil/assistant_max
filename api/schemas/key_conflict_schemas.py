"""
Pydantic schemas for key conflict resolution webhook.

This module defines request and response schemas for the key conflict resolution
webhook endpoint that handles GS_Key ownership conflicts between users.
"""

from pydantic import BaseModel, Field, field_validator


class KeyConflictWebhookPayload(BaseModel):
    """
    Payload for key conflict resolution webhook.
    
    Attributes:
        new_user_id: Messenger-specific ID of user claiming the key
        old_user_id: Messenger-specific ID of current key owner
        gs_key: GS_Key number being disputed
        resolution: Resolution decision ("transfer" or "reject")
        messenger: Messenger platform ("telegram" or "max")
        resolved_by_staff_id: Staff member ID who made the decision
        reason: Optional explanation for the resolution
    """
    
    new_user_id: int = Field(..., description="Messenger-specific ID of user claiming the key")
    old_user_id: int = Field(..., description="Messenger-specific ID of current key owner")
    gs_key: str = Field(..., min_length=1, description="GS_Key number being disputed")
    resolution: str = Field(..., description="Resolution decision (transfer or reject)")
    messenger: str = Field(..., description="Messenger platform (telegram or max)")
    resolved_by_staff_id: int = Field(..., description="Staff member ID who made the decision")
    reason: str | None = Field(None, description="Optional explanation for the resolution")
    
    @field_validator("new_user_id", "old_user_id", "resolved_by_staff_id")
    @classmethod
    def validate_positive_ids(cls, v: int) -> int:
        """Validate that IDs are positive integers."""
        if v <= 0:
            raise ValueError("ID must be a positive integer")
        return v
    
    @field_validator("gs_key")
    @classmethod
    def validate_gs_key_length(cls, v: str) -> str:
        """Validate that gs_key is non-empty."""
        if not v or not v.strip():
            raise ValueError("gs_key must be a non-empty string")
        return v.strip()
    
    @field_validator("messenger")
    @classmethod
    def validate_messenger_type(cls, v: str) -> str:
        """Validate that messenger is either 'telegram' or 'max'."""
        if v.lower() not in ("telegram", "max"):
            raise ValueError("messenger must be 'telegram' or 'max'")
        return v.lower()
    
    @field_validator("resolution")
    @classmethod
    def validate_resolution_type(cls, v: str) -> str:
        """Validate that resolution is either 'transfer' or 'reject'."""
        if v.lower() not in ("transfer", "reject"):
            raise ValueError("resolution must be 'transfer' or 'reject'")
        return v.lower()


class KeyConflictWebhookResponse(BaseModel):
    """
    Response for key conflict resolution webhook.
    
    Attributes:
        status: Operation status ("success" or "error")
        message: Human-readable status message
        resolution: Resolution type that was applied
        gs_key: GS_Key that was resolved
    """
    
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable status message")
    resolution: str = Field(..., description="Resolution type that was applied")
    gs_key: str = Field(..., description="GS_Key that was resolved")
