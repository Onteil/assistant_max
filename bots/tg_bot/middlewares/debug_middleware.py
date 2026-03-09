from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable

class DebugSpyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        state = data.get("state")
        current_state = await state.get_state() if state else "No State"
        
        # Достаем реальное имя функции-обработчика, которую выбрал Aiogram!
        matched_handler = data.get("handler")
        handler_name = matched_handler.callback.__name__ if matched_handler else "Unknown Handler"
        
        text_or_data = getattr(event, "text", getattr(event, "data", type(event).__name__))
        
        print(f"➡️ [SPY] Текст: '{text_or_data}' | Состояние: {current_state}")
        print(f"🚨 [SPY] Aiogram направил это сообщение в функцию: {handler_name} 🚨")
        
        result = await handler(event, data)
        
        print(f"⬅️ [SPY] Функция {handler_name} завершила работу.")
        return result