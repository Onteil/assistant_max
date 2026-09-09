from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from api.schemas.ticket_status_schemas import TicketStatusWebhookPayload
from api.utils import messenger_utils
from api.webhooks import ticket_status_webhooks
from api.webhooks.ticket_status_webhooks import _select_notification_messenger
from bots.max_bot.handlers.user.main_menu_callbacks import (
    _is_stale_callback_error,
    handle_main_menu_callback,
)
from bots.max_bot.keyboards.user import main_menu_kb
from bots.max_bot.keyboards.user.active_tickets_kb import (
    get_active_tickets_keyboard,
)
from bots.max_bot.payloads import MainMenuActionPayload
from bots.max_bot.texts import MAIN_MENU_WELCOME_TEXT
from bots.max_bot.utils import admin_notifications
from bots.max_bot.utils.callback_utils import (
    DEFAULT_CALLBACK_NOTIFICATION,
    answer_max_callback,
)
from celery_app.escalation_tasks import _is_max_chat_id
from celery_app.nps_tasks import (
    NPS_PROCESSING_LOCK_TTL_SECONDS,
    _claim_nps_delivery,
    _release_nps_delivery,
    build_nps_delivery_key,
    build_nps_task_id,
)
from database.models import (
    GS_Key,
    KeyConflictStatus,
    MessageType,
    NPS_Response,
    SurveyType,
    TicketStatus,
    TicketType,
    WorkMode,
)
from services import (
    itat_retry_helper,
    key_conflict_service,
    ticket_service,
    user_service,
)
from services.i_tat_service import (
    ITatAPIClient,
    NonRetryableAPIError,
    RetryableAPIError,
    _is_1c_version_conflict_response,
)
from services.nps_handler import handle_rating_response
from services.retry_service import _is_successful_api_response
from services.user_service import _insert_gs_key_with_savepoint


def _scalar_result(value):
    result = Mock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_close_ticket_skips_terminal_ticket_before_side_effects(monkeypatch):
    ticket = SimpleNamespace(
        id=315,
        ticket_status=TicketStatus.CLOSED,
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_scalar_result(ticket)),
        commit=AsyncMock(),
    )
    get_staff = AsyncMock()
    send_client = AsyncMock()
    monkeypatch.setattr(ticket_service, "_get_staff_internal_id", get_staff)
    monkeypatch.setattr(ticket_service, "send_message_to_client_max", send_client)

    with pytest.raises(ticket_service.TicketAlreadyClosedError) as error:
        await ticket_service.close_ticket_with_notification(
            session=session,
            ticket_id=ticket.id,
            employee_id=187660968,
            final_comment="Повторное закрытие",
            messenger_adapter=SimpleNamespace(),
        )

    assert error.value.ticket_id == ticket.id
    assert error.value.status is TicketStatus.CLOSED
    get_staff.assert_not_awaited()
    send_client.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_old_close_callback_does_not_restart_closing_flow(monkeypatch):
    from bots.max_bot.handlers.staff import manager
    from bots.max_bot.payloads import ManagerTicketActionPayload

    monkeypatch.setattr(manager, "answer_max_callback", AsyncMock(return_value=True))
    monkeypatch.setattr(
        manager,
        "is_staff_member",
        AsyncMock(return_value=SimpleNamespace(id=7)),
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_scalar_result(TicketStatus.CLOSED)),
    )
    context = SimpleNamespace(
        clear=AsyncMock(),
        set_state=AsyncMock(),
        update_data=AsyncMock(),
    )
    adapter = SimpleNamespace(
        delete_message=AsyncMock(),
        send_message=AsyncMock(),
    )
    event = SimpleNamespace(
        callback=SimpleNamespace(
            user=SimpleNamespace(user_id=187660968),
            callback_id="close-again",
        ),
        message=SimpleNamespace(
            recipient=SimpleNamespace(chat_id=9263059),
            body=SimpleNamespace(mid="old-message"),
        ),
    )

    await manager.handle_ticket_action(
        event=event,
        payload=ManagerTicketActionPayload(action="close", ticket_id=315),
        context=context,
        session=session,
        messenger_adapter=adapter,
    )

    context.clear.assert_awaited_once()
    context.set_state.assert_not_awaited()
    context.update_data.assert_not_awaited()
    assert "Повторное закрытие не выполнялось" in (
        adapter.send_message.await_args.kwargs["text"]
    )


@pytest.mark.asyncio
async def test_user_organization_query_refreshes_loaded_collection():
    organization = SimpleNamespace(inn="1111111111")
    user = SimpleNamespace(organizations=[organization])
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_scalar_result(user)),
    )

    organizations = await user_service.get_user_organizations(session, user_id=40)
    statement = session.execute.await_args.args[0]

    assert organizations == [organization]
    assert statement.get_execution_options()["populate_existing"] is True


def test_pending_conflict_key_is_marked_in_all_ticket_keyboards():
    from bots.max_bot.keyboards.tickets.consultation_kb import (
        get_consultation_key_selection_keyboard,
    )
    from bots.max_bot.keyboards.tickets.invoice_kb import (
        get_key_selection_keyboard,
    )
    from bots.max_bot.keyboards.tickets.support_kb import (
        get_key_context_keyboard,
    )

    key = GS_Key(
        id=51,
        key_number="07485_00255",
        user_id=40,
        conflict_status=KeyConflictStatus.PENDING_REVIEW,
    )
    keyboards = [
        get_key_selection_keyboard([key], set()),
        get_key_context_keyboard([key], set()),
        get_consultation_key_selection_keyboard([key], set()),
    ]

    for keyboard in keyboards:
        assert "⚠️" in keyboard.buttons[0][0].text


@pytest.mark.asyncio
async def test_escalation_task_operation_uses_scoped_db_and_disposes(monkeypatch):
    from celery_app import escalation_tasks

    task_session = object()
    task_engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(
        escalation_tasks,
        "_create_task_db",
        lambda: (task_engine, task_session),
    )

    async def operation(received_session):
        assert received_session is task_session
        return {"status": "success"}

    result = await escalation_tasks._run_task_operation(operation)

    assert result == {"status": "success"}
    task_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_escalation_timeout_reuses_task_session(monkeypatch):
    from celery_app import escalation_tasks
    from services import settings_service

    task_session = object()
    get_setting = AsyncMock(return_value="7")
    monkeypatch.setattr(settings_service, "get_setting", get_setting)

    timeout = await escalation_tasks.get_escalation_timeout(
        session=task_session,
    )

    assert timeout == 420
    get_setting.assert_awaited_once_with(
        task_session,
        "manager_response_timeout",
    )


@pytest.mark.asyncio
async def test_inn_timeout_diagnostics_are_hidden_when_flag_is_disabled(monkeypatch):
    from bots.max_bot.handlers.user import profile
    from services import i_tat_service

    user = SimpleNamespace(id=27, max_user_id=187660968)
    event = SimpleNamespace(
        message=SimpleNamespace(
            recipient=SimpleNamespace(chat_id=9263059),
            sender=SimpleNamespace(user_id=user.max_user_id),
            body=SimpleNamespace(text="9900000000"),
        )
    )
    context = SimpleNamespace(clear=AsyncMock())
    session = SimpleNamespace(commit=AsyncMock())
    adapter = SimpleNamespace(send_message=AsyncMock())

    monkeypatch.setattr(profile, "ENABLE_API_RETRY_DIAGNOSTICS", False)
    monkeypatch.setattr(profile, "validate_inn", lambda value: (True, ""))
    monkeypatch.setattr(profile, "get_user_by_max_id", AsyncMock(return_value=user))
    monkeypatch.setattr(profile, "get_user_organizations", AsyncMock(return_value=[]))
    monkeypatch.setattr(profile, "add_user_organization", AsyncMock())
    monkeypatch.setattr(profile, "call_itat_with_retry", AsyncMock(return_value={}))
    monkeypatch.setattr(profile, "show_organizations_list", AsyncMock())
    monkeypatch.setattr(
        i_tat_service,
        "get_itat_client",
        lambda: SimpleNamespace(
            check_inn=AsyncMock(side_effect=TimeoutError("i-TAT timeout"))
        ),
    )

    await profile.process_add_inn(
        event=event,
        context=context,
        session=session,
        messenger_adapter=adapter,
    )

    sent_texts = [call.kwargs["text"] for call in adapter.send_message.await_args_list]
    assert len(sent_texts) == 1
    assert all("i-TAT API" not in text for text in sent_texts)
    session.commit.assert_awaited_once()
    context.clear.assert_awaited_once()


def test_deferred_message_metadata_preserves_supported_attachment_types():
    from celery_app.ticket_notification_tasks import _stored_client_message_metadata

    cases = [
        (MessageType.PHOTO, "photo.jpg", "image"),
        (MessageType.DOCUMENT, "contract.pdf", "file"),
        (MessageType.VOICE, "voice.ogg", "voice"),
        (MessageType.VOICE, "audio.mp3", "audio"),
        (MessageType.VIDEO, "video.mp4", "video"),
    ]

    for message_type, file_name, expected_type in cases:
        attachment = SimpleNamespace(
            max_file_url="https://max.example/file",
            telegram_file_id="https://fallback.example/file",
            file_name=file_name,
            file_size=123,
        )
        message = SimpleNamespace(
            message_text="Тест",
            message_type=message_type,
            file_attachments=[attachment],
        )

        metadata = _stored_client_message_metadata(message)

        assert metadata["attachment_type"] == expected_type
        assert metadata["file_url"] == "https://max.example/file"
        assert metadata["file_name"] == file_name


@pytest.mark.asyncio
async def test_existing_client_message_is_marked_only_after_successful_delivery():
    staff = SimpleNamespace(id=7, max_user_id=700)
    max_data = SimpleNamespace(max_chat_id=900)
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[_scalar_result(staff), _scalar_result(max_data)]
        ),
        add=Mock(),
        flush=AsyncMock(),
    )
    adapter = SimpleNamespace(send_message=AsyncMock())
    ticket = SimpleNamespace(
        id=310,
        assigned_staff_id=7,
        ticket_status=TicketStatus.IN_PROGRESS,
    )
    user = SimpleNamespace(
        id=27,
        full_name="Тестовый клиент",
        first_name="Тест",
        phone_number=None,
        email=None,
    )
    message = SimpleNamespace(
        id=501,
        staff_notified_at=None,
        staff_notification_claimed_at=datetime(2026, 8, 1, 9, 0),
    )

    delivered = await ticket_service.forward_client_message_to_manager(
        session=session,
        messenger_adapter=adapter,
        ticket=ticket,
        user=user,
        message_text="Тест отложенной доставки",
        message_type_val=MessageType.TEXT.value,
        existing_message=message,
    )

    assert delivered is True
    assert message.staff_notified_at is not None
    assert message.staff_notification_claimed_at is None
    adapter.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_only_message_remains_pending_for_working_hours():
    session = SimpleNamespace(flush=AsyncMock())
    adapter = SimpleNamespace(send_message=AsyncMock())
    ticket = SimpleNamespace(
        id=311,
        assigned_staff_id=7,
        ticket_status=TicketStatus.IN_PROGRESS,
    )
    user = SimpleNamespace(id=27)
    message = SimpleNamespace(
        id=502,
        staff_notified_at=None,
        staff_notification_claimed_at=None,
    )

    delivered = await ticket_service.forward_client_message_to_manager(
        session=session,
        messenger_adapter=adapter,
        ticket=ticket,
        user=user,
        message_text="Тест сообщения в нерабочее время",
        message_type_val=MessageType.TEXT.value,
        save_only=True,
        existing_message=message,
    )

    assert delivered is False
    assert message.staff_notified_at is None
    adapter.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_deferred_processor_claims_and_delivers_existing_message(monkeypatch):
    from celery_app import ticket_notification_tasks

    candidate_result = Mock()
    candidate_result.scalars.return_value = [503]
    claim_result = _scalar_result(503)
    message = SimpleNamespace(
        id=503,
        message_text="Тест утренней пересылки",
        message_type=MessageType.VOICE,
        file_attachments=[
            SimpleNamespace(
                max_file_url="https://max.example/voice",
                telegram_file_id=None,
                file_name="voice.ogg",
                file_size=456,
            )
        ],
        ticket=SimpleNamespace(
            id=312,
            user=SimpleNamespace(id=27),
        ),
    )
    loaded_result = Mock()
    loaded_result.scalar_one.return_value = message
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[candidate_result, claim_result, loaded_result]
        ),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(ticket_service, "forward_client_message_to_manager", deliver)

    stats = await ticket_notification_tasks._process_deferred_client_messages(
        session=session,
        max_bot=SimpleNamespace(),
        work_mode=WorkMode.REGULAR,
    )

    assert stats == {"sent": 1, "failed": 0}
    assert session.commit.await_count == 2
    deliver.assert_awaited_once()
    call = deliver.await_args.kwargs
    assert call["existing_message"] is message
    assert call["attachment_type"] == "voice"
    assert call["file_url"] == "https://max.example/voice"


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
    async def reject_empty_callback(*, callback_id, message, notification):
        assert callback_id == "callback-1"
        assert message is not None or notification
        return SimpleNamespace()

    bot = SimpleNamespace(send_callback=AsyncMock(side_effect=reject_empty_callback))
    event = SimpleNamespace(
        bot=bot,
        callback=SimpleNamespace(callback_id="callback-1"),
        answer=AsyncMock(),
    )

    assert await answer_max_callback(event) is True
    bot.send_callback.assert_awaited_once_with(
        callback_id="callback-1",
        message=None,
        notification=DEFAULT_CALLBACK_NOTIFICATION,
    )
    event.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_plain_max_callback_ack_preserves_explicit_notification():
    bot = SimpleNamespace(send_callback=AsyncMock(return_value=SimpleNamespace()))
    event = SimpleNamespace(
        bot=bot,
        callback=SimpleNamespace(callback_id="callback-1"),
        answer=AsyncMock(),
    )

    assert await answer_max_callback(event, notification="Выполнено") is True

    bot.send_callback.assert_awaited_once_with(
        callback_id="callback-1",
        message=None,
        notification="Выполнено",
    )
    event.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_tickets_menu_button_routes_to_client_main_menu():
    keyboard = await get_active_tickets_keyboard([])

    menu_button = keyboard.buttons[-1][0]
    payload = MainMenuActionPayload.unpack(menu_button.payload)

    assert payload.action == "main_menu"


@pytest.mark.asyncio
async def test_main_menu_action_restores_client_actions_menu(monkeypatch):
    user = SimpleNamespace(id=42)
    expected_keyboard = SimpleNamespace()
    get_user = AsyncMock(return_value=user)
    get_count = AsyncMock(return_value=3)
    get_keyboard = AsyncMock(return_value=expected_keyboard)
    monkeypatch.setattr(user_service, "get_user_by_max_id", get_user)
    monkeypatch.setattr(
        ticket_service,
        "get_user_active_tickets_count",
        get_count,
    )
    monkeypatch.setattr(
        main_menu_kb,
        "get_main_menu_inline_keyboard",
        get_keyboard,
    )

    event = SimpleNamespace(
        bot=SimpleNamespace(send_callback=AsyncMock(return_value=SimpleNamespace())),
        callback=SimpleNamespace(
            callback_id="callback-menu",
            user=SimpleNamespace(user_id=123456),
        ),
        message=SimpleNamespace(
            recipient=SimpleNamespace(chat_id=789012),
            body=SimpleNamespace(mid=None),
        ),
    )
    context = SimpleNamespace(clear=AsyncMock())
    session = SimpleNamespace()
    messenger_adapter = SimpleNamespace(send_message=AsyncMock())

    await handle_main_menu_callback(
        event=event,
        payload=MainMenuActionPayload(action="main_menu"),
        context=context,
        session=session,
        messenger_adapter=messenger_adapter,
    )

    get_user.assert_awaited_once_with(session, 123456)
    context.clear.assert_awaited_once_with()
    get_count.assert_awaited_once_with(session, 42)
    get_keyboard.assert_awaited_once_with(3)
    messenger_adapter.send_message.assert_awaited_once_with(
        chat_id=789012,
        text=MAIN_MENU_WELCOME_TEXT,
        keyboard=expected_keyboard,
        parse_mode="HTML",
    )


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
async def test_obsolete_ticket_retry_does_not_regress_terminal_ticket():
    from database.models import RetryStatus
    from services import retry_service

    ticket = SimpleNamespace(ticket_status=TicketStatus.CLOSED)
    ticket_result = Mock()
    ticket_result.scalar_one_or_none.return_value = ticket
    session = SimpleNamespace(
        execute=AsyncMock(return_value=ticket_result),
        flush=AsyncMock(),
    )
    retry_record = SimpleNamespace(
        id=43,
        operation="log_ticket",
        payload={"ticket_id": "TKT_294", "status": "В работе"},
        attempt_count=0,
        status=RetryStatus.PENDING,
        completed_at=None,
        last_error="timeout",
    )
    api_client = SimpleNamespace(log_ticket=AsyncMock())

    succeeded = await retry_service.process_retry(
        session=session,
        retry_record=retry_record,
        api_client=api_client,
    )

    assert succeeded is True
    assert retry_record.status is RetryStatus.SUCCESS
    assert retry_record.attempt_count == 1
    assert retry_record.completed_at is not None
    assert "obsolete" in retry_record.last_error
    api_client.log_ticket.assert_not_awaited()
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_task_commits_each_processed_record(monkeypatch):
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
    task_engine = SimpleNamespace(dispose=AsyncMock())
    get_next = AsyncMock(side_effect=[*records, None])
    process = AsyncMock(return_value=True)

    monkeypatch.setattr(
        retry_tasks,
        "_create_task_db",
        lambda: (task_engine, lambda: _SessionContext()),
    )
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
    task_engine.dispose.assert_awaited_once()


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


@pytest.mark.asyncio
async def test_shared_key_conflict_flow_notifies_admins_without_ticket(monkeypatch):
    user = SimpleNamespace(id=10, max_user_id=100)
    key = SimpleNamespace(id=20)
    session = SimpleNamespace(commit=AsyncMock())
    add_key = AsyncMock(return_value=key)
    notify_admins = AsyncMock(return_value=2)

    monkeypatch.setattr(
        key_conflict_service,
        "check_key_conflict",
        AsyncMock(
            return_value=key_conflict_service.KeyConflictCheck(
                has_conflict=True,
                owner="Existing owner",
            )
        ),
    )
    monkeypatch.setattr(key_conflict_service, "add_user_key", add_key)
    monkeypatch.setattr(
        admin_notifications,
        "notify_admins_key_conflict",
        notify_admins,
    )

    result = await key_conflict_service.add_key_with_conflict_handling(
        session=session,
        user=user,
        key_number="00001_00001",
    )

    assert result.has_conflict is True
    add_key.assert_awaited_once_with(
        session,
        user.id,
        "00001_00001",
        KeyConflictStatus.PENDING_REVIEW,
    )
    session.commit.assert_awaited_once()
    notify_admins.assert_awaited_once_with(session, user.id, "00001_00001")


@pytest.mark.asyncio
async def test_key_conflict_check_falls_back_locally_on_itat_timeout(monkeypatch):
    api = SimpleNamespace(
        check_key_conflict=AsyncMock(side_effect=TimeoutError("i-TAT timeout"))
    )
    monkeypatch.setattr(key_conflict_service, "get_itat_client", lambda: api)
    query_result = Mock()
    query_result.scalar_one_or_none.return_value = None
    session = SimpleNamespace(execute=AsyncMock(return_value=query_result))

    result = await key_conflict_service.check_key_conflict(
        session=session,
        user=SimpleNamespace(max_user_id=100),
        key_number="00001_00002",
    )

    assert result.has_conflict is False
    assert result.source == "local_fallback"
    api.check_key_conflict.assert_awaited_once_with(
        grand_key="00001_00002",
        user_id=100,
    )


@pytest.mark.asyncio
async def test_legacy_key_conflict_resolution_closes_only_selected_tickets():
    legacy_ticket = SimpleNamespace(
        ticket_status=TicketStatus.NEW,
        closed_at=None,
        resolution_comment=None,
    )
    query_result = Mock()
    query_result.scalars.return_value.all.return_value = [legacy_ticket]
    session = SimpleNamespace(
        execute=AsyncMock(return_value=query_result),
        flush=AsyncMock(),
    )

    closed = await key_conflict_service.close_legacy_key_conflict_tickets(
        session=session,
        key_id=25,
        resolution="Resolved by admin",
    )

    assert closed == 1
    assert legacy_ticket.ticket_status == TicketStatus.CLOSED
    assert legacy_ticket.resolution_comment == "Resolved by admin"
    assert legacy_ticket.closed_at is not None
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "subscription_status", ["expired", "none"],
)
async def test_support_without_active_subscription_starts_form(
    monkeypatch,
    subscription_status,
):
    from bots.max_bot.handlers.tickets import support as support_handler
    from database.models import SubscriptionStatus

    user = SimpleNamespace(
        id=27,
        subscription_status=SubscriptionStatus(subscription_status),
        subscription_end_date=datetime(2026, 7, 31),
    )
    monkeypatch.setattr(
        support_handler,
        "get_user_by_max_id",
        AsyncMock(return_value=user),
    )
    show_organizations = AsyncMock()
    monkeypatch.setattr(
        support_handler, "get_user_active_ticket_by_type", AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        support_handler,
        "show_support_organization_selection",
        show_organizations,
    )

    event = SimpleNamespace(
        message=SimpleNamespace(
            recipient=SimpleNamespace(chat_id=10027),
            sender=SimpleNamespace(user_id=9027),
        )
    )
    context = SimpleNamespace(
        clear=AsyncMock(),
        update_data=AsyncMock(),
        set_state=AsyncMock(),
    )
    adapter = SimpleNamespace(send_message=AsyncMock())

    await support_handler.cmd_support(
        event=event,
        context=context,
        session=SimpleNamespace(),
        messenger_adapter=adapter,
    )

    from bots.max_bot.states import SupportStates
    context.update_data.assert_awaited_once()
    context.set_state.assert_awaited_once_with(SupportStates.selecting_organization)
    show_organizations.assert_awaited_once()
    adapter.send_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("processor_name", "duty_selector_name", "round_robin_name", "ticket_type"),
    [
        (
            "_process_support_ticket",
            "_get_duty_engineer",
            "get_next_support_staff",
            TicketType.TECHNICAL_SUPPORT,
        ),
        (
            "_process_consultation_ticket",
            "_get_duty_estimate_specialist",
            "get_next_consultation_specialist",
            TicketType.CONSULTATION,
        ),
    ],
)
async def test_extended_queue_uses_duty_staff_without_round_robin(
    monkeypatch,
    processor_name,
    duty_selector_name,
    round_robin_name,
    ticket_type,
):
    from celery_app import escalation_tasks, ticket_notification_tasks
    from services import round_robin_service

    user = SimpleNamespace(full_name="Test User", phone_number="+70000000000")
    ticket = SimpleNamespace(
        id=291,
        ticket_type=ticket_type,
        user=user,
        created_at=datetime.now(),
        description=None,
        organization_inn=None,
        organization=None,
        gs_keys=[],
        file_attachments=[SimpleNamespace(file_name="queued.txt")],
        assigned_staff_id=None,
    )
    duty = SimpleNamespace(id=15, max_chat_id=5015, max_user_id=1500)
    session = SimpleNamespace(commit=AsyncMock())
    bot = SimpleNamespace(send_message=AsyncMock())
    duty_selector = AsyncMock(return_value=duty)
    round_robin = AsyncMock()
    forward_attachments = AsyncMock()

    monkeypatch.setattr(ticket_service, duty_selector_name, duty_selector)
    monkeypatch.setattr(round_robin_service, round_robin_name, round_robin)
    monkeypatch.setattr(
        escalation_tasks,
        "schedule_technical_support_monitoring",
        AsyncMock(),
    )
    monkeypatch.setattr(
        ticket_notification_tasks,
        "_forward_ticket_attachments",
        forward_attachments,
    )

    processor = getattr(ticket_notification_tasks, processor_name)
    stats = {"notifications_sent": 0}
    sent = await processor(
        ticket,
        bot,
        session,
        stats,
        work_mode=WorkMode.EXTENDED,
    )

    assert sent is True
    assert ticket.assigned_staff_id == duty.id
    assert stats["notifications_sent"] == 1
    duty_selector.assert_awaited_once_with(session)
    round_robin.assert_not_awaited()
    forward_attachments.assert_awaited_once_with(
        ticket,
        duty.max_chat_id,
        bot,
        session,
    )


@pytest.mark.asyncio
async def test_invoice_queue_refreshes_manager_before_notification(monkeypatch):
    from celery_app import escalation_tasks, ticket_notification_tasks

    user = SimpleNamespace(
        id=10,
        full_name="Test User",
        phone_number="+70000000000",
        max_user_id=100,
    )
    ticket = SimpleNamespace(
        id=292,
        user_id=user.id,
        user=user,
        assigned_staff_id=5,
        created_at=datetime.now(),
        file_attachments=[SimpleNamespace(file_name="queued.txt")],
    )
    session = SimpleNamespace(commit=AsyncMock())
    determine_manager = AsyncMock(return_value=(8, True))
    send_notification = AsyncMock(return_value=True)
    forward_attachments = AsyncMock()
    bot = SimpleNamespace()

    monkeypatch.setattr(
        ticket_service,
        "determine_assigned_manager",
        determine_manager,
    )
    monkeypatch.setattr(
        ticket_notification_tasks,
        "send_staff_notification",
        send_notification,
    )
    monkeypatch.setattr(
        escalation_tasks,
        "schedule_escalation_monitoring",
        AsyncMock(),
    )
    from bots.max_bot.utils import staff_chat_resolver

    get_staff_chat_id = AsyncMock(return_value=7008)
    monkeypatch.setattr(
        staff_chat_resolver,
        "get_staff_chat_id",
        get_staff_chat_id,
    )
    monkeypatch.setattr(
        ticket_notification_tasks,
        "_forward_ticket_attachments",
        forward_attachments,
    )

    sent = await ticket_notification_tasks._process_invoice_ticket(
        ticket=ticket,
        max_bot=bot,
        messenger_type="max",
        messenger_id=user.max_user_id,
        session=session,
        stats={"notifications_sent": 0},
    )

    assert sent is True
    assert ticket.assigned_staff_id == 8
    determine_manager.assert_awaited_once_with(
        session=session,
        user_id=user.id,
        assign_admin_if_no_manager=True,
    )
    assert send_notification.await_args.kwargs["staff_id"] == 8
    forward_attachments.assert_awaited_once_with(
        ticket,
        7008,
        bot,
        session,
    )


@pytest.mark.asyncio
async def test_renewal_queue_forwards_attachments_to_refreshed_manager(monkeypatch):
    from bots.max_bot.utils import staff_chat_resolver
    from celery_app import escalation_tasks, ticket_notification_tasks

    manager = SimpleNamespace(id=8, is_active=True, is_working_today=True)
    query_result = Mock()
    query_result.scalar_one_or_none.return_value = manager
    session = SimpleNamespace(
        execute=AsyncMock(return_value=query_result),
        commit=AsyncMock(),
    )
    ticket = SimpleNamespace(
        id=294,
        user_id=10,
        user=SimpleNamespace(
            full_name="Test User",
            phone_number="+70000000000",
        ),
        assigned_staff_id=manager.id,
        created_at=datetime.now(),
        file_attachments=[SimpleNamespace(file_name="queued.txt")],
    )
    bot = SimpleNamespace()
    send_notification = AsyncMock(return_value=True)
    forward_attachments = AsyncMock()
    get_staff_chat_id = AsyncMock(return_value=7008)

    monkeypatch.setattr(
        ticket_notification_tasks,
        "send_staff_notification",
        send_notification,
    )
    monkeypatch.setattr(
        ticket_notification_tasks,
        "_forward_ticket_attachments",
        forward_attachments,
    )
    monkeypatch.setattr(
        staff_chat_resolver,
        "get_staff_chat_id",
        get_staff_chat_id,
    )
    monkeypatch.setattr(
        escalation_tasks,
        "schedule_escalation_monitoring",
        AsyncMock(),
    )

    sent = await ticket_notification_tasks._process_renewal_ticket(
        ticket=ticket,
        max_bot=bot,
        messenger_type="max",
        messenger_id=100,
        session=session,
        stats={"notifications_sent": 0},
    )

    assert sent is True
    get_staff_chat_id.assert_awaited_once_with(session, manager.id)
    forward_attachments.assert_awaited_once_with(
        ticket,
        7008,
        bot,
        session,
    )


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


@pytest.mark.asyncio
async def test_max_closure_commits_before_client_message_and_itat(monkeypatch):
    events = []
    closed_at = datetime(2026, 7, 31, 14, 30, 0)
    final_comment = "Работы завершены"
    user = SimpleNamespace(id=42, max_messenger_data=SimpleNamespace(max_user_id=1001))
    ticket = SimpleNamespace(
        id=285,
        user=user,
        user_id=user.id,
        ticket_status=TicketStatus.IN_PROGRESS,
        ticket_type=TicketType.INVOICE,
        closed_at=None,
        updated_at=None,
        resolution_comment=None,
    )
    ticket_result = Mock()
    ticket_result.scalar_one_or_none.return_value = ticket
    survey_result = Mock()
    survey_result.scalar_one_or_none.return_value = None
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[ticket_result, survey_result]),
        rollback=AsyncMock(),
    )

    async def commit():
        events.append("commit")

    async def send_client_message(**_kwargs):
        assert ticket.ticket_status is TicketStatus.CLOSED
        assert ticket.resolution_comment == final_comment
        assert events == ["commit"]
        events.append("max")

    async def log_to_itat(**_kwargs):
        assert events == ["commit", "max", "commit"]
        events.append("itat")

    session.commit = AsyncMock(side_effect=commit)
    add_ticket_message = AsyncMock()
    monkeypatch.setattr(ticket_service, "_get_staff_internal_id", AsyncMock(return_value=7))
    monkeypatch.setattr(ticket_service, "get_moscow_now_naive", lambda: closed_at)
    monkeypatch.setattr(ticket_service, "_log_action", AsyncMock())
    monkeypatch.setattr(ticket_service, "schedule_survey", AsyncMock(return_value=(False, "test")))
    monkeypatch.setattr(ticket_service, "send_message_to_client_max", send_client_message)
    monkeypatch.setattr(ticket_service, "add_ticket_message", add_ticket_message)
    monkeypatch.setattr(
        "bots.max_bot.utils.itat_logging.log_ticket_status_change_to_itat",
        log_to_itat,
    )

    result = await ticket_service.close_ticket_with_notification(
        session=session,
        ticket_id=ticket.id,
        employee_id=1002,
        final_comment=final_comment,
        messenger_adapter=Mock(),
    )

    assert result is ticket
    assert events == ["commit", "max", "commit", "itat"]
    assert ticket.closed_at == closed_at
    assert ticket.updated_at == closed_at
    add_ticket_message.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_closed_webhook_persists_its_comment(monkeypatch):
    user = SimpleNamespace(id=42, tg_user_id=None)
    ticket = SimpleNamespace(
        id=285,
        user=user,
        user_id=user.id,
        ticket_status=TicketStatus.IN_PROGRESS,
        closed_at=None,
        closed_by_staff_id=None,
        resolution_comment=None,
    )
    ticket_result = Mock()
    ticket_result.scalar_one_or_none.return_value = ticket
    session = SimpleNamespace(
        execute=AsyncMock(return_value=ticket_result),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        add=Mock(),
    )
    monkeypatch.setattr(
        ticket_status_webhooks,
        "_find_staff_by_messenger_id",
        AsyncMock(return_value=SimpleNamespace(id=7)),
    )
    monkeypatch.setattr(
        ticket_status_webhooks,
        "_select_notification_messenger",
        lambda **_kwargs: ("max", None),
    )
    monkeypatch.setattr(
        "api.utils.messenger_utils.get_max_chat_id",
        AsyncMock(return_value=None),
    )

    payload = TicketStatusWebhookPayload(
        ticket_id="285",
        status="closed",
        closed_by_staff_id=1002,
        messenger="max",
        comment="Закрыто специалистом",
    )

    await ticket_status_webhooks.ticket_status_update_webhook(
        payload=payload,
        session=session,
        api_key="test",
    )

    assert ticket.ticket_status is TicketStatus.CLOSED
    assert ticket.resolution_comment == "Закрыто специалистом"


@pytest.mark.asyncio
async def test_terminal_ticket_webhook_regression_is_ignored():
    user = SimpleNamespace(id=42, tg_user_id=None)
    ticket = SimpleNamespace(
        id=294,
        user=user,
        user_id=user.id,
        ticket_status=TicketStatus.CLOSED,
        closed_at=datetime(2026, 7, 31, 14, 30, 0),
        closed_by_staff_id=7,
        resolution_comment="Тест завершен",
    )
    ticket_result = Mock()
    ticket_result.scalar_one_or_none.return_value = ticket
    session = SimpleNamespace(
        execute=AsyncMock(return_value=ticket_result),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        add=Mock(),
    )
    payload = TicketStatusWebhookPayload(
        ticket_id="294",
        status="in_progress",
        messenger="max",
    )

    response = await ticket_status_webhooks.ticket_status_update_webhook(
        payload=payload,
        session=session,
        api_key="test",
    )

    assert response.status == "success"
    assert "Ignored obsolete" in response.message
    assert ticket.ticket_status is TicketStatus.CLOSED
    action_log = session.add.call_args.args[0]
    assert action_log.action_details["action"] == "ticket_status_regression_ignored"
    assert action_log.action_details["new_status"] == TicketStatus.IN_PROGRESS.value
    session.commit.assert_awaited_once()


def test_max_ticket_creation_messages_include_ticket_number():
    from bots.max_bot.texts import (
        CONSULTATION_TICKET_CREATED,
        get_consultation_non_working_hours_message,
        get_invoice_non_working_hours_message,
        get_support_non_working_hours_message,
    )

    messages = [
        get_invoice_non_working_hours_message(294),
        get_support_non_working_hours_message(295),
        CONSULTATION_TICKET_CREATED.format(ticket_id=296),
        get_consultation_non_working_hours_message(297),
    ]

    for ticket_id, message in zip(range(294, 298), messages, strict=True):
        assert f"#{ticket_id}" in message


@pytest.mark.asyncio
@pytest.mark.parametrize("diagnostics_enabled", [False, True])
async def test_retry_queue_diagnostics_require_explicit_flag(
    monkeypatch,
    diagnostics_enabled,
):
    session = SimpleNamespace(flush=AsyncMock())
    retry_record = SimpleNamespace(id=30)
    api_client = SimpleNamespace(
        log_ticket=AsyncMock(side_effect=RetryableAPIError("Request timeout")),
    )
    queued_notification = AsyncMock()

    async def queue_retry(**_kwargs):
        return retry_record

    monkeypatch.setattr(
        itat_retry_helper,
        "ENABLE_API_RETRY_DIAGNOSTICS",
        diagnostics_enabled,
    )
    monkeypatch.setattr(itat_retry_helper, "get_itat_client", lambda: api_client)
    monkeypatch.setattr("services.retry_service.queue_api_retry", queue_retry)
    monkeypatch.setattr(
        "bots.max_bot.utils.admin_notifications.notify_admins_api_retry_queued",
        queued_notification,
    )

    result = await itat_retry_helper.call_itat_with_retry(
        session=session,
        operation="log_ticket",
        payload={"ticket_id": "TKT_285"},
        user_id=42,
    )

    assert result is None
    session.flush.assert_awaited_once()
    if diagnostics_enabled:
        queued_notification.assert_awaited_once()
    else:
        queued_notification.assert_not_awaited()
