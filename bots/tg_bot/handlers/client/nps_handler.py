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
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.keyboards.nps_keyboards import build_nps_keyboard, build_review_links_keyboard
from bots.tg_bot.states import NPSStates
from database.models import SurveyType, User, NPS_Response
from services.nps_handler import (
    handle_rating_response,
    send_to_crm,
    format_thank_you_message,
    notify_staff_about_low_rating,
)
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
    session: AsyncSession,
    state: FSMContext
) -> None:
    """
    Handle NPS rating button press.
    
    Parses callback data, stores response in database, and:
    - For ratings 0-7: Asks for feedback comment
    - For ratings 8-10: Shows thank you with review links (2GIS, Yandex)
    
    Callback data format: "nps_rating:{survey_type}:{rating}:{trigger_event_id}"
    
    Args:
        callback: Callback query from inline button press
        session: Database session (injected by middleware)
        state: FSM context for state management
        
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
        
        logger.info(
            f"NPS response stored in database: "
            f"user_id={user.id}, rating={rating}, survey_type={survey_type.value}"
        )
        
        # Answer callback query to remove loading state
        await callback.answer()
        
        # Different flow based on rating
        if rating <= 7:
            # Low rating (0-7): Ask for feedback
            await state.set_state(NPSStates.waiting_for_feedback)
            await state.update_data(
                rating=rating,
                survey_type=survey_type.value,
                trigger_event_id=trigger_event_id
            )
            
            feedback_text = (
                f"Спасибо за вашу оценку: {rating}\n\n"
                f"Нам очень важно ваше мнение! 🙏\n"
                f"Пожалуйста, напишите, что мы можем улучшить?"
            )
            
            # Build keyboard with "Skip" button
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⏭️️ Пропустить",
                    callback_data=f"nps_skip_feedback:{survey_type.value}:{rating}:{trigger_event_id}"
                )]
            ])
            
            try:
                await callback.message.edit_text(
                    text=feedback_text,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.warning(f"Failed to edit message: {e}")
                await callback.message.answer(feedback_text, reply_markup=keyboard)
            
            logger.info(f"Requested feedback for low rating: user_id={user.id}, rating={rating}")
            
        else:
            # High rating (8-10): Show thank you with review links
            thank_you_text = format_thank_you_message()
            
            confirmation_text = (
                f"Спасибо за высокую оценку: {rating}! 🎉\n\n"
                f"{thank_you_text}\n\n"
                f"Если вам не сложно, оставьте, пожалуйста, отзыв на одной из площадок. "
                f"Это очень поможет нам! 💙"
            )
            
            # Build keyboard with review links
            keyboard = build_review_links_keyboard()
            
            try:
                await callback.message.edit_text(
                    text=confirmation_text,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.warning(f"Failed to edit message: {e}")
                await callback.message.answer(confirmation_text, reply_markup=keyboard)
            
            logger.info(f"Sent review request for high rating: user_id={user.id}, rating={rating}")
        
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


@router.message(F.text, NPSStates.waiting_for_feedback)
async def handle_nps_feedback(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle user feedback comment for low NPS rating (0-7).
    
    Stores the feedback comment in database and shows thank you message.
    
    Args:
        message: Message with user's feedback text
        state: FSM context with rating data
        session: Database session
    """
    try:
        telegram_user_id = message.from_user.id
        feedback_text = message.text
        
        # Get data from state
        data = await state.get_data()
        rating = data.get('rating')
        survey_type_str = data.get('survey_type')
        trigger_event_id = data.get('trigger_event_id')
        
        # Validate state data
        if rating is None or not survey_type_str:
            logger.error(f"Missing required data in state: {data}")
            await message.answer("Произошла ошибка. Попробуйте позже.")
            await state.clear()
            return
        
        # Get user from database
        stmt = select(User).where(User.tg_user_id == telegram_user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User not found for telegram_user_id: {telegram_user_id}")
            await state.clear()
            return
        
        # Update NPS response with feedback comment
        stmt = (
            update(NPS_Response)
            .where(
                NPS_Response.user_id == user.id,
                NPS_Response.rating == rating,
                NPS_Response.feedback_comment.is_(None)
            )
            .values(feedback_comment=feedback_text)
            .execution_options(synchronize_session="fetch")
        )
        result = await session.execute(stmt)
        await session.commit()
        
        if result.rowcount == 0:
            logger.warning(
                f"No NPS response found to update: user_id={user.id}, rating={rating}"
            )
        else:
            logger.info(
                f"NPS feedback stored: user_id={user.id}, rating={rating}, "
                f"feedback_length={len(feedback_text)}, rows_updated={result.rowcount}"
            )
            
            # Send notification to staff about low rating with feedback
            try:
                survey_type_enum = SurveyType(survey_type_str)
                await notify_staff_about_low_rating(
                    session=session,
                    user=user,
                    rating=rating,
                    survey_type=survey_type_enum,
                    feedback_comment=feedback_text
                )
            except Exception as e:
                logger.error(
                    f"Failed to send staff notification for low NPS: "
                    f"user_id={user.id}, rating={rating}, error={e}",
                    exc_info=True
                )
        
        # Clear FSM state
        await state.clear()
        
        # Send thank you message
        thank_you_text = format_thank_you_message()
        confirmation_text = (
            f"Спасибо за ваш отзыв! 🙏\n\n"
            f"{thank_you_text}\n\n"
            f"Мы обязательно учтём ваши пожелания и постараемся стать лучше! 💙"
        )
        
        await message.answer(confirmation_text)
        
        logger.info(f"NPS feedback processed successfully: user_id={user.id}")
        
    except Exception as e:
        logger.error(
            f"Unexpected error in NPS feedback handler: {e}",
            exc_info=True
        )
        await state.clear()


@router.callback_query(F.data.startswith("nps_skip_feedback:"))
async def handle_nps_skip_feedback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """
    Handle "Skip" button press for feedback request.
    
    Sends notification to staff without feedback comment.
    
    Callback data format: "nps_skip_feedback:{survey_type}:{rating}:{trigger_event_id}"
    
    Args:
        callback: Callback query from "Skip" button press
        state: FSM context with rating data
        session: Database session
    """
    try:
        # Parse callback data
        parts = callback.data.split(":")
        
        if len(parts) != 4:
            logger.error(f"Invalid callback data format: {callback.data}")
            await callback.answer("Ошибка обработки ответа", show_alert=True)
            return
        
        survey_type_str = parts[1]
        rating_str = parts[2]
        trigger_event_id_str = parts[3]
        
        # Convert to proper types
        try:
            survey_type = SurveyType(survey_type_str)
            rating = int(rating_str)
            trigger_event_id = int(trigger_event_id_str)
        except (ValueError, KeyError) as e:
            logger.error(f"Invalid callback data values: {e}")
            await callback.answer("Ошибка обработки ответа", show_alert=True)
            return
        
        # Get user from database
        telegram_user_id = callback.from_user.id
        stmt = select(User).where(User.tg_user_id == telegram_user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User not found for telegram_user_id: {telegram_user_id}")
            await state.clear()
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Answer callback query
        await callback.answer()
        
        # Clear FSM state
        await state.clear()
        
        # Send notification to staff about low rating WITHOUT feedback
        try:
            await notify_staff_about_low_rating(
                session=session,
                user=user,
                rating=rating,
                survey_type=survey_type,
                feedback_comment=None  # User skipped feedback
            )
        except Exception as e:
            logger.error(
                f"Failed to send staff notification for low NPS (skipped): "
                f"user_id={user.id}, rating={rating}, error={e}",
                exc_info=True
            )
        
        # Send thank you message
        thank_you_text = format_thank_you_message()
        confirmation_text = (
            f"Спасибо за вашу оценку! 🙏\n\n"
            f"{thank_you_text}"
        )
        
        try:
            await callback.message.edit_text(
                text=confirmation_text,
                reply_markup=None
            )
        except Exception as e:
            logger.warning(f"Failed to edit message: {e}")
            await callback.message.answer(confirmation_text)
        
        logger.info(f"NPS feedback skipped: user_id={user.id}, rating={rating}")
        
    except Exception as e:
        logger.error(
            f"Unexpected error in NPS skip feedback handler: {e}",
            exc_info=True
        )
        await state.clear()
        await callback.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)
