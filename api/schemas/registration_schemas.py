"""Pydantic schemas for Registration Approval System validation."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator

from database.models import SubscriptionStatus


class RegistrationWebhookPayload(BaseModel):
    """
    Webhook payload for registration approval/rejection from 1C CRM.
    
    Used when REGISTRATION_APPROVE_METHOD is set to "crm".
    
    Requirements: 4.2 - CRM manual registration confirmation
    """
    messenger: Literal["telegram", "max"] = Field(..., description="Messenger type (telegram or max)")
    user_id: int = Field(..., description="Messenger user ID (telegram_user_id or max_user_id)")
    phone: str = Field(..., description="User phone number for verification")
    status: Literal["approved", "rejected"] = Field(..., description="Registration status")
    reason: str | None = Field(None, description="Rejection reason (required if status=rejected)")
    
    # New fields for requirement 4.2
    manager_name: str | None = Field(None, description="Manager name for welcome message (required if status=approved)")
    manager_id: int | None = Field(None, description="Messenger ID of assigned manager (required if status=approved)")
    subscription_status: Literal["active", "expired", "none"] | None = Field(None, description="Subscription status (optional, defaults based on support_expires_at)")
    support_expires_at: datetime | None = Field(None, description="Support expiration date (required if status=approved and subscription_status=active)")
    
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
    
    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v: str | None, info) -> str | None:
        """Validate that reason is provided when status is rejected."""
        if info.data.get('status') == 'rejected' and not v:
            raise ValueError('reason is required when status is rejected')
        return v
    
    @field_validator('manager_name')
    @classmethod
    def validate_manager_name(cls, v: str | None, info) -> str | None:
        """Validate that manager_name is provided when status is approved."""
        if info.data.get('status') == 'approved' and not v:
            raise ValueError('manager_name is required when status is approved')
        return v
    
    @field_validator('manager_id')
    @classmethod
    def validate_manager_id(cls, v: int | None, info) -> int | None:
        """Validate that manager_id is provided and positive when status is approved."""
        if info.data.get('status') == 'approved':
            if v is None:
                raise ValueError('manager_id is required when status is approved')
            if v <= 0:
                raise ValueError('manager_id must be positive')
        return v
    
    @field_validator('subscription_status')
    @classmethod
    def validate_subscription_status(cls, v: str | None, info) -> str | None:
        """Validate subscription_status enum value."""
        if v is not None and v not in ["active", "expired", "none"]:
            raise ValueError('subscription_status must be one of: active, expired, none')
        return v
    
    @field_validator('support_expires_at')
    @classmethod
    def validate_support_expires_at(cls, v: datetime | None, info) -> datetime | None:
        """Validate that support_expires_at is provided when subscription_status is active."""
        if info.data.get('status') == 'approved':
            subscription_status = info.data.get('subscription_status')
            # If subscription_status is explicitly set to 'active', require support_expires_at
            if subscription_status == 'active' and v is None:
                raise ValueError('support_expires_at is required when subscription_status is active')
            # If subscription_status is not provided and support_expires_at is provided, that's OK (backward compatibility)
            # If subscription_status is 'none' or 'expired', support_expires_at is optional
        return v


class RegistrationWebhookResponse(BaseModel):
    """
    Response model for registration webhook endpoint.
    
    Provides status and message about webhook processing.
    """
    status: Literal["success", "error"] = Field(..., description="Processing status")
    message: str = Field(..., description="Human-readable message")
    messenger: str | None = Field(None, description="Messenger type that was processed")
    user_id: int | None = Field(None, description="Messenger user ID that was processed")
