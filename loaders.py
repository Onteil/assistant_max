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
    MAIN_BOT_TOKEN,
    MAX_BOT_TOKEN,
    REDIS,
    WEBHOOK_PATH_MAIN,
    WEBHOOK_PATH_MAX,
)
from bots.tg_bot.filters.chat_filter import ChatTypeFilter
from bots.tg_bot.middlewares.album_midleware import AlbumMiddleware
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

tg_bot = Bot(MAIN_BOT_TOKEN, session=bot_session, default=DefaultBotProperties(parse_mode="Markdown"))

main_dp = Dispatcher(storage=storage, fsm_strategy=FSMStrategy.USER_IN_CHAT)

# Регистрация обработчиков
tg_bot_router = Router(name="tgbot")

tg_bot_router.message.filter(ChatTypeFilter(chat_type=["private"]))
tg_bot_router.callback_query.filter(ChatTypeFilter(chat_type=["private"]))


for middleware in [
    DatabaseSessionMiddleware(),
    ThrottlingMiddleware(),
    BotInReconstruction(),
    UserDataMiddleware(),
    ErrorHandler(),
]:
    main_dp.message.middleware(middleware)
    main_dp.callback_query.middleware(middleware)


main_dp.message.outer_middleware(StateClearerMiddleware())
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
    from maxapi.client import DefaultConnectionProperties
    from bots.max_bot.messenger_adapter import MAXMessengerAdapter
    from bots.max_bot.handlers import register_max_handlers
    from bots.max_bot.middlewares import (
        DatabaseSessionMiddleware,
        ThrottlingMiddleware,
        BotInReconstructionMiddleware,
        UserDataMiddleware,
        ErrorHandlerMiddleware,
        StateClearerMiddleware,
        AlbumMiddleware,
        MessengerAdapterMiddleware,
    )
    
    # Initialize MAX bot with configuration
    if MAX_BOT_TOKEN:
        # Configure connection properties for session management
        # Requirements: 12.1, 12.4 - Initialize maxapi Bot with MAX_BOT_TOKEN and configure connection pooling
        connection_props = DefaultConnectionProperties(
            proxy=HTTP_PROXY if HTTP_PROXY else None,  # Use HTTP proxy if configured
            trust_env=True,  # Read proxy settings from environment variables
        )
        
        # Initialize MAX bot with session management and connection pooling
        # The maxapi Bot handles connection pooling internally via aiohttp ClientSession
        # Connection pooling enables concurrent request handling for better performance
        max_bot = MAXBot(
            token=MAX_BOT_TOKEN,
            parse_mode=ParseMode.HTML,  # Default parse mode for messages
            notify=True,  # Enable notifications by default
            disable_link_preview=False,  # Show link previews
            auto_requests=True,  # Auto-populate chat/user objects via API
            default_connection=connection_props,  # Connection properties with proxy support
            after_input_media_delay=2.0,  # Delay after file uploads (seconds) to prevent rate limiting
            auto_check_subscriptions=True,  # Warn if webhooks active during polling
        )
        
        # Initialize FSM storage (MemoryContext for development, can be switched to Redis for production)
        # Requirements: 12.3 - Preserve Redis connection management for FSM storage
        # Use Redis storage in production (non-local mode) for persistence and scalability
        # Use MemoryContext in development (local mode) for simplicity
        if not IS_LOCAL_BOT and redis:
            # Use Redis for FSM storage in production
            # This shares the same Redis connection pool as the Telegram bot
            # Requirements: 12.3 - Maintain existing Redis connection pool for FSM storage
            max_storage = MemoryContext()  # Note: maxapi uses MemoryContext, not RedisStorage
            # TODO: If maxapi adds Redis storage support in the future, switch to:
            # max_storage = RedisContext(redis=redis)
            logging.info("MAX bot FSM storage: MemoryContext (Redis support pending in maxapi)")
        else:
            # Use in-memory storage for development
            max_storage = MemoryContext()
            logging.info("MAX bot FSM storage: MemoryContext (local development mode)")
        
        # Initialize MAX dispatcher using maxapi's built-in Dispatcher
        # The dispatcher handles routing updates to appropriate handlers
        # Connect FSM storage to dispatcher for state management
        # Requirements: 6.1, 6.2, 6.3 - FSM state management with maxapi
        max_dp = MAXDispatcher(storage=max_storage)
        
        # Create router for organizing handlers into logical groups
        # Router provides modular architecture for handler organization
        max_bot_router = MAXRouter(router_id="max_bot_main")
        
        # Initialize messenger adapter
        max_messenger_adapter = MAXMessengerAdapter(bot=max_bot)
        
        # Register middleware in correct order (order matters for execution)
        # Middleware is applied globally to all handlers via dp.middleware()
        # Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 10.7, 14.5
        for middleware in [
            MessengerAdapterMiddleware(max_messenger_adapter),  # Inject messenger adapter (Requirement 14.5)
            DatabaseSessionMiddleware(),      # Inject database session
            ThrottlingMiddleware(),           # Rate limiting by chat_id
            BotInReconstructionMiddleware(),  # Block updates during maintenance
            UserDataMiddleware(),             # Load user data from database
            ErrorHandlerMiddleware(),         # Global error handler - catches exceptions from all handlers (Requirement 10.7)
        ]:
            max_dp.middleware(middleware)
        
        # State clearer middleware (applied to message_created events only)
        # This middleware clears FSM state on /start command
        max_dp.middleware(StateClearerMiddleware())
        
        # Album middleware (applied to message_created events only)
        # This middleware groups multiple media attachments into albums
        max_dp.middleware(AlbumMiddleware())
        
        # Register all MAX bot handlers with the router
        # Handlers are registered in priority order within the router
        # Messenger adapter is injected via MessengerAdapterMiddleware
        register_max_handlers(max_dp, max_bot_router)
        
        # Include router in dispatcher
        # This makes all router handlers available to the dispatcher
        max_dp.include_router(max_bot_router)
        
        logging.info("MAX bot initialized successfully: Dispatcher, Router, Middleware, and Handlers registered")
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
    await tg_bot.set_webhook(url=f"{HOST}{WEBHOOK_PATH_MAIN}")
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

    logging.info("All webhooks are set.")


async def delete_all_webhooks():
    """
    Удаляет вебхуки для всех ботов.
    Requirements: 12.2, 12.6 - Webhook lifecycle management on shutdown
    """
    # Delete Telegram webhook
    await tg_bot.delete_webhook(drop_pending_updates=True)
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
    await bot_session.close()
    
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
