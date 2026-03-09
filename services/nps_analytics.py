"""
NPS Analytics Service

Provides analytics and reporting functions for NPS survey data.
Calculates NPS scores, response breakdowns, and trend analysis.

Requirements: 10.1, 10.2, 10.3, 10.5
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import NPS_Response, SurveyType

logger = logging.getLogger(__name__)


async def calculate_nps_score(
    session: AsyncSession,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    survey_type: Optional[SurveyType] = None
) -> dict:
    """
    Calculate NPS score and response breakdown.
    
    NPS Score = (% Promoters - % Detractors)
    - Promoters: ratings 9-10
    - Passives: ratings 7-8
    - Detractors: ratings 0-6
    
    Args:
        session: Database session
        start_date: Optional start date filter
        end_date: Optional end date filter
        survey_type: Optional survey type filter (LOYALTY or SERVICE_QUALITY)
    
    Returns:
        dict with:
            - nps_score: int (-100 to 100)
            - promoters: int (count of ratings 9-10)
            - passives: int (count of ratings 7-8)
            - detractors: int (count of ratings 0-6)
            - total_responses: int
            - response_rate: float (placeholder, requires additional data)
    
    Requirements: 10.1, 10.2, 13.4
    """
    logger.info(
        f"Calculating NPS score: start_date={start_date}, end_date={end_date}, "
        f"survey_type={survey_type.value if survey_type else 'all'}, "
        f"action=calculate_nps"
    )
    
    try:
        # Build base query
        query = select(NPS_Response.rating)
        
        # Apply filters
        filters = []
        if start_date:
            filters.append(NPS_Response.responded_at >= start_date)
        if end_date:
            filters.append(NPS_Response.responded_at <= end_date)
        if survey_type:
            filters.append(NPS_Response.survey_type == survey_type)
        
        if filters:
            query = query.where(and_(*filters))
        
        # Execute query
        result = await session.execute(query)
        ratings = result.scalars().all()
        
        # Count responses by category
        promoters = sum(1 for r in ratings if r >= 9)
        passives = sum(1 for r in ratings if 7 <= r <= 8)
        detractors = sum(1 for r in ratings if r <= 6)
        total_responses = len(ratings)
        
        # Calculate NPS score
        if total_responses > 0:
            promoter_percentage = (promoters / total_responses) * 100
            detractor_percentage = (detractors / total_responses) * 100
            nps_score = int(promoter_percentage - detractor_percentage)
        else:
            nps_score = 0
            logger.info(
                f"No NPS responses found for filters: start_date={start_date}, "
                f"end_date={end_date}, survey_type={survey_type.value if survey_type else 'all'}, "
                f"action=calculate_nps, result=no_data"
            )
        
        # Response rate calculation would require total surveys sent
        # For now, return 0.0 as placeholder
        response_rate = 0.0
        
        logger.info(
            f"NPS score calculated: nps_score={nps_score}, promoters={promoters}, "
            f"passives={passives}, detractors={detractors}, "
            f"total_responses={total_responses}, "
            f"survey_type={survey_type.value if survey_type else 'all'}, "
            f"action=calculate_nps, result=success"
        )
        
        return {
            "nps_score": nps_score,
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
            "total_responses": total_responses,
            "response_rate": response_rate
        }
    
    except Exception as e:
        logger.error(
            f"Error calculating NPS score: start_date={start_date}, "
            f"end_date={end_date}, survey_type={survey_type.value if survey_type else 'all'}, "
            f"action=calculate_nps, result=error, error={e}",
            exc_info=True
        )
        raise


async def get_nps_trend(
    session: AsyncSession,
    period: str = "month",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    survey_type: Optional[SurveyType] = None
) -> list[dict]:
    """
    Get NPS score trend over time grouped by period.
    
    Args:
        session: Database session
        period: Grouping period - "day", "week", or "month"
        start_date: Optional start date filter
        end_date: Optional end date filter
        survey_type: Optional survey type filter
    
    Returns:
        List of dicts with:
            - date: datetime (start of period)
            - nps_score: int
            - response_count: int
    
    Requirements: 10.5, 13.4
    """
    logger.info(
        f"Calculating NPS trend: period={period}, start_date={start_date}, "
        f"end_date={end_date}, survey_type={survey_type.value if survey_type else 'all'}, "
        f"action=calculate_trend"
    )
    
    try:
        # Determine date truncation based on period
        if period == "day":
            date_trunc = func.date_trunc('day', NPS_Response.responded_at)
        elif period == "week":
            date_trunc = func.date_trunc('week', NPS_Response.responded_at)
        elif period == "month":
            date_trunc = func.date_trunc('month', NPS_Response.responded_at)
        else:
            logger.warning(f"Invalid period specified: {period}, defaulting to 'month'")
            raise ValueError(f"Invalid period: {period}. Must be 'day', 'week', or 'month'")
        
        # Build query to group by period
        query = select(
            date_trunc.label('period_start'),
            NPS_Response.rating
        )
        
        # Apply filters
        filters = []
        if start_date:
            filters.append(NPS_Response.responded_at >= start_date)
        if end_date:
            filters.append(NPS_Response.responded_at <= end_date)
        if survey_type:
            filters.append(NPS_Response.survey_type == survey_type)
        
        if filters:
            query = query.where(and_(*filters))
        
        # Order by period
        query = query.order_by('period_start')
        
        # Execute query
        result = await session.execute(query)
        rows = result.all()
        
        # Group ratings by period
        period_data = {}
        for row in rows:
            period_start = row.period_start
            rating = row.rating
            
            if period_start not in period_data:
                period_data[period_start] = []
            period_data[period_start].append(rating)
        
        # Calculate NPS for each period
        trend_data = []
        for period_start, ratings in sorted(period_data.items()):
            promoters = sum(1 for r in ratings if r >= 9)
            detractors = sum(1 for r in ratings if r <= 6)
            total = len(ratings)
            
            if total > 0:
                promoter_percentage = (promoters / total) * 100
                detractor_percentage = (detractors / total) * 100
                nps_score = int(promoter_percentage - detractor_percentage)
            else:
                nps_score = 0
            
            trend_data.append({
                "date": period_start,
                "nps_score": nps_score,
                "response_count": total
            })
        
        logger.info(
            f"NPS trend calculated: period={period}, periods_count={len(trend_data)}, "
            f"survey_type={survey_type.value if survey_type else 'all'}, "
            f"action=calculate_trend, result=success"
        )
        
        return trend_data
    
    except Exception as e:
        logger.error(
            f"Error calculating NPS trend: period={period}, start_date={start_date}, "
            f"end_date={end_date}, survey_type={survey_type.value if survey_type else 'all'}, "
            f"action=calculate_trend, result=error, error={e}",
            exc_info=True
        )
        raise
