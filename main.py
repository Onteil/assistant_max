import logging
from contextlib import asynccontextmanager

import uvicorn
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from fastapi import BackgroundTasks, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import api_router
from constants import (
    ALLOWED_HOSTS,
    BOT_MODE,
    COUNT_WORKERS,
    ENABLE_MAX_BOT,
    ENABLE_TG_BOT,
    IS_LOCAL_BOT,
    LOG_LEVEL,
    TG_BOT_TOKEN,
    PROJECT_HOST,
    PROJECT_PORT,
    WEBHOOK_PATH_MAIN,
    WEBHOOK_PATH_MAX,
    engine,
)
from loaders import (
    bot_session,
    close_bot_sessions,
    delete_all_webhooks,
    main_dp,
    max_bot,
    max_dp,
    set_all_webhooks,
)
from api.sqladmin_panel import setup_admin

ROOT_PATH = "" if IS_LOCAL_BOT else ""


from aiogram.types import ErrorEvent


if main_dp:
    @main_dp.errors()
    async def error_handler(event: ErrorEvent):
        logging.error(f"Update {event.update.update_id} caused error: {event.exception}", exc_info=True)
        return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Application startup...")
    from services.ssh_tunnel import start_tunnel, stop_tunnel
    await start_tunnel()
    await on_init()
    await set_all_webhooks()
    yield
    logging.info("Application shutdown...")
    await delete_all_webhooks()
    await close_bot_sessions()
    await stop_tunnel()


# Инициализируем FastAPI с lifespan и root_path
app = FastAPI(lifespan=lifespan, root_path=ROOT_PATH)

templates = Jinja2Templates(directory="api/templates")

# Setup SQLAdmin
admin = setup_admin(app, engine)


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


# Add CORS middleware to allow admin panel to make requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(GZipMiddleware, minimum_size=1000)


async def on_init():
    """
    Initialize all bot components in correct order.
    
    Initialization sequence:
    1. Include routers in dispatchers
    2. Register handlers
    3. Set up middleware (already done in loaders.py)
    4. Configure FSM storage (already done in loaders.py)
    5. Initialize default system settings
    
    This function is called during FastAPI lifespan startup.
    
    Requirements: 2.6, 2.7 - Initialize components and configure background task processing
    Requirements: 1.4 - Initialize default settings on application startup
    """
    if ENABLE_TG_BOT and main_dp:
        from bots.tg_bot.handlers import tg_bot_router as main_bot_router
        main_dp.include_router(main_bot_router)
        logging.info("Telegram bot router included")
    else:
        logging.info("Telegram bot router skipped: BOT_MODE=%s", BOT_MODE)
    
    # MAX bot initialization is already complete in loaders.py:
    # - MAX bot instance created
    # - Dispatcher initialized with FSM storage
    # - Middleware registered
    # - Handlers registered via register_max_handlers()
    # - Router included in dispatcher
    
    # Initialize default system settings
    from constants import AsyncSessionLocal
    from services.settings_service import initialize_default_settings
    
    try:
        async with AsyncSessionLocal() as session:
            await initialize_default_settings(session)
        logging.info("Default system settings initialized")
    except Exception as e:
        logging.error(f"Failed to initialize default settings: {e}", exc_info=True)
    
    logging.info("All bot components initialized successfully")


async def main_feed_update(token, update):
    if not ENABLE_TG_BOT or not main_dp or not bot_session or not token:
        logging.warning("Telegram update skipped: Telegram bot is not initialized")
        return
    # print(f">>> Получено обновление: {update}")  # Дебаг
    async with Bot(token, bot_session, DefaultBotProperties(parse_mode="HTML")).context(auto_close=False) as bot_:
        await main_dp.feed_raw_update(bot_, update)


@app.post(WEBHOOK_PATH_MAIN, include_in_schema=False)
async def main_telegram_update(
    request: Request,  # <-- Принимаем Request
    background_tasks: BackgroundTasks,
) -> Response:
    if not ENABLE_TG_BOT or not main_dp or not TG_BOT_TOKEN:
        logging.error("Telegram bot not initialized")
        return Response(
            content="Telegram bot not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Получаем JSON из тела запроса
    update_data = await request.json()

    # Передаем данные в фоновую задачу
    background_tasks.add_task(main_feed_update, TG_BOT_TOKEN, update_data)

    return Response(status_code=status.HTTP_202_ACCEPTED)


async def max_feed_update(update_data: dict):
    """
    Process MAX webhook update using maxapi Dispatcher.
    
    This function is executed as a FastAPI background task to enable
    non-blocking webhook processing. The webhook endpoint returns immediately
    while updates are processed asynchronously.
    
    Processing flow:
    1. Parse raw webhook data using maxapi process_update_webhook
    2. Handle the event using MAX dispatcher
    3. Dispatcher routes to appropriate handlers via middleware chain
    
    Args:
        update_data: Raw update data from MAX webhook
    
    Requirements: 2.6 - Background task processing for webhook handling
    Requirements: 2.4, 2.5 - MAX update parsing and routing
    """
    if not ENABLE_MAX_BOT or not max_bot or not max_dp:
        logging.error("MAX bot not initialized, cannot process update")
        return
    
    try:
        # Use maxapi's process_update_webhook to parse the update
        from maxapi.methods.types.getted_updates import process_update_webhook
        
        # Process the webhook update
        event_object = await process_update_webhook(
            event_json=update_data,
            bot=max_bot
        )
        
        logging.info(f"Processing MAX update: type={event_object.update_type}, event={type(event_object).__name__}")
        
        # Log callback payload if it's a message_callback event
        if event_object.update_type == "message_callback" and hasattr(event_object, 'callback'):
            callback = event_object.callback
            logging.info(f"Callback payload: {callback.payload!r}")
        
        # Log message details if it's a message_created event
        if hasattr(event_object, 'message'):
            msg = event_object.message
            has_contact = hasattr(msg.body, 'contact') if msg.body else False
            contact_value = getattr(msg.body, 'contact', None) if msg.body else None
            has_attachments = hasattr(msg.body, 'attachments') and msg.body.attachments
            attachments_info = []
            if has_attachments:
                for att in msg.body.attachments:
                    att_type = att.type if hasattr(att, 'type') else type(att).__name__
                    att_dict = att.__dict__ if hasattr(att, '__dict__') else str(att)
                    attachments_info.append(f"{att_type}: {att_dict}")
            
            logging.info(
                f"Message details: chat_id={msg.recipient.chat_id}, "
                f"user_id={msg.sender.user_id}, "
                f"text={msg.body.text if msg.body else 'None'}, "
                f"has_contact={has_contact}, "
                f"contact={contact_value}, "
                f"has_attachments={has_attachments}, "
                f"attachments={attachments_info if has_attachments else 'None'}"
            )
        
        # Handle the event using the dispatcher
        # This triggers the middleware chain and routes to appropriate handlers
        await max_dp.handle(event_object)
        
        logging.debug(f"MAX update processed: {event_object.update_type}")
    except Exception as e:
        logging.error(f"Error processing MAX update: {e}", exc_info=True)


@app.post(WEBHOOK_PATH_MAX, include_in_schema=False)
async def max_webhook_update(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """
    MAX messenger webhook endpoint.
    
    Receives incoming updates from MAX messenger and processes them
    using maxapi Dispatcher in background tasks for non-blocking operation.
    
    Processing flow:
    1. Validate MAX bot is initialized
    2. Parse JSON from request body
    3. Add update processing to background tasks (non-blocking)
    4. Return HTTP 200 OK immediately
    
    Background task processing enables:
    - Fast webhook response times (< 100ms)
    - Concurrent update handling
    - Prevents webhook timeout issues
    
    Returns:
        HTTP 200 OK for valid requests
        HTTP 503 if MAX bot not configured
        HTTP 500 for internal errors
    
    Requirements: 2.1, 2.2, 2.3 - MAX webhook endpoint with validation
    Requirements: 2.6, 2.7 - Background task processing configuration
    """
    if not ENABLE_MAX_BOT or not max_bot or not max_dp:
        logging.error("MAX bot not initialized")
        return Response(
            content="MAX bot not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    try:
        # Get JSON from request body
        update_data = await request.json()
        
        # Process update in background task (non-blocking)
        # This allows the webhook to return immediately
        background_tasks.add_task(max_feed_update, update_data)
        
        return Response(status_code=status.HTTP_200_OK)
    except Exception as e:
        logging.error(f"Error handling MAX webhook: {e}", exc_info=True)
        return Response(
            content="Internal server error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


if __name__ == "__main__":
    logger = logging.getLogger()  # Корневой логгер
    logger.setLevel(logging.DEBUG)
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
        workers=1,
        timeout_keep_alive=30,
        forwarded_allow_ips="*",
    )
