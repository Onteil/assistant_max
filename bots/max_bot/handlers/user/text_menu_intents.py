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
from types import SimpleNamespace

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


def direct_text_action(text: str) -> str | None:
    """Conservative commands that must work without an LLM or its availability."""
    value = re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip(" .!?\n")
    value = re.sub(r"^(?:пожалуйста[, ]+|бот[, ]+)", "", value)
    value = re.sub(r"[, ]+пожалуйста$", "", value)
    if re.fullmatch(r"(?:(?:я )?(?:хочу|нужно|надо) )?(?:закрой|закрыть|закройте)\s+(?:(?:мое|мою|это|эту|текущее|текущую|все|мои)\s+)*(?:заявк[ауи]|обращени[ея])(?:\s*(?:№|#)?\s*\d+)?", value):
        return "close_ticket"
    if re.fullmatch(r"(?:открой(?:те)? |открыть |покажи(?:те)? |показать |перейди в |перейти в )?(?:мой |мои )?профиль", value):
        return "profile"
    if re.fullmatch(r"(?:(?:открой(?:те)?|покажи(?:те)?|открыть|показать|вернись|вернуться)\s+)?(?:в |на )?(?:главное )?меню", value):
        return "main_menu"
    if re.fullmatch(r"(?:(?:открой(?:те)?|покажи(?:те)?|открыть|показать)\s+)?(?:мой |мои )?(?:архив|историю обращений|историю заявок)", value):
        return "archive"
    if re.fullmatch(r"(?:(?:открой(?:те)?|покажи(?:те)?|открыть|показать)\s+)?(?:(?:мои|активные|открытые|текущие)\s+)*(?:заявки|обращения)", value):
        return "active_tickets"
    section = re.sub(r"^(?:открой(?:те)?|открыть|перейди в|перейти в)\s+", "", value)
    if section in {"техподдержка", "техподдержку", "техническая поддержка", "техническую поддержку"}:
        return "support"
    if section in {"сметная консультация", "сметную консультацию", "консультация"}:
        return "consultation"
    if section in {"активация подписки", "активацию подписки"}:
        return "renewal"
    if "подпис" in value and (
        any(word in value for word in ("ключ", "гранд", "фснб", "годов"))
        or re.search(r"\b(?:какие|узнать|посмотреть|проверить)\b", value)
    ) and not re.search(r"\b(?:активир\w*|продл\w*|купить|оформить)\b", value):
        return "subscription_lookup"
    if value in {"отмена", "отмени", "выйти", "выход"}:
        return "cancel"
    return None
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
    explicit_only: bool = False,
) -> bool:
    """
    Route text requests like "open menu", "my profile" or "need invoice".

    Returns True when the message was handled as bot navigation/scenario start.
    """
    text = _get_message_text(event)
    if not text or text.startswith("/") or len(text) > MAX_ROUTABLE_TEXT_LENGTH:
        return False

    from bots.max_bot.states import ClientTicketCloseStates
    state_name = str(current_state) if current_state is not None else ""
    allowed_groups = ("AIAgentStates:", "InvoiceStates:", "SupportStates:",
                      "ConsultationStates:", "ProfileStates:", "ClientTicketCloseStates:")
    if state_name and not state_name.startswith(allowed_groups):
        return False
    direct_action = direct_text_action(text)
    # A reason is form data: "вопрос решен, закрыть заявку" must remain a reason.
    if current_state == ClientTicketCloseStates.waiting_for_reason and direct_action == "close_ticket":
        await messenger_adapter.send_message(
            chat_id=event.message.recipient.chat_id,
            text="Закрытие уже начато. Напишите причину или «пропустить», чтобы закрыть без причины.",
        )
        return True
    if current_state == ClientTicketCloseStates.selecting_ticket and direct_action is None:
        direct_action = "close_ticket"
    if direct_action == "cancel":
        if not state_name.startswith("AIAgentStates:") and current_state != ClientTicketCloseStates.selecting_ticket:
            return False  # Other forms have their own cancellation handlers.
        direct_action = "main_menu"
    if explicit_only and direct_action is None:
        return False
    if direct_action is None and not is_yandex_gpt_configured():
        return False

    try:
        intent = SimpleNamespace(action=direct_action, confidence=1.0) if direct_action else await asyncio.wait_for(
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

    if current_state is not None and action not in NAVIGATION_ACTIONS | {"close_ticket", "subscription_lookup"} and not direct_action:
        return False

    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    user = await get_user_by_max_id(session, max_user_id)
    if not user or user.registration_status != RegistrationStatus.ACTIVE:
        return False

    if intent.confidence < MIN_MENU_INTENT_CONFIDENCE:
        if action == "subscription_lookup":
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text="Вы хотите узнать подписки на ГРАНД-Смету по ключу? Напишите «подписки на моем ключе» или уточните запрос.",
            )
            return True
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

    if action == "close_ticket":
        from bots.max_bot.handlers.user.active_tickets import start_ticket_close_from_text
        await start_ticket_close_from_text(event, context, session, messenger_adapter, user)
        return True

    if action == "subscription_lookup":
        from bots.max_bot.handlers.user.ai_agent import start_subscription_lookup
        await start_subscription_lookup(event, context, session, messenger_adapter)
        return True

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

        if _looks_like_invoice_request(text):
            user_name = escape(user.first_name or user.full_name or "клиент")
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=(
                    f"Здравствуйте, {user_name}! "
                    "Я — Ассистент сметчика АЙТАТ. "
                    "Вижу, что запрашиваете счет. Задам пару уточняющих вопросов "
                    "и сделаю заявку менеджеру."
                ),
                parse_mode="HTML",
            )
            await cmd_invoice(event, context, session, messenger_adapter)
        elif is_yandex_gpt_configured():
            from bots.max_bot.handlers.user.ai_agent import handle_ai_agent_message
            await context.update_data(user_id=user.id, ai_user_name=user.first_name or user.full_name)
            # Process the request already supplied by the client instead of
            # discarding it and repeatedly asking for the same question.
            await handle_ai_agent_message(event, context, session, messenger_adapter)
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
