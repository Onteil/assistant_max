"""
Renewal service layer for subscription renewal operations.

Provides async functions for formatting subscription status messages,
creating renewal tickets, and managing renewal reminders.

Requirements: 1.1-1.5, 2.1-2.7, 3.1-3.9, 6.1-6.5, 8.1-8.7, 9.2-9.4
"""

import logging
from datetime import datetime
from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from database.models import (
    ActionType,
    SubscriptionStatus,
    Ticket,
    TicketType,
    User,
)
from services.calendar_service import get_current_work_mode
from services.ticket_service import (
    create_ticket,
    route_ticket,
    send_staff_notification,
)

logger = logging.getLogger(__name__)


# ========== Subscription Status Formatting ==========


async def format_subscription_status(user: User) -> str:
    """
    Format subscription status message based on user's subscription.
    
    Creates appropriate message text based on the user's subscription_status
    (ACTIVE/EXPIRED/NONE). For ACTIVE and EXPIRED statuses, includes the
    expiration date formatted as DD.MM.YYYY.
    
    Args:
        user: User object with subscription_status and subscription_end_date
    
    Returns:
        Formatted status message in Russian
    
    Message formats:
        - ACTIVE: "✅ Ваша подписка активна до {DD.MM.YYYY}"
        - EXPIRED: "⚠️ Ваша подписка истекла {DD.MM.YYYY}"
        - NONE: "❌ У вас нет активной подписки на техподдержку"
    
    Requirements: 1.1-1.5, 9.2-9.4
    """
    # Lazy import to avoid circular dependency
    from bots.tg_bot.texts import (
        RENEWAL_STATUS_ACTIVE,
        RENEWAL_STATUS_EXPIRED,
        RENEWAL_STATUS_NONE,
    )
    
    try:
        # Format expiration date if available
        expiry_date_str = ""
        if user.subscription_end_date:
            expiry_date_str = user.subscription_end_date.strftime("%d.%m.%Y")
        
        # Build message text based on subscription status
        if user.subscription_status == SubscriptionStatus.ACTIVE:
            message_text = RENEWAL_STATUS_ACTIVE.format(expiry_date=expiry_date_str)
        
        elif user.subscription_status == SubscriptionStatus.EXPIRED:
            message_text = RENEWAL_STATUS_EXPIRED.format(expiry_date=expiry_date_str)
        
        else:  # SubscriptionStatus.NONE
            message_text = RENEWAL_STATUS_NONE
        
        logger.debug(
            f"Formatted subscription status: user_id={user.id}, "
            f"status={user.subscription_status.value}, "
            f"expiry_date={expiry_date_str or 'N/A'}"
        )
        
        return message_text
    
    except Exception as e:
        logger.error(
            f"Error formatting subscription status: user_id={user.id}, "
            f"status={user.subscription_status.value}, error={e}",
            exc_info=True
        )
        raise


# ========== Renewal Ticket Creation ==========


async def create_renewal_ticket(
    session: AsyncSession,
    user: User,
    bot: Bot
) -> Ticket:
    """
    Create RENEWAL ticket and route to manager.
    
    Creates a renewal ticket assigned to the user's default manager,
    routes it appropriately, sends a Telegram notification to the manager,
    and logs the action in the Action_Log table.
    
    Steps:
    1. Validate user has default_manager_id
    2. Create ticket with type=RENEWAL
    3. Assign to user.default_manager_id
    4. Get current work mode
    5. Route ticket to manager
    6. Send manager notification
    7. Commit transaction (handled by caller)
    
    Args:
        session: Database session (transaction managed by caller)
        user: User object requesting renewal
        bot: Aiogram Bot instance for sending notifications
    
    Returns:
        Created Ticket object
    
    Raises:
        ValueError: If user has no default_manager_id
        SQLAlchemyError: On database errors (transaction rolled back by caller)
    
    Requirements: 2.2-2.7, 6.1-6.5
    """
    try:
        # Validate user has assigned manager
        if not user.default_manager_id:
            logger.error(
                f"User {user.id} has no default_manager_id, cannot create renewal ticket"
            )
            raise ValueError(
                f"User {user.id} has no assigned manager. "
                "Cannot create renewal ticket without manager assignment."
            )
        
        # Prepare ticket data
        ticket_data = {
            "ticket_type": TicketType.RENEWAL,
            "user_id": user.id,
            "assigned_staff_id": user.default_manager_id,
            "description": "Запрос на продление подписки техподдержки"
        }
        
        # Create ticket (this also logs TICKET_CREATED action)
        ticket = await create_ticket(session, ticket_data)
        
        logger.info(
            f"Renewal ticket created: ticket_id={ticket.id}, "
            f"user_id={user.id}, manager_id={user.default_manager_id}"
        )
        
        # Get current work mode for routing
        work_mode = await get_current_work_mode(session)
        
        # Route ticket to manager (RENEWAL tickets always go to manager)
        routing_info = await route_ticket(session, ticket, work_mode)
        
        logger.debug(
            f"Renewal ticket routed: ticket_id={ticket.id}, "
            f"routing={routing_info['target_type']}, "
            f"work_mode={work_mode.value}"
        )
        
        # Send notification to manager
        notification_sent = await send_staff_notification(
            bot=bot,
            staff_id=user.default_manager_id,
            ticket=ticket,
            routing_info=routing_info,
            session=session
        )
        
        if notification_sent:
            logger.info(
                f"Manager notification sent: ticket_id={ticket.id}, "
                f"manager_id={user.default_manager_id}"
            )
        else:
            logger.warning(
                f"Failed to send manager notification: ticket_id={ticket.id}, "
                f"manager_id={user.default_manager_id}"
            )
        
        return ticket
    
    except ValueError:
        # Re-raise validation errors
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error creating renewal ticket: user_id={user.id}, "
            f"manager_id={user.default_manager_id}, error={e}",
            exc_info=True
        )
        raise
    
    except Exception as e:
        logger.error(
            f"Unexpected error creating renewal ticket: user_id={user.id}, "
            f"error={e}",
            exc_info=True
        )
        raise


# ========== Renewal Reminder Scheduling ==========


async def schedule_renewal_reminders(
    session: AsyncSession,
    user: User,
    reminder_days: list[int] = None
) -> list[Any]:
    """
    Schedule renewal reminder notifications for a user.
    
    Creates Notification_Event records for each configured reminder day
    (default: 30 and 7 days before subscription expiration). Checks for
    existing reminders to avoid duplicates. Only schedules reminders for
    users with ACTIVE subscriptions and valid subscription_end_date.
    
    The function calculates the reminder dates by subtracting the reminder
    days from the subscription_end_date. For example, if subscription ends
    on 2024-03-15 and reminder_days=[30, 7], reminders will be scheduled
    for 2024-02-14 and 2024-03-08.
    
    Args:
        session: Database session (transaction managed by caller)
        user: User object to schedule reminders for
        reminder_days: List of days before expiration to send reminders.
                      Defaults to [30, 7] if not provided.
    
    Returns:
        List of created Notification_Event objects (empty if none created)
    
    Raises:
        SQLAlchemyError: On database errors (transaction rolled back by caller)
    
    Requirements: 8.1-8.7
    """
    from datetime import timedelta
    from sqlalchemy import select
    from database.models import Notification_Event, EventType, EventStatus
    
    # Default reminder days if not provided
    if reminder_days is None:
        reminder_days = [30, 7]
    
    try:
        # Validate user has ACTIVE subscription with valid end_date
        if user.subscription_status != SubscriptionStatus.ACTIVE:
            logger.debug(
                f"Skipping reminder scheduling: user_id={user.id}, "
                f"status={user.subscription_status.value} (not ACTIVE)"
            )
            return []
        
        if not user.subscription_end_date:
            logger.warning(
                f"Skipping reminder scheduling: user_id={user.id}, "
                f"subscription_end_date is None"
            )
            return []
        
        created_events = []
        
        # Create reminder for each configured day
        for days in reminder_days:
            # Calculate reminder date (days before expiration)
            reminder_date = user.subscription_end_date - timedelta(days=days)
            
            # Determine event type based on days
            if days == 30:
                event_type = EventType.RENEWAL_REMINDER_30
            elif days == 7:
                event_type = EventType.RENEWAL_REMINDER_7
            else:
                logger.warning(
                    f"Unknown reminder day value: {days}, skipping"
                )
                continue
            
            # Check for existing reminder to avoid duplicates
            existing_query = select(Notification_Event).where(
                Notification_Event.user_id == user.id,
                Notification_Event.event_type == event_type,
                Notification_Event.event_status == EventStatus.SCHEDULED,
                Notification_Event.scheduled_for == reminder_date
            )
            result = await session.execute(existing_query)
            existing_event = result.scalar_one_or_none()
            
            if existing_event:
                logger.debug(
                    f"Reminder already exists: user_id={user.id}, "
                    f"event_type={event_type.value}, "
                    f"scheduled_for={reminder_date.strftime('%Y-%m-%d')}"
                )
                continue
            
            # Create new notification event
            notification_event = Notification_Event(
                user_id=user.id,
                event_type=event_type,
                event_status=EventStatus.SCHEDULED,
                scheduled_for=reminder_date,
                event_data={
                    "subscription_end_date": user.subscription_end_date.isoformat(),
                    "reminder_days": days
                }
            )
            
            session.add(notification_event)
            created_events.append(notification_event)
            
            logger.info(
                f"Scheduled renewal reminder: user_id={user.id}, "
                f"event_type={event_type.value}, "
                f"scheduled_for={reminder_date.strftime('%Y-%m-%d')}, "
                f"subscription_end_date={user.subscription_end_date.strftime('%Y-%m-%d')}"
            )
        
        # Flush to get IDs but don't commit (caller manages transaction)
        if created_events:
            await session.flush()
        
        logger.info(
            f"Reminder scheduling complete: user_id={user.id}, "
            f"created={len(created_events)}, skipped={len(reminder_days) - len(created_events)}"
        )
        
        return created_events
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error scheduling reminders: user_id={user.id}, "
            f"error={e}",
            exc_info=True
        )
        raise
    
    except Exception as e:
        logger.error(
            f"Unexpected error scheduling reminders: user_id={user.id}, "
            f"error={e}",
            exc_info=True
        )
        raise


# ========== Reminder Cancellation ==========


async def cancel_pending_reminders(
    session: AsyncSession,
    user_id: int,
    old_expiration_date: datetime
) -> int:
    """
    Cancel pending renewal reminders for old expiration date.

    Called when a subscription is renewed and the expiration date changes.
    Updates all SCHEDULED Notification_Events associated with the old
    subscription_end_date to CANCELLED status. This prevents users from
    receiving outdated reminders after their subscription has been renewed.

    The function identifies reminders by:
    1. User ID
    2. Event type (RENEWAL_REMINDER_30 or RENEWAL_REMINDER_7)
    3. Event status (SCHEDULED only - don't cancel already SENT/FAILED)
    4. Scheduled date calculated from old_expiration_date

    Args:
        session: Database session (transaction managed by caller)
        user_id: ID of the user whose reminders should be cancelled
        old_expiration_date: Previous subscription_end_date before renewal

    Returns:
        Number of cancelled reminders (0 if none found)

    Raises:
        SQLAlchemyError: On database errors (transaction rolled back by caller)

    Requirements: 8.6
    """
    from datetime import timedelta
    from sqlalchemy import select, update
    from database.models import Notification_Event, EventType, EventStatus

    try:
        # Calculate the expected reminder dates from old expiration date
        reminder_30_date = old_expiration_date - timedelta(days=30)
        reminder_7_date = old_expiration_date - timedelta(days=7)

        # Build query to find pending reminders for old expiration date
        # We match on user_id, event_type, status=SCHEDULED, and scheduled_for date
        query = (
            update(Notification_Event)
            .where(
                Notification_Event.user_id == user_id,
                Notification_Event.event_type.in_([
                    EventType.RENEWAL_REMINDER_30,
                    EventType.RENEWAL_REMINDER_7
                ]),
                Notification_Event.event_status == EventStatus.SCHEDULED,
                Notification_Event.scheduled_for.in_([
                    reminder_30_date,
                    reminder_7_date
                ])
            )
            .values(event_status=EventStatus.CANCELLED)
            .execution_options(synchronize_session="fetch")
        )

        # Execute update
        result = await session.execute(query)
        cancelled_count = result.rowcount

        # Flush to ensure changes are visible in current transaction
        await session.flush()

        if cancelled_count > 0:
            logger.info(
                f"Cancelled pending reminders: user_id={user_id}, "
                f"old_expiration_date={old_expiration_date.strftime('%Y-%m-%d')}, "
                f"cancelled_count={cancelled_count}"
            )
        else:
            logger.debug(
                f"No pending reminders to cancel: user_id={user_id}, "
                f"old_expiration_date={old_expiration_date.strftime('%Y-%m-%d')}"
            )

        return cancelled_count

    except SQLAlchemyError as e:
        logger.error(
            f"Database error cancelling reminders: user_id={user_id}, "
            f"old_expiration_date={old_expiration_date.strftime('%Y-%m-%d')}, "
            f"error={e}",
            exc_info=True
        )
        raise

    except Exception as e:
        logger.error(
            f"Unexpected error cancelling reminders: user_id={user_id}, "
            f"error={e}",
            exc_info=True
        )
        raise

