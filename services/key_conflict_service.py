"""Shared key-conflict workflow for MAX user flows."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    GS_Key,
    KeyConflictStatus,
    Ticket,
    TicketStatus,
    TicketType,
    User,
    ticket_keys,
)
from services.i_tat_service import get_itat_client
from services.user_service import (
    KeyConflictError,
    add_user_key,
)
from utils.timezone_helpers import get_moscow_now_naive

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class KeyConflictCheck:
    has_conflict: bool
    owner: str | None = None
    source: str = "itat"


@dataclass(slots=True)
class KeyAdditionResult:
    key: GS_Key
    has_conflict: bool
    owner: str | None = None
    source: str = "itat"


async def check_key_conflict(
    session: AsyncSession,
    user: User,
    key_number: str,
) -> KeyConflictCheck:
    """Check i-TAT and the local unique-key constraint before adding a key."""
    source = "itat"
    try:
        response = await get_itat_client().check_key_conflict(
            grand_key=key_number,
            user_id=user.max_user_id,
        )
    except Exception as exc:
        logger.warning(
            "i-TAT key check failed for key %s; using local fallback: %s",
            key_number,
            exc,
        )
        response = None
        source = "local_fallback"

    if response is not None and not isinstance(response, dict):
        logger.warning(
            "Invalid i-TAT key check response for key %s: %r; using local fallback",
            key_number,
            response,
        )
        response = None
        source = "local_fallback"

    status = response.get("status") if isinstance(response, dict) else None
    if status == "conflict":
        return KeyConflictCheck(
            has_conflict=True,
            owner=response.get("owner") or "Неизвестный владелец",
        )
    if status == "available":
        source = "itat"
    elif response is not None:
        logger.warning(
            "Unexpected i-TAT key status for key %s: %r; using local fallback",
            key_number,
            status,
        )
        source = "local_fallback"

    result = await session.execute(
        select(GS_Key).where(GS_Key.key_number == key_number)
    )
    existing_key = result.scalar_one_or_none()
    if existing_key is not None and existing_key.user_id != user.id:
        return KeyConflictCheck(
            has_conflict=True,
            owner=f"Пользователь #{existing_key.user_id}",
            source="local_fallback",
        )

    return KeyConflictCheck(has_conflict=False, source=source)


async def add_key_with_conflict_handling(
    session: AsyncSession,
    user: User,
    key_number: str,
    *,
    force_conflict: bool = False,
    notify_admins: bool = True,
    prechecked: KeyConflictCheck | None = None,
) -> KeyAdditionResult:
    """Add a key, persist conflict metadata, and notify all active admins."""
    if force_conflict:
        check = KeyConflictCheck(has_conflict=True, source="confirmed_by_user")
    elif prechecked is not None:
        check = prechecked
    else:
        check = await check_key_conflict(session, user, key_number)

    try:
        key = await add_user_key(
            session,
            user.id,
            key_number,
            KeyConflictStatus.PENDING_REVIEW
            if check.has_conflict
            else KeyConflictStatus.NONE,
        )
    except KeyConflictError as exc:
        key = exc.gs_key
        check = KeyConflictCheck(
            has_conflict=True,
            owner=f"Пользователь #{exc.existing_user_id}",
            source="local_fallback",
        )

    await session.commit()

    if check.has_conflict and notify_admins:
        from bots.max_bot.utils.admin_notifications import notify_admins_key_conflict

        try:
            await notify_admins_key_conflict(session, user.id, key_number)
        except Exception as exc:
            logger.error(
                "Failed to notify admins about key conflict: user_id=%s, key=%s, error=%s",
                user.id,
                key_number,
                exc,
                exc_info=True,
            )

    return KeyAdditionResult(
        key=key,
        has_conflict=check.has_conflict,
        owner=check.owner,
        source=check.source,
    )


async def close_legacy_key_conflict_tickets(
    session: AsyncSession,
    key_id: int,
    resolution: str,
) -> int:
    """Close old KEY_CONFLICT tickets created by the former profile flow."""
    result = await session.execute(
        select(Ticket)
        .join(ticket_keys, ticket_keys.c.ticket_id == Ticket.id)
        .where(
            ticket_keys.c.key_id == key_id,
            Ticket.ticket_type == TicketType.KEY_CONFLICT,
            Ticket.ticket_status.in_((
                TicketStatus.NEW,
                TicketStatus.IN_PROGRESS,
                TicketStatus.WAITING_CLIENT,
            )),
        )
    )
    tickets = result.scalars().all()
    closed_at = get_moscow_now_naive()
    for ticket in tickets:
        ticket.ticket_status = TicketStatus.CLOSED
        ticket.closed_at = closed_at
        ticket.resolution_comment = resolution

    if tickets:
        await session.flush()
        logger.info(
            "Closed %s legacy KEY_CONFLICT ticket(s) for key_id=%s",
            len(tickets),
            key_id,
        )
    return len(tickets)
