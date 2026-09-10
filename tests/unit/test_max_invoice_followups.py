import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from maxapi.context import MemoryContext

from bots.max_bot.states import InvoiceStates
from services.max_invoice_followup_service import InvoiceFollowups, encode_draft, restore_data


class DraftStore:
    def __init__(self):
        self.drafts = {}
        self.locks = {}

    @asynccontextmanager
    async def lock(self, key):
        async with self.locks.setdefault(key, asyncio.Lock()):
            yield

    async def save(self, key, draft):
        self.drafts[key] = json.loads(encode_draft(draft))

    async def get(self, key):
        return deepcopy(self.drafts.get(key))

    async def delete(self, key):
        self.drafts.pop(key, None)

    async def due(self, now):
        return [k for k, d in self.drafts.items() if d['due_at'] is not None and d['due_at'] <= now]


@pytest.fixture
def setup():
    now = [0]
    store = DraftStore()
    adapter = SimpleNamespace(send_message=AsyncMock())
    service = InvoiceFollowups(store, adapter, None, reminder_seconds=60,
                               handoff_seconds=120, clock=lambda: now[0])
    dispatcher = SimpleNamespace(contexts={}, handle=AsyncMock())
    event = SimpleNamespace(update_type='message_created', get_ids=lambda: (10, 20))

    async def begin(_):
        context = dispatcher.contexts[(10, 20)]
        await context.update_data(user_id=30, initial_request='Нужен счет на ФСНБ')
        await context.set_state(InvoiceStates.selecting_keys)

    dispatcher.handle.side_effect = begin
    return service, dispatcher, event, now


@pytest.mark.asyncio
async def test_reminder_then_handoff_once(setup):
    service, dispatcher, event, now = setup
    await service.handle(dispatcher, event)
    service.handoff = AsyncMock(return_value=True)
    now[0] = 59
    await service.process_due()
    service.adapter.send_message.assert_not_awaited()
    now[0] = 60
    await service.process_due()
    service.adapter.send_message.assert_awaited_once()
    service.handoff.assert_not_awaited()
    now[0] = 179
    await service.process_due()
    service.handoff.assert_not_awaited()
    now[0] = 180
    await asyncio.gather(service.process_due(), service.process_due())
    service.handoff.assert_awaited_once()
    assert not service.store.drafts


@pytest.mark.asyncio
async def test_reply_resets_timer_and_restores_after_restart(setup):
    service, dispatcher, event, now = setup
    await service.handle(dispatcher, event)
    now[0] = 60
    await service.process_due()
    dispatcher.contexts.clear()

    async def reply(_):
        context = dispatcher.contexts[(10, 20)]
        assert await context.get_state() == InvoiceStates.selecting_keys
        assert (await context.get_data())['initial_request'] == 'Нужен счет на ФСНБ'
        await context.update_data(selected_keys=[7])
    dispatcher.handle.side_effect = reply
    now[0] = 170
    await service.handle(dispatcher, event)
    service.handoff = AsyncMock(return_value=True)
    now[0] = 180
    await service.process_due()
    service.handoff.assert_not_awaited()
    draft = await service.store.get('10:20')
    assert draft['due_at'] == 230
    assert draft['data']['selected_keys'] == [7]
    assert not draft['reminded']


@pytest.mark.asyncio
@pytest.mark.parametrize('update_type', ['message_created', 'message_callback'])
async def test_cancel_or_completion_removes_pending_handoff(setup, update_type):
    service, dispatcher, event, now = setup
    await service.handle(dispatcher, event)
    now[0] = 60
    await service.process_due()
    event.update_type = update_type

    async def cancel(_):
        await dispatcher.contexts[(10, 20)].clear()
    dispatcher.handle.side_effect = cancel
    await service.handle(dispatcher, event)
    service.handoff = AsyncMock()
    now[0] = 1000
    await service.process_due()
    service.handoff.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_reminder_does_not_start_handoff_countdown(setup):
    service, dispatcher, event, now = setup
    await service.handle(dispatcher, event)
    service.adapter.send_message.side_effect = RuntimeError('network down')
    now[0] = 60
    await service.process_due()
    assert not (await service.store.get('10:20'))['reminded']


@pytest.mark.asyncio
async def test_failed_handoff_is_retried_without_another_reminder(setup):
    service, dispatcher, event, now = setup
    await service.handle(dispatcher, event)
    now[0] = 60
    await service.process_due()
    service.handoff = AsyncMock(side_effect=[False, True])
    now[0] = 180
    await service.process_due()
    assert (await service.store.get('10:20'))['due_at'] == 240
    now[0] = 240
    await service.process_due()
    assert not service.store.drafts
    service.adapter.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_worker_context_is_cleared_after_other_worker_handoff(setup):
    service, dispatcher, event, _ = setup
    await service.handle(dispatcher, event)
    await service.store.delete('10:20')

    async def check(_):
        assert await dispatcher.contexts[(10, 20)].get_state() is None
    dispatcher.handle.side_effect = check
    await service.handle(dispatcher, event)


@pytest.mark.asyncio
@pytest.mark.parametrize('existing', [False, True])
async def test_handoff_keeps_collected_data_and_does_not_duplicate(setup, monkeypatch, existing):
    from services import ticket_service
    from bots.max_bot.handlers.tickets import invoice
    from database.models import DeliveryMethod
    service, dispatcher, event, _ = setup
    await service.handle(dispatcher, event)
    draft = await service.store.get('10:20')
    draft['data'].update(selected_keys=[7], selected_inn='1234567890',
                         attachments=[{'type': 'image', 'url': 'https://example.test/file'}],
                         delivery_method='email', delivery_email='client@example.test')
    monkeypatch.setattr(ticket_service, 'get_user_active_ticket_by_type',
                        AsyncMock(return_value=SimpleNamespace(id=9) if existing else None))
    create = AsyncMock()

    async def created(context, *args):
        data = await context.get_data()
        assert data['selected_keys'] == [7]
        assert data['selected_inn'] == '1234567890'
        assert data['attachments'] == draft['data']['attachments']
        assert data['delivery_method'] == DeliveryMethod.EMAIL
        assert 'Нужен счет на ФСНБ' in data['description']
        assert 'не ответил на напоминание' in data['description']
        await context.clear()
    create.side_effect = created
    monkeypatch.setattr(invoice, 'create_invoice_ticket', create)
    @asynccontextmanager
    async def session_factory():
        yield SimpleNamespace()
    service.session_factory = session_factory
    assert await service.handoff(draft)
    assert create.await_count == (0 if existing else 1)


def test_delivery_enum_survives_persistence():
    from database.models import DeliveryMethod
    data = restore_data(json.loads(encode_draft({'data': {'delivery_method': DeliveryMethod.EMAIL}})))
    assert data['delivery_method'] is DeliveryMethod.EMAIL


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['AIAgentStates:waiting_for_key', 'ClientTicketCloseStates:selecting_ticket',
                                  'ClientTicketCloseStates:waiting_for_reason'])
async def test_conversation_state_survives_worker_change_without_invoice_timer(setup, state):
    service, dispatcher, event, now = setup
    async def start(_):
        context = dispatcher.contexts[(10, 20)]
        await context.update_data(user_id=30, closing_ticket_id=330)
        await context.set_state(state)
    dispatcher.handle.side_effect = start
    await service.handle(dispatcher, event)
    assert (await service.store.get('10:20'))['due_at'] is None
    dispatcher.contexts.clear()
    async def restored(_):
        context = dispatcher.contexts[(10, 20)]
        assert await context.get_state() == state
        assert (await context.get_data())['closing_ticket_id'] == 330
        await context.clear()
    dispatcher.handle.side_effect = restored
    now[0] = 10000
    await service.process_due()
    service.adapter.send_message.assert_not_awaited()
    await service.handle(dispatcher, event)
    assert not service.store.drafts


@pytest.mark.asyncio
@pytest.mark.parametrize('description', [None, 'Обновление ФСНБ'])
async def test_description_next_allows_optional_comment(description):
    from bots.max_bot.handlers.tickets.invoice import handle_invoice_description_next
    from bots.max_bot.keyboards.tickets.invoice_kb import get_description_input_keyboard
    keyboard = get_description_input_keyboard(bool(description))
    buttons = [button for row in keyboard.buttons for button in row]
    assert len([b for b in buttons if 'Далее' in b.text]) == 1
    assert all('Пропустить' not in b.text for b in buttons)
    context = MemoryContext(10, 20)
    await context.update_data(description=description)
    await context.set_state(InvoiceStates.entering_description)
    event = SimpleNamespace(message=SimpleNamespace(recipient=SimpleNamespace(chat_id=10),
                                                   body=SimpleNamespace(mid=None)))
    adapter = SimpleNamespace(send_message=AsyncMock())
    await handle_invoice_description_next(event, context, SimpleNamespace(), adapter)
    assert await context.get_state() == InvoiceStates.selecting_delivery
    assert (await context.get_data())['description'] == description


@pytest.mark.asyncio
async def test_start_clears_old_form(monkeypatch):
    from bots.max_bot.handlers.user import registration
    from services import user_service, ticket_service
    from database.models import RegistrationStatus
    context = MemoryContext(10, 20)
    await context.set_state(InvoiceStates.selecting_delivery)
    await context.update_data(description='old request')
    monkeypatch.setattr(registration, 'get_user_by_max_id', AsyncMock(return_value=SimpleNamespace(
        id=30, registration_status=RegistrationStatus.ACTIVE)))
    monkeypatch.setattr(user_service, 'upsert_max_messenger_data', AsyncMock())
    monkeypatch.setattr(ticket_service, 'get_user_active_tickets_count', AsyncMock(return_value=0))
    event = SimpleNamespace(message=SimpleNamespace(recipient=SimpleNamespace(chat_id=10),
        sender=SimpleNamespace(user_id=20), body=SimpleNamespace(text='/start')))
    adapter = SimpleNamespace(send_message=AsyncMock())
    await registration.cmd_start(event, context, SimpleNamespace(commit=AsyncMock()), adapter)
    assert await context.get_state() is None
    assert not await context.get_data()
    assert 'словами' in adapter.send_message.await_args.kwargs['text']


@pytest.mark.parametrize('text, expected', [
    ('Все неактуально, мне нужно продлить ИТС', True),
    ('не надо счет на почту', True),
    ('отмена', True),
    ('❌ Отмена', True),
    ('закрой все мои заявки', True),
    ('не могу закрыть программу', False),
    ('обновление не нужно, нужен счет на новую базу', False),
])
def test_cancellation_does_not_capture_problem_description(text, expected):
    from bots.max_bot.handlers.user.text_scenario_intents import is_cancel_text
    assert is_cancel_text(text) is expected


@pytest.mark.asyncio
async def test_stale_invoice_button_cannot_restart_form(setup, monkeypatch):
    from bots.max_bot.utils import callback_utils
    service, dispatcher, event, _ = setup
    event.update_type = 'message_callback'
    event.callback = SimpleNamespace(payload='delivery|confirm')
    monkeypatch.setattr(callback_utils, 'answer_max_callback', AsyncMock(return_value=True))
    await service.handle(dispatcher, event)
    dispatcher.handle.assert_not_awaited()
    assert not service.store.drafts
    assert 'завершено или отменено' in service.adapter.send_message.await_args.kwargs['text']


@pytest.mark.asyncio
async def test_cancel_with_key_is_not_processed_as_key_selection(monkeypatch):
    from bots.max_bot.handlers.tickets import invoice
    from bots.max_bot.handlers.user.text_scenario_intents import route_text_scenario_action
    cancel = AsyncMock()
    monkeypatch.setattr(invoice, 'cancel_invoice_flow', cancel)
    event = SimpleNamespace(message=SimpleNamespace(body=SimpleNamespace(
        text='Не надо счет на ключ 00001_00011')))
    assert await route_text_scenario_action(event, None, None, None, InvoiceStates.selecting_keys)
    cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_handoff_notifies_manager_even_if_client_unreachable(monkeypatch):
    from unittest.mock import Mock
    from bots.max_bot.handlers.tickets import invoice
    from services import calendar_service, ticket_service
    from bots.max_bot.utils import itat_logging
    from database.models import WorkMode
    context = MemoryContext(10, 20)
    await context.update_data(user_id=30, initial_request='Счет на ФСНБ', automatic_handoff=True)
    await context.set_state(InvoiceStates.selecting_keys)
    ticket = SimpleNamespace(id=99)
    create = AsyncMock(return_value=ticket)
    notify = AsyncMock(return_value=True)
    monkeypatch.setattr(invoice, 'get_user_by_id', AsyncMock(return_value=SimpleNamespace(id=30)))
    monkeypatch.setattr(invoice, 'create_ticket', create)
    monkeypatch.setattr(ticket_service, 'determine_assigned_manager', AsyncMock(return_value=(40, True)))
    monkeypatch.setattr(ticket_service, 'save_initial_ticket_attachments', AsyncMock())
    monkeypatch.setattr(ticket_service, 'get_user_active_tickets_count', AsyncMock(return_value=1))
    monkeypatch.setattr(ticket_service, 'route_ticket', AsyncMock(return_value={}))
    monkeypatch.setattr(ticket_service, 'send_staff_notification', notify)
    monkeypatch.setattr(calendar_service, 'get_current_work_mode', AsyncMock(return_value=WorkMode.REGULAR))
    monkeypatch.setattr(itat_logging, 'log_ticket_creation_to_itat', AsyncMock())
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(),
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=Mock(return_value=None))))
    adapter = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError('client unavailable')))
    await invoice.create_invoice_ticket(context, session, adapter, 10, 30)
    assert create.await_args.args[1]['description'] == 'Счет на ФСНБ'
    notify.assert_awaited_once()
    assert await context.get_state() is None
