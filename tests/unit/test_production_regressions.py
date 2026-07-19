from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from api.utils import messenger_utils
from api.webhooks.ticket_status_webhooks import _select_notification_messenger
from bots.max_bot.handlers.user.main_menu_callbacks import _is_stale_callback_error
from celery_app.escalation_tasks import _is_max_chat_id
from celery_app.nps_tasks import (
    NPS_PROCESSING_LOCK_TTL_SECONDS,
    _claim_nps_delivery,
    _release_nps_delivery,
    build_nps_delivery_key,
    build_nps_task_id,
)
from database.models import SurveyType
from services.i_tat_service import (
    ITatAPIClient,
    NonRetryableAPIError,
    RetryableAPIError,
    _is_1c_version_conflict_response,
)
from services.user_service import _insert_gs_key_with_savepoint


def test_nps_business_key_is_stable_and_event_specific():
    first = build_nps_delivery_key(10, "service_quality", 245)
    duplicate = build_nps_delivery_key(10, "service_quality", 245)
    another_ticket = build_nps_delivery_key(10, "service_quality", 246)

    assert first == duplicate
    assert first != another_ticket
    assert build_nps_task_id(10, "service_quality", 245).startswith("nps-")


def test_nps_delivery_claim_uses_atomic_set_nx():
    redis_client = Mock()
    redis_client.set.return_value = True

    claimed = _claim_nps_delivery(redis_client, "nps:key", "task-1")

    assert claimed is True
    redis_client.set.assert_called_once_with(
        "nps:key",
        "processing:task-1",
        nx=True,
        ex=NPS_PROCESSING_LOCK_TTL_SECONDS,
    )


def test_nps_delivery_release_compares_lock_owner():
    redis_client = Mock()

    _release_nps_delivery(redis_client, "nps:key", "task-1")

    script, key_count, key, owner = redis_client.eval.call_args.args
    assert 'redis.call("get", KEYS[1])' in script
    assert (key_count, key, owner) == (1, "nps:key", "processing:task-1")


@pytest.mark.asyncio
async def test_schedule_survey_uses_deterministic_task_id(monkeypatch):
    from celery_app.nps_tasks import send_nps_survey_task
    from services import nps_service

    monkeypatch.setattr(
        nps_service,
        "check_frequency_limit",
        AsyncMock(return_value=(True, None)),
    )
    monkeypatch.setattr(
        nps_service,
        "get_setting",
        AsyncMock(return_value=1),
    )
    apply_async = Mock(return_value=SimpleNamespace(id="scheduled-task"))
    monkeypatch.setattr(send_nps_survey_task, "apply_async", apply_async)

    scheduled, reason = await nps_service.schedule_survey(
        session=AsyncMock(),
        user_id=10,
        survey_type=SurveyType.SERVICE_QUALITY,
        trigger_event_id=245,
        event_date=datetime(2026, 7, 18, 13, 57),
    )

    assert (scheduled, reason) == (True, "scheduled")
    assert apply_async.call_args.kwargs["task_id"] == build_nps_task_id(
        10,
        SurveyType.SERVICE_QUALITY.value,
        245,
    )


def test_itat_409_version_mismatch_is_detected_as_transient():
    response = (
        "1C:Enterprise 8 application error: "
        "Различаются версии клиента и сервера (8.3.27.1719 - 8.3.27.2130)"
    )

    assert _is_1c_version_conflict_response(response)
    assert not _is_1c_version_conflict_response("User already exists")


@pytest.mark.asyncio
async def test_itat_409_version_mismatch_is_retryable():
    endpoint = "http://itat/tickets/log"
    response = httpx.Response(
        409,
        text="Различаются версии клиента и сервера",
        request=httpx.Request("POST", endpoint),
    )
    client = object.__new__(ITatAPIClient)
    client.client = SimpleNamespace(post=AsyncMock(return_value=response))

    with pytest.raises(RetryableAPIError):
        await client._make_request("POST", endpoint, json={})


@pytest.mark.asyncio
async def test_regular_itat_409_remains_non_retryable():
    endpoint = "http://itat/user/register"
    response = httpx.Response(
        409,
        text="User already exists",
        request=httpx.Request("POST", endpoint),
    )
    client = object.__new__(ITatAPIClient)
    client.client = SimpleNamespace(post=AsyncMock(return_value=response))

    with pytest.raises(NonRetryableAPIError):
        await client._make_request("POST", endpoint, json={})


@pytest.mark.asyncio
async def test_webhook_telegram_notification_resolves_internal_user_id(monkeypatch):
    query_result = Mock()
    query_result.scalar_one_or_none.return_value = 777000111
    session = SimpleNamespace(execute=AsyncMock(return_value=query_result))
    send_telegram = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(messenger_utils, "_send_telegram_message", send_telegram)

    result = await messenger_utils.send_message_to_user(
        messenger="telegram",
        user_id=42,
        text="Ticket closed",
        session=session,
    )

    assert result == {"success": True}
    send_telegram.assert_awaited_once_with(
        777000111,
        "Ticket closed",
        None,
        "HTML",
    )


@pytest.mark.parametrize(
    ("preferred", "tg_id", "max_chat_id", "expected"),
    [
        ("telegram", 100, 200, ("telegram", 100)),
        ("telegram", None, 200, ("max", 200)),
        ("max", 100, None, ("telegram", 100)),
        ("max", 100, 200, ("max", 200)),
        ("max", None, None, (None, None)),
    ],
)
def test_ticket_notification_messenger_fallback(
    preferred,
    tg_id,
    max_chat_id,
    expected,
):
    assert _select_notification_messenger(
        preferred,
        tg_id,
        max_chat_id,
    ) == expected


def test_only_known_stale_max_callback_error_is_suppressed():
    assert _is_stale_callback_error(
        RuntimeError("code=400 message=error.edit.invalid.message")
    )
    assert not _is_stale_callback_error(RuntimeError("network timeout"))


@pytest.mark.parametrize(
    ("chat_id", "expected"),
    [
        ("12345678", True),
        (123456789, True),
        ("-100123456789", False),
        ("not-a-chat", False),
        (None, False),
    ],
)
def test_max_chat_id_accepts_real_short_positive_ids(chat_id, expected):
    assert _is_max_chat_id(chat_id) is expected


class _NestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_gs_key_insert_race_does_not_roll_back_outer_transaction():
    session = SimpleNamespace(
        begin_nested=Mock(return_value=_NestedTransaction()),
        add=Mock(),
        flush=AsyncMock(
            side_effect=IntegrityError("INSERT", {}, RuntimeError("duplicate"))
        ),
        rollback=AsyncMock(),
    )

    inserted = await _insert_gs_key_with_savepoint(
        session=session,
        gs_key=SimpleNamespace(),
    )

    assert inserted is False
    session.rollback.assert_not_awaited()
