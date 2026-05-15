"""Data access object for task persistence and Meta entity lookups."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.dao.database import get_connection


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class TaskDao:
    """CRUD operations for async tasks stored in SQLite.

    Also provides lookups across previously created Meta entities
    (campaigns, ad sets, ads) to support reuse and deduplication.
    """

    def create_task(
        self,
        task_id: str,
        task_type: str,
        params: Dict[str, Any],
        payload_hash: str,
    ) -> None:
        """Insert a new task row with status 'pending'."""
        now = utc_now()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, task_type, status, payload_hash, params,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task_type,
                    "pending",
                    payload_hash,
                    json.dumps(params, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.commit()

    def find_reusable_task(
        self,
        task_type: str,
        payload_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """Return the most recent task with the same type and payload hash.

        Only considers tasks in 'pending', 'processing', or 'success' status.
        Used to deduplicate identical ad creation requests.
        """
        if not payload_hash:
            return None

        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM tasks
                WHERE task_type = ?
                  AND payload_hash = ?
                  AND status IN ('pending', 'processing', 'success')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (task_type, payload_hash),
            ).fetchone()

        if row is None:
            return None

        task = dict(row)
        task["params"] = json.loads(task["params"])
        task["result"] = json.loads(task["result"]) if task["result"] else None
        return task

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return a single task by its ID, or None if not found."""
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()

        if row is None:
            return None

        task = dict(row)
        task["params"] = json.loads(task["params"])
        task["result"] = json.loads(task["result"]) if task["result"] else None
        return task

    def mark_processing(self, task_id: str) -> None:
        """Transition a task to 'processing' status."""
        self._update_status(task_id, "processing")

    def mark_success(self, task_id: str, result: Dict[str, Any]) -> None:
        """Mark a task as 'success' and store its result JSON."""
        now = utc_now()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, result = ?, error = NULL,
                    updated_at = ?, finished_at = ?
                WHERE task_id = ?
                """,
                (
                    "success",
                    json.dumps(result, ensure_ascii=False),
                    now,
                    now,
                    task_id,
                ),
            )
            connection.commit()

    def mark_fail(self, task_id: str, error: str, result: Dict[str, Any]) -> None:
        """Mark a task as 'fail', persisting the error message and partial result."""
        now = utc_now()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, result = ?, error = ?,
                    updated_at = ?, finished_at = ?
                WHERE task_id = ?
                """,
                (
                    "fail",
                    json.dumps(result, ensure_ascii=False),
                    error,
                    now,
                    now,
                    task_id,
                ),
            )
            connection.commit()

    # ------------------------------------------------------------------
    # Meta entity reference lookups (cross-task deduplication)
    # ------------------------------------------------------------------

    def find_meta_campaign_ref(
        self,
        account_id: str,
        campaign_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Search past tasks for a campaign with the same name under the same account.

        Returns the campaign id and name if found, None otherwise.
        """
        for task in self._iter_meta_ref_tasks():
            params = task["params"]
            result = task["result"] or {}
            campaign = params.get("campaign") or {}
            if campaign.get("name") != campaign_name:
                continue
            if result.get("ad_account_id") != account_id:
                continue
            campaign_id = result.get("campaign_id")
            if campaign_id:
                return {"id": campaign_id, "name": campaign_name}
        return None

    def find_meta_adset_ref(
        self,
        account_id: str,
        campaign_id: str,
        adset_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Search past tasks for an ad set with the same name under the same campaign.

        Returns the ad set id and name if found, None otherwise.
        """
        for task in self._iter_meta_ref_tasks():
            params = task["params"]
            result = task["result"] or {}
            ad_sets = params.get("ad_sets") or []
            if not ad_sets or ad_sets[0].get("name") != adset_name:
                continue
            if result.get("ad_account_id") != account_id:
                continue
            if result.get("campaign_id") != campaign_id:
                continue
            adset_id = result.get("adset_id")
            if adset_id:
                return {"id": adset_id, "name": adset_name}
        return None

    def find_meta_ad_ref(
        self,
        account_id: str,
        adset_id: str,
        ad_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Search past tasks for an ad with the same name under the same ad set.

        Returns ad id, name, and effective_status if found, None otherwise.
        """
        for task in self._iter_meta_ref_tasks():
            params = task["params"]
            result = task["result"] or {}
            ad_sets = params.get("ad_sets") or []
            ads = ad_sets[0].get("ads") if ad_sets else []
            if not ads or ads[0].get("name") != ad_name:
                continue
            if result.get("ad_account_id") != account_id:
                continue
            if result.get("adset_id") != adset_id:
                continue
            ad_id = result.get("ad_id")
            if ad_id:
                return {
                    "id": ad_id,
                    "name": ad_name,
                    "effective_status": result.get("meta_status"),
                }
        return None

    def _iter_meta_ref_tasks(self) -> list:
        """Return all completed fb_ad_create tasks with non-null results."""
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM tasks
                WHERE task_type = 'fb_ad_create'
                  AND status IN ('success', 'fail')
                  AND result IS NOT NULL
                ORDER BY created_at DESC
                """
            ).fetchall()

        tasks = []
        for row in rows:
            task = dict(row)
            task["params"] = json.loads(task["params"])
            task["result"] = json.loads(task["result"]) if task["result"] else None
            tasks.append(task)
        return tasks

    def _update_status(self, task_id: str, status: str) -> None:
        """Low-level helper to set the status and updated_at timestamp of a task."""
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (status, utc_now(), task_id),
            )
            connection.commit()
