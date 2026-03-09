"""
NPS Survey Keyboards

Inline keyboards for NPS rating collection.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import SurveyType


def build_nps_keyboard(survey_type: SurveyType, trigger_event_id: int) -> InlineKeyboardMarkup:
    """
    Build inline keyboard with rating buttons 0-10 for NPS survey.
    
    Args:
        survey_type: Type of survey (LOYALTY or SERVICE_QUALITY)
        trigger_event_id: ID of the trigger event (invoice_id or ticket_id)
        
    Returns:
        InlineKeyboardMarkup with 11 buttons in 2 rows:
        - Row 1: [0] [1] [2] [3] [4] [5]
        - Row 2: [6] [7] [8] [9] [10]
        
    Callback data format: "nps_rating:{survey_type}:{rating}:{trigger_event_id}"
    """
    # First row: ratings 0-5
    row1 = [
        InlineKeyboardButton(
            text=str(rating),
            callback_data=f"nps_rating:{survey_type.value}:{rating}:{trigger_event_id}"
        )
        for rating in range(6)
    ]
    
    # Second row: ratings 6-10
    row2 = [
        InlineKeyboardButton(
            text=str(rating),
            callback_data=f"nps_rating:{survey_type.value}:{rating}:{trigger_event_id}"
        )
        for rating in range(6, 11)
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])
