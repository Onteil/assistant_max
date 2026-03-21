"""
User service layer for managing user-related database operations.

Provides async functions for user CRUD operations, organization and key management,
with comprehensive error handling and logging.

Requirements: 1.5, 2.7, 7.5, 17.6, 18.6, 32.1, 33.1
"""

import logging
from datetime import datetime
from typing import Any, TYPE_CHECKING

from utils.timezone_helpers import get_moscow_now_naive

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    ActionType,
    Action_Log,
    GS_Key,
    KeyConflictStatus,
    Organization,
    RegistrationStatus,
    User,
    user_organizations,
)


class KeyConflictError(Exception):
    """Raised when a key already exists in DB under another user."""

    def __init__(self, key_number: str, existing_user_id: int, gs_key: "GS_Key") -> None:
        self.key_number = key_number
        self.existing_user_id = existing_user_id
        self.gs_key = gs_key
        super().__init__(f"Key {key_number!r} already owned by user_id={existing_user_id}")

logger = logging.getLogger(__name__)


# ========== User CRUD Operations ==========


async def get_user_by_tg_id(session: AsyncSession, tg_user_id: int) -> User | None:
    """
    Retrieve user by Telegram ID.
    
    Args:
        session: Database session
        tg_user_id: Telegram user ID
    
    Returns:
        User object if found, None otherwise
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        result = await session.execute(
            select(User).where(User.tg_user_id == tg_user_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            logger.debug(f"User found: tg_user_id={tg_user_id}, user_id={user.id}")
        else:
            logger.debug(f"User not found: tg_user_id={tg_user_id}")
        
        return user
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error retrieving user: tg_user_id={tg_user_id}, error={e}",
            exc_info=True
        )
        raise


async def get_user_by_max_id(session: AsyncSession, max_user_id: int) -> User | None:
    """
    Retrieve user by MAX messenger ID.
    
    Args:
        session: Database session
        max_user_id: MAX messenger user ID
    
    Returns:
        User object if found, None otherwise
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        result = await session.execute(
            select(User).where(User.max_user_id == max_user_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            logger.debug(f"User found: max_user_id={max_user_id}, user_id={user.id}")
        else:
            logger.debug(f"User not found: max_user_id={max_user_id}")
        
        return user
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error retrieving user: max_user_id={max_user_id}, error={e}",
            exc_info=True
        )
        raise


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """
    Retrieve user by internal user ID.
    
    Args:
        session: Database session
        user_id: Internal user ID (primary key)
    
    Returns:
        User object if found, None otherwise
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            logger.debug(f"User found: user_id={user_id}")
        else:
            logger.debug(f"User not found: user_id={user_id}")
        
        return user
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error retrieving user: user_id={user_id}, error={e}",
            exc_info=True
        )
        raise


async def get_user_by_phone(session: AsyncSession, phone_number: str) -> User | None:
    """
    Retrieve user by phone number.
    
    Args:
        session: Database session
        phone_number: User's phone number
    
    Returns:
        User object if found, None otherwise
    
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        result = await session.execute(
            select(User).where(User.phone_number == phone_number)
        )
        user = result.scalar_one_or_none()
        
        if user:
            logger.debug(f"User found by phone: phone={phone_number}, user_id={user.id}")
        else:
            logger.debug(f"User not found by phone: phone={phone_number}")
        
        return user
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error retrieving user by phone: phone={phone_number}, error={e}",
            exc_info=True
        )
        raise


async def upsert_max_messenger_data(
    session: AsyncSession,
    user_id: int,
    max_user_id: int,
    max_chat_id: int
) -> None:
    """
    Create or update MAX messenger data for a user.
    
    This function ensures that MAX messenger data is always up-to-date
    when a user interacts with the bot (e.g., /start command).
    
    Args:
        session: Database session
        user_id: Internal user ID
        max_user_id: MAX user identifier
        max_chat_id: MAX chat identifier for sending messages
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 15.3
    """
    try:
        from database.models import MAX_Messenger_Data
        
        # Check if record exists
        result = await session.execute(
            select(MAX_Messenger_Data).where(MAX_Messenger_Data.user_id == user_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Update existing record if chat_id changed
            if existing.max_chat_id != max_chat_id or existing.max_user_id != max_user_id:
                existing.max_user_id = max_user_id
                existing.max_chat_id = max_chat_id
                existing.updated_at = get_moscow_now_naive()
                await session.flush()
                
                logger.info(
                    f"MAX messenger data updated: user_id={user_id}, "
                    f"max_user_id={max_user_id}, max_chat_id={max_chat_id}"
                )
            else:
                logger.debug(
                    f"MAX messenger data unchanged: user_id={user_id}, "
                    f"max_user_id={max_user_id}, max_chat_id={max_chat_id}"
                )
        else:
            # Create new record
            max_data = MAX_Messenger_Data(
                user_id=user_id,
                max_user_id=max_user_id,
                max_chat_id=max_chat_id
            )
            
            session.add(max_data)
            await session.flush()
            
            logger.info(
                f"MAX messenger data created: user_id={user_id}, "
                f"max_user_id={max_user_id}, max_chat_id={max_chat_id}"
            )
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error upserting MAX messenger data: user_id={user_id}, "
            f"max_user_id={max_user_id}, max_chat_id={max_chat_id}, error={e}",
            exc_info=True
        )
        raise


async def create_user(session: AsyncSession, user_data: dict[str, Any]) -> User:
    """
    Create new user record with PENDING status.
    
    Args:
        session: Database session
        user_data: Dictionary containing user fields:
            - tg_user_id (int, optional) - Telegram user ID
            - max_user_id (int, optional) - MAX user ID
            - max_chat_id (int, optional) - MAX chat ID (required if max_user_id provided)
            - phone_number (str, required)
            - full_name (str, required)
            - username (str, optional)
            - first_name (str, optional)
            - last_name (str, optional)
            - default_manager_id (int, optional)
    
    Returns:
        Created User object
    
    Raises:
        IntegrityError: If phone number already exists or constraint violated
        SQLAlchemyError: If database operation fails
    
    Requirements: 1.5, 4.4, 15.3
    """
    try:
        user = User(
            tg_user_id=user_data.get("tg_user_id"),  # Can be None initially
            max_user_id=user_data.get("max_user_id"),  # Can be None initially
            phone_number=user_data["phone_number"],
            full_name=user_data["full_name"],
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            registration_status=RegistrationStatus.PENDING,
            default_manager_id=user_data.get("default_manager_id"),
        )
        
        session.add(user)
        await session.flush()
        
        # Create MAX messenger data if MAX user ID and chat ID provided
        max_user_id = user_data.get("max_user_id")
        max_chat_id = user_data.get("max_chat_id")
        
        if max_user_id and max_chat_id:
            from database.models import MAX_Messenger_Data
            from sqlalchemy import select
            
            # Check for orphaned max_messenger_data record before creating new one
            # This prevents IntegrityError if orphaned record exists
            result = await session.execute(
                select(MAX_Messenger_Data).where(
                    MAX_Messenger_Data.max_user_id == max_user_id
                )
            )
            existing_max_data = result.scalar_one_or_none()
            
            if existing_max_data:
                # Check if it's truly orphaned (user_id doesn't match our new user)
                if existing_max_data.user_id != user.id:
                    logger.warning(
                        f"Found existing max_messenger_data for max_user_id={max_user_id}: "
                        f"id={existing_max_data.id}, user_id={existing_max_data.user_id}. "
                        f"Updating to new user_id={user.id}"
                    )
                    # Update existing record instead of creating new one
                    existing_max_data.user_id = user.id
                    existing_max_data.max_chat_id = max_chat_id
                    await session.flush()
                    
                    logger.info(
                        f"MAX messenger data updated: id={existing_max_data.id}, "
                        f"user_id={user.id}, max_user_id={max_user_id}, max_chat_id={max_chat_id}"
                    )
                else:
                    # Record already exists for this user, just update chat_id if needed
                    if existing_max_data.max_chat_id != max_chat_id:
                        existing_max_data.max_chat_id = max_chat_id
                        await session.flush()
                        logger.info(f"MAX messenger data chat_id updated: id={existing_max_data.id}")
            else:
                # No existing record, create new one
                max_data = MAX_Messenger_Data(
                    user_id=user.id,
                    max_user_id=max_user_id,
                    max_chat_id=max_chat_id
                )
                
                session.add(max_data)
                await session.flush()
                
                logger.info(
                    f"MAX messenger data created: user_id={user.id}, "
                    f"max_user_id={max_user_id}, max_chat_id={max_chat_id}"
                )
        
        # Log user registration action
        await _log_action(
            session=session,
            action_type=ActionType.USER_REGISTERED,
            user_id=user.id,
            action_details={
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "registration_status": user.registration_status.value,
                "tg_user_id": user.tg_user_id,
                "max_user_id": user.max_user_id,
            }
        )
        
        logger.info(
            f"User created: user_id={user.id}, tg_user_id={user.tg_user_id}, "
            f"max_user_id={user.max_user_id}, phone={user.phone_number}, "
            f"status={user.registration_status.value}"
        )
        
        return user
    
    except IntegrityError as e:
        logger.error(
            f"Integrity error creating user: tg_user_id={user_data.get('tg_user_id')}, "
            f"max_user_id={user_data.get('max_user_id')}, "
            f"phone={user_data.get('phone_number')}, error={e}",
            exc_info=True
        )
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error creating user: tg_user_id={user_data.get('tg_user_id')}, "
            f"max_user_id={user_data.get('max_user_id')}, error={e}",
            exc_info=True
        )
        raise


async def update_user_status(
    session: AsyncSession,
    user_id: int,
    status: RegistrationStatus
) -> User:
    """
    Update user registration status.
    
    Args:
        session: Database session
        user_id: Internal user ID (primary key)
        status: New registration status
    
    Returns:
        Updated User object
    
    Raises:
        ValueError: If user not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 5.1, 5.3
    """
    try:
        user = await get_user_by_id(session, user_id)
        
        if not user:
            error_msg = f"User not found for status update: user_id={user_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        old_status = user.registration_status
        user.registration_status = status
        
        await session.flush()
        
        logger.info(
            f"User status updated: user_id={user_id}, "
            f"old_status={old_status.value}, new_status={status.value}"
        )
        
        return user
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error updating user status: user_id={user_id}, "
            f"status={status.value}, error={e}",
            exc_info=True
        )
        raise


# ========== Organization Management ==========


async def get_user_organizations(
    session: AsyncSession,
    user_id: int
) -> list[Organization]:
    """
    Retrieve all organizations associated with user.
    
    Args:
        session: Database session
        user_id: Internal user ID (primary key)
    
    Returns:
        List of Organization objects
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 7.2, 16.3
    """
    try:
        result = await session.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.organizations))
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"User not found for organizations query: user_id={user_id}")
            return []
        
        organizations = user.organizations
        logger.debug(
            f"Retrieved {len(organizations)} organizations for user: user_id={user_id}"
        )
        
        return organizations
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error retrieving user organizations: user_id={user_id}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def add_user_organization(
    session: AsyncSession,
    user_id: int,
    inn: str
) -> Organization:
    """
    Create organization and user_organizations association.
    
    Creates Organization record if it doesn't exist, then creates association
    with user. Prevents duplicate associations.
    
    Args:
        session: Database session
        user_id: Internal user ID (primary key)
        inn: Organization INN (10 or 12 digits)
    
    Returns:
        Organization object
    
    Raises:
        ValueError: If user not found
        IntegrityError: If association already exists
        SQLAlchemyError: If database operation fails
    
    Requirements: 7.5, 17.6
    """
    try:
        # Verify user exists
        user = await get_user_by_id(session, user_id)
        if not user:
            error_msg = f"User not found for organization addition: user_id={user_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Get or create organization
        result = await session.execute(
            select(Organization).where(Organization.inn == inn)
        )
        organization = result.scalar_one_or_none()
        
        if not organization:
            organization = Organization(inn=inn)
            session.add(organization)
            await session.flush()
            logger.info(f"Organization created: inn={inn}")
        
        # Check if association already exists
        result = await session.execute(
            select(user_organizations).where(
                user_organizations.c.user_id == user_id,
                user_organizations.c.organization_inn == inn
            )
        )
        existing = result.first()
        
        if existing:
            logger.warning(
                f"Organization association already exists: user_id={user_id}, inn={inn}"
            )
            return organization
        
        # Create association
        await session.execute(
            user_organizations.insert().values(
                user_id=user_id,
                organization_inn=inn,
                added_at=get_moscow_now_naive()
            )
        )
        await session.flush()
        
        logger.info(
            f"Organization association created: user_id={user_id}, inn={inn}"
        )
        
        return organization
    
    except IntegrityError as e:
        logger.error(
            f"Integrity error adding user organization: user_id={user_id}, "
            f"inn={inn}, error={e}",
            exc_info=True
        )
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error adding user organization: user_id={user_id}, "
            f"inn={inn}, error={e}",
            exc_info=True
        )
        raise


# ========== GS_Key Management ==========


async def get_user_keys(session: AsyncSession, user_id: int) -> list[GS_Key]:
    """
    Retrieve all GS_Keys associated with user.
    
    Args:
        session: Database session
        user_id: Internal user ID (primary key)
    
    Returns:
        List of GS_Key objects
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 8.1, 16.4
    """
    try:
        result = await session.execute(
            select(GS_Key)
            .where(GS_Key.user_id == user_id)
            .order_by(GS_Key.created_at.desc())
        )
        keys = result.scalars().all()
        
        logger.debug(
            f"Retrieved {len(keys)} GS_Keys for user: user_id={user_id}"
        )
        
        return list(keys)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error retrieving user keys: user_id={user_id}, error={e}",
            exc_info=True
        )
        raise


async def add_user_key(
    session: AsyncSession,
    user_id: int,
    key_number: str,
    conflict_status: KeyConflictStatus = KeyConflictStatus.NONE
) -> GS_Key:
    """
    Create or update GS_Key record with conflict status.

    If conflict_status is PENDING_REVIEW, the key already belongs to another user.
    In that case we update the existing key's conflict_status instead of inserting
    a duplicate (key_number has a unique constraint).  The new claimant's user_id
    is stored in Action_Log so admin handlers can retrieve it.

    Args:
        session: Database session
        user_id: Internal user ID of the user who is adding the key
        key_number: GS_Key number (e.g., MG123456 or 00000_00001)
        conflict_status: Conflict status (default: NONE)

    Returns:
        GS_Key object (existing record updated, or newly created)

    Raises:
        ValueError: If user not found
        SQLAlchemyError: If database operation fails

    Requirements: 18.6
    """
    try:
        # Verify user exists
        user = await get_user_by_id(session, user_id)
        if not user:
            error_msg = f"User not found for key addition: user_id={user_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if conflict_status == KeyConflictStatus.PENDING_REVIEW:
            # Key already exists in DB under another user.
            # Find that existing record and mark it as PENDING_REVIEW.
            stmt = select(GS_Key).where(GS_Key.key_number == key_number)
            result = await session.execute(stmt)
            existing_key = result.scalar_one_or_none()

            if existing_key:
                # Update conflict status on the existing record
                existing_key.conflict_status = KeyConflictStatus.PENDING_REVIEW
                existing_key.conflict_reported_at = get_moscow_now_naive()
                await session.flush()

                action_details_dict = {
                    "key_number": key_number,
                    "conflict_status": conflict_status.value,
                    "conflict_reported_at": existing_key.conflict_reported_at.isoformat(),
                    "new_user_id": user_id,
                    "existing_user_id": existing_key.user_id,
                }

                await _log_action(
                    session=session,
                    action_type=ActionType.KEY_CONFLICT_DETECTED,
                    user_id=user_id,
                    action_details=action_details_dict,
                )
                logger.warning(
                    f"Key conflict recorded on existing record: key={key_number}, "
                    f"owner_user_id={existing_key.user_id}, claimant_user_id={user_id}"
                )
                return existing_key

            # Key doesn't exist in DB yet but i-TAT says conflict — create new record
            # (edge case: key exists in i-TAT but not locally)
            gs_key = GS_Key(
                key_number=key_number,
                user_id=user_id,
                conflict_status=conflict_status,
                conflict_reported_at=get_moscow_now_naive(),
            )
            session.add(gs_key)
            await session.flush()

            action_details_dict = {
                "key_number": key_number,
                "conflict_status": conflict_status.value,
                "conflict_reported_at": gs_key.conflict_reported_at.isoformat(),
                "new_user_id": user_id,
            }
            await _log_action(
                session=session,
                action_type=ActionType.KEY_CONFLICT_DETECTED,
                user_id=user_id,
                action_details=action_details_dict,
            )
            logger.warning(
                f"Key conflict (no local owner): key={key_number}, claimant_user_id={user_id}"
            )
            return gs_key

        # No conflict from i-TAT — but check DB first to avoid UniqueViolationError
        stmt = select(GS_Key).where(GS_Key.key_number == key_number)
        result = await session.execute(stmt)
        existing_key = result.scalar_one_or_none()

        if existing_key:
            # Key exists in DB under another user but i-TAT didn't flag it.
            # Treat as a conflict to avoid unique constraint violation.
            logger.warning(
                f"Key exists in DB but i-TAT returned no conflict: key={key_number}, "
                f"owner_user_id={existing_key.user_id}, claimant_user_id={user_id}"
            )
            existing_key.conflict_status = KeyConflictStatus.PENDING_REVIEW
            existing_key.conflict_reported_at = get_moscow_now_naive()
            await session.flush()

            await _log_action(
                session=session,
                action_type=ActionType.KEY_CONFLICT_DETECTED,
                user_id=user_id,
                action_details={
                    "key_number": key_number,
                    "conflict_status": KeyConflictStatus.PENDING_REVIEW.value,
                    "conflict_reported_at": existing_key.conflict_reported_at.isoformat(),
                    "new_user_id": user_id,
                    "existing_user_id": existing_key.user_id,
                    "source": "db_check_fallback",
                },
            )
            # Raise a specific exception so callers can handle it as a conflict
            raise KeyConflictError(
                key_number=key_number,
                existing_user_id=existing_key.user_id,
                gs_key=existing_key,
            )

        # Safe to insert
        gs_key = GS_Key(
            key_number=key_number,
            user_id=user_id,
            conflict_status=KeyConflictStatus.NONE,
        )
        session.add(gs_key)
        await session.flush()

        logger.info(f"GS_Key created: user_id={user_id}, key_number={key_number}")
        return gs_key

    except KeyConflictError:
        raise
    except SQLAlchemyError as e:
        logger.error(
            f"Database error adding user key: user_id={user_id}, "
            f"key_number={key_number}, error={e}",
            exc_info=True,
        )
        raise


# ========== Helper Functions ==========


async def _log_action(
    session: AsyncSession,
    action_type: ActionType,
    user_id: int | None = None,
    ticket_id: int | None = None,
    staff_id: int | None = None,
    action_details: dict[str, Any] | None = None
) -> Action_Log:
    """
    Create action log entry.
    
    Internal helper function for logging significant user actions.
    
    Args:
        session: Database session
        action_type: Type of action being logged
        user_id: Internal user ID (optional)
        ticket_id: Ticket ID (optional)
        staff_id: Staff member ID (optional)
        action_details: Additional details as JSON (optional)
    
    Returns:
        Created Action_Log object
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 32.1, 32.2, 32.3, 32.4, 32.5
    """
    try:
        action_log = Action_Log(
            action_type=action_type,
            user_id=user_id,
            ticket_id=ticket_id,
            staff_id=staff_id,
            action_details=action_details,
            action_timestamp=get_moscow_now_naive()
        )
        
        session.add(action_log)
        await session.flush()
        
        logger.debug(
            f"Action logged: type={action_type.value}, user_id={user_id}, "
            f"ticket_id={ticket_id}"
        )
        
        return action_log
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error logging action: action_type={action_type.value}, "
            f"user_id={user_id}, error={e}",
            exc_info=True
        )
        raise
