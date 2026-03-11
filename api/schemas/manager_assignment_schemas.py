"""Pydantic schemas for Manager Assignment System validation."""

from typing import Literal
from pydantic import BaseModel, Field, field_validator


class ManagerAssignmentWebhookPayload(BaseModel):
    """
    Webhook payload for assigning/updating manager for a user from 1C CRM.
    
    Used when manager is assigned or changed for a client in CRM.
    """
    messenger: Literal["telegram", "max"] = Field(..., description="Messenger type (telegram or max)")
    user_id: int = Field(..., description="Messenger user ID (telegram_user_id or max_user_id)")
    phone: str = Field(..., description="User phone number for verification")
    
    # Manager assignment
    manager_id: int = Field(..., description="Messenger ID of assigned manager")
    manager_name: str | None = Field(
        None, 
        description="[DEPRECATED] Manager name - not used, data fetched from database"
    )
    
    # Optional: send notification to user
    send_notification: bool = Field(
        default=False, 
        description="Whether to send notification to user about manager assignment"
    )
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v: int) -> int:
        """Validate that user_id is positive."""
        if v <= 0:
            raise ValueError('user_id must be positive')
        return v
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate phone number format."""
        if not v or len(v) < 10:
            raise ValueError('phone must be at least 10 characters')
        return v
    
    @field_validator('manager_id')
    @classmethod
    def validate_manager_id(cls, v: int) -> int:
        """Validate that manager_id is positive."""
        if v <= 0:
            raise ValueError('manager_id must be positive')
        return v


class ManagerAssignmentWebhookResponse(BaseModel):
    """
    Response model for manager assignment webhook endpoint.
    
    Provides status, message, and details about the assignment.
    """
    status: Literal["success", "error"] = Field(..., description="Processing status")
    message: str = Field(..., description="Human-readable message")
    messenger: str | None = Field(None, description="Messenger type that was processed")
    user_id: int | None = Field(None, description="Messenger user ID that was processed")
    manager_id: int | None = Field(None, description="Manager internal ID that was assigned")
    manager_name: str | None = Field(None, description="Manager name")
    notification_sent: bool = Field(default=False, description="Whether notification was sent to user")
