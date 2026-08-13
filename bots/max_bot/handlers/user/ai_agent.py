"""
AI manager assistant handlers for MAX bot.

The assistant greets the client, classifies free-form requests with Yandex GPT
Lite, and routes recognized intents to existing bot flows. Subscription lookup
is a stub until the 1C API contract is ready.
"""

from __future__ import annotations

import asyncio
import logging
from html import escape

from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.states import AIAgentStates
from services.tech_support_knowledge_service import (
    format_knowledge_answer,
    search_tech_support_knowledge,
)
from services.user_service import get_user_by_max_id
from services.yandex_gpt_service import (
    INTENT_CONSULTATION,
    INTENT_FAQ,
    INTENT_GOODBYE,
    INTENT_GREETING,
    INTENT_INVOICE,
    INTENT_OFFTOPIC,
    INTENT_SUBSCRIPTION,
    INTENT_SUPPORT,
    classify_ai_agent_intent,
)

logger = logging.getLogger(__name__)

AI_AGENT_PROCESSING_TEXT = "Пожалуйста, подождите, я обрабатываю ваш запрос..."
AI_AGENT_PROCESSING_DELAY_SECONDS = 5
AI_AGENT_SCOPE_TEXT = (
    "Я могу помочь только по вопросам АЙТАТ: подписки по ключу, счет, "
    "техническая поддержка, сметная консультация или обращение к менеджеру. "
    "Опишите, пожалуйста, ваш вопрос по этим темам."
)
AI_AGENT_CONTINUE_TEXT = (
    "Информация по подпискам готова.\n"
    "Напишите, что вы хотите сделать. Например:\n"
    "• Продлить ГРАНД-Смету\n"
    "• Нужен счет на оплату\n"
    "• Хочу подключить ИТС\n"
    "• Не открывается программа\n"
    "• Нужна консультация"
)

AI_QUESTION_MARKERS = (
    "?",
    "как ",
    "где ",
    "что ",
    "почему ",
    "зачем ",
    "можно ",
    "можете ",
    "подскаж",
    "расскаж",
    "что делать",
    "как узнать",
    "как посмотреть",
    "как найти",
    "как получить",
    "как добавить",
    "как выписать",
    "можно ли",
    "нужен счет",
    "нужен счёт",
    "нужна консультация",
    "не найден ключ",
    "не видит ключ",
    "номер ключа",
    "ключ защиты",
    "не запускается",
    "не открывается",
)


def _get_event_ids(event: MessageCreated | MessageCallback) -> tuple[int, int]:
    chat_id = event.message.recipient.chat_id
    if isinstance(event, MessageCallback):
        max_user_id = event.callback.user.user_id
    else:
        max_user_id = event.message.sender.user_id
    return chat_id, max_user_id


def _get_message_text(event: MessageCreated) -> str:
    return (event.message.body.text or "").strip()


def should_route_text_to_ai_assistant(text: str) -> bool:
    """Return True when a free text message looks like a question to the assistant."""
    normalized = f" {text.strip().lower()} "
    if not normalized.strip():
        return False

    if len(normalized) > 500:
        return False

    return any(marker in normalized for marker in AI_QUESTION_MARKERS)


async def start_ai_agent(
    event: MessageCreated | MessageCallback,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Start AI assistant flow from the Manager menu button."""
    chat_id, max_user_id = _get_event_ids(event)
    user = await get_user_by_max_id(session, max_user_id)

    if not user:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Пользователь не найден. Пожалуйста, начните работу командой /start.",
            parse_mode="HTML",
        )
        await context.clear()
        return

    user_name = user.first_name or user.full_name or "клиент"
    await context.clear()
    await context.update_data(user_id=user.id, ai_user_name=user_name)
    await context.set_state(AIAgentStates.waiting_for_request)

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=(
            f"Здравствуйте, {escape(user_name)}! "
            "Я — Ассистент сметчика АЙТАТ. Опишите, пожалуйста, ваш вопрос, "
            "и я помогу найти решение или направлю к нужному специалисту."
        ),
        parse_mode="HTML",
    )


async def handle_ai_agent_message(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    keep_ai_state: bool = True,
) -> None:
    """Handle free-form client request in AI assistant mode."""
    chat_id, max_user_id = _get_event_ids(event)
    user_text = _get_message_text(event)

    if not user_text:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Опишите, пожалуйста, ваш вопрос текстом.",
            parse_mode="HTML",
        )
        return

    user = await get_user_by_max_id(session, max_user_id)
    user_name = (
        user.first_name or user.full_name
        if user
        else (await context.get_data()).get("ai_user_name")
    )

    processing_task = asyncio.create_task(
        _send_processing_message_after_delay(chat_id, messenger_adapter)
    )
    try:
        knowledge_results = await search_tech_support_knowledge(session, user_text)
        if knowledge_results:
            if keep_ai_state:
                await context.set_state(AIAgentStates.waiting_for_request)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=format_knowledge_answer(knowledge_results[0]),
                parse_mode="HTML",
            )
            return

        intent = await classify_ai_agent_intent(user_text, user_name)
    finally:
        processing_task.cancel()
        try:
            await processing_task
        except asyncio.CancelledError:
            pass

    logger.info(
        "AI agent intent classified: max_user_id=%s, intent=%s, confidence=%s",
        max_user_id,
        intent.intent,
        intent.confidence,
    )

    await _route_ai_intent(
        event=event,
        context=context,
        session=session,
        messenger_adapter=messenger_adapter,
        intent=intent.intent,
        key_number=intent.key_number,
        reply=intent.reply,
        user_name=user_name,
        keep_ai_state=keep_ai_state,
    )


async def handle_ai_agent_key(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    """Handle key number after the assistant requested it."""
    chat_id, _ = _get_event_ids(event)
    key_number = _get_message_text(event)
    data = await context.get_data()
    user_name = data.get("ai_user_name") or "клиент"

    if not _looks_like_key(key_number):
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Введите номер ключа в формате 00000_00000.",
            parse_mode="HTML",
        )
        return

    await _send_subscription_stub(
        chat_id=chat_id,
        user_name=user_name,
        key_number=key_number,
        context=context,
        messenger_adapter=messenger_adapter,
    )


async def _route_ai_intent(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    intent: str,
    key_number: str | None,
    reply: str | None,
    user_name: str | None,
    keep_ai_state: bool = True,
) -> None:
    chat_id, _ = _get_event_ids(event)

    if intent == INTENT_SUBSCRIPTION:
        if not key_number:
            await context.set_state(AIAgentStates.waiting_for_key)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="Уточните, пожалуйста, номер ключа в формате 00000_00000.",
                parse_mode="HTML",
            )
            return

        await _send_subscription_stub(
            chat_id=chat_id,
            user_name=user_name or "клиент",
            key_number=key_number,
            context=context,
            messenger_adapter=messenger_adapter,
        )
        return

    if intent == INTENT_INVOICE:
        from bots.max_bot.handlers.tickets.invoice import cmd_invoice

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Поняла, нужен счет. Сейчас соберу данные для заявки менеджеру.",
            parse_mode="HTML",
        )
        await cmd_invoice(event, context, session, messenger_adapter)
        return

    if intent == INTENT_SUPPORT:
        from bots.max_bot.handlers.tickets.support import cmd_support

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Поняла, нужен специалист технической поддержки. Передаю в нужный сценарий.",
            parse_mode="HTML",
        )
        await cmd_support(event, context, session, messenger_adapter)
        return

    if intent == INTENT_CONSULTATION:
        from bots.max_bot.handlers.tickets.consultation import cmd_consultation

        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Поняла, нужна сметная консультация. Сейчас оформим обращение.",
            parse_mode="HTML",
        )
        await cmd_consultation(event, context, session, messenger_adapter)
        return

    if intent == INTENT_GOODBYE:
        await context.clear()
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="Спасибо за обращение. Хорошего дня!",
            parse_mode="HTML",
        )
        return

    if intent == INTENT_GREETING:
        if keep_ai_state:
            await context.set_state(AIAgentStates.waiting_for_request)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=reply or (
                "Здравствуйте! Я — Ассистент сметчика АЙТАТ. "
                "Опишите, пожалуйста, ваш вопрос."
            ),
            parse_mode="HTML",
        )
        return

    if intent == INTENT_FAQ:
        if keep_ai_state:
            await context.set_state(AIAgentStates.waiting_for_request)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=reply or AI_AGENT_SCOPE_TEXT,
            parse_mode="HTML",
        )
        return

    if intent == INTENT_OFFTOPIC:
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=AI_AGENT_SCOPE_TEXT,
            parse_mode="HTML",
        )
        return

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=(
            "Мне нужно чуть больше деталей, чтобы правильно направить обращение.\n\n"
            "Напишите, что вы хотите сделать. Например:\n"
            "• Продлить ГРАНД-Смету\n"
            "• Нужен счет на оплату\n"
            "• Хочу подключить ИТС\n"
            "• Не открывается программа\n"
            "• Нужна консультация"
        ),
        parse_mode="HTML",
    )


async def _send_subscription_stub(
    chat_id: int,
    user_name: str,
    key_number: str,
    context: MemoryContext,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    await context.set_state(AIAgentStates.waiting_for_request)
    await context.update_data(last_subscription_key=key_number)

    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=(
            f"{escape(user_name)}, нашла информацию по ключу "
            f"<code>{escape(key_number)}</code>:\n"
            "1) подписка на ГРАНД-Смету — данные ожидают подключения API 1С;\n"
            "2) подписка на базу ФСНБ-2022 — данные ожидают подключения API 1С;\n"
            "3) подписка на ИТС — данные ожидают подключения API 1С.\n\n"
            "Информация по подпискам будет выводиться автоматически после "
            "подключения метода 1С.\n\n"
            f"{AI_AGENT_CONTINUE_TEXT}"
        ),
        parse_mode="HTML",
    )


def _looks_like_key(value: str) -> bool:
    parts = value.split("_")
    return (
        len(parts) == 2
        and len(parts[0]) == 5
        and len(parts[1]) == 5
        and parts[0].isdigit()
        and parts[1].isdigit()
    )


async def _send_processing_message_after_delay(
    chat_id: int,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    await asyncio.sleep(AI_AGENT_PROCESSING_DELAY_SECONDS)
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=AI_AGENT_PROCESSING_TEXT,
        parse_mode="HTML",
    )
