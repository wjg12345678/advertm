"""
Meta Marketing API client for programmatic ad creation.

Wraps the Meta Graph API to create campaigns, ad sets, ads, and creatives.
Supports reuse/deduplication of existing Meta entities by name.
"""

import re
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.dao.task_dao import TaskDao
from app.services.meta.constants import MetaAdCreationError
from app.services.meta.targeting import TargetingBuilder
from app.utils.helpers import json_dumps


class MetaMarketingApiService:
    """
    Client for the Meta Marketing (Graph) API.

    Fields:
        base_url: Graph API base URL including version (e.g. https://graph.facebook.com/v21.0).
        access_token: Meta developer access token for API calls.
        task_dao: Task DAO for cross-task entity lookup (reuse/dedup).
        targeting: TargetingBuilder instance for audience search and targeting specs.
    """

    def __init__(self) -> None:
        self.base_url = f"https://graph.facebook.com/{settings.meta_api_version}"
        self.access_token = settings.meta_access_token
        self.task_dao = TaskDao()
        self.targeting = TargetingBuilder(self.base_url, self.access_token)

    # ------------------------------------------------------------------
    # main entry points
    # ------------------------------------------------------------------

    async def create_ads(
        self,
        task_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Create a campaign with one ad set and one ad via the Meta API.

        The flow:
        1. Find or create the campaign (by name).
        2. Find or create the ad set (by name, under the campaign).
        3. Check for duplicate ad (by name, under the ad set).
        4. Create a creative and then the ad.

        On partial failure, raises MetaAdCreationError with the
        intermediate result so the caller can persist it.
        """
        self._ensure_configured()

        campaign = payload["campaign"]
        ad_set = payload["ad_sets"][0]
        ad = ad_set["ads"][0]
        account_id = self._resolve_ad_account_id(campaign)
        page_id = self._resolve_page_id(campaign)
        partial_result: Dict[str, Any] = {
            "task_id": task_id,
            "driver": "meta_marketing_api",
            "status": "partial_failed",
            "publish_clicked": False,
            "ad_account_id": account_id,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                campaign_record = await self._get_or_create_campaign(
                    client, account_id, campaign["name"]
                )
                partial_result.update(
                    {
                        "campaign_id": campaign_record["id"],
                        "campaign_name": campaign["name"],
                        "reused_campaign": campaign_record["reused"],
                    }
                )

                adset_record = await self._get_or_create_adset(
                    client, account_id, campaign_record["id"], ad_set
                )
                partial_result.update(
                    {
                        "adset_id": adset_record["id"],
                        "adset_name": ad_set["name"],
                        "reused_adset": adset_record["reused"],
                    }
                )

                existing_ad = self.task_dao.find_meta_ad_ref(
                    account_id, adset_record["id"], ad["name"]
                )
                if existing_ad is None:
                    existing_ad = await self._find_existing_ad_in_adset(
                        client, account_id, adset_record["id"], ad["name"]
                    )
                if existing_ad:
                    return {
                        "task_id": task_id,
                        "driver": "meta_marketing_api",
                        "status": "duplicate_prevented",
                        "publish_clicked": False,
                        "meta_status": existing_ad.get("effective_status"),
                        "ad_account_id": account_id,
                        "campaign_id": campaign_record["id"],
                        "adset_id": adset_record["id"],
                        "ad_id": existing_ad["id"],
                        "reused_campaign": campaign_record["reused"],
                        "reused_adset": adset_record["reused"],
                        "duplicate_reason": (
                            "An ad with the same name already exists under "
                            "the same campaign and ad set in Meta."
                        ),
                    }

                creative_id = await self._create_creative(
                    client, account_id, page_id, ad
                )
                partial_result["creative_id"] = creative_id

                ad_id = await self._create_ad(
                    client, account_id, adset_record["id"], creative_id, ad["name"]
                )
                partial_result.update(
                    {"ad_id": ad_id, "ad_name": ad["name"], "meta_status": "PAUSED"}
                )
        except Exception as exc:
            raise MetaAdCreationError(str(exc), partial_result) from exc

        return {
            "task_id": task_id,
            "driver": "meta_marketing_api",
            "status": "draft_created",
            "publish_clicked": False,
            "meta_status": "PAUSED",
            "ad_account_id": account_id,
            "campaign_id": campaign_record["id"],
            "adset_id": adset_record["id"],
            "creative_id": creative_id,
            "ad_id": ad_id,
            "reused_campaign": campaign_record["reused"],
            "reused_adset": adset_record["reused"],
        }

    async def get_audience_options(
        self,
        ad_account_id: str = "",
        query: str = "",
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Search for audience targeting options via the Meta API.

        Delegates to TargetingBuilder for the actual API calls.
        """
        self._ensure_configured()
        return await self.targeting.get_audience_options(
            ad_account_id=ad_account_id or settings.meta_ad_account_id,
            query=query,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # campaign
    # ------------------------------------------------------------------

    async def _get_or_create_campaign(
        self, client: httpx.AsyncClient, account_id: str, name: str
    ) -> Dict[str, Any]:
        """Return an existing campaign by name, or create a new one.

        Checks local task history first, then queries the Meta API.
        """
        local_existing = self.task_dao.find_meta_campaign_ref(account_id, name)
        if local_existing is not None:
            return {**local_existing, "reused": True, "source": "local_task"}

        existing = await self._find_campaign_by_name(client, account_id, name)
        if existing is not None:
            return {**existing, "reused": True, "source": "meta_api"}

        campaign_id = await self._create_campaign(client, account_id, name)
        return {"id": campaign_id, "name": name, "reused": False, "source": "created"}

    async def _find_campaign_by_name(
        self, client: httpx.AsyncClient, account_id: str, name: str
    ) -> Optional[Dict[str, Any]]:
        """Query the Meta API for a campaign with an exact name match."""
        response = await client.get(
            f"{self.base_url}/act_{account_id}/campaigns",
            params={
                "fields": "id,name,status,effective_status",
                "filtering": json_dumps(
                    [{"field": "name", "operator": "EQUAL", "value": name}]
                ),
                "limit": 10,
                "access_token": self.access_token,
            },
        )
        payload = response.json()
        if response.status_code >= 400 or "error" in payload:
            error = payload.get("error", payload)
            raise RuntimeError(f"Meta API campaign lookup failed: {error}")
        for item in payload.get("data", []):
            if item.get("name") == name:
                return item
        return None

    async def _create_campaign(
        self, client: httpx.AsyncClient, account_id: str, name: str
    ) -> str:
        """Create a new PAUSED campaign with OUTCOME_TRAFFIC objective.

        Returns the new campaign ID.
        """
        data = await self._post(
            client,
            f"/act_{account_id}/campaigns",
            {
                "name": name,
                "objective": "OUTCOME_TRAFFIC",
                "status": "PAUSED",
                "special_ad_categories": "[]",
                "buying_type": "AUCTION",
            },
        )
        return data["id"]

    # ------------------------------------------------------------------
    # adset
    # ------------------------------------------------------------------

    async def _get_or_create_adset(
        self,
        client: httpx.AsyncClient,
        account_id: str,
        campaign_id: str,
        ad_set: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return an existing ad set by name, or create a new one."""
        local_existing = self.task_dao.find_meta_adset_ref(
            account_id, campaign_id, ad_set["name"]
        )
        if local_existing is not None:
            return {**local_existing, "reused": True, "source": "local_task"}

        existing = await self._find_adset_by_name(
            client, account_id, campaign_id, ad_set["name"]
        )
        if existing is not None:
            return {**existing, "reused": True, "source": "meta_api"}

        adset_id = await self._create_adset(client, account_id, campaign_id, ad_set)
        return {
            "id": adset_id,
            "name": ad_set["name"],
            "reused": False,
            "source": "created",
        }

    async def _find_adset_by_name(
        self,
        client: httpx.AsyncClient,
        account_id: str,
        campaign_id: str,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """Query the Meta API for an ad set matching both name and campaign ID."""
        response = await client.get(
            f"{self.base_url}/act_{account_id}/adsets",
            params={
                "fields": "id,name,status,effective_status,campaign_id",
                "filtering": json_dumps(
                    [
                        {"field": "name", "operator": "EQUAL", "value": name},
                        {"field": "campaign.id", "operator": "EQUAL", "value": campaign_id},
                    ]
                ),
                "limit": 10,
                "access_token": self.access_token,
            },
        )
        payload = response.json()
        if response.status_code >= 400 or "error" in payload:
            error = payload.get("error", payload)
            raise RuntimeError(f"Meta API ad set lookup failed: {error}")
        for item in payload.get("data", []):
            if item.get("name") == name and item.get("campaign_id") == campaign_id:
                return item
        return None

    async def _create_adset(
        self,
        client: httpx.AsyncClient,
        account_id: str,
        campaign_id: str,
        ad_set: Dict[str, Any],
    ) -> str:
        """Create a new PAUSED ad set under the given campaign.

        Budget is scaled by meta_default_currency_multiplier.
        Returns the new ad set ID.
        """
        targeting = await self.targeting.build_targeting(client, account_id, ad_set)
        budget = int(
            float(ad_set["budget"]) * settings.meta_default_currency_multiplier
        )
        data = await self._post(
            client,
            f"/act_{account_id}/adsets",
            {
                "name": ad_set["name"],
                "campaign_id": campaign_id,
                "daily_budget": str(budget),
                "billing_event": "IMPRESSIONS",
                "optimization_goal": "LINK_CLICKS",
                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                "destination_type": "WEBSITE",
                "targeting": json_dumps(targeting),
                "status": "PAUSED",
            },
        )
        return data["id"]

    # ------------------------------------------------------------------
    # ad
    # ------------------------------------------------------------------

    async def _find_existing_ad_in_adset(
        self,
        client: httpx.AsyncClient,
        account_id: str,
        adset_id: str,
        ad_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Search for an existing ad by name within a specific ad set via the Meta API."""
        response = await client.get(
            f"{self.base_url}/act_{account_id}/ads",
            params={
                "fields": "id,name,status,effective_status,adset_id",
                "filtering": json_dumps(
                    [
                        {"field": "name", "operator": "EQUAL", "value": ad_name},
                        {"field": "adset.id", "operator": "EQUAL", "value": adset_id},
                    ]
                ),
                "limit": 10,
                "access_token": self.access_token,
            },
        )
        payload = response.json()
        if response.status_code >= 400 or "error" in payload:
            error = payload.get("error", payload)
            raise RuntimeError(f"Meta API ad lookup failed: {error}")
        for item in payload.get("data", []):
            if item.get("name") == ad_name and item.get("adset_id") == adset_id:
                return item
        return None

    async def _create_creative(
        self,
        client: httpx.AsyncClient,
        account_id: str,
        page_id: str,
        ad: Dict[str, Any],
    ) -> str:
        """Create an ad creative with a link_data object_story_spec.

        Returns the new creative ID.
        """
        link = ad["link"]
        link_data = {
            "link": link,
            "message": ad["copy"],
            "name": ad["title"],
            "description": ad.get("description") or "",
            "call_to_action": {"type": "LEARN_MORE", "value": {"link": link}},
        }
        object_story_spec = {"page_id": page_id, "link_data": link_data}
        data = await self._post(
            client,
            f"/act_{account_id}/adcreatives",
            {
                "name": f"{ad['name']} Creative",
                "object_story_spec": json_dumps(object_story_spec),
            },
        )
        return data["id"]

    async def _create_ad(
        self,
        client: httpx.AsyncClient,
        account_id: str,
        adset_id: str,
        creative_id: str,
        name: str,
    ) -> str:
        """Create a new PAUSED ad linking the creative to the ad set.

        Returns the new ad ID.
        """
        data = await self._post(
            client,
            f"/act_{account_id}/ads",
            {
                "name": name,
                "adset_id": adset_id,
                "creative": json_dumps({"creative_id": creative_id}),
                "status": "PAUSED",
            },
        )
        return data["id"]

    # ------------------------------------------------------------------
    # http helpers
    # ------------------------------------------------------------------

    async def _post(
        self,
        client: httpx.AsyncClient,
        path: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """POST to the Meta Graph API and return the JSON response.

        Automatically attaches access_token. Raises RuntimeError on error
        responses.
        """
        response = await client.post(
            f"{self.base_url}{path}",
            data={**data, "access_token": self.access_token},
        )
        payload = response.json()
        if response.status_code >= 400 or "error" in payload:
            error = payload.get("error", payload)
            raise RuntimeError(f"Meta API error on {path}: {error}")
        return payload

    # ------------------------------------------------------------------
    # config helpers
    # ------------------------------------------------------------------

    def _ensure_configured(self) -> None:
        """Raise if required Meta API credentials are missing from config."""
        missing = []
        if not settings.meta_access_token:
            missing.append("META_ACCESS_TOKEN")
        if not settings.meta_ad_account_id:
            missing.append("META_AD_ACCOUNT_ID")
        if missing:
            raise RuntimeError(
                "Meta Marketing API missing config: " + ", ".join(missing)
            )

    def _resolve_ad_account_id(self, campaign: Dict[str, Any]) -> str:
        """Resolve the ad account ID from config or campaign payload.

        Extracts numeric id (6+ digits) from strings like 'act_123456789'.
        """
        configured = self._digits(settings.meta_ad_account_id)
        if configured:
            return configured
        form_value = campaign.get("ad_account") or ""
        form_id = self._digits(form_value)
        if form_id:
            return form_id
        raise RuntimeError("ad account id is required")

    def _resolve_page_id(self, campaign: Dict[str, Any]) -> str:
        """Resolve the Facebook page ID from config or campaign payload."""
        configured = self._digits(settings.meta_default_page_id)
        if configured:
            return configured
        form_value = campaign.get("page_id") or ""
        form_id = self._digits(form_value)
        if form_id:
            return form_id
        raise RuntimeError("page id is required")

    @staticmethod
    def _digits(value: str) -> str:
        """Extract the first 6+ digit numeric id from a value string.

        Returns empty string if no match is found.
        """
        match = re.search(r"\d{6,}", value or "")
        return match.group(0) if match else ""
