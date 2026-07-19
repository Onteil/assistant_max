"""Shared helpers for MAX callback acknowledgements."""

import logging
from typing import Any

from maxapi.types import MessageCallback

logger = logging.getLogger(__name__)

STALE_CALLBACK_ERROR = "error.edit.invalid.message"


def is_stale_max_callback_error(error: Exception) -> bool:
    """Return True when MAX reports that the callback was already handled."""
    return STALE_CALLBACK_ERROR in str(error).lower()


async def answer_max_callback(
    event: MessageCallback,
    notification: str | None = None,
    new_text: str | None = None,
    link: Any = None,
    format: Any = None,
    *,
    notify: bool = True,
    raise_if_not_exists: bool = True,
) -> bool:
    """
    Acknowledge a MAX callback.

    False means the callback was already handled and the caller must stop to
    avoid executing the same business action twice.
    """
    try:
        if new_text is None and link is None and format is None:
            if event.bot is None:
                raise RuntimeError("MAX bot is not initialized")
            await event.bot.send_callback(
                callback_id=event.callback.callback_id,
                message=None,
                notification=notification,
            )
        else:
            await event.answer(
                notification=notification,
                new_text=new_text,
                link=link,
                format=format,
                notify=notify,
                raise_if_not_exists=raise_if_not_exists,
            )
        return True
    except Exception as error:
        if is_stale_max_callback_error(error):
            logger.debug("Stale MAX callback skipped: %s", error)
            return False
        raise
