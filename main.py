import logging
from contextlib import asynccontextmanager

import uvicorn
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from fastapi import BackgroundTasks, FastAPI, Request, Response, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import api_router
from bots.tg_bot.handlers import tg_bot_router as main_bot_router
from constants import (
    ALLOWED_HOSTS,
    COUNT_WORKERS,
    IS_LOCAL_BOT,
    LOG_LEVEL,
    MAIN_BOT_TOKEN,
    PROJECT_HOST,
    PROJECT_PORT,
    WEBHOOK_PATH_MAIN,
)
from loaders import bot_session, close_bot_sessions, delete_all_webhooks, main_dp, set_all_webhooks

ROOT_PATH = "" if IS_LOCAL_BOT else "/i-tat"


from aiogram.types import ErrorEvent


@main_dp.errors()
async def error_handler(event: ErrorEvent):
    logging.error(f"Update {event.update.update_id} caused error: {event.exception}", exc_info=True)
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Выполняется при старте и остановке приложения.
    """
    logging.info("Application startup...")
    await on_init()
    await set_all_webhooks()
    yield
    logging.info("Application shutdown...")
    await delete_all_webhooks()
    await close_bot_sessions()


# Инициализируем FastAPI с lifespan и root_path
app = FastAPI(lifespan=lifespan, root_path=ROOT_PATH)

templates = Jinja2Templates(directory="api/templates")


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401 and "/admin" in request.url.path:
        return templates.TemplateResponse("login.html", {"request": request}, status_code=401)

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# Включаем роутер.
app.include_router(api_router, prefix="/bot/api")

# Монтируем директорию static. Путь всегда одинаковый.
app.mount("/static", StaticFiles(directory="api/static"), name="static")

# Монтируем директорию media.
app.mount("/media", StaticFiles(directory="media"), name="media")

templates = Jinja2Templates(directory="api/templates")


@app.get("/upload", response_class=HTMLResponse)
async def read_upload_form(request: Request):
    """Отдает страницу upload.html"""
    return templates.TemplateResponse("upload.html", {"request": request})


app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(GZipMiddleware, minimum_size=1000)


async def on_init():
    # await run_webhook(BOT_TOKEN)
    main_dp.include_router(main_bot_router)
    # access_dp.include_router(access_bot_router)
    # main_dp.include_router(channel_router)


async def main_feed_update(token, update):
    # print(f">>> Получено обновление: {update}")  # Дебаг
    async with Bot(token, bot_session, DefaultBotProperties(parse_mode="markdown")).context(auto_close=False) as bot_:
        await main_dp.feed_raw_update(bot_, update)


@app.post(WEBHOOK_PATH_MAIN, include_in_schema=False)
async def main_telegram_update(
    request: Request,  # <-- Принимаем Request
    background_tasks: BackgroundTasks,
) -> Response:
    # Получаем JSON из тела запроса
    update_data = await request.json()

    # Передаем данные в фоновую задачу
    background_tasks.add_task(main_feed_update, MAIN_BOT_TOKEN, update_data)

    return Response(status_code=status.HTTP_202_ACCEPTED)


if __name__ == "__main__":
    logger = logging.getLogger()  # Корневой логгер
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()  # Вывод в консоль
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.handlers = [handler]

    uvicorn.run(
        "main:app",
        host=PROJECT_HOST,
        port=PROJECT_PORT,
        log_level=LOG_LEVEL,
        reload=False,
        access_log=True,
        proxy_headers=True,
        workers=COUNT_WORKERS,
        timeout_keep_alive=30,
        forwarded_allow_ips="*",
    )
