"""
Helper for calling i-TAT API methods with automatic retry queue support.

Usage:
    from services.itat_retry_helper import call_itat_with_retry

    result = await call_itat_with_retry(
        session=session,
        operation="update_user_assets",
        payload=dict(
            messenger="max",
            user_id=user.max_user_id,
            asset_type="inn",
            action="add",
            value=inn,
        ),
        user_id=user.id,  # internal DB id, optional
    )
    # result is None if queued for retry, or the API response dict on success

On transient errors (connection, timeout, 5xx):
  - Queues the operation in api_retry_queue
  - Notifies admins (temporary, for testing)
  - Returns None so the caller can continue without crashing

On non-retryable errors (4xx):
  - Re-raises NonRetryableAPIError so the caller can handle it
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from services.i_tat_service import NonRetryableAPIError, RetryableAPIError, get_itat_client

logger = logging.getLogger(__name__)


async def call_itat_with_retry(
    session: AsyncSession,
    operation: str,
    payload: dict[str, Any],
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Call an ITatAPIClient method and automatically queue for retry on transient errors.

    Args:
        session: Active database session (must be open for the duration of the call)
        operation: ITatAPIClient method name, e.g. "update_user_assets"
        payload: Keyword arguments to pass to the method
        user_id: Internal user DB id for context (optional, used in notifications)

    Returns:
        API response dict on success, or None if the call was queued for retry.

    Raises:
        NonRetryableAPIError: For 4xx errors — caller must handle these explicitly.
        AttributeError: If `operation` is not a valid ITatAPIClient method.
    """
    from services.retry_service import queue_api_retry
    from bots.max_bot.utils.admin_notifications import notify_admins_api_retry_queued

    api_client = get_itat_client()
    try:
        if not hasattr(api_client, operation):
            raise AttributeError(f"ITatAPIClient has no method '{operation}'")

        method = getattr(api_client, operation)
        result = await method(**payload)
        return result

    except NonRetryableAPIError:
        # 4xx — let the caller decide what to do
        raise

    except RetryableAPIError as e:
        error_message = str(e)
        logger.warning(
            f"Transient i-TAT error, queuing for retry: "
            f"operation={operation}, user_id={user_id}, error={error_message}"
        )

        try:
            retry_record = await queue_api_retry(
                session=session,
                operation=operation,
                payload=payload,
                user_id=user_id,
                error_message=error_message,
            )
            await session.flush()

            # Notify admins (temporary — remove after production stabilises)
            try:
                await notify_admins_api_retry_queued(
                    session=session,
                    operation=operation,
                    payload=payload,
                    error_message=error_message,
                    retry_id=retry_record.id,
                    user_id=user_id,
                )
            except Exception as notify_err:
                logger.warning(f"Failed to send retry_queued admin notification: {notify_err}")

        except Exception as queue_err:
            logger.error(
                f"Failed to queue retry for operation={operation}: {queue_err}",
                exc_info=True,
            )

        return None

    finally:
        await api_client.close()
