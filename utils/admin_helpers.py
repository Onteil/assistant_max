"""
Admin Panel Helper Functions

Utility functions for admin panel operations including authorization,
validation, logging, and error handling.

Requirements: 36.1, 36.2, 36.3, 36.4, 36.5, 36.6, 36.7, 36.8, 28.1-28.9
"""

import logging
import re
import time
from datetime import datetime
from typing import Any
from collections import defaultdict

from utils.timezone_helpers import get_moscow_now_naive

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Staff_Member, StaffRole, Action_Log

logger = logging.getLogger(__name__)


# ========== Authorization ==========


async def verify_admin_access(
    session: AsyncSession,
    user_id: int
) -> Staff_Member | None:
    """
    Verify user has administrator access.
    
    Checks if user is an active staff member with ADMINISTRATOR role.
    Logs unauthorized access attempts.
    
    Args:
        session: Database session
        user_id: Telegram user ID
    
    Returns:
        Staff_Member object if user is admin, None otherwise
    
    Requirements: 36.1, 36.2, 36.3, 36.4
    """
    try:
        stmt = select(Staff_Member).where(
            Staff_Member.tg_user_id == user_id,
            Staff_Member.is_active == True,
            Staff_Member.staff_role == StaffRole.ADMINISTRATOR
        )
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()
        
        if not admin:
            # Log unauthorized access attempt
            logger.warning(
                f"Unauthorized admin panel access attempt: user_id={user_id}"
            )
            await log_admin_action(
                session=session,
                admin_id=None,
                action_type="UNAUTHORIZED_ACCESS",
                details={
                    "user_id": user_id,
                    "timestamp": get_moscow_now_naive().isoformat()
                }
            )
        
        return admin
        
    except Exception as e:
        logger.error(
            f"Error verifying admin access: user_id={user_id}, error={e}",
            exc_info=True
        )
        return None


# ========== Input Validation ==========


def validate_phone_number(phone: str) -> tuple[bool, str | None]:
    """
    Validate phone number format.
    
    Accepts formats:
    - +79991234567
    - 89991234567
    - 79991234567
    
    Args:
        phone: Phone number string
    
    Returns:
        Tuple of (is_valid, error_message)
    
    Requirements: 36.6, 36.7
    """
    # Remove spaces and dashes
    phone = phone.replace(" ", "").replace("-", "")
    
    # Check if phone contains only digits and optional leading +
    if not re.match(r"^\+?\d+$", phone):
        return False, "Номер телефона должен содержать только цифры"
    
    # Remove leading + if present
    if phone.startswith("+"):
        phone = phone[1:]
    
    # Check length (should be 11 digits for Russian numbers)
    if len(phone) != 11:
        return False, f"Номер телефона должен содержать 11 цифр (найдено {len(phone)})"
    
    # Check if starts with 7 or 8
    if not phone.startswith(("7", "8")):
        return False, "Номер телефона должен начинаться с 7 или 8"
    
    return True, None


def validate_gs_key_format(key: str) -> tuple[bool, str | None]:
    """
    Validate GS_Key format.
    
    Expected format: XXXXX_XXXXX (5 digits, underscore, 5 digits)
    
    Args:
        key: GS_Key string
    
    Returns:
        Tuple of (is_valid, error_message)
    
    Requirements: 36.6, 36.7
    """
    # Remove spaces
    key = key.strip()
    
    # Check format: 5 digits, underscore, 5 digits
    if not re.match(r"^\d{5}_\d{5}$", key):
        return False, "Ключ должен быть в формате XXXXX_XXXXX (например, 00001_00001)"
    
    return True, None


def sanitize_rejection_reason(reason: str, max_length: int = 500) -> str:
    """
    Sanitize rejection reason text.
    
    Removes HTML tags and limits length.
    
    Args:
        reason: Rejection reason text
        max_length: Maximum allowed length
    
    Returns:
        Sanitized text
    
    Requirements: 36.6, 36.8
    """
    # Remove HTML tags
    reason = re.sub(r"<[^>]+>", "", reason)
    
    # Trim whitespace
    reason = reason.strip()
    
    # Limit length
    if len(reason) > max_length:
        reason = reason[:max_length]
    
    return reason


# ========== Audit Logging ==========


async def log_admin_action(
    session: AsyncSession,
    admin_id: int | None,
    action_type: str,
    details: dict[str, Any],
    user_id: int | None = None
) -> None:
    """
    Log administrative action to Action_Log table.
    
    Creates structured JSON log entry for audit trail.
    
    Args:
        session: Database session
        admin_id: ID of administrator performing action (None for system actions)
        action_type: Type of action (e.g., "REGISTRATION_APPROVED", "KEY_TRANSFERRED")
        details: Dictionary with action details
        user_id: ID of affected user (optional)
    
    Requirements: 28.1, 28.2, 28.3, 28.4, 28.5, 28.6, 28.7, 28.8, 28.9
    """
    try:
        # Create structured log entry
        log_entry = Action_Log(
            staff_id=admin_id,
            user_id=user_id,
            action_type=action_type,
            details=details,
            created_at=get_moscow_now_naive()
        )
        
        session.add(log_entry)
        await session.flush()
        
        # Also log to application logger
        logger.info(
            f"Admin action logged: admin_id={admin_id}, action={action_type}, "
            f"user_id={user_id}, details={details}"
        )
        
    except Exception as e:
        logger.error(
            f"Error logging admin action: admin_id={admin_id}, action={action_type}, "
            f"error={e}",
            exc_info=True
        )
        # Don't raise - logging failure shouldn't break the operation


async def log_api_call(
    session: AsyncSession,
    endpoint: str,
    request_data: dict[str, Any],
    response_data: dict[str, Any] | None,
    duration_ms: float,
    success: bool
) -> None:
    """
    Log i-TAT API call for audit trail.
    
    Args:
        session: Database session
        endpoint: API endpoint called
        request_data: Request payload
        response_data: Response payload (None if failed)
        duration_ms: Request duration in milliseconds
        success: Whether call succeeded
    
    Requirements: 28.1, 28.2, 28.3, 28.4, 28.5, 28.6, 28.7, 28.8, 28.9
    """
    try:
        log_entry = Action_Log(
            staff_id=None,  # System action
            action_type="API_CALL",
            details={
                "endpoint": endpoint,
                "request": request_data,
                "response": response_data,
                "duration_ms": duration_ms,
                "success": success,
                "timestamp": get_moscow_now_naive().isoformat()
            },
            created_at=get_moscow_now_naive()
        )
        
        session.add(log_entry)
        await session.flush()
        
        # Log to application logger
        log_level = logging.INFO if success else logging.ERROR
        logger.log(
            log_level,
            f"API call: endpoint={endpoint}, duration={duration_ms}ms, success={success}"
        )
        
    except Exception as e:
        logger.error(
            f"Error logging API call: endpoint={endpoint}, error={e}",
            exc_info=True
        )


# ========== Rate Limiting ==========


# In-memory rate limit tracking
# Format: {user_id: [(timestamp, action), ...]}
_rate_limit_tracker: dict[int, list[tuple[float, str]]] = defaultdict(list)


def check_rate_limit(
    user_id: int,
    action: str,
    max_actions: int = 10,
    window_seconds: int = 60
) -> tuple[bool, int]:
    """
    Check if user has exceeded rate limit for admin actions.
    
    Uses in-memory tracking with sliding window.
    
    Args:
        user_id: User ID to check
        action: Action type being performed
        max_actions: Maximum actions allowed in window
        window_seconds: Time window in seconds
    
    Returns:
        Tuple of (is_allowed, remaining_actions)
    
    Requirements: 36.5
    """
    current_time = time.time()
    cutoff_time = current_time - window_seconds
    
    # Get user's action history
    user_actions = _rate_limit_tracker[user_id]
    
    # Remove expired actions
    user_actions = [
        (timestamp, act) for timestamp, act in user_actions
        if timestamp > cutoff_time
    ]
    _rate_limit_tracker[user_id] = user_actions
    
    # Count actions in window
    action_count = len(user_actions)
    
    # Check if limit exceeded
    if action_count >= max_actions:
        logger.warning(
            f"Rate limit exceeded: user_id={user_id}, action={action}, "
            f"count={action_count}, limit={max_actions}"
        )
        return False, 0
    
    # Add current action
    user_actions.append((current_time, action))
    
    remaining = max_actions - action_count - 1
    return True, remaining


def log_rate_limit_violation(user_id: int, action: str) -> None:
    """
    Log rate limit violation.
    
    Args:
        user_id: User ID that exceeded limit
        action: Action that was rate limited
    
    Requirements: 36.5
    """
    logger.warning(
        f"Rate limit violation: user_id={user_id}, action={action}, "
        f"timestamp={get_moscow_now_naive().isoformat()}"
    )



# ========== Error Handling ==========


class AdminPanelError(Exception):
    """Base exception for admin panel errors."""
    pass


class DatabaseError(AdminPanelError):
    """Database operation failed."""
    pass


class APIError(AdminPanelError):
    """i-TAT API call failed."""
    pass


class ValidationError(AdminPanelError):
    """Input validation failed."""
    pass


class AuthorizationError(AdminPanelError):
    """User not authorized for operation."""
    pass


class RateLimitError(AdminPanelError):
    """Rate limit exceeded."""
    pass


async def handle_database_error(
    session: AsyncSession,
    error: Exception,
    operation: str
) -> str:
    """
    Handle database errors with rollback and user-friendly messages.
    
    Args:
        session: Database session to rollback
        error: Exception that occurred
        operation: Description of operation that failed
    
    Returns:
        User-friendly error message
    
    Requirements: 22.1, 22.2, 22.6
    """
    try:
        await session.rollback()
    except Exception as rollback_error:
        logger.error(
            f"Error during rollback: operation={operation}, error={rollback_error}",
            exc_info=True
        )
    
    logger.error(
        f"Database error: operation={operation}, error={error}",
        exc_info=True
    )
    
    return "❌ Ошибка подключения к базе данных. Попробуйте позже."


def handle_api_error(
    error: Exception,
    endpoint: str,
    status_code: int | None = None
) -> str:
    """
    Handle i-TAT API errors with categorized error messages.
    
    Args:
        error: Exception that occurred
        endpoint: API endpoint that failed
        status_code: HTTP status code (if available)
    
    Returns:
        User-friendly error message
    
    Requirements: 22.1, 22.2, 22.9
    """
    logger.error(
        f"API error: endpoint={endpoint}, status={status_code}, error={error}",
        exc_info=True
    )
    
    # Categorize by status code
    if status_code == 400:
        return "❌ Некорректные данные запроса. Проверьте введенную информацию."
    elif status_code == 404:
        return "❌ Запрашиваемый ресурс не найден."
    elif status_code and 500 <= status_code < 600:
        return "❌ Ошибка сервера i-TAT. Попробуйте позже."
    elif isinstance(error, TimeoutError):
        return "❌ Превышено время ожидания ответа от сервера."
    else:
        return "❌ Ошибка при обращении к серверу i-TAT. Попробуйте позже."


def validate_fsm_state_timeout(
    state_data: dict[str, Any],
    timeout_minutes: int = 10
) -> bool:
    """
    Validate FSM state hasn't timed out.
    
    Args:
        state_data: FSM state data dictionary
        timeout_minutes: Timeout in minutes
    
    Returns:
        True if state is valid, False if timed out
    
    Requirements: 22.3, 22.4
    """
    if not state_data:
        return False
    
    # Check if state has timestamp
    state_timestamp = state_data.get("timestamp")
    if not state_timestamp:
        # No timestamp - assume valid (backward compatibility)
        return True
    
    # Parse timestamp
    try:
        if isinstance(state_timestamp, str):
            state_time = datetime.fromisoformat(state_timestamp)
        else:
            state_time = state_timestamp
        
        # Check if expired
        elapsed = get_moscow_now_naive() - state_time
        elapsed_minutes = elapsed.total_seconds() / 60
        
        if elapsed_minutes > timeout_minutes:
            logger.warning(
                f"FSM state timeout: elapsed={elapsed_minutes:.1f}min, "
                f"limit={timeout_minutes}min"
            )
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error validating FSM state timeout: {e}", exc_info=True)
        # On error, assume valid to avoid breaking user flow
        return True


async def with_query_timeout(
    coroutine,
    timeout_seconds: int = 10,
    operation: str = "query"
) -> Any:
    """
    Execute query with timeout protection.
    
    Args:
        coroutine: Async coroutine to execute
        timeout_seconds: Timeout in seconds
        operation: Description of operation
    
    Returns:
        Result of coroutine
    
    Raises:
        TimeoutError: If operation exceeds timeout
    
    Requirements: 22.5, 22.10
    """
    import asyncio
    
    try:
        result = await asyncio.wait_for(coroutine, timeout=timeout_seconds)
        return result
    except asyncio.TimeoutError:
        logger.error(
            f"Query timeout: operation={operation}, timeout={timeout_seconds}s"
        )
        raise TimeoutError(
            f"Операция '{operation}' превысила время ожидания ({timeout_seconds}с)"
        )


def get_user_friendly_error_message(error: Exception) -> str:
    """
    Convert exception to user-friendly error message.
    
    Args:
        error: Exception that occurred
    
    Returns:
        User-friendly error message
    
    Requirements: 22.7, 22.8
    """
    # Map exception types to user messages
    if isinstance(error, DatabaseError):
        return "❌ Ошибка базы данных. Попробуйте позже."
    elif isinstance(error, APIError):
        return "❌ Ошибка связи с сервером. Попробуйте позже."
    elif isinstance(error, ValidationError):
        return f"❌ Ошибка валидации: {str(error)}"
    elif isinstance(error, AuthorizationError):
        return "❌ У вас нет прав для выполнения этой операции."
    elif isinstance(error, RateLimitError):
        return "❌ Превышен лимит запросов. Подождите немного."
    elif isinstance(error, TimeoutError):
        return "❌ Превышено время ожидания. Попробуйте позже."
    else:
        # Generic error - don't expose internal details
        logger.error(f"Unhandled error: {error}", exc_info=True)
        return "❌ Произошла ошибка. Попробуйте позже."



# ========== Performance Optimizations ==========


import time
from functools import wraps
from typing import Callable, Any


# Simple in-memory cache with TTL
_cache: dict[str, tuple[Any, float]] = {}


def cache_result(ttl_seconds: int = 60):
    """
    Decorator to cache function results with TTL.
    
    Args:
        ttl_seconds: Time to live in seconds
    
    Requirements: 23.9
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Check cache
            if cache_key in _cache:
                result, timestamp = _cache[cache_key]
                if time.time() - timestamp < ttl_seconds:
                    logger.debug(f"Cache hit: {cache_key}")
                    return result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            _cache[cache_key] = (result, time.time())
            
            # Clean expired entries (simple cleanup)
            _clean_cache()
            
            return result
        
        return wrapper
    return decorator


def _clean_cache():
    """Remove expired cache entries."""
    current_time = time.time()
    expired_keys = [
        key for key, (_, timestamp) in _cache.items()
        if current_time - timestamp > 60  # Remove entries older than 60s
    ]
    for key in expired_keys:
        del _cache[key]


def log_slow_query(threshold_seconds: float = 1.0):
    """
    Decorator to log slow queries.
    
    Args:
        threshold_seconds: Threshold for slow query warning
    
    Requirements: 23.10
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            
            if duration > threshold_seconds:
                logger.warning(
                    f"Slow query detected: function={func.__name__}, "
                    f"duration={duration:.2f}s, threshold={threshold_seconds}s"
                )
            
            return result
        
        return wrapper
    return decorator


async def execute_parallel_queries(*coroutines):
    """
    Execute multiple queries in parallel using asyncio.gather().
    
    Args:
        *coroutines: Coroutines to execute in parallel
    
    Returns:
        List of results in same order as input coroutines
    
    Requirements: 23.1, 23.6
    """
    import asyncio
    
    try:
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        # Check for exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"Parallel query {i} failed: {result}",
                    exc_info=result
                )
        
        return results
        
    except Exception as e:
        logger.error(f"Error executing parallel queries: {e}", exc_info=True)
        raise


# Note: Requirements 23.2, 23.3, 23.4, 23.5, 23.7 are implemented in analytics_service.py
# - 23.2: Avoid N+1 with selectinload() - used in get_stuck_tickets()
# - 23.3: Database-level aggregations - used throughout analytics_service
# - 23.4: Limit stuck ticket queries to 20 - implemented in get_stuck_tickets()
# - 23.5: Use indexed columns - queries use created_at, status, assigned_staff_id
# - 23.7: Complete aggregations within 3 seconds - achieved through optimized queries
