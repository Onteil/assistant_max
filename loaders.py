import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiogram.fsm.strategy import FSMStrategy
from redis.asyncio.client import Redis

from constants import AIOGRAM_REDIS_DB_NUMBER, HOST, IS_LOCAL_BOT, MAIN_BOT_TOKEN, REDIS, WEBHOOK_PATH_MAIN
from filters.chat_filter import ChatTypeFilter
from middlewares.album_midleware import AlbumMiddleware
from middlewares.bot_reconstruction import BotInReconstruction
from middlewares.clear_state_middleware import StateClearerMiddleware
from middlewares.database import DatabaseSessionMiddleware
from middlewares.error_handler import ErrorHandler
from middlewares.trottling import ThrottlingMiddleware
from middlewares.user_data import UserDataMiddleware

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


# Функции для управления жизненным циклом (для main.py) ---
async def set_all_webhooks():
    """Устанавливает вебхуки для всех ботов."""
    await tg_bot.set_webhook(url=f"{HOST}{WEBHOOK_PATH_MAIN}")

    logging.info("All webhooks are set.")


async def delete_all_webhooks():
    """Удаляет вебхуки для всех ботов."""
    await tg_bot.delete_webhook(drop_pending_updates=True)

    logging.info("All webhooks are deleted.")


async def close_bot_sessions():
    """Закрывает все сессии и соединения."""
    await bot_session.close()
    if not IS_LOCAL_BOT:
        await storage.redis.close()
    logging.info("All sessions are closed.")
