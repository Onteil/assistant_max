"""Handle explicit client commands before FSM input or ticket forwarding."""

from maxapi.filters.middleware import BaseMiddleware
from maxapi.types import MessageCreated


class ConversationMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, MessageCreated) and event.message.body and event.message.body.text:
            from bots.max_bot.handlers.user.text_menu_intents import route_text_menu_intent, _looks_like_menu_navigation
            context = data['context']
            state = await context.get_state()
            # Also allow LLM navigation variants inside AI mode, where the
            # ordinary catch-all router would otherwise never see them.
            ai_navigation = str(state).startswith('AIAgentStates:') and _looks_like_menu_navigation(event.message.body.text)
            if await route_text_menu_intent(
                event, context, data['session'], data['messenger_adapter'],
                current_state=state, explicit_only=not ai_navigation,
            ):
                return
        return await handler(event, data)
