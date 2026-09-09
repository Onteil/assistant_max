"""Text controls for existing MAX bot scenarios.

This module lets users type the same actions that are available as buttons.
Business logic stays in the original scenario handlers.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from typing import Any

from maxapi.context import MemoryContext
from maxapi.types import MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from bots.max_bot.messenger_adapter import MAXMessengerAdapter
from bots.max_bot.states import ConsultationStates, InvoiceStates, SupportStates
from services.yandex_gpt_service import YandexGPTService, is_yandex_gpt_configured

logger = logging.getLogger(__name__)

MIN_STEP_ACTION_CONFIDENCE = 0.6
KEY_RE = re.compile(r"\b\d{5}_\d{5}\b")


def _text(event: MessageCreated) -> str:
    if not event.message.body or not event.message.body.text:
        return ""
    return event.message.body.text.strip()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()


def _is_cancel(text: str) -> bool:
    value = _norm(text)
    cancel_markers = (
        "отмена",
        "отмени",
        "отменить",
        "cancel",
        "/cancel",
        "не надо",
        "ненадо",
        "не нужно",
        "не нужен",
        "не нужна",
        "не актуально",
        "неактуально",
        "уже не актуально",
        "передумал",
        "передумала",
        "закрыть",
        "закрой",
        "счет не нужен",
        "счёт не нужен",
        "не надо счет",
        "не надо счёт",
        "заявка не нужна",
    )
    return value in cancel_markers or any(marker in value for marker in cancel_markers)


def is_cancel_text(text: str) -> bool:
    """Return True when user text clearly cancels the current flow."""
    return _is_cancel(text)


def _is_back(text: str) -> bool:
    value = _norm(text)
    return value in {"назад", "вернуться", "предыдущий шаг", "обратно"}


def _is_next(text: str) -> bool:
    value = _norm(text)
    return value in {"далее", "готово", "продолжить", "следующий шаг", "дальше"}


def _is_skip(text: str) -> bool:
    value = _norm(text)
    return value in {"пропустить", "без ключа", "без ключей", "не выбирать", "не указывать"}


def _is_add_key(text: str) -> bool:
    value = _norm(text)
    return "добав" in value and "ключ" in value


def _is_chat_delivery(text: str) -> bool:
    value = _norm(text)
    return value in {"в чат", "чат", "сюда", "здесь", "сообщением"}


def _is_email_delivery(text: str) -> bool:
    value = _norm(text)
    return any(marker in value for marker in ("email", "e-mail", "почт", "емейл", "имейл"))


def _is_confirm(text: str) -> bool:
    value = _norm(text)
    return value in {"подтвердить", "подтверждаю", "да", "верно", "создать", "оформить"}


def _make_callback_event(event: MessageCreated, payload: str | dict[str, Any] | None = None) -> Any:
    """Build the small callback-shaped object used by existing handlers."""
    return SimpleNamespace(
        message=event.message,
        callback=SimpleNamespace(
            user=SimpleNamespace(user_id=event.message.sender.user_id),
            payload=payload,
            callback_id=None,
        ),
        bot=None,
    )


async def _classify_step_action(
    text: str,
    scenario: str,
    step: str,
    allowed_actions: dict[str, str],
) -> str:
    if not is_yandex_gpt_configured():
        return "unknown"

    try:
        result = await YandexGPTService().classify_scenario_action(
            user_text=text,
            scenario=scenario,
            step=step,
            allowed_actions=allowed_actions,
        )
    except Exception as exc:
        logger.warning("Scenario text action classification failed: %s", exc, exc_info=True)
        return "unknown"

    if result.confidence < MIN_STEP_ACTION_CONFIDENCE:
        return "unknown"
    return result.action


async def route_text_scenario_action(
    event: MessageCreated,
    context: MemoryContext,
    session: AsyncSession,
    messenger_adapter: MAXMessengerAdapter,
    current_state: Any,
) -> bool:
    """Handle typed button-equivalent actions inside active FSM scenarios."""
    text = _text(event)
    if not text:
        return False

    if current_state == InvoiceStates.selecting_keys:
        return await _route_invoice_keys(event, context, session, messenger_adapter, text)
    if current_state == InvoiceStates.selecting_delivery:
        return await _route_invoice_delivery(event, context, session, messenger_adapter, text)
    if current_state == InvoiceStates.confirming_email:
        return await _route_invoice_email_confirm(event, context, session, messenger_adapter, text)
    if current_state == SupportStates.selecting_key_context:
        return await _route_support_keys(event, context, session, messenger_adapter, text)
    if current_state == ConsultationStates.selecting_keys:
        return await _route_consultation_keys(event, context, session, messenger_adapter, text)

    return False


async def _route_invoice_keys(event, context, session, messenger_adapter, text: str) -> bool:
    from bots.max_bot.handlers.tickets.invoice import (
        cancel_invoice_flow,
        get_user_id_with_fallback_from_message,
        process_new_key,
        show_key_selection,
        show_organization_selection,
    )
    from bots.max_bot.keyboards.tickets.invoice_kb import get_description_input_keyboard
    from bots.max_bot.texts import INVOICE_ENTER_DESCRIPTION
    from bots.max_bot.states import InvoiceStates
    from services.user_service import get_user_keys

    chat_id = event.message.recipient.chat_id
    user_id = await get_user_id_with_fallback_from_message(context, event, session, messenger_adapter)
    if not user_id:
        return True

    data = await context.get_data()
    selected_keys = set(data.get("selected_keys", []))
    key_match = KEY_RE.search(text)
    if key_match:
        key_number = key_match.group(0)
        keys = await get_user_keys(session, user_id)
        existing = next((key for key in keys if key.key_number == key_number), None)
        if existing:
            selected_keys.add(existing.id)
            await context.update_data(selected_keys=list(selected_keys))
            await show_key_selection(chat_id, user_id, selected_keys, 0, session, messenger_adapter)
        else:
            await context.set_state(InvoiceStates.adding_new_key)
            await process_new_key(event, context, session, messenger_adapter)
        return True

    action = _direct_key_action(text) or await _classify_step_action(
        text,
        "получение счета",
        "выбор ключа",
        {
            "add_new": "клиент хочет добавить новый ключ",
            "done": "клиент закончил выбор ключей и хочет перейти дальше",
            "skip": "клиент хочет пропустить выбор ключей",
            "back": "клиент хочет вернуться к выбору организации",
            "cancel": "клиент хочет отменить сценарий",
            "unknown": "сообщение не относится к действиям шага",
        },
    )

    if action == "add_new":
        await context.set_state(InvoiceStates.adding_new_key)
        from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="🔑 Введите новый ключ Гранд-сметы (формат: 00001_00011):",
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML",
        )
        return True
    if action in {"done", "skip"}:
        if action == "skip":
            selected_keys = set()
            await context.update_data(selected_keys=[])
        await context.set_state(InvoiceStates.entering_description)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_ENTER_DESCRIPTION,
            keyboard=get_description_input_keyboard(has_content=False),
            parse_mode="HTML",
        )
        return True
    if action == "back":
        await context.set_state(InvoiceStates.selecting_organization)
        await show_organization_selection(chat_id, user_id, 0, session, messenger_adapter)
        return True
    if action == "cancel":
        await cancel_invoice_flow(_make_callback_event(event), context, session, messenger_adapter)
        return True
    return False


async def _route_invoice_delivery(event, context, session, messenger_adapter, text: str) -> bool:
    from bots.max_bot.handlers.tickets.invoice import (
        cancel_invoice_flow,
        create_invoice_ticket,
        get_user_id_with_fallback_from_message,
        show_invoice_confirmation,
    )
    from bots.max_bot.keyboards.tickets.invoice_kb import (
        get_description_input_keyboard,
        get_email_confirm_keyboard,
        get_email_input_keyboard,
        get_delivery_keyboard,
    )
    from bots.max_bot.texts import INVOICE_CONFIRM_EMAIL, INVOICE_ENTER_DESCRIPTION, INVOICE_ENTER_EMAIL, INVOICE_SELECT_DELIVERY
    from bots.max_bot.states import InvoiceStates
    from database.models import DeliveryMethod
    from services.user_service import get_user_by_max_id

    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    user_id = await get_user_id_with_fallback_from_message(context, event, session, messenger_adapter)
    if not user_id:
        return True

    action = None
    if _is_chat_delivery(text):
        action = "chat"
    elif _is_email_delivery(text):
        action = "email"
    elif _is_confirm(text):
        action = "confirm"
    elif _is_back(text):
        action = "back"
    elif _is_cancel(text):
        action = "cancel"
    else:
        action = await _classify_step_action(
            text,
            "получение счета",
            "выбор способа доставки или подтверждение заявки",
            {
                "chat": "клиент хочет получить результат в чат",
                "email": "клиент хочет получить результат на email или почту",
                "confirm": "клиент подтверждает создание заявки",
                "back": "клиент хочет вернуться назад",
                "cancel": "клиент хочет отменить сценарий",
                "unknown": "сообщение не относится к действиям шага",
            },
        )

    if action == "chat":
        await context.update_data(delivery_method=DeliveryMethod.TELEGRAM, delivery_email=None)
        await show_invoice_confirmation(chat_id, context, session, messenger_adapter)
        return True
    if action == "email":
        user = await get_user_by_max_id(session, max_user_id)
        await context.update_data(delivery_method=DeliveryMethod.EMAIL)
        if user and user.email:
            await context.set_state(InvoiceStates.confirming_email)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_CONFIRM_EMAIL.format(email=user.email),
                keyboard=get_email_confirm_keyboard(),
                parse_mode="HTML",
            )
        else:
            await context.set_state(InvoiceStates.entering_email)
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_ENTER_EMAIL,
                keyboard=get_email_input_keyboard(),
                parse_mode="HTML",
            )
        return True
    if action == "confirm":
        data = await context.get_data()
        if not data.get("delivery_method"):
            await messenger_adapter.send_message(
                chat_id=chat_id,
                text=INVOICE_SELECT_DELIVERY,
                keyboard=get_delivery_keyboard(),
                parse_mode="HTML",
            )
            return True
        await create_invoice_ticket(context, session, messenger_adapter, chat_id, user_id)
        return True
    if action == "back":
        data = await context.get_data()
        await context.set_state(InvoiceStates.entering_description)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_ENTER_DESCRIPTION,
            keyboard=get_description_input_keyboard(
                has_content=bool(data.get("description")) or bool(data.get("attachments"))
            ),
            parse_mode="HTML",
        )
        return True
    if action == "cancel":
        await cancel_invoice_flow(_make_callback_event(event), context, session, messenger_adapter)
        return True
    return False


async def _route_invoice_email_confirm(event, context, session, messenger_adapter, text: str) -> bool:
    from bots.max_bot.handlers.tickets.invoice import (
        cancel_invoice_flow,
        get_user_id_with_fallback_from_message,
        show_invoice_confirmation,
    )
    from bots.max_bot.keyboards.tickets.invoice_kb import get_email_input_keyboard
    from bots.max_bot.texts import INVOICE_ENTER_EMAIL
    from bots.max_bot.states import InvoiceStates
    from services.user_service import get_user_by_max_id

    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    user_id = await get_user_id_with_fallback_from_message(context, event, session, messenger_adapter)
    if not user_id:
        return True

    value = _norm(text)
    if value in {"да", "верно", "использовать", "используй", "оставить", "на этот"}:
        user = await get_user_by_max_id(session, max_user_id)
        if user and user.email:
            await context.update_data(delivery_email=user.email)
            await show_invoice_confirmation(chat_id, context, session, messenger_adapter)
        return True
    if value in {"другой", "другая почта", "новый", "ввести новый", "изменить"} or _is_email_delivery(text):
        await context.set_state(InvoiceStates.entering_email)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=INVOICE_ENTER_EMAIL,
            keyboard=get_email_input_keyboard(),
            parse_mode="HTML",
        )
        return True
    if _is_cancel(text):
        await cancel_invoice_flow(_make_callback_event(event), context, session, messenger_adapter)
        return True
    return False


async def _route_support_keys(event, context, session, messenger_adapter, text: str) -> bool:
    from bots.max_bot.handlers.tickets.support import (
        cancel_support_flow,
        create_support_ticket,
        process_new_key_for_support,
        show_key_context_selection,
    )
    from bots.max_bot.keyboards.tickets.support_kb import get_add_key_keyboard, get_problem_description_keyboard
    from bots.max_bot.texts import SUPPORT_CREATE_TICKET
    from bots.max_bot.states import SupportStates
    from services.user_service import get_user_keys

    chat_id = event.message.recipient.chat_id
    data = await context.get_data()
    user_id = data.get("user_id")
    if not user_id:
        return False

    selected_keys = set(data.get("selected_keys", []))
    key_match = KEY_RE.search(text)
    if key_match:
        key_number = key_match.group(0)
        keys = await get_user_keys(session, user_id)
        existing = next((key for key in keys if key.key_number == key_number), None)
        if existing:
            selected_keys.add(existing.id)
            await context.update_data(selected_keys=list(selected_keys))
            await show_key_context_selection(chat_id, user_id, selected_keys, 0, session, messenger_adapter)
        else:
            await context.set_state(SupportStates.adding_new_key)
            await process_new_key_for_support(event, context, session, messenger_adapter)
        return True

    action = _direct_key_action(text) or await _classify_step_action(
        text,
        "техподдержка",
        "выбор ключа",
        {
            "add_new": "клиент хочет добавить новый ключ",
            "done": "клиент закончил выбор ключей и хочет создать заявку",
            "skip": "клиент хочет создать заявку без выбора ключа",
            "back": "клиент хочет вернуться к описанию проблемы",
            "cancel": "клиент хочет отменить сценарий",
            "unknown": "сообщение не относится к действиям шага",
        },
    )

    if action == "add_new":
        await context.set_state(SupportStates.adding_new_key)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text="🔑 Введите новый ключ Гранд-сметы (формат: 00001_00011):",
            keyboard=get_add_key_keyboard(),
            parse_mode="HTML",
        )
        return True
    if action in {"done", "skip"}:
        if action == "skip":
            await context.update_data(selected_keys=[])
        await create_support_ticket(context, session, messenger_adapter, chat_id, user_id)
        return True
    if action == "back":
        await context.set_state(SupportStates.entering_problem)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=SUPPORT_CREATE_TICKET,
            keyboard=get_problem_description_keyboard(
                has_content=bool(data.get("problem_description")) or bool(data.get("attachments"))
            ),
            parse_mode="HTML",
        )
        return True
    if action == "cancel":
        await cancel_support_flow(_make_callback_event(event), context, session, messenger_adapter)
        return True
    return False


async def _route_consultation_keys(event, context, session, messenger_adapter, text: str) -> bool:
    from bots.max_bot.handlers.tickets.consultation import (
        _cancel_flow,
        _get_user_id,
        _show_key_selection,
        _show_organization_selection,
        process_consultation_new_key,
    )
    from bots.max_bot.keyboards.tickets.consultation_kb import get_consultation_description_keyboard
    from bots.max_bot.texts import CONSULTATION_ADD_NEW_KEY, CONSULTATION_ENTER_DESCRIPTION
    from bots.max_bot.states import ConsultationStates
    from services.user_service import get_user_keys

    chat_id = event.message.recipient.chat_id
    max_user_id = event.message.sender.user_id
    user_id = await _get_user_id(context, max_user_id, session, chat_id, messenger_adapter)
    if not user_id:
        return True

    data = await context.get_data()
    selected_keys = set(data.get("selected_keys", []))
    key_match = KEY_RE.search(text)
    if key_match:
        key_number = key_match.group(0)
        keys = await get_user_keys(session, user_id)
        existing = next((key for key in keys if key.key_number == key_number), None)
        if existing:
            selected_keys.add(existing.id)
            await context.update_data(selected_keys=list(selected_keys))
            await _show_key_selection(chat_id, user_id, selected_keys, 0, session, messenger_adapter)
        else:
            await context.set_state(ConsultationStates.adding_new_key)
            await process_consultation_new_key(event, context, session, messenger_adapter)
        return True

    action = _direct_key_action(text) or await _classify_step_action(
        text,
        "сметная консультация",
        "выбор ключа",
        {
            "add_new": "клиент хочет добавить новый ключ",
            "done": "клиент закончил выбор ключей и хочет перейти дальше",
            "skip": "клиент хочет пропустить выбор ключей",
            "back": "клиент хочет вернуться к выбору организации",
            "cancel": "клиент хочет отменить сценарий",
            "unknown": "сообщение не относится к действиям шага",
        },
    )

    if action == "add_new":
        await context.set_state(ConsultationStates.adding_new_key)
        from bots.max_bot.keyboards.user.registration_kb import get_cancel_keyboard
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_ADD_NEW_KEY,
            keyboard=get_cancel_keyboard(),
            parse_mode="HTML",
        )
        return True
    if action in {"done", "skip"}:
        if action == "skip":
            await context.update_data(selected_keys=[])
        await context.set_state(ConsultationStates.entering_description)
        await messenger_adapter.send_message(
            chat_id=chat_id,
            text=CONSULTATION_ENTER_DESCRIPTION,
            keyboard=get_consultation_description_keyboard(has_content=False),
            parse_mode="HTML",
        )
        return True
    if action == "back":
        await context.set_state(ConsultationStates.selecting_organization)
        await _show_organization_selection(chat_id, user_id, 0, session, messenger_adapter)
        return True
    if action == "cancel":
        await _cancel_flow(_make_callback_event(event), context, session, messenger_adapter)
        return True
    return False


def _direct_key_action(text: str) -> str | None:
    if _is_add_key(text):
        return "add_new"
    if _is_next(text):
        return "done"
    if _is_skip(text):
        return "skip"
    if _is_back(text):
        return "back"
    if _is_cancel(text):
        return "cancel"
    return None


async def is_description_text_control(text: str, scenario: str) -> str:
    """Return next/back/cancel/unknown for typed controls in description steps."""
    if _is_next(text):
        return "next"
    if _is_back(text):
        return "back"
    if _is_cancel(text):
        return "cancel"
    return await _classify_step_action(
        text,
        scenario,
        "ввод описания",
        {
            "next": "клиент закончил ввод описания и хочет перейти дальше",
            "back": "клиент хочет вернуться на предыдущий шаг",
            "cancel": "клиент хочет отменить сценарий",
            "unknown": "это само описание заявки, а не команда управления шагом",
        },
    )
