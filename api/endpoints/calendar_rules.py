"""
Calendar Rules API Endpoints

This module implements API endpoints for managing calendar rules (work schedule).
Used by admin panel to test ticket routing based on work mode.
"""

import logging
from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from constants import get_session, WEBHOOK_API_KEY
from database.models import WorkMode
from services.calendar_service import CalendarService, get_current_work_mode

router = APIRouter()
logger = logging.getLogger(__name__)


async def verify_webhook_api_key(
    x_api_key: Annotated[str | None, Header()] = None
) -> str:
    """Verify webhook API key authentication."""
    if not x_api_key:
        logger.warning("Calendar API request received without API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    if not WEBHOOK_API_KEY:
        logger.error("WEBHOOK_API_KEY not configured in environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured on server",
        )
    
    if x_api_key != WEBHOOK_API_KEY:
        logger.warning(f"Invalid API key attempt: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return x_api_key


class CreateCalendarRuleRequest(BaseModel):
    """Request schema for creating calendar rule."""
    start_date: date = Field(..., description="Start date of the rule")
    end_date: date = Field(..., description="End date of the rule")
    work_mode: WorkMode = Field(..., description="Work mode (REGULAR, EXTENDED, NON_WORKING)")
    work_start_time: time | None = Field(None, description="Work start time (required for REGULAR/EXTENDED)")
    work_end_time: time | None = Field(None, description="Work end time (required for REGULAR/EXTENDED)")


class CalendarRuleResponse(BaseModel):
    """Response schema for calendar rule."""
    id: int
    start_date: date
    end_date: date
    work_mode: str
    work_start_time: time | None
    work_end_time: time | None
    rule_priority: int
    message: str


class CurrentWorkModeResponse(BaseModel):
    """Response schema for current work mode."""
    work_mode: str
    description: str
    timestamp: str


class ClearRulesResponse(BaseModel):
    """Response schema for clearing rules."""
    deleted_count: int
    message: str


@router.post("/calendar/rules", response_model=CalendarRuleResponse)
async def create_calendar_rule(
    request: CreateCalendarRuleRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> CalendarRuleResponse:
    """
    Create a new calendar rule to define work schedule.
    
    This endpoint allows testing different work modes:
    - REGULAR: Normal working hours, tickets assigned to managers
    - EXTENDED: Extended hours, tickets assigned to duty staff
    - NON_WORKING: Non-working hours, tickets queued for next working day
    
    Example request:
    POST /api/calendar/rules
    {
        "start_date": "2026-03-01",
        "end_date": "2026-03-01",
        "work_mode": "REGULAR",
        "work_start_time": "08:00:00",
        "work_end_time": "17:00:00"
    }
    """
    logger.info(
        f"Creating calendar rule: {request.start_date} to {request.end_date}, "
        f"mode={request.work_mode}"
    )
    
    try:
        # Validate work hours for REGULAR/EXTENDED modes
        if request.work_mode in [WorkMode.REGULAR, WorkMode.EXTENDED]:
            if not request.work_start_time or not request.work_end_time:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"work_start_time and work_end_time are required for {request.work_mode} mode"
                )
        
        # Create rule using CalendarService
        calendar_service = CalendarService()
        rule = await calendar_service.create_rule(
            session=session,
            start_date=request.start_date,
            end_date=request.end_date,
            work_mode=request.work_mode,
            work_start_time=request.work_start_time,
            work_end_time=request.work_end_time
        )
        
        # Build response
        response = CalendarRuleResponse(
            id=rule.id,
            start_date=rule.start_date,
            end_date=rule.end_date,
            work_mode=rule.work_mode.value,
            work_start_time=rule.work_start_time,
            work_end_time=rule.work_end_time,
            rule_priority=rule.rule_priority,
            message=f"Calendar rule created successfully (priority={rule.rule_priority})"
        )
        
        logger.info(f"Calendar rule created: id={rule.id}, priority={rule.rule_priority}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating calendar rule: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.get("/calendar/current-mode", response_model=CurrentWorkModeResponse)
async def get_current_work_mode_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> CurrentWorkModeResponse:
    """
    Get current work mode based on Moscow time and calendar rules.
    
    This endpoint helps test ticket routing logic by showing the current work mode.
    """
    logger.info("Checking current work mode")
    
    try:
        from datetime import datetime
        import pytz
        
        # Get current work mode
        work_mode = await get_current_work_mode(session)
        
        # Get current Moscow time
        MOSCOW_TZ = pytz.timezone('Europe/Moscow')
        current_time = datetime.now(MOSCOW_TZ)
        
        # Build description
        descriptions = {
            WorkMode.REGULAR: "Regular working hours - tickets assigned to managers",
            WorkMode.EXTENDED: "Extended hours - tickets assigned to duty staff",
            WorkMode.NON_WORKING: "Non-working hours - tickets queued for next working day"
        }
        
        response = CurrentWorkModeResponse(
            work_mode=work_mode.value,
            description=descriptions.get(work_mode, "Unknown mode"),
            timestamp=current_time.isoformat()
        )
        
        logger.info(f"Current work mode: {work_mode.value}")
        return response
        
    except Exception as e:
        logger.error(f"Error getting current work mode: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.delete("/calendar/rules/clear", response_model=ClearRulesResponse)
async def clear_all_calendar_rules(
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> ClearRulesResponse:
    """
    Clear all calendar rules.
    
    This endpoint removes all custom calendar rules, reverting to base schedule.
    Use with caution - this action cannot be undone.
    """
    logger.warning("Clearing all calendar rules")
    
    try:
        from datetime import date
        
        # Delete all rules using a very wide date range
        calendar_service = CalendarService()
        deleted_count = await calendar_service.delete_rules_in_period(
            session=session,
            start_date=date(2000, 1, 1),
            end_date=date(2100, 12, 31)
        )
        
        response = ClearRulesResponse(
            deleted_count=deleted_count,
            message=f"Successfully deleted {deleted_count} calendar rules. Base schedule is now active."
        )
        
        logger.info(f"Cleared {deleted_count} calendar rules")
        return response
        
    except Exception as e:
        logger.error(f"Error clearing calendar rules: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )
