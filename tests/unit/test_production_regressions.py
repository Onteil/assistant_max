from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from api.utils import messenger_utils
from api.webhooks.ticket_status_webhooks import _select_notification_messenger
from bots.max_bot.handlers.user.main_menu_callbacks import _is_stale_callback_error
from bots.max_bot.utils import admin_notifications
from bots.max_bot.utils.callback_utils import answer_max_callback
from celery_app.escalation_tasks import _is_max_chat_id
from celery_app.nps_tasks import (
    NPS_PROCESSING_LOCK_TTL_SECONDS,
    _claim_nps_delivery,
    _release_nps_delivery,
    build_nps_delivery_key,
    build_nps_task_id,
)
from database.models import NPS_Response, SurveyType
from services.i_tat_service import (
    ITatAPIClient,
    NonRetryableAPIError,
    RetryableAPIError,
    _is_1c_version_conflict_response,
)
from services.nps_handler import handle_rating_response
from services.retry_service import _is_successful_api_response
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


@pytest.mark.asyncio
async def test_plain_max_callback_ack_does_not_edit_message():
    bot = SimpleNamespace(send_callback=AsyncMock(return_value=SimpleNamespace()))
    event = SimpleNamespace(
        bot=bot,
        callback=SimpleNamespace(callback_id="callback-1"),
        answer=AsyncMock(),
    )

    assert await answer_max_callback(event) is True
    bot.send_callback.assert_awaited_once_with(
        callback_id="callback-1",
        message=None,
        notification=None,
    )
    event.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_max_callback_stops_business_handler():
    bot = SimpleNamespace(
        send_callback=AsyncMock(
            side_effect=RuntimeError("error.edit.invalid.message")
        )
    )
    event = SimpleNamespace(
        bot=bot,
        callback=SimpleNamespace(callback_id="callback-2"),
        answer=AsyncMock(),
    )

    assert await answer_max_callback(event) is False


@pytest.mark.asyncio
async def test_unknown_max_callback_error_is_not_hidden():
    bot = SimpleNamespace(
        send_callback=AsyncMock(side_effect=RuntimeError("network timeout"))
    )
    event = SimpleNamespace(
        bot=bot,
        callback=SimpleNamespace(callback_id="callback-3"),
        answer=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="network timeout"):
        await answer_max_callback(event)


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


def test_nps_response_model_has_business_key_uniqueness():
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in NPS_Response.__table__.constraints
        if constraint.name
    }

    assert unique_constraints["uq_nps_response_user_survey_trigger"] == (
        "user_id",
        "survey_type",
        "trigger_event_id",
    )


@pytest.mark.asyncio
async def test_nps_duplicate_callback_is_idempotent():
    existing_result = Mock()
    existing_result.scalar_one_or_none.return_value = 42
    session = SimpleNamespace(
        execute=AsyncMock(return_value=existing_result),
        add=Mock(),
        begin_nested=Mock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    result = await handle_rating_response(
        session=session,
        user_id=10,
        rating=7,
        survey_type=SurveyType.SERVICE_QUALITY,
        trigger_event_id=245,
    )

    assert result == (True, "already_recorded")
    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_nps_insert_race_does_not_roll_back_outer_transaction():
    existing_result = Mock()
    existing_result.scalar_one_or_none.return_value = None
    session = SimpleNamespace(
        execute=AsyncMock(return_value=existing_result),
        add=Mock(),
        begin_nested=Mock(return_value=_NestedTransaction()),
        flush=AsyncMock(
            side_effect=IntegrityError("INSERT", {}, RuntimeError("duplicate"))
        ),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    result = await handle_rating_response(
        session=session,
        user_id=10,
        rating=7,
        survey_type=SurveyType.SERVICE_QUALITY,
        trigger_event_id=245,
    )

    assert result == (True, "already_recorded")
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"status": "ok"}, True),
        ({"status": "SUCCESS"}, True),
        ({"status": "error"}, False),
        ({"status": ""}, False),
        ({"message": "missing status"}, False),
        (True, False),
        (None, False),
    ],
)
def test_retry_api_response_requires_explicit_success_status(response, expected):
    assert _is_successful_api_response(response) is expected


@pytest.mark.asyncio
async def test_retry_error_response_is_recorded_as_failure(monkeypatch):
    from services import retry_service

    retry_record = SimpleNamespace(
        id=11,
        operation="update_user_assets",
        payload={},
        attempt_count=0,
    )
    api_client = SimpleNamespace(
        update_user_assets=AsyncMock(
            return_value={"status": "error", "message": "rejected"}
        )
    )
    mark_failed = AsyncMock(return_value=retry_record)
    mark_success = AsyncMock()
    monkeypatch.setattr(retry_service, "mark_retry_failed", mark_failed)
    monkeypatch.setattr(retry_service, "mark_retry_success", mark_success)

    succeeded = await retry_service.process_retry(
        session=SimpleNamespace(),
        retry_record=retry_record,
        api_client=api_client,
    )

    assert succeeded is False
    mark_failed.assert_awaited_once()
    mark_success.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_task_commits_each_processed_record(monkeypatch):
    import constants
    from celery_app import retry_tasks
    from services import i_tat_service, retry_service

    records = [
        SimpleNamespace(id=1, operation="update_user_assets"),
        SimpleNamespace(id=2, operation="update_staff"),
    ]
    session = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        refresh=AsyncMock(),
    )

    class _SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    client = SimpleNamespace(close=AsyncMock())
    get_next = AsyncMock(side_effect=[*records, None])
    process = AsyncMock(return_value=True)

    monkeypatch.setattr(constants, "AsyncSessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(i_tat_service, "ITatAPIClient", lambda: client)
    monkeypatch.setattr(retry_service, "get_next_pending_retry", get_next)
    monkeypatch.setattr(retry_service, "process_retry", process)

    stats = await retry_tasks._process_api_retry_queue_async()

    assert stats == {
        "processed": 2,
        "succeeded": 2,
        "failed": 0,
        "exhausted": 0,
    }
    assert session.commit.await_count == 2
    session.rollback.assert_not_awaited()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_max_key_conflict_notification_uses_messenger_data_fallback(
    monkeypatch,
):
    new_user = SimpleNamespace(
        id=10,
        full_name="Test User",
        phone_number="+70000000000",
        max_user_id=100,
    )
    admin = SimpleNamespace(id=20, max_chat_id=None, max_user_id=200)

    def scalar_result(value):
        result = Mock()
        result.scalar_one_or_none.return_value = value
        return result

    admins_result = Mock()
    admins_result.scalars.return_value.all.return_value = [admin]
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                scalar_result(new_user),
                scalar_result(None),
                admins_result,
                scalar_result(300),
            ]
        )
    )
    bot = SimpleNamespace(
        send_message=AsyncMock(),
        session=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(admin_notifications, "MaxBot", lambda token: bot)

    notified_count = await admin_notifications.notify_admins_key_conflict(
        session=session,
        new_user_id=new_user.id,
        key_number="00001_00001",
    )

    assert notified_count == 1
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == 300
    bot.session.close.assert_awaited_once()


def test_timezone_migration_does_not_swallow_update_errors(monkeypatch):
    import importlib.util
    from pathlib import Path

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "convert_utc_to_moscow_timezone.py"
    )
    spec = importlib.util.spec_from_file_location(
        "convert_utc_to_moscow_timezone_test",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    preparer = SimpleNamespace(
        quote_schema=lambda value: value,
        quote=lambda value: value,
    )
    connection = SimpleNamespace(
        dialect=SimpleNamespace(identifier_preparer=preparer),
        execute=Mock(side_effect=RuntimeError("database update failed")),
    )
    inspector = SimpleNamespace(
        get_table_names=Mock(return_value=["users"]),
        get_columns=Mock(return_value=[{"name": "created_at"}]),
    )
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration.sa, "inspect", lambda _: inspector)

    with pytest.raises(RuntimeError, match="database update failed"):
        migration._shift_existing_timestamps(hours=3)
