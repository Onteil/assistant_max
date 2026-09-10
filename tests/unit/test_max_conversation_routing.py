from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from maxapi import Dispatcher, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCreated

from bots.max_bot.handlers.user import ai_agent, active_tickets, text_menu_intents
from bots.max_bot.middlewares.conversation import ConversationMiddleware
from bots.max_bot.states import AIAgentStates, ClientTicketCloseStates, InvoiceStates
from database.models import RegistrationStatus, TicketStatus


def event(text):
    return MessageCreated.model_construct(
        timestamp=0, update_type='message_created',
        message=SimpleNamespace(
            recipient=SimpleNamespace(chat_id=10), sender=SimpleNamespace(user_id=20),
            body=SimpleNamespace(text=text, attachments=None, mid=None),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['Проблема с профилем после обновления', '12345_12345',
                                  '7707083893', 'client@example.org', 'далее', 'отмена'])
async def test_ordinary_form_input_reaches_original_handler(bot, text):
    await bot.context.set_state(InvoiceStates.entering_description)
    await bot.context.update_data(selected_keys=[42])
    await bot.dp.handle(event(text))
    bot.forwarded.assert_awaited_once()
    assert await bot.context.get_state() == InvoiceStates.entering_description
    assert (await bot.context.get_data())['selected_keys'] == [42]


@pytest.mark.asyncio
async def test_registration_input_is_not_consumed_as_navigation(bot):
    from bots.max_bot.states import RegistrationStates
    await bot.context.set_state(RegistrationStates.waiting_for_name)
    await bot.dp.handle(event('открой профиль'))
    bot.forwarded.assert_awaited_once()
    assert await bot.context.get_state() == RegistrationStates.waiting_for_name


@pytest.mark.asyncio
async def test_ordinary_ticket_message_reaches_original_handler(bot):
    await bot.dp.handle(event('Спасибо, отправляю подробности ошибки'))
    bot.forwarded.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['active', 'expired', 'none'])
async def test_text_consultation_keeps_subscription_rules(bot, monkeypatch, status):
    from bots.max_bot.handlers.tickets import consultation
    from bots.max_bot.states import ConsultationStates
    from database.models import SubscriptionStatus
    bot.user.subscription_status = SubscriptionStatus(status)
    monkeypatch.setattr(consultation, 'get_user_by_max_id', AsyncMock(return_value=bot.user))
    monkeypatch.setattr(consultation, 'get_user_active_ticket_by_type', AsyncMock(return_value=None))
    organizations, renewal = AsyncMock(), AsyncMock()
    monkeypatch.setattr(consultation, '_show_organization_selection', organizations)
    monkeypatch.setattr(consultation, '_create_renewal_ticket_for_consultation', renewal)
    await bot.dp.handle(event('сметная консультация'))
    if status == 'active':
        organizations.assert_awaited_once()
        renewal.assert_not_awaited()
        assert await bot.context.get_state() == ConsultationStates.selecting_organization
    else:
        organizations.assert_not_awaited()
        renewal.assert_awaited_once()
        assert await bot.context.get_state() is None
    bot.forwarded.assert_not_awaited()


@pytest.fixture
def bot(monkeypatch):
    user = SimpleNamespace(id=30, first_name='Гузель', full_name='Гузель',
                           registration_status=RegistrationStatus.ACTIVE)
    for module in (text_menu_intents, ai_agent, active_tickets):
        monkeypatch.setattr(module, 'get_user_by_max_id', AsyncMock(return_value=user))
    classifier = AsyncMock(side_effect=AssertionError('explicit command reached LLM'))
    monkeypatch.setattr(text_menu_intents, 'classify_menu_navigation', classifier)
    monkeypatch.setattr(text_menu_intents, 'is_yandex_gpt_configured', lambda: False)
    session = SimpleNamespace()
    adapter = SimpleNamespace(send_message=AsyncMock())
    class Dependencies:
        async def __call__(self, handler, evt, data):
            data.update(session=session, messenger_adapter=adapter)
            return await handler(evt, data)
    dp = Dispatcher()
    dp.middlewares = [Dependencies(), ConversationMiddleware()]
    router = Router(router_id='regression')
    router.message_created(AIAgentStates.waiting_for_request)(ai_agent.handle_ai_agent_message)
    router.message_created(AIAgentStates.waiting_for_key)(ai_agent.handle_ai_agent_key)
    router.message_created(ClientTicketCloseStates.waiting_for_reason)(active_tickets.process_client_ticket_close_reason)
    forwarded = AsyncMock()
    async def fallback(event):
        await forwarded(event)
    router.message_created()(fallback)
    dp.include_routers(router)
    context = MemoryContext(10, 20)
    dp.contexts[(10, 20)] = context
    return SimpleNamespace(dp=dp, context=context, adapter=adapter, forwarded=forwarded,
                           classifier=classifier, user=user)


@pytest.mark.asyncio
@pytest.mark.parametrize('state', [None, AIAgentStates.waiting_for_request,
                                  AIAgentStates.waiting_for_key, InvoiceStates.entering_description])
async def test_open_profile_precedes_ai_and_form_handlers(bot, monkeypatch, state):
    from bots.max_bot.handlers.user import profile
    open_profile = AsyncMock()
    monkeypatch.setattr(profile, 'cmd_profile', open_profile)
    await bot.context.set_state(state)
    await bot.dp.handle(event('Открой Мой профиль'))
    open_profile.assert_awaited_once()
    assert await bot.context.get_state() is None
    bot.forwarded.assert_not_awaited()
    bot.classifier.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscription_question_key_then_profile(bot, monkeypatch):
    from bots.max_bot.handlers.user import profile, renewal
    renewal_status = AsyncMock()
    open_profile = AsyncMock()
    monkeypatch.setattr(renewal, 'show_subscription_status', renewal_status)
    monkeypatch.setattr(profile, 'cmd_profile', open_profile)
    await bot.dp.handle(event('как узнать подписки на моем ключе'))
    assert await bot.context.get_state() == AIAgentStates.waiting_for_key
    assert 'номер ключа' in bot.adapter.send_message.await_args.kwargs['text']
    await bot.dp.handle(event('мой ключ 12345_12345'))
    assert (await bot.context.get_data())['last_subscription_key'] == '12345_12345'
    reply = bot.adapter.send_message.await_args.kwargs['text']
    assert 'не могу проверить' in reply
    assert 'нет активной подписки' not in reply
    await bot.dp.handle(event('открой профиль'))
    open_profile.assert_awaited_once()
    renewal_status.assert_not_awaited()
    bot.forwarded.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_one_ticket_then_skip_reason(bot, monkeypatch):
    ticket = SimpleNamespace(id=330, user_id=30, ticket_status=TicketStatus.NEW)
    monkeypatch.setattr(active_tickets, 'get_user_active_tickets', AsyncMock(return_value=[ticket]))
    monkeypatch.setattr(active_tickets, 'get_ticket_by_id', AsyncMock(return_value=ticket))
    async def closed(**kwargs):
        await kwargs['context'].clear()
    close = AsyncMock(side_effect=closed)
    monkeypatch.setattr(active_tickets, '_close_client_ticket_with_reason', close)
    await bot.dp.handle(event('закрой обращение'))
    assert await bot.context.get_state() == ClientTicketCloseStates.waiting_for_reason
    assert (await bot.context.get_data())['closing_ticket_id'] == 330
    # Repeating the command must not be saved as a reason or cancel the close.
    await bot.dp.handle(event('закрыть заявку'))
    assert await bot.context.get_state() == ClientTicketCloseStates.waiting_for_reason
    await bot.dp.handle(event('пропустить'))
    close.assert_awaited_once()
    assert close.await_args.kwargs['ticket_id'] == 330
    assert close.await_args.kwargs['reason'] == 'Причина не указана'
    bot.forwarded.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_multiple_requires_owned_ticket_number(bot, monkeypatch):
    tickets = [SimpleNamespace(id=i, user_id=30, ticket_status=TicketStatus.NEW) for i in (330, 331)]
    monkeypatch.setattr(active_tickets, 'get_user_active_tickets', AsyncMock(return_value=tickets))
    get_ticket = AsyncMock(return_value=tickets[1])
    monkeypatch.setattr(active_tickets, 'get_ticket_by_id', get_ticket)
    await bot.dp.handle(event('закрой обращение'))
    assert await bot.context.get_state() == ClientTicketCloseStates.selecting_ticket
    await bot.dp.handle(event('999'))
    get_ticket.assert_not_awaited()
    assert await bot.context.get_state() == ClientTicketCloseStates.selecting_ticket
    await bot.dp.handle(event('331'))
    assert (await bot.context.get_data())['closing_ticket_id'] == 331
    assert await bot.context.get_state() == ClientTicketCloseStates.waiting_for_reason
    bot.forwarded.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_ai_response_exits_to_choices(bot, monkeypatch):
    await bot.context.set_state(AIAgentStates.waiting_for_request)
    monkeypatch.setattr(ai_agent, 'search_tech_support_knowledge', AsyncMock(return_value=[]))
    monkeypatch.setattr(ai_agent, 'classify_ai_agent_intent', AsyncMock(return_value=SimpleNamespace(
        intent=ai_agent.INTENT_OFFTOPIC, confidence=0.9, key_number=None, reply=None)))
    await bot.dp.handle(event('непонятный запрос'))
    assert await bot.context.get_state() is None
    assert bot.adapter.send_message.await_args.kwargs['keyboard'] is not None
    bot.forwarded.assert_not_awaited()


@pytest.mark.parametrize('text, action', [
    ('Открой Мой профиль', 'profile'), ('в меню', 'main_menu'),
    ('закрыть заявку', 'close_ticket'), ('закрой обращение #330', 'close_ticket'),
    ('какие подписки есть на моем ключе?', 'subscription_lookup'),
    ('я про годовые подписки на гранд-смету', 'subscription_lookup'),
    ('активация подписки', 'renewal'),
    ('профиль не загружается, помогите', None),
    ('менеджер сказал закрыть заявку после проверки', None),
])
def test_explicit_commands_do_not_consume_ordinary_text(text, action):
    assert text_menu_intents.direct_text_action(text) == action
