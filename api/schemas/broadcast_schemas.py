"""
Pydantic schemas for broadcast campaign webhook.

This module defines request and response schemas for the broadcast campaign
webhook endpoint that schedules mass messaging campaigns to user segments.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class BroadcastWebhookPayload(BaseModel):
    """
    Payload for broadcast campaign webhook.
    
    Attributes:
        campaign_id: Unique campaign identifier
        message_text: Message content to broadcast
        target_audience: Audience type ("all_users", "subscribed_users", or "allow_notification_users")
        schedule_time: When to send the broadcast (ignored if send_now=True)
        messenger: Messenger platform ("telegram" or "max")
        send_now: If True, send immediately; if False, use schedule_time
        manager_messenger_id: Messenger ID (tg_user_id or max_user_id) of staff member who created the broadcast
    """
    
    campaign_id: str = Field(..., min_length=1, description="Unique campaign identifier")
    message_text: str = Field(..., min_length=1, description="Message content to broadcast")
    target_audience: str = Field(..., description="Audience type")
    schedule_time: datetime = Field(..., description="When to send the broadcast")
    messenger: str = Field(..., description="Messenger platform (telegram or max)")
    send_now: bool = Field(default=False, description="Send immediately instead of scheduling")
    manager_messenger_id: int = Field(..., description="Messenger ID of staff member who created the broadcast")
    
    @field_validator("campaign_id", "message_text")
    @classmethod
    def validate_non_empty_string(cls, v: str) -> str:
        """Validate that string fields are non-empty."""
        if not v or not v.strip():
            raise ValueError("Field must be a non-empty string")
        return v.strip()
    
    @field_validator("target_audience")
    @classmethod
    def validate_target_audience(cls, v: str) -> str:
        """Validate that target_audience is a valid value."""
        valid_audiences = ("all_users", "subscribed_users", "allow_notification_users")
        if v.lower() not in valid_audiences:
            raise ValueError(f"target_audience must be one of: {', '.join(valid_audiences)}")
        return v.lower()
    
    @field_validator("messenger")
    @classmethod
    def validate_messenger_type(cls, v: str) -> str:
        """Validate that messenger is either 'telegram' or 'max'."""
        if v.lower() not in ("telegram", "max"):
            raise ValueError("messenger must be 'telegram' or 'max'")
        return v.lower()


class BroadcastWebhookResponse(BaseModel):
    """
    Response for broadcast campaign webhook.
    
    Attributes:
        status: Operation status ("success" or "error")
        message: Human-readable status message
        campaign_id: Campaign ID that was created
        target_count: Number of users targeted
        schedule_time: Scheduled delivery time
    """
    
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable status message")
    campaign_id: str = Field(..., description="Campaign ID that was created")
    target_count: int = Field(..., description="Number of users targeted")
    schedule_time: datetime = Field(..., description="Scheduled delivery time")
