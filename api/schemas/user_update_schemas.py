"""Pydantic schemas for User Data Update System validation."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class GS_KeyUpdate(BaseModel):
    """GS_Key update data."""
    key_number: str = Field(..., description="GRAND-Smeta key number")
    action: Literal["add", "remove"] = Field(..., description="Action to perform with the key")
    
    @field_validator('key_number')
    @classmethod
    def validate_key_number(cls, v: str) -> str:
        """Validate key number format."""
        if not v or len(v) < 3:
            raise ValueError('key_number must be at least 3 characters')
        return v


class OrganizationUpdate(BaseModel):
    """Organization update data."""
    inn: str = Field(..., description="Organization INN (10 or 12 digits)")
    organization_name: str | None = Field(None, description="Organization name")
    action: Literal["add", "remove"] = Field(..., description="Action to perform with the organization")
    
    @field_validator('inn')
    @classmethod
    def validate_inn(cls, v: str) -> str:
        """Validate INN format."""
        if not v or len(v) not in [10, 12]:
            raise ValueError('inn must be 10 or 12 digits')
        if not v.isdigit():
            raise ValueError('inn must contain only digits')
        return v


class UserUpdateWebhookPayload(BaseModel):
    """
    Webhook payload for updating user data and assets from 1C CRM.
    
    Used when client pays invoice, support is extended, keys are added/removed,
    or other user data is updated manually in CRM.
    
    Note: Manager assignment is handled by separate manager_assignment webhook.
    """
    messenger: Literal["telegram", "max"] = Field(..., description="Messenger type (telegram or max)")
    user_id: int = Field(..., description="Messenger user ID (telegram_user_id or max_user_id)")
    phone: str = Field(..., description="User phone number for verification")
    
    # Optional user profile updates
    email: str | None = Field(None, description="User email address")
    full_name: str | None = Field(None, description="User full name")
    
    # Subscription updates
    subscription_end_date: datetime | None = Field(None, description="New subscription end date")
    subscription_status: Literal["active", "expired", "none"] | None = Field(
        None, 
        description="New subscription status"
    )
    
    # GS Keys updates
    gs_keys: list[GS_KeyUpdate] | None = Field(None, description="List of GS_Key updates to apply")
    
    # Organizations updates
    organizations: list[OrganizationUpdate] | None = Field(
        None, 
        description="List of organization updates to apply"
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
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        """Validate email format."""
        if v and '@' not in v:
            raise ValueError('email must contain @')
        return v


class UserUpdateWebhookResponse(BaseModel):
    """
    Response model for user update webhook endpoint.
    
    Provides status, message, and details about what was updated.
    """
    status: Literal["success", "error"] = Field(..., description="Processing status")
    message: str = Field(..., description="Human-readable message")
    messenger: str | None = Field(None, description="Messenger type that was processed")
    user_id: int | None = Field(None, description="Messenger user ID that was processed")
    updates_applied: dict | None = Field(None, description="Summary of updates applied")
