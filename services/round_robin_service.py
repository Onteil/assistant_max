"""
Round-Robin Assignment Service.

Implements circular staff assignment for TECHNICAL_SUPPORT and CONSULTATION tickets.
Instead of broadcasting to all available specialists, each new ticket is assigned
to the next specialist in rotation, preventing duplicate handling.

State is persisted in system_settings:
  - support_rr_last_staff_id   — last assigned support staff ID
  - consultation_rr_last_staff_id — last assigned consultation specialist ID

If the stored ID is 0 or not found among active staff, assignment starts from
the first staff member in the sorted list (by id ascending).
"""

import logging

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    SettingCategory,
    SettingDataType,
    Staff_Member,
    StaffRole,
    System_Settings,
)

logger = logging.getLogger(__name__)

# Setting keys used to persist round-robin state
_RR_KEY_SUPPORT = "support_rr_last_staff_id"
_RR_KEY_CONSULTATION = "consultation_rr_last_staff_id"

# Mapping from ticket type label to setting key
_RR_KEYS: dict[str, str] = {
    "support": _RR_KEY_SUPPORT,
    "consultation": _RR_KEY_CONSULTATION,
}


# ========== Internal helpers ==========


async def _ensure_rr_setting(session: AsyncSession, key: str) -> None:
    """
    Create the round-robin setting row if it does not exist yet.

    Uses an upsert-style check so it is safe to call on every request.
    """
    result = await session.execute(
        select(System_Settings).where(System_Settings.key == key)
    )
    if result.scalar_one_or_none() is None:
        setting = System_Settings(
            key=key,
            category=SettingCategory.DUTY_SUPPORT,
            value="0",
            data_type=SettingDataType.INTEGER,
            default_value="0",
            min_value=0,
            max_value=None,
            description=(
                "ID последнего сотрудника, которому была назначена заявка "
                "через круговое распределение (round-robin). "
                "Значение 0 означает «начать с первого»."
            ),
            display_name=(
                "Последний назначенный (ТП)"
                if key == _RR_KEY_SUPPORT
                else "Последний назначенный (Консультация)"
            ),
            requires_test=False,
        )
        session.add(setting)
        await session.flush()
        logger.info(f"Created round-robin setting: {key}")


async def _get_last_staff_id(session: AsyncSession, key: str) -> int:
    """Return the last assigned staff ID (0 if not set / not found)."""
    result = await session.execute(
        select(System_Settings.value).where(System_Settings.key == key)
    )
    raw = result.scalar_one_or_none()
    if raw is None:
        return 0
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


async def _save_last_staff_id(session: AsyncSession, key: str, staff_id: int) -> None:
    """Persist the newly assigned staff ID."""
    await session.execute(
        update(System_Settings)
        .where(System_Settings.key == key)
        .values(value=str(staff_id))
    )


# ========== Core round-robin logic ==========


async def _pick_next_staff(
    session: AsyncSession,
    staff_list: list[Staff_Member],
    rr_key: str,
) -> Staff_Member | None:
    """
    Select the next staff member in round-robin order.

    Algorithm:
      1. Sort staff by id ascending (stable, deterministic order).
      2. Read last_staff_id from system_settings.
      3. Find the position of last_staff_id in the sorted list.
      4. Return the member at position (last_pos + 1) % len(list).
      5. Persist the chosen member's id.

    Args:
        session: Database session (must be within an active transaction).
        staff_list: Non-empty list of active staff candidates.
        rr_key: system_settings key for this ticket type.

    Returns:
        The chosen Staff_Member, or None if staff_list is empty.
    """
    if not staff_list:
        return None

    # Ensure the setting row exists
    await _ensure_rr_setting(session, rr_key)

    # Sort by id for a stable, predictable rotation order
    sorted_staff = sorted(staff_list, key=lambda s: s.id)

    last_id = await _get_last_staff_id(session, rr_key)

    # Find the index of the last assigned staff member
    last_index = -1
    for i, staff in enumerate(sorted_staff):
        if staff.id == last_id:
            last_index = i
            break
    # If last_id is 0 or not found, last_index stays -1 → next = index 0

    next_index = (last_index + 1) % len(sorted_staff)
    chosen = sorted_staff[next_index]

    await _save_last_staff_id(session, rr_key, chosen.id)

    logger.info(
        f"Round-robin [{rr_key}]: last_id={last_id}, "
        f"candidates={[s.id for s in sorted_staff]}, "
        f"chosen={chosen.id} ({chosen.full_name})"
    )

    return chosen


# ========== Public API ==========


async def get_next_support_staff(session: AsyncSession) -> Staff_Member | None:
    """
    Return the next TECHNICAL_SUPPORT staff member via round-robin.

    Selects from active staff with:
      - staff_role == TECHNICAL_SUPPORT
      - is_active == True
      - max_user_id IS NOT NULL  (must be reachable via MAX)
      - is_estimate_tech_specialist == False  (exclude consultation specialists)

    Returns None if no eligible staff members exist.

    Args:
        session: Database session.

    Returns:
        Staff_Member to assign, or None.
    """
    stmt = select(Staff_Member).where(
        and_(
            Staff_Member.staff_role == StaffRole.TECHNICAL_SUPPORT,
            Staff_Member.is_active.is_(True),
            Staff_Member.max_user_id.isnot(None),
            Staff_Member.is_estimate_tech_specialist.is_(False),
        )
    )
    result = await session.execute(stmt)
    candidates = result.scalars().all()

    if not candidates:
        logger.warning("No active support staff available for round-robin assignment")
        return None

    return await _pick_next_staff(session, list(candidates), _RR_KEY_SUPPORT)


async def get_next_consultation_specialist(session: AsyncSession) -> Staff_Member | None:
    """
    Return the next consultation specialist via round-robin.

    Selects from active staff with:
      - is_estimate_tech_specialist == True
      - is_active == True
      - max_user_id IS NOT NULL

    Returns None if no eligible specialists exist.

    Args:
        session: Database session.

    Returns:
        Staff_Member to assign, or None.
    """
    stmt = select(Staff_Member).where(
        and_(
            Staff_Member.is_active.is_(True),
            Staff_Member.is_estimate_tech_specialist.is_(True),
            Staff_Member.max_user_id.isnot(None),
        )
    )
    result = await session.execute(stmt)
    candidates = result.scalars().all()

    if not candidates:
        logger.warning("No active consultation specialists available for round-robin assignment")
        return None

    return await _pick_next_staff(session, list(candidates), _RR_KEY_CONSULTATION)
