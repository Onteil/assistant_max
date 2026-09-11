from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from maxapi.context import MemoryContext

from database.models import TicketStatus, TicketType, WorkMode
from services import ticket_service
from bots.max_bot.handlers.user import messages


@pytest.mark.asyncio
async def test_closure_reaches_max_after_commit_using_real_sender(monkeypatch):
    ticket = SimpleNamespace(id=334, user_id=42, ticket_status=TicketStatus.IN_PROGRESS,
        ticket_type=TicketType.KEY_CONFLICT,
        user=SimpleNamespace(id=42, max_user_id=99,
            max_messenger_data=SimpleNamespace(max_chat_id=100)))
    result = Mock()
    result.scalar_one_or_none.return_value = ticket
    session = SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock(),
                              rollback=AsyncMock())
    monkeypatch.setattr(ticket_service, '_get_staff_internal_id', AsyncMock(return_value=7))
    monkeypatch.setattr(ticket_service, '_log_action', AsyncMock())
    record = AsyncMock(return_value=SimpleNamespace(id=9))
    monkeypatch.setattr(ticket_service, 'add_ticket_message', record)
    monkeypatch.setattr('services.employee_service.get_employee_signature', AsyncMock(return_value='Иван <специалист>'))
    monkeypatch.setattr('bots.max_bot.utils.itat_logging.log_ticket_status_change_to_itat', AsyncMock())
    async def send(**kwargs):
        assert session.commit.await_count == 1
        assert ticket.ticket_status == TicketStatus.CLOSED
        assert kwargs['chat_id'] == 100
        assert 'Заявка #334 закрыта' in kwargs['text']
        assert '&lt;готово&gt;' in kwargs['text']
    adapter = SimpleNamespace(send_message=AsyncMock(side_effect=send))
    await ticket_service.close_ticket_with_notification(session, 334, 77, '<готово>', adapter)
    adapter.send_message.assert_awaited_once()
    record.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [TicketStatus.CLOSED, TicketStatus.CANCELLED])
async def test_regular_messages_to_terminal_ticket_stay_blocked(status):
    result = Mock()
    result.scalar_one_or_none.return_value = SimpleNamespace(ticket_status=status)
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    adapter = SimpleNamespace(send_message=AsyncMock())
    with pytest.raises(ValueError, match='closed ticket'):
        await ticket_service.send_message_to_client_max(adapter, session, 334, 7, 'ответ')
    adapter.send_message.assert_not_awaited()


def test_client_attachment_keeps_caption():
    event = SimpleNamespace(message=SimpleNamespace(body=SimpleNamespace(
        text='Ошибка <123>: вот скриншот', attachments=[SimpleNamespace(
            type='image', payload=SimpleNamespace(url='https://example.test/photo'))])))
    meta = messages.extract_attachment_metadata(event)
    assert meta['message_text'] == 'Ошибка <123>: вот скриншот'
    assert meta['file_url'] == 'https://example.test/photo'


@pytest.mark.asyncio
@pytest.mark.parametrize('closed', [False, True])
async def test_failed_delivery_never_claims_sent_or_redirects_closed_reply(monkeypatch, closed):
    context = MemoryContext(10, 20)
    await context.update_data(active_ticket_id=334)
    ticket = SimpleNamespace(id=334, assigned_staff_id=7,
        ticket_status=TicketStatus.CLOSED if closed else TicketStatus.IN_PROGRESS,
        ticket_type=TicketType.TECHNICAL_SUPPORT)
    monkeypatch.setattr(messages, 'get_ticket_by_id', AsyncMock(return_value=ticket))
    monkeypatch.setattr(messages, 'get_current_work_mode', AsyncMock(return_value=WorkMode.REGULAR))
    forward = AsyncMock(return_value=False)
    monkeypatch.setattr(messages, 'handle_client_message_to_ticket_max', forward)
    event = SimpleNamespace(message=SimpleNamespace(recipient=SimpleNamespace(chat_id=10),
        sender=SimpleNamespace(user_id=20), body=SimpleNamespace(text='ответ', attachments=[])))
    adapter = SimpleNamespace(send_message=AsyncMock())
    assert await messages.route_client_message_to_ticket(event, context, SimpleNamespace(), adapter)
    reply = adapter.send_message.await_args.kwargs['text']
    if closed:
        forward.assert_not_awaited()
        assert 'не отправлено' in reply
    else:
        assert 'сохранено' in reply and 'не удалось' in reply
    assert 'отправлено менеджеру' not in reply
