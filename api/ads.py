"""Facebook ad API endpoints."""

from fastapi import APIRouter, BackgroundTasks

from app.core.response import success
from app.schemas.ad import FacebookAdCreatePayload
from app.schemas.task import TaskSubmitRequest
from app.services.ad_service import FacebookAdService
from app.services.task_service import TaskService

router = APIRouter(prefix="/fb/ad", tags=["facebook-ad"])

task_service = TaskService()
facebook_ad_service = FacebookAdService()


@router.post("/create")
def create_facebook_ad(
    payload: FacebookAdCreatePayload,
    background_tasks: BackgroundTasks,
):
    """
    Submit an async task to create Facebook ads from the given payload.
    Returns immediately with a task_id; ad creation runs in the background.
    """
    request = TaskSubmitRequest(task_type="fb_ad_create", params=payload)
    task_id = task_service.submit_task(request, background_tasks)
    return success({"task_id": task_id}, "任务提交成功")


@router.get("/audience/options")
async def get_audience_options(
    ad_account_id: str = "",
    query: str = "",
    limit: int = 20,
):
    """
    Search for audience targeting options (interests + saved audiences).

    Args:
        ad_account_id: Meta ad account ID. Uses config default if empty.
        query: Search keywords for interest/audience matching.
        limit: Maximum number of results to return.
    """
    result = await facebook_ad_service.get_audience_options(
        ad_account_id=ad_account_id,
        query=query,
        limit=limit,
    )
    return success(result)
