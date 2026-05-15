"""Pydantic schemas for the task management API."""

from typing import Any

from pydantic import BaseModel


class TaskSubmitRequest(BaseModel):
    """
    Request body for submitting an async task.

    Fields:
        task_type: Type discriminator for the task (e.g. "fb_ad_create").
        params: Task-specific parameters (schema depends on task_type).
    """

    task_type: str
    params: Any
