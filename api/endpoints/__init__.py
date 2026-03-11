"""
API Endpoints Package

This package contains API endpoints for external systems (CRM) to query data from the bot.
"""

from api.endpoints.ticket_history import router as ticket_history_router

__all__ = ["ticket_history_router"]
