"""Health-check endpoints for service monitoring."""

from fastapi import APIRouter

from app.core.config import settings
from app.core.response import success

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/new_bi_api/health")
def health_check():
    """Return basic service metadata and the current dry-run status."""
    return success(
        {
            "service": settings.app_name,
            "dry_run": settings.fb_ad_dry_run,
        }
    )
