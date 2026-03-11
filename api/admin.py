import os
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "api", "templates"))

# --- Dependencies ---


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
