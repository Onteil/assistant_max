"""
Admin Data Endpoints

API endpoints for fetching data for admin panel dropdowns.
"""

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Header, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from constants import get_session
from database.models import User, Staff_Member, RegistrationStatus

router = APIRouter()
logger = logging.getLogger(__name__)

# Get API key from environment
WEBHOOK_API_KEY = os.getenv("WEBHOOK_API_KEY")


async def verify_api_key(
    x_api_key: Annotated[str | None, Header()] = None
) -> str:
    """
    Verify API key authentication.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        Validated API key
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    if not x_api_key:
        logger.warning("Admin data API request received without API key")
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


@router.get("/admin/users")
async def get_users_list(
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_api_key)],
    messenger: str = Query(default="all", description="Filter by messenger: telegram, max, or all"),
    search: str = Query(default="", description="Search by name or phone"),
    status: str = Query(default="all", description="Filter by registration status: active, pending, under_review, rejected, or all"),
    limit: int = Query(default=500, le=1000, description="Maximum number of results")
):
    """
    Get list of users for admin panel dropdowns.
    
    Args:
        session: Database session
        messenger: Filter by messenger type
        search: Search query for name or phone
        status: Filter by registration status
        limit: Maximum results to return
    
    Returns:
        List of users with id, name, phone, and messenger IDs
    """
    try:
        # Build query - by default show all users except rejected
        stmt = select(User)
        
        # Filter by registration status
        if status == "active":
            stmt = stmt.where(User.registration_status == RegistrationStatus.ACTIVE)
        elif status == "pending":
            stmt = stmt.where(User.registration_status == RegistrationStatus.PENDING)
        elif status == "under_review":
            stmt = stmt.where(User.registration_status == RegistrationStatus.UNDER_REVIEW)
        elif status == "rejected":
            stmt = stmt.where(User.registration_status == RegistrationStatus.REJECTED)
        elif status == "all":
            # Show all users except rejected (most common use case)
            stmt = stmt.where(User.registration_status != RegistrationStatus.REJECTED)
        
        # Filter by messenger
        if messenger == "telegram":
            stmt = stmt.where(User.tg_user_id.isnot(None))
        elif messenger == "max":
            stmt = stmt.where(User.max_user_id.isnot(None))
        
        # Search filter
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(search_pattern),
                    User.phone_number.ilike(search_pattern),
                    User.first_name.ilike(search_pattern),
                    User.last_name.ilike(search_pattern)
                )
            )
        
        # Order and limit - show newest users first
        stmt = stmt.order_by(User.created_at.desc()).limit(limit)
        
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        # Format response
        users_list = []
        for user in users:
            # Build full name
            full_name = user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip() or "Без имени"
            
            # Build display string with all information
            phone = user.phone_number or "N/A"
            max_id = user.max_user_id or "N/A"
            reg_date = user.created_at.strftime('%d.%m.%Y') if user.created_at else "N/A"
            
            # Add status indicator
            status_icon = {
                RegistrationStatus.ACTIVE: "✓",
                RegistrationStatus.PENDING: "⏳",
                RegistrationStatus.UNDER_REVIEW: "🔍",
                RegistrationStatus.REJECTED: "✗"
            }.get(user.registration_status, "?")
            
            users_list.append({
                "id": user.id,
                "full_name": full_name,
                "phone": user.phone_number,
                "tg_user_id": user.tg_user_id,
                "max_user_id": user.max_user_id,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "registration_status": user.registration_status.value,
                "display": f"{status_icon} {full_name} | {phone} | MAX: {max_id} | Рег: {reg_date}"
            })
        
        return {
            "status": "success",
            "count": len(users_list),
            "users": users_list
        }
        
    except Exception as e:
        logger.error(f"Error fetching users list: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "users": []
        }


@router.get("/admin/staff")
async def get_staff_list(
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_api_key)],
    messenger: str = Query(default="all", description="Filter by messenger: telegram, max, or all"),
    search: str = Query(default="", description="Search by name or position"),
    limit: int = Query(default=100, le=500, description="Maximum number of results")
):
    """
    Get list of staff members for admin panel dropdowns.
    
    Args:
        session: Database session
        messenger: Filter by messenger type
        search: Search query for name or position
        limit: Maximum results to return
    
    Returns:
        List of staff members with id, name, position, role, and messenger IDs
    """
    try:
        # Build query
        stmt = select(Staff_Member).where(Staff_Member.is_active == True)
        
        # Filter by messenger
        if messenger == "telegram":
            stmt = stmt.where(Staff_Member.tg_user_id.isnot(None))
        elif messenger == "max":
            stmt = stmt.where(Staff_Member.max_user_id.isnot(None))
        
        # Search filter
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Staff_Member.full_name.ilike(search_pattern),
                    Staff_Member.position.ilike(search_pattern)
                )
            )
        
        # Order and limit
        stmt = stmt.order_by(Staff_Member.full_name).limit(limit)
        
        result = await session.execute(stmt)
        staff_members = result.scalars().all()
        
        # Format response
        staff_list = []
        for staff in staff_members:
            # Build display string with all information
            role = staff.staff_role.value if staff.staff_role else "N/A"
            position = staff.position or "N/A"
            max_id = staff.max_user_id or "N/A"
            status = "✓" if staff.is_active else "✗"
            
            staff_list.append({
                "id": staff.id,
                "full_name": staff.full_name,
                "position": staff.position,
                "role": role,
                "tg_user_id": staff.tg_user_id,
                "max_user_id": staff.max_user_id,
                "is_active": staff.is_active,
                "display": f"{staff.full_name} | {position} ({role}) | MAX: {max_id} | {status}"
            })
        
        return {
            "status": "success",
            "count": len(staff_list),
            "staff": staff_list
        }
        
    except Exception as e:
        logger.error(f"Error fetching staff list: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "staff": []
        }


@router.get("/admin/user/{user_id}")
async def get_user_details(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_api_key)]
):
    """
    Get detailed information about a specific user.
    
    Args:
        user_id: Internal user ID
        session: Database session
    
    Returns:
        User details including messenger IDs and phone
    """
    try:
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return {
                "status": "error",
                "message": "User not found"
            }
        
        return {
            "status": "success",
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "phone": user.phone_number,
                "email": user.email,
                "tg_user_id": user.tg_user_id,
                "max_user_id": user.max_user_id,
                "registration_status": user.registration_status.value,
                "subscription_status": user.subscription_status.value,
                "subscription_end_date": user.subscription_end_date.isoformat() if user.subscription_end_date else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


@router.get("/admin/staff/{staff_id}")
async def get_staff_details(
    staff_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str, Depends(verify_api_key)]
):
    """
    Get detailed information about a specific staff member.
    
    Args:
        staff_id: Internal staff ID
        session: Database session
    
    Returns:
        Staff member details including messenger IDs
    """
    try:
        stmt = select(Staff_Member).where(Staff_Member.id == staff_id)
        result = await session.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if not staff:
            return {
                "status": "error",
                "message": "Staff member not found"
            }
        
        return {
            "status": "success",
            "staff": {
                "id": staff.id,
                "full_name": staff.full_name,
                "position": staff.position,
                "role": staff.staff_role.value,
                "tg_user_id": staff.tg_user_id,
                "max_user_id": staff.max_user_id,
                "is_active": staff.is_active
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching staff {staff_id}: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }
