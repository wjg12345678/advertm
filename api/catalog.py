"""Catalog ad (DPA) API endpoints."""

from fastapi import APIRouter, BackgroundTasks

from app.core.response import success, failure
from app.schemas.ad import CatalogAdCreatePayload
from app.schemas.task import TaskSubmitRequest
from app.services.catalog.payload import normalize_payload, validate_payload
from app.services.task_service import TaskService

router = APIRouter(prefix="/fb/catalog", tags=["catalog-ad"])

task_service = TaskService()


@router.post("/validate")
def validate_catalog_ad(payload: CatalogAdCreatePayload):
    """Validate and normalize a catalog ad payload without creating anything."""
    payload_data = payload.model_dump()
    errors = validate_payload(payload_data)
    if errors:
        return failure("参数校验失败", 400, errors)
    normalized = normalize_payload(payload_data)
    return success({"normalized": normalized}, "校验通过")


@router.post("/create")
def create_catalog_ad(
    payload: CatalogAdCreatePayload,
    background_tasks: BackgroundTasks,
):
    """Submit an async task to create catalog ads. Returns task_id immediately."""
    request = TaskSubmitRequest(task_type="fb_catalog_ad_create", params=payload)
    task_id = task_service.submit_task(request, background_tasks)
    return success({"task_id": task_id}, "任务提交成功")


@router.get("/config")
def catalog_config():
    """Return available ad accounts and auth status for catalog ads."""
    from app.core.config import settings
    from pathlib import Path
    import json

    token_map_path = settings.fb_token_map_path
    site_data = None
    site_data_available = False
    if token_map_path:
        path = Path(token_map_path)
        if path.exists():
            try:
                site_data = json.loads(path.read_text(encoding="utf-8"))
                site_data_available = True
            except json.JSONDecodeError:
                pass

    available_accounts = sorted(site_data.keys()) if site_data_available and site_data else []
    return success({
        "meta_sdk_available": _detect_sdk(),
        "env_auth_available": bool(settings.meta_access_token),
        "token_map_path": token_map_path,
        "available_accounts": available_accounts,
    })


def _detect_sdk() -> bool:
    try:
        import facebook_business  # noqa: F401
        return True
    except ImportError:
        return False
