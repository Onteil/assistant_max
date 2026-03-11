"""
CRM Webhooks Package

This package contains webhook handlers for receiving events from 1C CRM.
All webhooks require API key authentication via X-API-Key header.
"""

from .key_conflict_webhooks import router as key_conflict_router
from .subscription_webhooks import router as subscription_router

__all__ = [
    "key_conflict_router",
    "subscription_router",
]
