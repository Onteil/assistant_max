"""
User service layer for managing user-related database operations.

Provides async functions for user CRUD operations, organization and key management,
with comprehensive error handling and logging.

Requirements: 1.5, 2.7, 7.5, 17.6, 18.6, 32.1, 33.1
"""

import logging
from datetime import datetime
from typing import Any

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
            logger.debug(f"User found: tg_user_id={tg_user_id}")
        else:
            logger.debug(f"User not found: tg_user_id={tg_user_id}")
        
        return user
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error retrieving user: tg_user_id={tg_user_id}, error={e}",
            exc_info=True
        )
        raise


async def create_user(session: AsyncSession, user_data: dict[str, Any]) -> User:
    """
    Create new user record with PENDING status.
    
    Args:
        session: Database session
        user_data: Dictionary containing user fields:
            - tg_user_id (int, required)
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
    
    Requirements: 1.5, 4.4
    """
    try:
        user = User(
            tg_user_id=user_data["tg_user_id"],
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
        
        # Log user registration action
        await _log_action(
            session=session,
            action_type=ActionType.USER_REGISTERED,
            tg_user_id=user.tg_user_id,
            action_details={
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "registration_status": user.registration_status.value,
            }
        )
        
        logger.info(
            f"User created: tg_user_id={user.tg_user_id}, "
            f"phone={user.phone_number}, status={user.registration_status.value}"
        )
        
        return user
    
    except IntegrityError as e:
        logger.error(
            f"Integrity error creating user: tg_user_id={user_data.get('tg_user_id')}, "
            f"phone={user_data.get('phone_number')}, error={e}",
            exc_info=True
        )
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error creating user: tg_user_id={user_data.get('tg_user_id')}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def update_user_status(
    session: AsyncSession,
    tg_user_id: int,
    status: RegistrationStatus
) -> User:
    """
    Update user registration status.
    
    Args:
        session: Database session
        tg_user_id: Telegram user ID
        status: New registration status
    
    Returns:
        Updated User object
    
    Raises:
        ValueError: If user not found
        SQLAlchemyError: If database operation fails
    
    Requirements: 5.1, 5.3
    """
    try:
        user = await get_user_by_tg_id(session, tg_user_id)
        
        if not user:
            error_msg = f"User not found for status update: tg_user_id={tg_user_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        old_status = user.registration_status
        user.registration_status = status
        
        await session.flush()
        
        logger.info(
            f"User status updated: tg_user_id={tg_user_id}, "
            f"old_status={old_status.value}, new_status={status.value}"
        )
        
        return user
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error updating user status: tg_user_id={tg_user_id}, "
            f"status={status.value}, error={e}",
            exc_info=True
        )
        raise


# ========== Organization Management ==========


async def get_user_organizations(
    session: AsyncSession,
    tg_user_id: int
) -> list[Organization]:
    """
    Retrieve all organizations associated with user.
    
    Args:
        session: Database session
        tg_user_id: Telegram user ID
    
    Returns:
        List of Organization objects
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 7.2, 16.3
    """
    try:
        result = await session.execute(
            select(User)
            .where(User.tg_user_id == tg_user_id)
            .options(selectinload(User.organizations))
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"User not found for organizations query: tg_user_id={tg_user_id}")
            return []
        
        organizations = user.organizations
        logger.debug(
            f"Retrieved {len(organizations)} organizations for user: tg_user_id={tg_user_id}"
        )
        
        return organizations
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error retrieving user organizations: tg_user_id={tg_user_id}, "
            f"error={e}",
            exc_info=True
        )
        raise


async def add_user_organization(
    session: AsyncSession,
    tg_user_id: int,
    inn: str
) -> Organization:
    """
    Create organization and user_organizations association.
    
    Creates Organization record if it doesn't exist, then creates association
    with user. Prevents duplicate associations.
    
    Args:
        session: Database session
        tg_user_id: Telegram user ID
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
        user = await get_user_by_tg_id(session, tg_user_id)
        if not user:
            error_msg = f"User not found for organization addition: tg_user_id={tg_user_id}"
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
                user_organizations.c.tg_user_id == tg_user_id,
                user_organizations.c.organization_inn == inn
            )
        )
        existing = result.first()
        
        if existing:
            logger.warning(
                f"Organization association already exists: tg_user_id={tg_user_id}, inn={inn}"
            )
            return organization
        
        # Create association
        await session.execute(
            user_organizations.insert().values(
                tg_user_id=tg_user_id,
                organization_inn=inn,
                added_at=datetime.utcnow()
            )
        )
        await session.flush()
        
        logger.info(
            f"Organization association created: tg_user_id={tg_user_id}, inn={inn}"
        )
        
        return organization
    
    except IntegrityError as e:
        logger.error(
            f"Integrity error adding user organization: tg_user_id={tg_user_id}, "
            f"inn={inn}, error={e}",
            exc_info=True
        )
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error adding user organization: tg_user_id={tg_user_id}, "
            f"inn={inn}, error={e}",
            exc_info=True
        )
        raise


# ========== GS_Key Management ==========


async def get_user_keys(session: AsyncSession, tg_user_id: int) -> list[GS_Key]:
    """
    Retrieve all GS_Keys associated with user.
    
    Args:
        session: Database session
        tg_user_id: Telegram user ID
    
    Returns:
        List of GS_Key objects
    
    Raises:
        SQLAlchemyError: If database operation fails
    
    Requirements: 8.1, 16.4
    """
    try:
        result = await session.execute(
            select(GS_Key)
            .where(GS_Key.tg_user_id == tg_user_id)
            .order_by(GS_Key.created_at.desc())
        )
        keys = result.scalars().all()
        
        logger.debug(
            f"Retrieved {len(keys)} GS_Keys for user: tg_user_id={tg_user_id}"
        )
        
        return list(keys)
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error retrieving user keys: tg_user_id={tg_user_id}, error={e}",
            exc_info=True
        )
        raise


async def add_user_key(
    session: AsyncSession,
    tg_user_id: int,
    key_number: str,
    conflict_status: KeyConflictStatus = KeyConflictStatus.NONE
) -> GS_Key:
    """
    Create GS_Key record with conflict status.
    
    Args:
        session: Database session
        tg_user_id: Telegram user ID
        key_number: GS_Key number (e.g., MG123456)
        conflict_status: Conflict status (default: NONE)
    
    Returns:
        Created GS_Key object
    
    Raises:
        ValueError: If user not found
        IntegrityError: If key_number already exists
        SQLAlchemyError: If database operation fails
    
    Requirements: 18.6
    """
    try:
        # Verify user exists
        user = await get_user_by_tg_id(session, tg_user_id)
        if not user:
            error_msg = f"User not found for key addition: tg_user_id={tg_user_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Create GS_Key record
        gs_key = GS_Key(
            key_number=key_number,
            tg_user_id=tg_user_id,
            conflict_status=conflict_status,
            conflict_reported_at=datetime.utcnow() if conflict_status == KeyConflictStatus.PENDING_REVIEW else None
        )
        
        session.add(gs_key)
        await session.flush()
        
        # Log key conflict if detected
        if conflict_status == KeyConflictStatus.PENDING_REVIEW:
            await _log_action(
                session=session,
                action_type=ActionType.KEY_CONFLICT_DETECTED,
                tg_user_id=tg_user_id,
                action_details={
                    "key_number": key_number,
                    "conflict_status": conflict_status.value,
                    "conflict_reported_at": gs_key.conflict_reported_at.isoformat() if gs_key.conflict_reported_at else None
                }
            )
            logger.warning(
                f"GS_Key created with conflict: tg_user_id={tg_user_id}, "
                f"key_number={key_number}, conflict_status={conflict_status.value}"
            )
        else:
            logger.info(
                f"GS_Key created: tg_user_id={tg_user_id}, key_number={key_number}"
            )
        
        return gs_key
    
    except IntegrityError as e:
        logger.error(
            f"Integrity error adding user key: tg_user_id={tg_user_id}, "
            f"key_number={key_number}, error={e}",
            exc_info=True
        )
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error adding user key: tg_user_id={tg_user_id}, "
            f"key_number={key_number}, error={e}",
            exc_info=True
        )
        raise


# ========== Helper Functions ==========


async def _log_action(
    session: AsyncSession,
    action_type: ActionType,
    tg_user_id: int | None = None,
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
        tg_user_id: User ID (optional)
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
            tg_user_id=tg_user_id,
            ticket_id=ticket_id,
            staff_id=staff_id,
            action_details=action_details,
            action_timestamp=datetime.utcnow()
        )
        
        session.add(action_log)
        await session.flush()
        
        logger.debug(
            f"Action logged: type={action_type.value}, tg_user_id={tg_user_id}, "
            f"ticket_id={ticket_id}"
        )
        
        return action_log
    
    except SQLAlchemyError as e:
        logger.error(
            f"Database error logging action: action_type={action_type.value}, "
            f"tg_user_id={tg_user_id}, error={e}",
            exc_info=True
        )
        raise
