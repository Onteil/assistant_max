"""
NPS Survey Handler for MAX Bot

Handles NPS survey delivery and rating collection for MAX bot.
Sends surveys triggered by payment confirmations or ticket closures,
collects user ratings on 0-10 scale, and processes responses.
"""

import logging
from datetime import datetime

from maxapi import Bot, F, Router
from maxapi.types import MessageCallback, MessageCreated
from maxapi.types.attachments.buttons import CallbackButton, LinkButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from maxapi.context import MemoryContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.states import NPSStates
from database.models import SurveyType, User
from services.nps_handler import handle_rating_response, format_thank_you_message
from utils.time_helpers import format_relative_time

logger = logging.getLogger(__name__)

# Create router for NPS handlers
router = Router()


async def send_nps_survey(
    bot: Bot,
    user_id: int,  # This is chat_id for MAX
    survey_type: SurveyType,
    event_description: str,
    trigger_event_id: int,
    event_date: datetime
) -> bool:
    """
    Send NPS survey message to user via MAX bot.
    
    Args:
        bot: MAX Bot instance
        user_id: MAX chat_id to send survey to
        survey_type: Type of survey (LOYALTY or SERVICE_QUALITY)
        event_description: Description of the trigger event (e.g., invoice number, ticket number)
        trigger_event_id: ID of the trigger event for callback tracking
        event_date: Date when the trigger event occurred
        
    Returns:
        True if survey was sent successfully, False otherwise
    """
    try:
        # Format relative time expression
        time_expression = format_relative_time(event_date)
        
        # Build message text based on survey type (no HTML tags for MAX)
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
        
        # Build inline keyboard with rating buttons (0-10)
        builder = InlineKeyboardBuilder()
        
        # Add rating buttons in rows of 4
        # Row 1: 0-3
        builder.row(
            CallbackButton(text="0", payload=f"nps_rating:{survey_type.value}:0:{trigger_event_id}"),
            CallbackButton(text="1", payload=f"nps_rating:{survey_type.value}:1:{trigger_event_id}"),
            CallbackButton(text="2", payload=f"nps_rating:{survey_type.value}:2:{trigger_event_id}"),
            CallbackButton(text="3", payload=f"nps_rating:{survey_type.value}:3:{trigger_event_id}")
        )
        
        # Row 2: 4-7
        builder.row(
            CallbackButton(text="4", payload=f"nps_rating:{survey_type.value}:4:{trigger_event_id}"),
            CallbackButton(text="5", payload=f"nps_rating:{survey_type.value}:5:{trigger_event_id}"),
            CallbackButton(text="6", payload=f"nps_rating:{survey_type.value}:6:{trigger_event_id}"),
            CallbackButton(text="7", payload=f"nps_rating:{survey_type.value}:7:{trigger_event_id}")
        )
        
        # Row 3: 8-10
        builder.row(
            CallbackButton(text="8", payload=f"nps_rating:{survey_type.value}:8:{trigger_event_id}"),
            CallbackButton(text="9", payload=f"nps_rating:{survey_type.value}:9:{trigger_event_id}"),
            CallbackButton(text="10", payload=f"nps_rating:{survey_type.value}:10:{trigger_event_id}")
        )
        
        keyboard = builder.as_markup()
        
        # Send survey message
        await bot.send_message(
            chat_id=user_id,
            text=message_text,
            attachments=[keyboard]
        )
        
        logger.info(
            f"MAX NPS survey sent successfully: chat_id={user_id}, "
            f"survey_type={survey_type.value}, trigger_event_id={trigger_event_id}"
        )
        return True
        
    except Exception as e:
        logger.error(
            f"Failed to send MAX NPS survey: chat_id={user_id}, "
            f"survey_type={survey_type.value}, error={str(e)}",
            exc_info=True
        )
        return False


@router.message_callback(F.callback.payload.startswith("nps_rating:"))
async def handle_nps_rating_callback(
    event: MessageCallback,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    context: MemoryContext
) -> None:
    """
    Handle NPS rating button press.
    
    Parses callback data, stores response in database, and:
    - For ratings 0-7: Asks for feedback comment
    - For ratings 8-10: Shows thank you with review links (2GIS, Yandex)
    
    Callback data format: "nps_rating:{survey_type}:{rating}:{trigger_event_id}"
    
    Args:
        event: MessageCallback from inline button press
        session: Database session (injected by middleware)
        messenger_adapter: MAX messenger adapter (injected by middleware)
        context: FSM context for state management
    """
    try:
        chat_id = event.message.recipient.chat_id
        max_user_id = event.callback.user.user_id
        message_id = event.message.body.mid if hasattr(event.message.body, 'mid') else None
        
        # Parse callback data
        # Format: "nps_rating:{survey_type}:{rating}:{trigger_event_id}"
        parts = event.callback.payload.split(":")
        
        if len(parts) != 4:
            logger.error(f"Invalid callback data format: {event.callback.payload}")
            return
        
        survey_type_str = parts[1]
        rating_str = parts[2]
        trigger_event_id_str = parts[3]
        
        # Convert survey type string to enum
        try:
            survey_type = SurveyType(survey_type_str)
        except ValueError:
            logger.error(f"Invalid survey type: {survey_type_str}")
            return
        
        # Convert rating to integer
        try:
            rating = int(rating_str)
        except ValueError:
            logger.error(f"Invalid rating value: {rating_str}")
            return
        
        # Convert trigger_event_id to integer
        try:
            trigger_event_id = int(trigger_event_id_str)
        except ValueError:
            logger.error(f"Invalid trigger_event_id: {trigger_event_id_str}")
            return
        
        # Get user's internal database ID from MAX user ID
        stmt = select(User).where(User.max_user_id == max_user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User not found for max_user_id: {max_user_id}")
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
            return
        
        logger.info(
            f"NPS response stored in database: "
            f"user_id={user.id}, rating={rating}, survey_type={survey_type.value}"
        )
        
        # Delete old message with buttons (replace_message pattern)
        if message_id:
            try:
                await messenger_adapter.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Failed to delete old message: {e}")
        
        # Different flow based on rating
        if rating <= 7:
            # Low rating (0-7): Ask for feedback
            await context.set_state(NPSStates.waiting_for_feedback)
            await context.update_data(
                rating=rating,
                survey_type=survey_type.value,
                trigger_event_id=trigger_event_id
            )
            
            feedback_text = (
                f"Спасибо за вашу оценку: {rating}\n\n"
                f"Нам очень важно ваше мнение! 🙏\n"
                f"Пожалуйста, напишите, что мы можем улучшить?"
            )
            
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=feedback_text,
                parse_mode="HTML"
            )
            
            logger.info(f"Requested feedback for low rating: user_id={user.id}, rating={rating}")
            
        else:
            # High rating (8-10): Show thank you with review links
            thank_you_text = format_thank_you_message()
            
            # Build keyboard with review links
            builder = InlineKeyboardBuilder()
            builder.row(
                LinkButton(
                    text="⭐ Оставить отзыв на 2ГИС",
                    url="https://2gis.ru/nabchelny/branches/4081924033218712/firm/70000001047304265/52.449828%2C55.738183/tab/reviews?m=52.448955%2C55.72034%2F12.71"
                )
            )
            builder.row(
                LinkButton(
                    text="⭐ Оставить отзыв на Яндекс",
                    url="https://yandex.com/maps/org/i_tat/1247186021/reviews/?ll=49.160695%2C55.789136&tab=reviews&z=13.88"
                )
            )
            
            confirmation_text = (
                f"Спасибо за высокую оценку: {rating}! 🎉\n\n"
                f"{thank_you_text}\n\n"
                f"Если вам не сложно, оставьте, пожалуйста, отзыв на одной из площадок. "
                f"Это очень поможет нам! 💙"
            )
            
            keyboard_attachment = builder.as_markup()
            
            # Send message with keyboard using bot directly (not messenger_adapter)
            from maxapi import Bot as MAXBot
            from constants import MAX_BOT_TOKEN
            
            bot = MAXBot(token=MAX_BOT_TOKEN)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=confirmation_text,
                    attachments=[keyboard_attachment]
                )
            finally:
                await bot.session.close()
            
            logger.info(f"Sent review request for high rating: user_id={user.id}, rating={rating}")
        
        logger.info(
            f"NPS rating processed successfully: user_id={user.id}, "
            f"max_user_id={max_user_id}, rating={rating}, "
            f"survey_type={survey_type.value}"
        )
        
    except Exception as e:
        logger.error(
            f"Unexpected error in NPS callback handler: {e}",
            exc_info=True
        )



@router.message_created(F.message.body.text, NPSStates.waiting_for_feedback)
async def handle_nps_feedback(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter
) -> None:
    """
    Handle user feedback comment for low NPS rating (0-7).
    
    Stores the feedback comment in database and shows thank you message.
    
    Args:
        event: MessageCreated event with user's feedback text
        context: FSM context with rating data
        session: Database session
        messenger_adapter: MAX messenger adapter
    """
    try:
        chat_id = event.message.recipient.chat_id
        max_user_id = event.message.sender.user_id
        feedback_text = event.message.body.text
        
        # Get data from context
        data = await context.get_data()
        rating = data.get('rating')
        survey_type_str = data.get('survey_type')
        trigger_event_id = data.get('trigger_event_id')
        
        # Validate context data (trigger_event_id can be 0 for test surveys)
        if rating is None or not survey_type_str:
            logger.error(f"Missing required data in context: {data}")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="Произошла ошибка. Попробуйте позже.",
                parse_mode="HTML"
            )
            await context.clear()
            return
        
        # Get user from database
        stmt = select(User).where(User.max_user_id == max_user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User not found for max_user_id: {max_user_id}")
            await context.clear()
            return
        
        # Update NPS response with feedback comment
        from database.models import NPS_Response
        from sqlalchemy import update
        
        # For test surveys, trigger_event_id might be 0
        # Find the most recent response for this user with matching rating
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
        
        # Clear FSM state
        await context.clear()
        
        # Send thank you message
        thank_you_text = format_thank_you_message()
        confirmation_text = (
            f"Спасибо за ваш отзыв! 🙏\n\n"
            f"{thank_you_text}\n\n"
            f"Мы обязательно учтём ваши пожелания и постараемся стать лучше! 💙"
        )
        
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=confirmation_text,
            parse_mode="HTML"
        )
        
        logger.info(f"NPS feedback processed successfully: user_id={user.id}")
        
    except Exception as e:
        logger.error(
            f"Unexpected error in NPS feedback handler: {e}",
            exc_info=True
        )
        await context.clear()
