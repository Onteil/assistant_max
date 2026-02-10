from fastapi import APIRouter

from .admin import router as admin_router
from .payments import router as clientbot_api_router

api_router = APIRouter()
api_router.include_router(clientbot_api_router, prefix="/test")
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
