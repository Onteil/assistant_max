"""
Pydantic schemas for subscription status change webhook.

This module defines request and response schemas for the subscription status
change webhook endpoint that synchronizes user subscription updates from CRM to bot.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator


class SubscriptionWebhookPayload(BaseModel):
    """
    Payload for subscription status change webhook.
    
    Attributes:
        user_id: Messenger-specific ID of user
        messenger: Messenger platform ("telegram" or "max")
        subscription_status: New subscription status (active, expired, none)
        subscription_end_date: Subscription expiration date (required if status="active")
    """
    
    user_id: int = Field(..., description="Messenger-specific ID of user")
    messenger: str = Field(..., description="Messenger platform (telegram or max)")
    subscription_status: str = Field(..., description="New subscription status (active, expired, none)")
    subscription_end_date: datetime | None = Field(None, description="Subscription expiration date")
    
    @field_validator("user_id")
    @classmethod
    def validate_positive_id(cls, v: int) -> int:
        """Validate that user_id is a positive integer."""
        if v <= 0:
            raise ValueError("user_id must be a positive integer")
        return v
    
    @field_validator("messenger")
    @classmethod
    def validate_messenger_type(cls, v: str) -> str:
        """Validate that messenger is either 'telegram' or 'max'."""
        if v.lower() not in ("telegram", "max"):
            raise ValueError("messenger must be 'telegram' or 'max'")
        return v.lower()
    
    @field_validator("subscription_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate that subscription_status is one of: active, expired, none."""
        if not v or not v.strip():
            raise ValueError("subscription_status must be a non-empty string")
        
        v = v.strip().lower()
        if v not in ("active", "expired", "none"):
            raise ValueError("subscription_status must be one of: active, expired, none")
        
        return v
    
    @model_validator(mode="after")
    def validate_subscription_end_date_required(self) -> "SubscriptionWebhookPayload":
        """Validate that subscription_end_date is provided when status='active'."""
        if self.subscription_status.lower() == "active" and self.subscription_end_date is None:
            raise ValueError("subscription_end_date is required when subscription_status='active'")
        
        # Validate that end_date is in the future if status is active
        if self.subscription_status.lower() == "active" and self.subscription_end_date:
            # Make end_date timezone-aware if it isn't
            end_date = self.subscription_end_date
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            if end_date < now:
                raise ValueError("subscription_end_date must be in the future when status='active'")
        
        return self


class SubscriptionWebhookResponse(BaseModel):
    """
    Response for subscription status change webhook.
    
    Attributes:
        status: Operation status ("success" or "error")
        message: Human-readable status message
        user_id: User ID that was updated
        subscription_status: Subscription status that was applied
    """
    
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable status message")
    user_id: int = Field(..., description="User ID that was updated")
    subscription_status: str = Field(..., description="Subscription status that was applied")
