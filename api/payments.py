import logging

from fastapi import APIRouter, BackgroundTasks, Request

router = APIRouter()
logger = logging.getLogger()


@router.post("/test/")
async def test(
    request: Request,
    background_tasks: BackgroundTasks,
):
    data = request.data
    pass
