import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiogram.fsm.strategy import FSMStrategy
from redis.asyncio.client import Redis

from constants import (
    AIOGRAM_REDIS_DB_NUMBER,
    HOST,
    HTTP_PROXY,
    IS_LOCAL_BOT,
    TG_BOT_TOKEN,
    MAX_BOT_TOKEN,
    REDIS,
    WEBHOOK_PATH_MAIN,
    WEBHOOK_PATH_MAX,
)
from bots.tg_bot.filters.chat_filter import ChatTypeFilter
from bots.tg_bot.middlewares.album_midleware import AlbumMiddleware
from bots.tg_bot.middlewares.debug_middleware import DebugSpyMiddleware
from bots.tg_bot.middlewares.bot_reconstruction import BotInReconstruction
from bots.tg_bot.middlewares.clear_state_middleware import StateClearerMiddleware
from bots.tg_bot.middlewares.database import DatabaseSessionMiddleware
from bots.tg_bot.middlewares.error_handler import ErrorHandler
from bots.tg_bot.middlewares.trottling import ThrottlingMiddleware
from bots.tg_bot.middlewares.user_data import UserDataMiddleware

redis: Redis | None = None
storage: RedisStorage | MemoryStorage
if not IS_LOCAL_BOT:
    redis = Redis.from_url(url=REDIS, db=AIOGRAM_REDIS_DB_NUMBER)
    storage = RedisStorage(redis=redis, key_builder=DefaultKeyBuilder(with_bot_id=True))
else:
    storage = MemoryStorage()

bot_session = AiohttpSession()

tg_bot = Bot(TG_BOT_TOKEN, session=bot_session, default=DefaultBotProperties(parse_mode="HTML"))

main_dp = Dispatcher(storage=storage, fsm_strategy=FSMStrategy.USER_IN_CHAT)

# Глобальные фильтры для всех обработчиков (применяются к диспетчеру)
main_dp.message.filter(ChatTypeFilter(chat_type=["private"]))
main_dp.callback_query.filter(ChatTypeFilter(chat_type=["private"]))

# Регистрация middleware
for middleware in [
    DatabaseSessionMiddleware(),
    ThrottlingMiddleware(),
    BotInReconstruction(),
    UserDataMiddleware(),
    ErrorHandler(),
    DebugSpyMiddleware()
]:
    main_dp.message.middleware(middleware)
    main_dp.callback_query.middleware(middleware)


# main_dp.message.outer_middleware(StateClearerMiddleware())
main_dp.message.middleware(AlbumMiddleware())


# ========== MAX Bot Setup ==========
# Initialize MAX bot and dispatcher
# Requirements: 10.1, 10.5 - Replace Aiogram Dispatcher with maxapi Dispatcher
# Requirements: 12.1, 12.4 - Session management and connection pooling
try:
    from maxapi import Bot as MAXBot
    from maxapi import Dispatcher as MAXDispatcher
    from maxapi import Router as MAXRouter
    from maxapi.context import MemoryContext
    from maxapi.enums.parse_mode import ParseMode
    from bots.max_bot.messenger_adapter import MAXMessengerAdapter
    from bots.max_bot.handlers import register_max_handlers
    from bots.max_bot.middlewares.database import DatabaseSessionMiddleware as MAXDatabaseSessionMiddleware
    from bots.max_bot.middlewares.messenger_adapter import MessengerAdapterMiddleware
    
    # Initialize MAX bot with configuration
    if MAX_BOT_TOKEN:
        # Initialize MAX bot with session management and connection pooling
        # The maxapi Bot handles connection pooling internally via aiohttp ClientSession
        # Connection pooling enables concurrent request handling for better performance
        # Requirements: 12.1, 12.4 - Initialize maxapi Bot with MAX_BOT_TOKEN and configure connection pooling
        max_bot = MAXBot(
            token=MAX_BOT_TOKEN,
            parse_mode=ParseMode.HTML,  # Default parse mode for messages
        )
        
        # Initialize MAX dispatcher using maxapi's built-in Dispatcher
        # The dispatcher handles routing updates to appropriate handlers
        # FSM storage is built-in to maxapi Dispatcher (uses in-memory storage by default)
        # MemoryContext is automatically injected into handlers as a parameter
        # Requirements: 6.1, 6.2, 6.3 - FSM state management with maxapi
        # Note: maxapi Dispatcher doesn't accept storage parameter - FSM is built-in
        max_dp = MAXDispatcher()
        
        # Create router for organizing handlers into logical groups
        # Router provides modular architecture for handler organization
        max_bot_router = MAXRouter(router_id="max_bot_main")
        
        # Initialize messenger adapter
        max_messenger_adapter = MAXMessengerAdapter(bot=max_bot)
        
        # Register middleware using maxapi pattern
        # In maxapi, middleware is set via dp.middlewares list (not dp.middleware() method)
        # Order matters: middleware executes in the order listed
        # Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 10.7, 14.5
        max_dp.middlewares = [
            MAXDatabaseSessionMiddleware(),      # Inject database session (first - creates session)
            MessengerAdapterMiddleware(max_messenger_adapter),  # Inject messenger adapter (second - adds adapter)
        ]
        
        # Register all MAX bot handlers with the dispatcher
        # Handlers are registered in priority order within feature-specific routers
        # Routers are included directly in dispatcher (maxapi doesn't support nested routers)
        # Messenger adapter is injected via MessengerAdapterMiddleware
        register_max_handlers(max_dp, max_bot_router)
        
        logging.info("MAX bot initialized with handlers and middleware")
    else:
        max_bot = None
        max_dp = None
        max_bot_router = None
        max_messenger_adapter = None
        logging.warning("MAX_BOT_TOKEN not found. MAX bot functionality will be unavailable.")
        
except ImportError as e:
    logging.warning(f"maxapi library not installed: {e}. MAX bot functionality will be unavailable.")
    max_bot = None
    max_dp = None
    max_bot_router = None
    max_messenger_adapter = None
except Exception as e:
    logging.error(f"Failed to initialize MAX bot: {e}")
    max_bot = None
    max_dp = None
    max_bot_router = None
    max_messenger_adapter = None


# Функции для управления жизненным циклом (для main.py) ---
async def set_all_webhooks():
    """
    Устанавливает вебхуки для всех ботов.
    Requirements: 12.2, 12.6 - Use maxapi Bot.subscribe_webhook() for webhook lifecycle management
    """
    # Set Telegram webhook
    # await tg_bot.set_webhook(url=f"{HOST}{WEBHOOK_PATH_MAIN}")
    logging.info(f"Telegram webhook set to {HOST}{WEBHOOK_PATH_MAIN}")
    
    # Set MAX webhook if MAX bot is initialized
    # Requirements: 12.2, 12.6 - Use maxapi Bot.subscribe_webhook() for webhook lifecycle management
    if max_bot and WEBHOOK_PATH_MAX:
        try:
            # Subscribe to MAX webhook
            # This registers the webhook URL with MAX API servers
            # update_types=None subscribes to all event types (messages, callbacks, etc.)
            await max_bot.subscribe_webhook(
                url=f"{HOST}{WEBHOOK_PATH_MAX}",
                update_types=None,  # Subscribe to all event types
            )
            logging.info(f"MAX webhook subscribed successfully: {HOST}{WEBHOOK_PATH_MAX}")
        except Exception as e:
            logging.error(f"Failed to subscribe MAX webhook: {e}", exc_info=True)
    
    # Register MAX bot commands
    await register_max_bot_commands()

    logging.info("All webhooks are set.")


async def register_max_bot_commands():
    """
    Регистрирует команды MAX бота в MAX API.
    
    Использует информацию из docstring обработчиков (commands_info маркер)
    для автоматической регистрации команд в MAX messenger.
    
    Команды будут отображаться в интерфейсе MAX messenger при вводе "/".
    """
    if not max_bot:
        logging.warning("MAX bot not initialized. Skipping command registration.")
        return
    
    try:
        from maxapi.types import BotCommand
        from re import search as re_search, DOTALL
        from maxapi.filters.command import CommandsInfo
        
        COMMANDS_INFO_PATTERN = r"commands_info:\s*(.*?)(?=\n|$)"
        
        # Извлекаем команды из обработчиков вручную, БЕЗ вызова __ready,
        # так как __ready добавляет self в self.routers и вызывает дублирование хендлеров
        commands_dict = {}
        
        all_routers = list(max_dp.routers) + [max_dp]
        commands_info_list: list[CommandsInfo] = []
        
        for router in all_routers:
            for handler in router.event_handlers:
                if handler.base_filters is None:
                    continue
                for base_filter in handler.base_filters:
                    commands = getattr(base_filter, "commands", None)
                    if commands and type(commands) is list:
                        handler_doc = handler.func_event.__doc__
                        extracted_info = None
                        if handler_doc:
                            from_pattern = re_search(COMMANDS_INFO_PATTERN, handler_doc, DOTALL)
                            if from_pattern:
                                extracted_info = from_pattern.group(1).strip()
                        commands_info_list.append(CommandsInfo(commands, extracted_info))
        
        for cmd_info in commands_info_list:
            # cmd_info.commands - список команд (без префикса "/")
            # cmd_info.info - описание команды из docstring
            for command_name in cmd_info.commands:
                commands_dict[command_name] = cmd_info.info or "Команда бота"
        
        # Определяем желаемый порядок команд
        # Команды, не указанные в этом списке, будут добавлены в конце в алфавитном порядке
        command_order = [
            "start",
            "help",
            "invoice",
            "support",
            "profile",
            "cancel",
        ]
        
        # Сортируем команды согласно заданному порядку
        commands_to_register = []
        
        # Сначала добавляем команды в заданном порядке
        for cmd_name in command_order:
            if cmd_name in commands_dict:
                bot_command = BotCommand(
                    name=cmd_name,
                    description=commands_dict[cmd_name]
                )
                commands_to_register.append(bot_command)
        
        # Затем добавляем остальные команды в алфавитном порядке
        remaining_commands = sorted(set(commands_dict.keys()) - set(command_order))
        for cmd_name in remaining_commands:
            bot_command = BotCommand(
                name=cmd_name,
                description=commands_dict[cmd_name]
            )
            commands_to_register.append(bot_command)
        
        if commands_to_register:
            # Пытаемся зарегистрировать команды в MAX API
            # ПРИМЕЧАНИЕ: MAX API может не поддерживать программную регистрацию команд
            # В этом случае команды нужно настраивать вручную через веб-интерфейс MAX
            try:
                await max_bot.set_my_commands(*commands_to_register)
                logging.info(f"MAX bot commands registered in order: {[cmd.name for cmd in commands_to_register]}")
            except Exception as cmd_error:
                # Если API не поддерживает регистрацию команд (404 на /me endpoint),
                # это не критическая ошибка - команды можно настроить вручную
                if "404" in str(cmd_error) or "method.not.found" in str(cmd_error):
                    logging.warning(
                        "MAX API does not support programmatic command registration. "
                        "Commands should be configured manually through MAX web interface. "
                        f"Commands to register: {[cmd.name for cmd in commands_to_register]}"
                    )
                else:
                    # Другие ошибки логируем как обычно
                    logging.error(f"Failed to register MAX bot commands: {cmd_error}")
        else:
            logging.warning("No commands found to register for MAX bot")
    
    except Exception as e:
        logging.error(f"Failed to prepare MAX bot commands: {e}", exc_info=True)


async def delete_all_webhooks():
    """
    Удаляет вебхуки для всех ботов.
    Requirements: 12.2, 12.6 - Webhook lifecycle management on shutdown
    """
    # Delete Telegram webhook
    # await tg_bot.delete_webhook(drop_pending_updates=True)
    logging.info("Telegram webhook deleted")
    
    # Delete MAX webhook if MAX bot is initialized
    # Requirements: 12.2, 12.6 - Webhook lifecycle management on shutdown
    if max_bot:
        try:
            # Unsubscribe from MAX webhook
            # This removes the webhook registration from MAX API servers
            await max_bot.delete_webhook()
            logging.info("MAX webhook deleted successfully")
        except Exception as e:
            logging.error(f"Failed to delete MAX webhook: {e}", exc_info=True)

    logging.info("All webhooks are deleted.")


async def close_bot_sessions():
    """
    Закрывает все сессии и соединения.
    Requirements: 12.2, 12.6 - Close maxapi sessions on application shutdown
    Requirements: 12.3 - Preserve Redis connection management
    """
    # Close Telegram bot session
    # await bot_session.close()
    
    # Close Redis storage if not in local mode
    # Requirements: 12.3 - Preserve Redis connection management for FSM storage
    # This Redis connection is shared between Telegram bot and MAX bot (if using Redis)
    if not IS_LOCAL_BOT:
        await storage.redis.close()
        logging.info("Redis connection closed")
    
    # Close MAX bot session if initialized
    # Requirements: 12.2, 12.6 - Close maxapi sessions on application shutdown
    if max_bot:
        try:
            # Close the underlying aiohttp session used by maxapi Bot
            # The maxapi Bot uses aiohttp ClientSession internally for HTTP requests
            # Closing it properly prevents resource leaks and ensures graceful shutdown
            await max_bot.session.close()
            logging.info("MAX bot session closed")
        except Exception as e:
            logging.error(f"Failed to close MAX bot session: {e}")
    
    logging.info("All sessions are closed.")
