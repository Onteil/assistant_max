"""
User Data Update System - CRM Webhook Handler

This module implements the webhook endpoint for receiving user data and asset updates
from 1C CRM. This webhook is called when:
- Client pays invoice and support is extended
- GS_Keys are added or removed
- Organizations (INNs) are added or removed
- User profile data is updated manually in CRM

Requirements: CRM integration for user data synchronization
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.user_update_schemas import (
    UserUpdateWebhookPayload,
    UserUpdateWebhookResponse,
)
from constants import get_session, WEBHOOK_API_KEY, TG_BOT_TOKEN, MAX_BOT_TOKEN
from database.models import (
    Action_Log,
    ActionType,
    GS_Key,
    KeyConflictStatus,
    Organization,
    Staff_Member,
    SubscriptionStatus,
    User,
    user_organizations,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def _send_user_update_notification(
    messenger: str,
    user_id: int,
    updates_applied: dict,
    session: AsyncSession
) -> None:
    """
    Send friendly notification to user about data changes.
    
    Args:
        messenger: Messenger platform ("telegram" or "max")
        user_id: Internal user ID (from users.id)
        updates_applied: Dictionary with applied updates
        session: Database session (required for MAX to get chat_id)
    """
    try:
        # Build notification message (different format for Telegram and MAX)
        if messenger == "telegram":
            message_parts = ["🔔 <b>Уведомление об обновлении данных</b>\n"]
            message_parts.append("В ваш профиль были внесены следующие изменения:\n")
            
            # Profile updates
            if updates_applied["profile"]:
                message_parts.append("\n📝 <b>Профиль:</b>")
                for field in updates_applied["profile"]:
                    if field == "email":
                        message_parts.append("  • Обновлен email")
                    elif field == "full_name":
                        message_parts.append("  • Обновлено ФИО")
            
            # Subscription updates
            if updates_applied["subscription"]:
                message_parts.append("\n⏰ <b>Подписка:</b>")
                for field in updates_applied["subscription"]:
                    if field == "end_date":
                        message_parts.append("  • Обновлена дата окончания подписки")
                    elif field == "status":
                        message_parts.append("  • Обновлен статус подписки")
                    elif field == "status_auto_expired":
                        message_parts.append("  • Подписка истекла")
            
            # GS Keys updates
            if updates_applied["gs_keys_added"] > 0:
                count = updates_applied["gs_keys_added"]
                message_parts.append(f"\n🔑 <b>Ключи GS:</b>")
                message_parts.append(f"  • Добавлено ключей: {count}")
            
            if updates_applied["gs_keys_removed"] > 0:
                count = updates_applied["gs_keys_removed"]
                if updates_applied["gs_keys_added"] == 0:
                    message_parts.append(f"\n🔑 <b>Ключи GS:</b>")
                message_parts.append(f"  • Удалено ключей: {count}")
            
            # Organizations updates
            if updates_applied["organizations_added"] > 0:
                count = updates_applied["organizations_added"]
                message_parts.append(f"\n🏢 <b>Организации:</b>")
                message_parts.append(f"  • Добавлено организаций: {count}")
            
            if updates_applied["organizations_removed"] > 0:
                count = updates_applied["organizations_removed"]
                if updates_applied["organizations_added"] == 0:
                    message_parts.append(f"\n🏢 <b>Организации:</b>")
                message_parts.append(f"  • Удалено организаций: {count}")
            
            message_parts.append("\n\n<i>С уважением,\nКоманда АЙТАТ</i> 💙")
        else:  # MAX - no HTML tags
            message_parts = ["🔔 Уведомление об обновлении данных\n"]
            message_parts.append("В ваш профиль были внесены следующие изменения:\n")
            
            # Profile updates
            if updates_applied["profile"]:
                message_parts.append("\n📝 Профиль:")
                for field in updates_applied["profile"]:
                    if field == "email":
                        message_parts.append("  • Обновлен email")
                    elif field == "full_name":
                        message_parts.append("  • Обновлено ФИО")
            
            # Subscription updates
            if updates_applied["subscription"]:
                message_parts.append("\n⏰ Подписка:")
                for field in updates_applied["subscription"]:
                    if field == "end_date":
                        message_parts.append("  • Обновлена дата окончания подписки")
                    elif field == "status":
                        message_parts.append("  • Обновлен статус подписки")
                    elif field == "status_auto_expired":
                        message_parts.append("  • Подписка истекла")
            
            # GS Keys updates
            if updates_applied["gs_keys_added"] > 0:
                count = updates_applied["gs_keys_added"]
                message_parts.append(f"\n🔑 Ключи GS:")
                message_parts.append(f"  • Добавлено ключей: {count}")
            
            if updates_applied["gs_keys_removed"] > 0:
                count = updates_applied["gs_keys_removed"]
                if updates_applied["gs_keys_added"] == 0:
                    message_parts.append(f"\n🔑 Ключи GS:")
                message_parts.append(f"  • Удалено ключей: {count}")
            
            # Organizations updates
            if updates_applied["organizations_added"] > 0:
                count = updates_applied["organizations_added"]
                message_parts.append(f"\n🏢 Организации:")
                message_parts.append(f"  • Добавлено организаций: {count}")
            
            if updates_applied["organizations_removed"] > 0:
                count = updates_applied["organizations_removed"]
                if updates_applied["organizations_added"] == 0:
                    message_parts.append(f"\n🏢 Организации:")
                message_parts.append(f"  • Удалено организаций: {count}")
            
            message_parts.append("\n\nС уважением,\nКоманда АЙТАТ 💙")
        
        message_text = "\n".join(message_parts)
        
        # Send via centralized utility
        from api.utils.messenger_utils import send_message_to_user
        
        result = await send_message_to_user(
            messenger=messenger,
            user_id=user_id,
            text=message_text,
            session=session,
            parse_mode="HTML" if messenger == "telegram" else None
        )
        
        if result["success"]:
            logger.info(f"User update notification sent to {messenger} user {user_id}")
        else:
            logger.warning(
                f"Failed to send user update notification to {messenger} user {user_id}: "
                f"{result['message']}"
            )
    
    except Exception as e:
        logger.error(
            f"Error sending user update notification to {messenger} user {user_id}: {e}",
            exc_info=True
        )


async def verify_webhook_api_key(
    x_api_key: Annotated[str | None, Header()] = None
) -> str:
    """
    Verify webhook API key authentication.
    
    This dependency validates that incoming webhook requests include a valid
    API key in the X-API-Key header.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        Validated API key
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    if not x_api_key:
        logger.warning("User update webhook request received without API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    if not WEBHOOK_API_KEY:
        logger.error("WEBHOOK_API_KEY not configured in environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook API key not configured on server",
        )
    
    if x_api_key != WEBHOOK_API_KEY:
        logger.warning(f"Invalid API key attempt: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return x_api_key


@router.post("/user_update", response_model=UserUpdateWebhookResponse)
async def user_update_webhook(
    payload: UserUpdateWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_webhook_api_key)],
) -> UserUpdateWebhookResponse:
    """
    Handle user data and asset updates webhook from 1C CRM.
    
    This endpoint receives user data updates from the CRM system when:
    - Client pays invoice and support is extended
    - GS_Keys are added or removed
    - Organizations (INNs) are added or removed  
    - User profile data is updated manually in CRM
    
    Request body example:
    {
        "messenger": "max",
        "user_id": 123456789,
        "phone": "+79991234567",
        "email": "user@example.com",
        "full_name": "Иван Иванов",
        "subscription_end_date": "2027-12-31T23:59:59",
        "subscription_status": "active",
        "gs_keys": [
            {"key_number": "KEY123456", "action": "add"},
            {"key_number": "KEY789012", "action": "remove"}
        ],
        "organizations": [
            {"inn": "1234567890", "organization_name": "ООО Рога и Копыта", "action": "add"},
            {"inn": "9876543210", "action": "remove"}
        ]
    }
    
    Response:
    {
        "status": "success",
        "message": "User data updated successfully",
        "messenger": "max",
        "user_id": 123456789,
        "updates_applied": {
            "profile": ["email", "full_name"],
            "subscription": ["end_date", "status"],
            "gs_keys_added": 1,
            "gs_keys_removed": 1,
            "organizations_added": 1,
            "organizations_removed": 1
        }
    }
    
    Args:
        payload: User update webhook payload
        session: Database session
        api_key: Validated API key from header
        
    Returns:
        JSON response with status and update summary
        
    Raises:
        HTTPException: 400 if payload validation fails
        HTTPException: 404 if user not found
        HTTPException: 500 if internal error occurs
    """
    logger.info(
        f"User update webhook received: messenger={payload.messenger}, "
        f"user_id={payload.user_id}, phone={payload.phone}"
    )
    
    try:
        # Query user by messenger-specific ID
        if payload.messenger == "telegram":
            stmt = select(User).where(User.tg_user_id == payload.user_id)
        elif payload.messenger == "max":
            stmt = select(User).where(User.max_user_id == payload.user_id)
        else:
            logger.error(f"Invalid messenger type: {payload.messenger}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid messenger type: {payload.messenger}",
            )
        
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(
                f"User with {payload.messenger}_user_id={payload.user_id} not found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with {payload.messenger.upper()} ID {payload.user_id} not found",
            )
        
        # Verify phone number matches (log warning but continue)
        if user.phone_number != payload.phone:
            logger.warning(
                f"Phone number mismatch for {payload.messenger}_user_id={payload.user_id}: "
                f"expected {user.phone_number}, got {payload.phone}"
            )
        
        # Track what was updated
        updates_applied = {
            "profile": [],
            "subscription": [],
            "gs_keys_added": 0,
            "gs_keys_removed": 0,
            "organizations_added": 0,
            "organizations_removed": 0,
        }
        
        # Check which fields have actually changed (deduplication for 1C CRM multiple triggers)
        from api.webhooks.webhook_utils import has_field_changed
        
        # Update user profile fields only if changed
        if payload.email is not None and has_field_changed(user.email, payload.email, "email"):
            user.email = payload.email
            updates_applied["profile"].append("email")
            logger.info(f"Updated email for user {user.id}")
        
        if payload.full_name is not None and has_field_changed(user.full_name, payload.full_name, "full_name"):
            user.full_name = payload.full_name
            updates_applied["profile"].append("full_name")
            logger.info(f"Updated full_name for user {user.id}")
        
        # Update subscription data only if changed
        if payload.subscription_end_date is not None:
            # Convert timezone-aware datetime to naive datetime for PostgreSQL TIMESTAMP WITHOUT TIME ZONE
            from datetime import timezone
            end_date = payload.subscription_end_date
            
            # Make timezone-aware if it isn't (assume UTC)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            
            # Store as naive datetime (remove timezone info)
            new_end_date = end_date.replace(tzinfo=None)
            
            # Check if end_date has actually changed
            if has_field_changed(user.subscription_end_date, new_end_date, "subscription_end_date"):
                user.subscription_end_date = new_end_date
                updates_applied["subscription"].append("end_date")
                
                # Auto-check if subscription is expired
                now = datetime.now(timezone.utc)
                
                if end_date < now:
                    # Override status to EXPIRED if date is in the past
                    user.subscription_status = SubscriptionStatus.EXPIRED
                    updates_applied["subscription"].append("status_auto_expired")
                    logger.warning(
                        f"Subscription end date {payload.subscription_end_date} is in the past. "
                        f"Auto-setting subscription_status to EXPIRED for user {user.id}"
                    )
                else:
                    logger.info(
                        f"Updated subscription_end_date for user {user.id} to {payload.subscription_end_date}"
                    )
        
        if payload.subscription_status is not None:
            # Map string to enum
            status_map = {
                "active": SubscriptionStatus.ACTIVE,
                "expired": SubscriptionStatus.EXPIRED,
                "none": SubscriptionStatus.NONE,
            }
            new_status = status_map[payload.subscription_status]
            
            # Check if status has actually changed
            if has_field_changed(user.subscription_status, new_status, "subscription_status"):
                # Only apply if not already set to EXPIRED by date check above
                if "status_auto_expired" not in updates_applied["subscription"]:
                    user.subscription_status = new_status
                    updates_applied["subscription"].append("status")
                    logger.info(f"Updated subscription_status for user {user.id} to {payload.subscription_status}")
                else:
                    logger.info(
                        f"Skipping manual subscription_status update for user {user.id} "
                        f"because it was auto-set to EXPIRED due to past end_date"
                    )
        
        # Process GS_Keys updates
        if payload.gs_keys:
            from services.user_service import KeyConflictError, KeyAlreadyOwnedByUserError, add_user_key

            for key_update in payload.gs_keys:
                if key_update.action == "add":
                    try:
                        await add_user_key(session, user.id, key_update.key_number)
                        updates_applied["gs_keys_added"] += 1
                        logger.info(f"Added GS_Key {key_update.key_number} to user {user.id}")

                    except KeyAlreadyOwnedByUserError:
                        # Key already belongs to this user — idempotent, skip silently
                        logger.info(
                            f"GS_Key {key_update.key_number} already belongs to user {user.id}. "
                            f"Skipping duplicate add operation."
                        )

                    except KeyConflictError as conflict_err:
                        # Key belongs to another user — mark PENDING_REVIEW (done inside add_user_key)
                        # and notify admins
                        logger.warning(
                            f"Key conflict detected via CRM webhook: key={key_update.key_number}, "
                            f"new_user_id={user.id}, existing_user_id={conflict_err.existing_user_id}"
                        )
                        try:
                            from bots.max_bot.utils.admin_notifications import notify_admins_key_conflict
                            await notify_admins_key_conflict(session, user.id, key_update.key_number)
                        except Exception as notify_err:
                            logger.error(
                                f"Failed to send key conflict notification: {notify_err}",
                                exc_info=True
                            )
                
                elif key_update.action == "remove":
                    # Find and remove key
                    stmt_key = select(GS_Key).where(
                        GS_Key.key_number == key_update.key_number,
                        GS_Key.user_id == user.id
                    )
                    result_key = await session.execute(stmt_key)
                    key_to_remove = result_key.scalar_one_or_none()
                    
                    if key_to_remove:
                        await session.delete(key_to_remove)
                        updates_applied["gs_keys_removed"] += 1
                        logger.info(f"Removed GS_Key {key_update.key_number} from user {user.id}")
                    else:
                        logger.warning(
                            f"GS_Key {key_update.key_number} not found for user {user.id}. "
                            f"Remove operation skipped."
                        )
        
        # Process Organizations updates
        if payload.organizations:
            # Cache user.id before any potential rollback that would expire the user object
            user_id_cached = user.id
            for org_update in payload.organizations:
                if org_update.action == "add":
                    # Check if organization exists
                    stmt_org = select(Organization).where(Organization.inn == org_update.inn)
                    result_org = await session.execute(stmt_org)
                    organization = result_org.scalar_one_or_none()
                    
                    if not organization:
                        # Create organization if it doesn't exist (name will be fetched from i-TAT API later)
                        organization = Organization(
                            inn=org_update.inn,
                            organization_name=None,  # Will be populated by bot when user requests organization data
                        )
                        session.add(organization)
                        try:
                            await session.flush()  # Get organization into session
                            logger.info(f"Created organization {org_update.inn} without name (will be fetched later)")
                        except IntegrityError as integrity_err:
                            # Race condition: organization was created by another transaction
                            # Don't rollback - just re-fetch the organization and continue
                            logger.warning(
                                f"Organization {org_update.inn} was created by another transaction. "
                                f"Re-fetching from database."
                            )
                            # Expire the failed organization object from session
                            await session.rollback()  # Rollback only the flush, not the entire transaction
                            # Re-fetch organization
                            result_org = await session.execute(stmt_org)
                            organization = result_org.scalar_one_or_none()
                            if not organization:
                                # Still not found - this shouldn't happen, but handle it
                                logger.error(f"Organization {org_update.inn} still not found after race condition")
                                raise
                    
                    # Check if user-organization link exists
                    stmt_link = select(user_organizations).where(
                        user_organizations.c.user_id == user_id_cached,
                        user_organizations.c.organization_inn == org_update.inn
                    )
                    result_link = await session.execute(stmt_link)
                    existing_link = result_link.first()
                    
                    if not existing_link:
                        # Create user-organization link
                        stmt_insert = user_organizations.insert().values(
                            user_id=user_id_cached,
                            organization_inn=org_update.inn
                        )
                        await session.execute(stmt_insert)
                        updates_applied["organizations_added"] += 1
                        logger.info(f"Linked organization {org_update.inn} to user {user_id_cached}")
                    else:
                        logger.info(
                            f"Organization {org_update.inn} already linked to user {user_id_cached}"
                        )
                
                elif org_update.action == "remove":
                    # Remove user-organization link
                    stmt_delete = user_organizations.delete().where(
                        user_organizations.c.user_id == user_id_cached,
                        user_organizations.c.organization_inn == org_update.inn
                    )
                    result_delete = await session.execute(stmt_delete)
                    
                    if result_delete.rowcount > 0:
                        updates_applied["organizations_removed"] += 1
                        logger.info(f"Unlinked organization {org_update.inn} from user {user_id_cached}")
                    else:
                        logger.warning(
                            f"Organization {org_update.inn} not linked to user {user_id_cached}. "
                            f"Remove operation skipped."
                        )
        
        # Commit all changes
        await session.commit()
        
        # Check if there are any actual updates to notify about
        has_updates = (
            updates_applied["profile"] or
            updates_applied["subscription"] or
            updates_applied["gs_keys_added"] > 0 or
            updates_applied["gs_keys_removed"] > 0 or
            updates_applied["organizations_added"] > 0 or
            updates_applied["organizations_removed"] > 0
        )
        
        # If nothing changed, skip notification and action log
        if not has_updates:
            logger.info(
                f"No actual changes detected for user {user.id}. "
                f"Skipping notification and action log (likely duplicate webhook from 1C CRM)."
            )
            return UserUpdateWebhookResponse(
                status="success",
                message="User data already up to date (no changes detected)",
                messenger=payload.messenger,
                user_id=payload.user_id,
                updates_applied=updates_applied
            )
        
        # Log action in Action_Log
        action_log = Action_Log(
            action_type=ActionType.SETTING_CHANGED,  # Using existing enum, could add USER_DATA_UPDATED
            user_id=user.id,
            action_details={
                "action": "user_data_updated_via_crm",
                "messenger": payload.messenger,
                "messenger_user_id": payload.user_id,
                "updates_applied": updates_applied,
            },
            action_timestamp=datetime.now()
        )
        session.add(action_log)
        await session.commit()
        
        # Send notification to user about the changes
        # Check if there are any actual updates to notify about
        has_updates = (
            updates_applied["profile"] or
            updates_applied["subscription"] or
            updates_applied["gs_keys_added"] > 0 or
            updates_applied["gs_keys_removed"] > 0 or
            updates_applied["organizations_added"] > 0 or
            updates_applied["organizations_removed"] > 0
        )
        
        if has_updates:
            try:
                await _send_user_update_notification(
                    messenger=payload.messenger,
                    user_id=user.id,  # Internal user ID
                    updates_applied=updates_applied,
                    session=session  # Required for MAX
                )
            except Exception as e:
                # Don't fail the webhook if notification fails
                logger.error(
                    f"Failed to send user update notification, but webhook succeeded: {e}",
                    exc_info=True
                )
        
        logger.info(
            f"User update webhook processed successfully for {payload.messenger}_user_id={payload.user_id}. "
            f"Updates: {updates_applied}"
        )
        
        return UserUpdateWebhookResponse(
            status="success",
            message="User data updated successfully",
            messenger=payload.messenger,
            user_id=payload.user_id,
            updates_applied=updates_applied
        )
        
    except HTTPException as http_exc:
        # Rollback transaction on HTTP errors
        await session.rollback()
        
        # Notify admins about HTTP errors (validation, not found, etc.) with fresh session
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            from constants import AsyncSessionLocal
            
            error_type = f"HTTP {http_exc.status_code}"
            error_details = http_exc.detail
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}"
            
            async with AsyncSessionLocal() as notification_session:
                await notify_admins_webhook_error(
                    session=notification_session,
                    webhook_name="user_update",
                    error_type=error_type,
                    error_details=error_details,
                    payload_summary=payload_summary
                )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        # Re-raise HTTP exceptions (404, 400, etc.)
        raise
        
    except Exception as e:
        # Rollback transaction on error
        await session.rollback()
        
        # Unexpected error - notify admins with fresh session
        try:
            from bots.max_bot.utils.admin_notifications import notify_admins_webhook_error
            from constants import AsyncSessionLocal
            
            error_type = type(e).__name__
            error_details = str(e)
            payload_summary = f"messenger={payload.messenger}, user_id={payload.user_id}"
            
            async with AsyncSessionLocal() as notification_session:
                await notify_admins_webhook_error(
                    session=notification_session,
                    webhook_name="user_update",
                    error_type=error_type,
                    error_details=error_details,
                    payload_summary=payload_summary
                )
        except Exception as notify_error:
            logger.error(f"Failed to send webhook error notification: {notify_error}")
        
        logger.error(
            f"Error processing user update webhook for {payload.messenger}_user_id={payload.user_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )
