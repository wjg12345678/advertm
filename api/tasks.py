"""Async task management API endpoints."""

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.response import success
from app.schemas.task import TaskSubmitRequest
from app.services.task_service import TaskService

# Router registered under /new_bi_api/task
router = APIRouter(prefix="/new_bi_api/task", tags=["task"])

# Module-level service instance
task_service = TaskService()


@router.post("/submit")
def submit_task(
    request: TaskSubmitRequest,
    background_tasks: BackgroundTasks,
):
    """
    Submit a new async task.
    Currently only "fb_ad_create" is supported. Returns the assigned task_id
    immediately; the actual work executes via BackgroundTasks.
    """
    if request.task_type != "fb_ad_create":
        raise HTTPException(
            status_code=400,
            detail=f"unsupported task_type: {request.task_type}",
        )

    task_id = task_service.submit_task(request, background_tasks)
    return success({"task_id": task_id}, "任务提交成功")


@router.get("/{task_id}")
def get_task(task_id: str):
    """
    Query task status and result by task_id.
    Returns 404 if the task does not exist.
    """
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return success(task)
