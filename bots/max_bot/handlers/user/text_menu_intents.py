"""AI-assisted text routing for MAX bot menu sections and scenarios.

Buttons remain available. This module lets a client type a request in free
form and opens the matching existing menu section or scenario when Yandex GPT
is configured.
"""

from __future__ import annotations

import logging
import asyncio
import re
from html import escape
from typing import Any

from maxapi.context import MemoryContext
from maxapi.types import MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import Keyboard, KeyboardButton, MAXMessengerAdapter
from bots.max_bot.payloads import MainMenuActionPayload
from bots.max_bot.texts import MAIN_MENU_WELCOME_TEXT
from database.models import RegistrationStatus
from services.ticket_service import get_user_active_tickets_count
from services.user_service import get_user_by_max_id
from services.yandex_gpt_service import (
    classify_menu_navigation,
    is_yandex_gpt_configured,
)

logger = logging.getLogger(__name__)

MIN_MENU_INTENT_CONFIDENCE = 0.6
MIN_MENU_CLARIFICATION_CONFIDENCE = 0.35
MENU_INTENT_TIMEOUT_SECONDS = 2
MAX_ROUTABLE_TEXT_LENGTH = 500
NAVIGATION_ACTIONS = {"main_menu", "profile", "archive", "active_tickets"}
ACTION_LABELS = {
    "main_menu": "Главное меню",
    "profile": "Мой профиль",
    "archive": "Архив",
    "active_tickets": "Мои заявки",
    "manager": "Менеджер",
    "support": "Техподдержка",
    "consultation": "Сметная консультация",
    "renewal": "Активация подписки",
}
ACTION_PAYLOADS = {
    "main_menu": "main_menu",
    "profile": "profile",
    "archive": "archive",
    "active_tickets": "active_tickets",
    "manager": "invoice",
    "support": "support",
    "consultation": "consultation",
    "renewal": "renewal",
}
MENU_NAVIGATION_WORDS = (
    "мен",
    "мню",
    "мнею",
    "медю",
    "проф",
    "арх",
    "актив",
    "открыт",
    "текущ",
    "заяв",
    "обращ",
    "менедж",
    "счет",
    "счёт",
    "поддерж",
    "тех",
    "консульт",
    "смет",
    "подпис",
    "активац",
    "продл",
)
AMBIGUOUS_HELP_WORDS = (
    "помог",
    "помощ",
    "вопрос",
    "подскаж",
    "не понимаю",
    "не понятно",
    "непонятно",
    "надо разобраться",
    "нужно разобраться",
    "что делать",
    "как быть",
    "проблем",
    "сложно",
)


def _get_message_text(event: MessageCreated) -> str:
    if not event.message.body or not event.message.body.text:
        return ""
    return event.message.body.text.strip()


def _looks_like_menu_navigation(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()
    if not normalized:
        return False

    words = normalized.split()
    if len(words) > 12:
        return False

    return any(marker in normalized for marker in MENU_NAVIGATION_WORDS)


def _looks_like_invoice_request(text: str) -> bool:
    normalized = text.lower().replace("ё", "е")
    return any(
        marker in normalized
        for marker in (
            "счет",
            "счёт",
            "оплат",
            "выстав",
            "выпис",
            "коммерческ",
            "кп",
        )
    )


def _looks_like_ambiguous_help_request(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()
    if not normalized:
        return False
    if len(normalized.split()) > 20:
        return False
    return any(marker in normalized for marker in AMBIGUOUS_HELP_WORDS)


async def route_text_menu_intent(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    current_state: Any = None,
) -> bool:
    """
    Route text requests like "open menu", "my profile" or "need invoice".

    Returns True when the message was handled as bot navigation/scenario start.
    """
    if not is_yandex_gpt_configured():
        return False

    text = _get_message_text(event)
    if not text or text.startswith("/") or len(text) > MAX_ROUTABLE_TEXT_LENGTH:
        return False

    try:
        intent = await asyncio.wait_for(
            classify_menu_navigation(text),
            timeout=MENU_INTENT_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "Text menu intent classification skipped: %s",
            exc,
            exc_info=True,
        )
        return False

    action = intent.action
    if action == "unknown":
        if current_state is None and _looks_like_ambiguous_help_request(text):
            await _send_general_intent_clarification(
                chat_id=event.message.recipient.chat_id,
                messenger_adapter=messenger_adapter,
            )
            return True
        return False

    if current_state is not None and action not in NAVIGATION_ACTIONS:
        return False

    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    user = await get_user_by_max_id(session, max_user_id)
    if not user or user.registration_status != RegistrationStatus.ACTIVE:
        return False

    if intent.confidence < MIN_MENU_INTENT_CONFIDENCE:
        if intent.confidence >= MIN_MENU_CLARIFICATION_CONFIDENCE:
            await _send_menu_intent_clarification(
                chat_id=chat_id,
                action=action,
                messenger_adapter=messenger_adapter,
            )
            return True
        if current_state is None and _looks_like_ambiguous_help_request(text):
            await _send_general_intent_clarification(
                chat_id=chat_id,
                messenger_adapter=messenger_adapter,
            )
            return True
        return False

    logger.info(
        "Text menu intent routed: max_user_id=%s, action=%s, confidence=%s",
        max_user_id,
        action,
        intent.confidence,
    )

    await context.clear()

    if action == "main_menu":
        await _show_main_menu(chat_id, user.id, session, messenger_adapter)
        return True

    if action == "profile":
        from bots.max_bot.handlers.user.profile import cmd_profile

        await cmd_profile(event, session, messenger_adapter)
        return True

    if action == "archive":
        from bots.max_bot.handlers.user.archive import show_archive_list

        await show_archive_list(
            chat_id,
            max_user_id,
            session,
            messenger_adapter,
            context,
        )
        return True

    if action == "active_tickets":
        from bots.max_bot.handlers.user.main_menu_callbacks import (
            show_active_tickets_list,
        )

        await show_active_tickets_list(event, session, messenger_adapter)
        return True

    if action == "manager":
        from bots.max_bot.handlers.tickets.invoice import cmd_invoice
        from bots.max_bot.handlers.user.ai_agent import start_ai_agent

        if _looks_like_invoice_request(text):
            user_name = escape(user.first_name or user.full_name or "клиент")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    f"Здравствуйте, {user_name}! "
                    "Вижу, что запрашиваете счет. Задам пару уточняющих вопросов "
                    "и сделаю заявку менеджеру."
                ),
                parse_mode="HTML",
            )
            await cmd_invoice(event, context, session, messenger_adapter)
        elif is_yandex_gpt_configured():
            await start_ai_agent(event, context, session, messenger_adapter)
        else:
            await cmd_invoice(event, context, session, messenger_adapter)
        return True

    if action == "support":
        from bots.max_bot.handlers.tickets.support import cmd_support

        await cmd_support(event, context, session, messenger_adapter)
        return True

    if action == "consultation":
        from bots.max_bot.handlers.tickets.consultation import cmd_consultation

        await cmd_consultation(event, context, session, messenger_adapter)
        return True

    if action == "renewal":
        from bots.max_bot.handlers.user.renewal import show_subscription_status

        await show_subscription_status(event, session, messenger_adapter)
        return True

    return False


async def _send_menu_intent_clarification(
    chat_id: int,
    action: str,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    label = ACTION_LABELS.get(action)
    payload_action = ACTION_PAYLOADS.get(action)
    if not label or not payload_action:
        return

    keyboard = Keyboard(
        buttons=[
            [
                KeyboardButton(
                    text=label,
                    payload=MainMenuActionPayload(action=payload_action).pack(),
                )
            ],
            [
                KeyboardButton(
                    text="Главное меню",
                    payload=MainMenuActionPayload(action="main_menu").pack(),
                )
            ],
        ],
        inline=True,
    )
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=f"Не совсем понял запрос. Возможно, вы имели в виду «{label}»?",
        keyboard=keyboard,
        parse_mode="HTML",
    )


async def _send_general_intent_clarification(
    chat_id: int,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    keyboard = Keyboard(
        buttons=[
            [
                KeyboardButton(
                    text="Менеджер",
                    payload=MainMenuActionPayload(action="invoice").pack(),
                ),
                KeyboardButton(
                    text="Техподдержка",
                    payload=MainMenuActionPayload(action="support").pack(),
                ),
            ],
            [
                KeyboardButton(
                    text="Сметная консультация",
                    payload=MainMenuActionPayload(action="consultation").pack(),
                )
            ],
            [
                KeyboardButton(
                    text="Активация подписки",
                    payload=MainMenuActionPayload(action="renewal").pack(),
                ),
                KeyboardButton(
                    text="Мои заявки",
                    payload=MainMenuActionPayload(action="active_tickets").pack(),
                ),
            ],
            [
                KeyboardButton(
                    text="Мой профиль",
                    payload=MainMenuActionPayload(action="profile").pack(),
                ),
                KeyboardButton(
                    text="Главное меню",
                    payload=MainMenuActionPayload(action="main_menu").pack(),
                ),
            ],
        ],
        inline=True,
    )
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=(
            "Не совсем понял, что именно нужно сделать. "
            "Выберите подходящий вариант или напишите подробнее."
        ),
        keyboard=keyboard,
        parse_mode="HTML",
    )


async def _show_main_menu(
    chat_id: int,
    user_id: int,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
) -> None:
    from bots.max_bot.keyboards.user.main_menu_kb import (
        get_main_menu_inline_keyboard,
    )

    active_tickets_count = await get_user_active_tickets_count(session, user_id)
    keyboard = await get_main_menu_inline_keyboard(active_tickets_count)
    await messenger_adapter.send_message(
        chat_id=chat_id,
        text=MAIN_MENU_WELCOME_TEXT,
        keyboard=keyboard,
        parse_mode="HTML",
    )
