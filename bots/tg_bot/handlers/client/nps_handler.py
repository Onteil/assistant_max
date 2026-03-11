"""
NPS Survey Handler

Handles NPS survey delivery and rating collection for Telegram bot.
Sends surveys triggered by payment confirmations or ticket closures,
collects user ratings on 0-10 scale, and processes responses.

Requirements: 4.1-4.5, 11.1-11.5
"""

import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.keyboards.nps_keyboards import build_nps_keyboard
from database.models import SurveyType, User
from services.nps_handler import handle_rating_response, send_to_crm, format_thank_you_message
from utils.time_helpers import format_relative_time

logger = logging.getLogger(__name__)

# Create router for NPS handlers
router = Router(name="nps")


async def send_nps_survey(
    bot: Bot,
    user_id: int,
    survey_type: SurveyType,
    event_description: str,
    trigger_event_id: int,
    event_date: datetime
) -> bool:
    """
    Send NPS survey message to user via Telegram.
    
    Args:
        bot: Telegram Bot instance
        user_id: Telegram user ID to send survey to
        survey_type: Type of survey (LOYALTY or SERVICE_QUALITY)
        event_description: Description of the trigger event (e.g., invoice number, ticket number)
        trigger_event_id: ID of the trigger event for callback tracking
        event_date: Date when the trigger event occurred
        
    Returns:
        True if survey was sent successfully, False otherwise
        
    Examples:
        >>> await send_nps_survey(
        ...     bot=bot,
        ...     user_id=123456789,
        ...     survey_type=SurveyType.LOYALTY,
        ...     event_description="INV-12345",
        ...     trigger_event_id=12345,
        ...     event_date=datetime(2024, 2, 10)
        ... )
        True
    """
    try:
        # Format relative time expression
        time_expression = format_relative_time(event_date)
        
        # Build message text based on survey type
        if survey_type == SurveyType.LOYALTY:
            message_text = (
                f"Здравствуйте! 👋\n\n"
                f"{time_expression.capitalize()} вы оплатили счет в АЙТАТ. "
                f"Мы понимаем, что ваше время ценно, но нам очень важно ваше мнение! 🙏\n\n"
                f"Оцените, пожалуйста, от 0 до 10: насколько вероятно, что вы порекомендуете нас коллегам?\n\n"
                f"С уважением,\nКоманда АЙТАТ 💙"
            )
        elif survey_type == SurveyType.SERVICE_QUALITY:
            message_text = (
                f"Здравствуйте! 👋\n\n"
                f"{time_expression.capitalize()} вы обращались в техподдержку (заявка #{event_description}). "
                f"Мы ценим ваше время и будем благодарны за минутку обратной связи! 🙏\n\n"
                f"Оцените, пожалуйста, качество решения от 0 до 10.\n\n"
                f"С уважением,\nКоманда АЙТАТ 💙"
            )
        else:
            logger.error(f"Unknown survey type: {survey_type}")
            return False
        
        # Build inline keyboard with rating buttons
        keyboard = build_nps_keyboard(survey_type, trigger_event_id)
        
        # Send survey message
        await bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=keyboard
        )
        
        logger.info(
            f"NPS survey sent successfully: user_id={user_id}, "
            f"survey_type={survey_type.value}, trigger_event_id={trigger_event_id}"
        )
        return True
        
    except Exception as e:
        logger.error(
            f"Failed to send NPS survey: user_id={user_id}, "
            f"survey_type={survey_type.value}, error={str(e)}",
            exc_info=True
        )
        return False



@router.callback_query(F.data.startswith("nps_rating:"))
async def handle_nps_rating_callback(
    callback: CallbackQuery,
    session: AsyncSession
) -> None:
    """
    Handle NPS rating button press.
    
    Parses callback data, stores response in database, sends to CRM,
    and displays thank you message to user.
    
    Callback data format: "nps_rating:{survey_type}:{rating}:{trigger_event_id}"
    
    Args:
        callback: Callback query from inline button press
        session: Database session (injected by middleware)
        
    Requirements: 4.4, 4.5, 5.2, 5.3
    """
    try:
        # Parse callback data
        # Format: "nps_rating:{survey_type}:{rating}:{trigger_event_id}"
        parts = callback.data.split(":")
        
        if len(parts) != 4:
            logger.error(f"Invalid callback data format: {callback.data}")
            await callback.answer("Ошибка обработки ответа", show_alert=True)
            return
        
        survey_type_str = parts[1]
        rating_str = parts[2]
        trigger_event_id_str = parts[3]
        
        # Convert survey type string to enum
        try:
            survey_type = SurveyType(survey_type_str)
        except ValueError:
            logger.error(f"Invalid survey type: {survey_type_str}")
            await callback.answer("Ошибка обработки ответа", show_alert=True)
            return
        
        # Convert rating to integer
        try:
            rating = int(rating_str)
        except ValueError:
            logger.error(f"Invalid rating value: {rating_str}")
            await callback.answer("Ошибка обработки ответа", show_alert=True)
            return
        
        # Convert trigger_event_id to integer
        try:
            trigger_event_id = int(trigger_event_id_str)
        except ValueError:
            logger.error(f"Invalid trigger_event_id: {trigger_event_id_str}")
            await callback.answer("Ошибка обработки ответа", show_alert=True)
            return
        
        # Get user's internal database ID from Telegram user ID
        telegram_user_id = callback.from_user.id
        
        stmt = select(User).where(User.tg_user_id == telegram_user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User not found for telegram_user_id: {telegram_user_id}")
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Store rating response in database
        success, message = await handle_rating_response(
            session=session,
            user_id=user.id,
            rating=rating,
            survey_type=survey_type,
            trigger_event_id=trigger_event_id
        )
        
        if not success:
            logger.error(f"Failed to store NPS response: {message}")
            await callback.answer("Ошибка сохранения ответа", show_alert=True)
            return
        
        # CRM integration temporarily disabled - i-TAT API endpoint not ready (405 error)
        # Data is stored in database and can be synced later when endpoint is available
        # TODO: Re-enable when i-TAT implements /nps/response endpoint
        logger.info(
            f"NPS response stored in database (CRM sync disabled): "
            f"user_id={user.id}, rating={rating}, survey_type={survey_type.value}"
        )
        
        # Get thank you message
        thank_you_text = format_thank_you_message()
        
        # Answer callback query to remove loading state
        await callback.answer()
        
        # Edit original message to show selected rating
        confirmation_text = (
            f"Вы выбрали оценку: {rating}\n\n"
            f"{thank_you_text}"
        )
        
        try:
            await callback.message.edit_text(
                text=confirmation_text,
                reply_markup=None  # Remove keyboard
            )
        except Exception as e:
            # If edit fails (message too old, etc.), send new message
            logger.warning(f"Failed to edit message: {e}")
            await callback.message.answer(confirmation_text)
        
        logger.info(
            f"NPS rating processed successfully: user_id={user.id}, "
            f"telegram_user_id={telegram_user_id}, rating={rating}, "
            f"survey_type={survey_type.value}"
        )
        
    except Exception as e:
        logger.error(
            f"Unexpected error in NPS callback handler: {e}",
            exc_info=True
        )
        await callback.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)
