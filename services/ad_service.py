"""High-level service that orchestrates Facebook ad creation via Meta API."""

from pathlib import Path
from typing import Any, Dict, List

from app.core.config import settings
from app.schemas.ad import FacebookAdCreatePayload
from app.services.meta.api import MetaMarketingApiService
from app.services.meta.constants import MetaAdCreationError
from app.utils.helpers import to_dict
from app.utils.image_store import persist_payload_images


class FacebookAdService:
    """Orchestrates material ad creation via the Meta Marketing API."""

    def __init__(self) -> None:
        self.api_service = MetaMarketingApiService()

    async def get_audience_options(
        self,
        ad_account_id: str = "",
        query: str = "",
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Search for audience targeting options via the Meta Marketing API.

        Args:
            ad_account_id: Meta ad account ID.
            query: Search keywords for interests and saved audiences.
            limit: Max number of results.
        """
        return await self.api_service.get_audience_options(
            ad_account_id=ad_account_id,
            query=query,
            limit=limit,
        )

    async def create_ads(
        self,
        task_id: str,
        payload: FacebookAdCreatePayload,
    ) -> Dict[str, Any]:
        """
        Run the full ad creation flow for a task.

        Persists base64 images to disk, then calls the Meta API.
        On partial failure, the MetaAdCreationError carries the intermediate
        result so the caller can persist it.
        """
        normalized_payload = to_dict(payload)
        image_dir = Path(settings.storage_dir) / "images" / task_id
        image_records = persist_payload_images(normalized_payload, image_dir)

        if settings.fb_ad_dry_run:
            return self._build_dry_run_result(
                task_id, normalized_payload, image_records
            )

        try:
            automation_result = await self.api_service.create_ads(
                task_id, normalized_payload
            )
        except MetaAdCreationError as exc:
            exc.partial_result["images"] = image_records
            exc.partial_result["dry_run"] = False
            raise

        automation_result["images"] = image_records
        automation_result["dry_run"] = False
        return automation_result

    def _build_dry_run_result(
        self,
        task_id: str,
        payload: Dict[str, Any],
        image_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build a preview result without creating real ads."""
        ad_count = sum(len(ad_set["ads"]) for ad_set in payload["ad_sets"])
        return {
            "task_id": task_id,
            "dry_run": True,
            "campaign_name": payload["campaign"]["name"],
            "ad_set_count": len(payload["ad_sets"]),
            "ad_count": ad_count,
            "images": image_records,
            "next_step": (
                "Set FB_AD_DRY_RUN=false to create real ads via the Meta API."
            ),
            "preview": payload,
        }
