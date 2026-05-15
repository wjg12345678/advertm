"""Async task lifecycle management.

Handles task submission, deduplication via payload hashing, background
execution, and status transitions.
"""

import asyncio
import hashlib
import json
import traceback
from uuid import uuid4

from fastapi import BackgroundTasks

from app.dao.task_dao import TaskDao
from app.schemas.ad import FacebookAdCreatePayload
from app.schemas.task import TaskSubmitRequest
from app.services.ad_service import FacebookAdService
from app.services.catalog.creation import create_ads as create_catalog_ads
from app.services.meta.constants import MetaAdCreationError
from app.utils.helpers import to_dict


class TaskService:
    """Manages the full lifecycle of async tasks.

    Fields:
        task_dao: Data access object for task persistence.
        facebook_ad_service: Ad creation orchestrator invoked by background jobs.
    """

    def __init__(self) -> None:
        self.task_dao = TaskDao()
        self.facebook_ad_service = FacebookAdService()

    def submit_task(
        self,
        request: TaskSubmitRequest,
        background_tasks: BackgroundTasks,
    ) -> str:
        """Submit a new task or return an existing task_id for duplicate payload.

        Deduplication is based on a content hash of the normalized params.
        If a matching task is found in a reusable state, its task_id is
        returned immediately. Otherwise a new task is created and scheduled.
        """
        params = to_dict(request.params)
        payload_hash = self._payload_hash(params)
        reusable_task = self.task_dao.find_reusable_task(
            request.task_type, payload_hash
        )
        if reusable_task:
            return reusable_task["task_id"]

        task_id = uuid4().hex
        self.task_dao.create_task(task_id, request.task_type, params, payload_hash)
        background_tasks.add_task(self._run_task_sync, task_id)
        return task_id

    def get_task(self, task_id: str):
        """Return a task by ID, or None if not found."""
        return self.task_dao.get_task(task_id)

    def _run_task_sync(self, task_id: str) -> None:
        """Synchronous wrapper that drives the async _run_task via asyncio.run.

        Required because FastAPI BackgroundTasks expects synchronous callables.
        """
        asyncio.run(self._run_task(task_id))

    async def _run_task(self, task_id: str) -> None:
        """Execute the ad creation flow and persist the result.

        Transitions the task through processing → success, or processing → fail
        on error. MetaAdCreationError preserves partial results for debugging.
        """
        task = self.task_dao.get_task(task_id)
        if task is None:
            return

        self.task_dao.mark_processing(task_id)
        try:
            if task["task_type"] == "fb_catalog_ad_create":
                result = create_catalog_ads(task["params"])
            else:
                payload = FacebookAdCreatePayload(**task["params"])
                result = await self.facebook_ad_service.create_ads(task_id, payload)
            self.task_dao.mark_success(task_id, result)
        except MetaAdCreationError as exc:
            self.task_dao.mark_fail(
                task_id,
                str(exc),
                {
                    **exc.partial_result,
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=8),
                },
            )
        except Exception as exc:
            self.task_dao.mark_fail(
                task_id,
                str(exc),
                {
                    "traceback": traceback.format_exc(limit=8),
                    "message": str(exc),
                },
            )

    def _payload_hash(self, params) -> str:
        """Compute a deterministic SHA-256 hash for the given payload params.

        Base64 image fields are hashed individually rather than included raw
        so the hash remains compact and stable.
        """
        normalized = self._normalize_for_hash(params)
        raw = json.dumps(
            normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _normalize_for_hash(self, value):
        """Recursively normalize a value for consistent hashing.

        - dict keys are sorted.
        - Strings are stripped.
        - Base64 image fields are replaced by their SHA-256 hex digest.
        """
        if isinstance(value, dict):
            normalized = {}
            for key, item in value.items():
                if key in {"image_base64"} and item:
                    normalized[key] = hashlib.sha256(
                        str(item).encode("utf-8")
                    ).hexdigest()
                else:
                    normalized[key] = self._normalize_for_hash(item)
            return normalized
        if isinstance(value, list):
            return [self._normalize_for_hash(item) for item in value]
        if isinstance(value, str):
            return value.strip()
        return value
