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
    BOT_MODE,
    ENABLE_MAX_BOT,
    ENABLE_TG_BOT,
    HOST,
    HTTP_PROXY,
    IS_LOCAL_BOT,
    TG_BOT_TOKEN,
    MAX_BOT_TOKEN,
    REDIS,
    WEBHOOK_PATH_MAIN,
    WEBHOOK_PATH_MAX,
)

redis: Redis | None = None
storage: RedisStorage | MemoryStorage | None = None
bot_session: AiohttpSession | None = None
tg_bot: Bot | None = None
main_dp: Dispatcher | None = None

if ENABLE_TG_BOT:
    from bots.tg_bot.filters.chat_filter import ChatTypeFilter
    from bots.tg_bot.middlewares.album_midleware import AlbumMiddleware
    from bots.tg_bot.middlewares.bot_reconstruction import BotInReconstruction
    from bots.tg_bot.middlewares.database import DatabaseSessionMiddleware
    from bots.tg_bot.middlewares.debug_middleware import DebugSpyMiddleware
    from bots.tg_bot.middlewares.error_handler import ErrorHandler
    from bots.tg_bot.middlewares.trottling import ThrottlingMiddleware
    from bots.tg_bot.middlewares.user_data import UserDataMiddleware

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
        DebugSpyMiddleware(),
    ]:
        main_dp.message.middleware(middleware)
        main_dp.callback_query.middleware(middleware)


# main_dp.message.outer_middleware(StateClearerMiddleware())
    main_dp.message.middleware(AlbumMiddleware())
    logging.info("Telegram bot initialized")
else:
    logging.info("Telegram bot disabled: BOT_MODE=%s, TG_BOT_TOKEN is set=%s", BOT_MODE, bool(TG_BOT_TOKEN))


# ========== MAX Bot Setup ==========
# Initialize MAX bot and dispatcher
# Requirements: 10.1, 10.5 - Replace Aiogram Dispatcher with maxapi Dispatcher
# Requirements: 12.1, 12.4 - Session management and connection pooling
max_bot = None
max_dp = None
max_bot_router = None
max_messenger_adapter = None
max_invoice_followups = None
max_followup_redis = None

if ENABLE_MAX_BOT:
    try:
        from maxapi import Bot as MAXBot
        from maxapi import Dispatcher as MAXDispatcher
        from maxapi import Router as MAXRouter
        from maxapi.enums.parse_mode import ParseMode
        from bots.max_bot.handlers import register_max_handlers
        from bots.max_bot.messenger_adapter import MAXMessengerAdapter
        from bots.max_bot.middlewares.database import DatabaseSessionMiddleware as MAXDatabaseSessionMiddleware
        from bots.max_bot.middlewares.messenger_adapter import MessengerAdapterMiddleware
        from bots.max_bot.middlewares.conversation import ConversationMiddleware

        max_bot = MAXBot(
            token=MAX_BOT_TOKEN,
            parse_mode=ParseMode.HTML,
        )
        max_dp = MAXDispatcher()
        max_bot_router = MAXRouter(router_id="max_bot_main")
        max_messenger_adapter = MAXMessengerAdapter(bot=max_bot)
        from services.max_invoice_followup_service import InvoiceFollowups, RedisDraftStore
        from constants import AsyncSessionLocal, MAX_INVOICE_REMINDER_MINUTES, MAX_INVOICE_HANDOFF_MINUTES
        max_followup_redis = Redis.from_url(url=REDIS, db=AIOGRAM_REDIS_DB_NUMBER)
        max_invoice_followups = InvoiceFollowups(
            RedisDraftStore(max_followup_redis), max_messenger_adapter, AsyncSessionLocal,
            reminder_seconds=MAX_INVOICE_REMINDER_MINUTES * 60,
            handoff_seconds=MAX_INVOICE_HANDOFF_MINUTES * 60,
        )
        max_dp.middlewares = [
            MAXDatabaseSessionMiddleware(),
            MessengerAdapterMiddleware(max_messenger_adapter),
            ConversationMiddleware(),
        ]
        register_max_handlers(max_dp, max_bot_router)
        logging.info("MAX bot initialized with handlers and middleware")
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
else:
    logging.info("MAX bot disabled: BOT_MODE=%s, MAX_BOT_TOKEN is set=%s", BOT_MODE, bool(MAX_BOT_TOKEN))


# Функции для управления жизненным циклом (для main.py) ---
async def set_all_webhooks():
    """
    Устанавливает вебхуки для всех ботов.
    Requirements: 12.2, 12.6 - Use maxapi Bot.subscribe_webhook() for webhook lifecycle management
    """
    if tg_bot and WEBHOOK_PATH_MAIN:
        # await tg_bot.set_webhook(url=f"{HOST}{WEBHOOK_PATH_MAIN}")
        logging.info(f"Telegram webhook configured: {HOST}{WEBHOOK_PATH_MAIN}")
    
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
    if tg_bot:
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
    if bot_session:
        await bot_session.close()
        logging.info("Telegram bot session closed")
    
    # Close Redis storage if not in local mode
    # Requirements: 12.3 - Preserve Redis connection management for FSM storage
    # This Redis connection is shared between Telegram bot and MAX bot (if using Redis)
    if redis:
        await redis.close()
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
