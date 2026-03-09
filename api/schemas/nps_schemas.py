"""Pydantic schemas for NPS Survey System validation."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class PaymentWebhookPayload(BaseModel):
    """
    Webhook payload for payment confirmation from 1C CRM.
    
    Used to trigger LOYALTY surveys after invoice payment.
    Supports both Telegram and MAX messengers.
    """
    messenger: Literal["telegram", "max"] = Field(..., description="Messenger type (telegram or max)")
    user_id: int = Field(..., description="Messenger user ID (telegram_user_id or max_user_id)")
    payment_date: datetime = Field(..., description="Payment timestamp")
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v: int) -> int:
        """Validate that user_id is positive."""
        if v <= 0:
            raise ValueError('user_id must be positive')
        return v


class CRMNPSPayload(BaseModel):
    """
    Payload for sending NPS data to 1C CRM.
    
    Sent after user submits rating to integrate with CRM analytics.
    """
    telegram_id: int = Field(..., description="User's Telegram ID")
    rating: int = Field(..., ge=0, le=10, description="NPS rating (0-10)")
    survey_type: str = Field(..., description="Survey type: 'loyalty' or 'service_quality'")
    event_date: datetime = Field(..., description="Original trigger event timestamp")
    response_timestamp: datetime = Field(..., description="When user submitted rating")


class NPSAnalyticsResponse(BaseModel):
    """
    Response model for NPS analytics endpoints.
    
    Provides calculated NPS score and breakdown statistics.
    """
    nps_score: int = Field(..., description="Net Promoter Score (-100 to 100)")
    promoters: int = Field(..., description="Count of ratings 9-10")
    passives: int = Field(..., description="Count of ratings 7-8")
    detractors: int = Field(..., description="Count of ratings 0-6")
    total_responses: int = Field(..., description="Total number of responses")
    response_rate: float = Field(..., ge=0.0, le=1.0, description="Response rate (0.0-1.0)")
