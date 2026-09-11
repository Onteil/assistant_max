"""Durable follow-up for unfinished MAX invoice forms.

Redis stores invoice drafts and AI/client-close conversation state, separately
from Telegram/Celery. Only invoice drafts have reminder deadlines.
The webhook and timer share a renewable lock, so a reply/cancel cannot race a
handoff. Existing ticket creation handles assignment, working hours and files.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from enum import Enum

from maxapi.context import MemoryContext

from bots.max_bot.states import InvoiceStates, AIAgentStates, ClientTicketCloseStates, EmployeeStates

logger = logging.getLogger(__name__)
DUE_KEY = "max:invoice-followup:due"
DRAFT_PREFIX = "max:invoice-followup:draft:"
INVOICE_STATES = set(InvoiceStates.states())
PERSISTED_STATES = INVOICE_STATES | set(AIAgentStates.states()) | set(ClientTicketCloseStates.states()) | set(EmployeeStates.states())


def has_ticket_context(data):
    return bool(data.get('active_ticket_id') or data.get('awaiting_more_questions') or any(key.startswith('pending_message') and value for key, value in data.items()))
INVOICE_CALLBACKS = {
    "org_select", "org_page", "org_action", "key_toggle", "key_page",
    "key_action", "delivery", "email_confirm", "inv_desc_next",
}


def encode_draft(draft):
    def encode(value):
        if isinstance(value, Enum):
            return value.value
        raise TypeError(f"Unsupported invoice draft value: {type(value).__name__}")
    return json.dumps(draft, ensure_ascii=False, default=encode)


def restore_data(draft):
    from database.models import DeliveryMethod
    data = dict(draft["data"])
    if data.get("delivery_method"):
        data["delivery_method"] = DeliveryMethod(data["delivery_method"])
    return data


class RedisDraftStore:
    def __init__(self, redis):
        self.redis = redis

    async def get(self, key):
        raw = await self.redis.get(DRAFT_PREFIX + key)
        return json.loads(raw) if raw else None

    async def save(self, key, draft):
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.set(DRAFT_PREFIX + key, encode_draft(draft))
            if draft["due_at"] is not None:
                pipe.zadd(DUE_KEY, {key: draft["due_at"]})
            else:
                pipe.zrem(DUE_KEY, key)
            await pipe.execute()

    async def delete(self, key):
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.delete(DRAFT_PREFIX + key)
            pipe.zrem(DUE_KEY, key)
            await pipe.execute()

    async def due(self, now):
        return await self.redis.zrangebyscore(DUE_KEY, "-inf", now, start=0, num=100)

    @asynccontextmanager
    async def lock(self, key):
        lock = self.redis.lock(
            DRAFT_PREFIX + key + ":lock", timeout=120, blocking_timeout=120,
        )
        async with lock:
            async def renew():
                while True:
                    await asyncio.sleep(30)
                    await lock.extend(120, replace_ttl=True)

            task = asyncio.create_task(renew())
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


class InvoiceFollowups:
    def __init__(self, store, adapter, session_factory, *, reminder_seconds=900,
                 handoff_seconds=1800, clock=time.time):
        self.store = store
        self.adapter = adapter
        self.session_factory = session_factory
        self.reminder_seconds = reminder_seconds
        self.handoff_seconds = handoff_seconds
        self.clock = clock

    async def handle(self, dispatcher, event):
        """Restore the draft BEFORE maxapi evaluates its state filters."""
        update_type = getattr(event.update_type, "value", event.update_type)
        if update_type not in {"message_created", "message_callback", "bot_started"}:
            return await dispatcher.handle(event)
        chat_id, max_user_id = event.get_ids()
        if chat_id is None or max_user_id is None:
            return await dispatcher.handle(event)
        key = f"{chat_id}:{max_user_id}"
        async with self.store.lock(key):
            context = dispatcher.contexts.get((chat_id, max_user_id))
            if context is None:
                context = MemoryContext(chat_id, max_user_id)
                dispatcher.contexts[(chat_id, max_user_id)] = context
            draft = await self.store.get(key)
            if draft:
                await context.set_data(restore_data(draft))
                await context.set_state(draft["state"])
            elif str(await context.get_state()) in PERSISTED_STATES or has_ticket_context(await context.get_data()):
                # Another worker completed/cancelled this persisted form.
                await context.clear()

            payload = getattr(getattr(event, "callback", None), "payload", "") or ""
            invoice_active = draft and draft["state"] in INVOICE_STATES
            if not invoice_active and isinstance(payload, str) and payload.split("|", 1)[0] in INVOICE_CALLBACKS:
                from bots.max_bot.utils.callback_utils import answer_max_callback
                await answer_max_callback(event)
                await self.adapter.send_message(
                    chat_id=chat_id,
                    text="Это оформление уже завершено или отменено. Напишите новый запрос или используйте /start.",
                    parse_mode="HTML",
                )
                return

            await dispatcher.handle(event)
            state = await context.get_state()
            state = str(state) if state is not None else None
            data = await context.get_data()
            if str(state) in PERSISTED_STATES or (state is None and has_ticket_context(data)):
                # A reply or button press restarts both stages of the timer.
                await self.store.save(key, {
                    "chat_id": chat_id, "max_user_id": max_user_id,
                    "state": state, "data": data,
                    "due_at": self.clock() + self.reminder_seconds if state in INVOICE_STATES else None,
                    "reminded": False,
                })
            else:
                await self.store.delete(key)

    async def process_due(self):
        for key in await self.store.due(self.clock()):
            if isinstance(key, bytes):
                key = key.decode()
            try:
                async with self.store.lock(key):
                    draft = await self.store.get(key)
                    if not draft:
                        await self.store.delete(key)
                        continue
                    if draft["due_at"] is None or draft["due_at"] > self.clock():
                        continue
                    if not draft["reminded"]:
                        await self.adapter.send_message(
                            chat_id=draft["chat_id"],
                            text=(
                                "Оформление обращения по счету ещё актуально? "
                                "Продолжите с текущего шага или напишите «отмена». "
                                f"Если ответа не будет ещё {self.handoff_seconds // 60} мин., "
                                "передам собранные данные менеджеру, чтобы он мог связаться с вами."
                            ),
                            parse_mode="HTML",
                        )
                        draft.update(reminded=True, due_at=self.clock() + self.handoff_seconds)
                        await self.store.save(key, draft)
                    elif await self.handoff(draft):
                        await self.store.delete(key)
                    else:
                        draft["due_at"] = self.clock() + 60
                        await self.store.save(key, draft)
            except Exception:
                logger.exception("MAX invoice follow-up failed for %s", key)

    async def handoff(self, draft):
        from bots.max_bot.handlers.tickets.invoice import create_invoice_ticket
        from database.models import TicketType
        from services.ticket_service import get_user_active_ticket_by_type

        data = restore_data(draft)
        user_id = data.get("user_id")
        if not user_id:
            logger.error("Invoice draft without a registered user: %s", draft["chat_id"])
            return True
        async with self.session_factory() as session:
            # Also covers recovery after a process stopped just after DB commit.
            existing = await get_user_active_ticket_by_type(session, user_id, TicketType.INVOICE)
            if existing:
                return True
            details = data.get("description") or data.get("initial_request") or "Запрос счета"
            data.update(
                description=(
                    "Клиент не завершил оформление счета и не ответил на напоминание. "
                    "Необходимо связаться с клиентом и уточнить актуальность запроса.\n\n"
                    f"Собранное описание: {details}"
                ),
                automatic_handoff=True,
            )
            context = MemoryContext(draft["chat_id"], draft["max_user_id"])
            await context.set_data(data)
            await context.set_state(draft["state"])
            await create_invoice_ticket(context, session, self.adapter, draft["chat_id"], user_id)
            # Handlers clear the state after success or an existing-ticket limit.
            return await context.get_state() is None

    async def run(self):
        while True:
            try:
                await self.process_due()
            except Exception:
                logger.exception("MAX invoice follow-up scan failed")
            await asyncio.sleep(30)
