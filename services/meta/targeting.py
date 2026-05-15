"""
Meta ad targeting and audience search logic.

Handles audience parsing, interest keyword search, saved audience lookup,
and targeting spec assembly for the Meta Marketing API.
"""

import json
import re
from typing import Any, Dict, Optional

import httpx

from app.services.meta.constants import (
    COUNTRY_CODE_MAP,
    DEFAULT_INTEREST_KEYWORDS,
    INTEREST_NAME_MAP,
)


class TargetingBuilder:
    """
    Builds and queries Meta ad targeting specifications.

    Fields:
        base_url: Base URL of the Meta Graph API (e.g. https://graph.facebook.com/v21.0).
        access_token: Meta developer access token for API authentication.
    """

    def __init__(self, base_url: str, access_token: str) -> None:
        self.base_url = base_url
        self.access_token = access_token

    # ------------------------------------------------------------------
    # public entry points
    # ------------------------------------------------------------------

    async def get_audience_options(
        self,
        ad_account_id: Optional[str] = None,
        query: str = "",
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Search for targeting options combining saved audiences and interests.

        Args:
            ad_account_id: Meta ad account ID.
            query: Search keywords; parsed into comma/Chinese-delimited tokens.
            limit: Maximum results to return across all categories.
        """
        account_id = self._digits(ad_account_id)
        if not account_id:
            raise RuntimeError("ad account id is required")

        keywords = self._parse_keywords(query)
        async with httpx.AsyncClient(timeout=30) as client:
            saved_audiences = await self._get_saved_audiences(
                client, account_id, query, limit
            )
            interests = await self._search_interests(client, keywords, limit)

        return {
            "ad_account_id": account_id,
            "query": query,
            "keywords": keywords,
            "options": saved_audiences + interests,
        }

    async def build_targeting(
        self,
        client: httpx.AsyncClient,
        account_id: str,
        ad_set: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Assemble a targeting spec dict for the given ad set.

        Handles three audience types:
        - audience_group: combines saved_audience + interests.
        - interest: single interest entry.
        - saved_audience: copies targeting from a saved audience.
        """
        targeting: Dict[str, Any] = {
            "geo_locations": {
                "countries": [self._country_code(ad_set.get("country"))],
            },
        }
        audience = self._parse_audience_value(ad_set.get("audience"))
        if not audience:
            return targeting

        if audience.get("type") == "audience_group":
            saved_audience = audience.get("saved_audience")
            if saved_audience:
                saved_targeting = await self._get_saved_audience_targeting(
                    client, account_id, saved_audience["id"]
                )
                saved_targeting["geo_locations"] = targeting["geo_locations"]
                targeting = saved_targeting

            interests = self._normalize_interests(audience.get("interests"))
            if interests:
                targeting["flexible_spec"] = [{"interests": interests}]
            return targeting

        if audience.get("type") == "interest":
            targeting["flexible_spec"] = [
                {
                    "interests": [
                        {"id": audience["id"], "name": audience.get("name", "")}
                    ]
                }
            ]
            return targeting

        if audience.get("type") == "saved_audience":
            saved_targeting = await self._get_saved_audience_targeting(
                client, account_id, audience["id"]
            )
            saved_targeting["geo_locations"] = targeting["geo_locations"]
            return saved_targeting

        return targeting

    # ------------------------------------------------------------------
    # audience parsing
    # ------------------------------------------------------------------

    def _parse_audience_value(self, value: Any) -> Optional[Dict[str, Any]]:
        """
        Parse an audience value from JSON string, list, or dict.

        Returns a normalized dict with keys: type, id, name (and optionally
        interests / saved_audience for audience_group). Returns None if the
        input is empty or unparseable.
        """
        if not value:
            return None
        if isinstance(value, list):
            return self._build_audience_group(value)
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(parsed, dict):
            return None
        if parsed.get("type") == "audience_group":
            return self._build_audience_group(parsed.get("items") or parsed)
        if parsed.get("type") not in {"interest", "saved_audience"}:
            return None
        if not parsed.get("id"):
            return None
        return parsed

    def _build_audience_group(self, value: Any) -> Optional[Dict[str, Any]]:
        """
        Normalize a list or dict of audience items into an audience_group dict.

        Deduplicates interests by id and picks the first saved_audience found.
        """
        items = value
        if isinstance(value, dict):
            items = []
            items.extend(value.get("items") or [])
            items.extend(value.get("interests") or [])
            saved_audience = value.get("saved_audience")
            if saved_audience:
                items.append(saved_audience)
        if not isinstance(items, list):
            return None

        interests = []
        saved_audience = None
        seen_ids: set = set()
        for item in items:
            if isinstance(item, str):
                try:
                    item = json.loads(item)
                except json.JSONDecodeError:
                    continue
            if not isinstance(item, dict) or not item.get("id"):
                continue
            if item.get("type") == "saved_audience" and saved_audience is None:
                saved_audience = item
                continue
            if item.get("type") != "interest":
                continue
            if item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            interests.append({"id": item["id"], "name": item.get("name", "")})

        if not interests and not saved_audience:
            return None
        return {
            "type": "audience_group",
            "interests": interests,
            "saved_audience": saved_audience,
        }

    def _normalize_interests(self, value: Any) -> list:
        """Extract a deduplicated list of {id, name} interest dicts from input."""
        if not isinstance(value, list):
            return []
        interests = []
        seen_ids: set = set()
        for item in value:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            if item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            interests.append({"id": item["id"], "name": item.get("name", "")})
        return interests

    def _parse_keywords(self, query: str) -> list:
        """
        Parse a user query string into a list of Meta-compatible interest keywords.

        Supports comma, Chinese comma, and "或" as delimiters. Falls back to
        DEFAULT_INTEREST_KEYWORDS when the query is empty.
        """
        normalized = (query or "").strip()
        if not normalized:
            return list(DEFAULT_INTEREST_KEYWORDS)

        normalized = normalized.replace("、", ",").replace("，", ",")
        normalized = re.sub(r"\s*或\s*", ",", normalized)
        raw_keywords = [item.strip() for item in normalized.split(",")]
        keywords = []
        seen_keywords: set = set()
        for keyword in raw_keywords:
            if not keyword:
                continue
            clean_keyword = re.sub(r"\s*[（(][^)）]*[)）]\s*$", "", keyword)
            clean_keyword = clean_keyword.strip()
            search_keyword = INTEREST_NAME_MAP.get(clean_keyword, clean_keyword)
            normalized_key = search_keyword.lower()
            if normalized_key in seen_keywords:
                continue
            seen_keywords.add(normalized_key)
            keywords.append(search_keyword)
        return keywords or list(DEFAULT_INTEREST_KEYWORDS)

    # ------------------------------------------------------------------
    # Meta API calls
    # ------------------------------------------------------------------

    async def _get_saved_audiences(
        self,
        client: httpx.AsyncClient,
        account_id: str,
        query: str,
        limit: int,
    ) -> list:
        """Query the Meta API for saved audiences matching the given query."""
        response = await client.get(
            f"{self.base_url}/act_{account_id}/saved_audiences",
            params={
                "fields": "id,name,targeting",
                "limit": min(max(limit, 1), 50),
                "access_token": self.access_token,
            },
        )
        payload = response.json()
        if response.status_code >= 400 or "error" in payload:
            error = payload.get("error", payload)
            raise RuntimeError(f"Meta API saved audience query failed: {error}")

        normalized_query = query.strip().lower()
        options = []
        for item in payload.get("data", []):
            name = item.get("name") or ""
            if normalized_query and normalized_query not in name.lower():
                continue
            options.append(
                {
                    "label": f"保存受众：{name}",
                    "value": json.dumps(
                        {
                            "type": "saved_audience",
                            "id": item.get("id"),
                            "name": name,
                        },
                        ensure_ascii=False,
                    ),
                    "type": "saved_audience",
                    "id": item.get("id"),
                    "name": name,
                }
            )
        return options

    async def _search_interests(
        self,
        client: httpx.AsyncClient,
        keywords: list,
        limit: int,
    ) -> list:
        """
        Search Meta for interests matching each keyword.

        Aggregates results across keywords, deduplicates by interest id,
        and stops early once the overall limit is reached.
        """
        options = []
        seen_ids: set = set()
        per_keyword_limit = min(max(limit, 1), 50)
        for keyword in keywords:
            response = await client.get(
                f"{self.base_url}/search",
                params={
                    "type": "adinterest",
                    "q": keyword,
                    "limit": per_keyword_limit,
                    "access_token": self.access_token,
                },
            )
            payload = response.json()
            if response.status_code >= 400 or "error" in payload:
                error = payload.get("error", payload)
                raise RuntimeError(f"Meta API interest query failed: {error}")

            for item in payload.get("data", []):
                name = item.get("name") or ""
                item_id = item.get("id")
                if not name or not item_id or item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                audience_size = item.get("audience_size")
                suffix = f"（{audience_size}）" if audience_size else ""
                options.append(
                    {
                        "label": f"兴趣：{name}{suffix}",
                        "value": json.dumps(
                            {"type": "interest", "id": item_id, "name": name},
                            ensure_ascii=False,
                        ),
                        "type": "interest",
                        "id": item_id,
                        "name": name,
                        "keyword": keyword,
                        "audience_size": audience_size,
                    }
                )
                if len(options) >= limit:
                    return options
        return options

    async def _get_saved_audience_targeting(
        self,
        client: httpx.AsyncClient,
        account_id: str,
        audience_id: str,
    ) -> Dict[str, Any]:
        """Fetch the raw targeting spec from a saved audience by ID."""
        response = await client.get(
            f"{self.base_url}/{audience_id}",
            params={
                "fields": "id,name,targeting",
                "access_token": self.access_token,
            },
        )
        payload = response.json()
        if response.status_code >= 400 or "error" in payload:
            error = payload.get("error", payload)
            raise RuntimeError(f"Meta API saved audience read failed: {error}")
        targeting = payload.get("targeting")
        if not isinstance(targeting, dict):
            raise RuntimeError(f"saved audience has no targeting: {audience_id}")
        return targeting

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _country_code(self, value: Optional[str]) -> str:
        """Map a country name or code to a 2-letter ISO code. Defaults to US."""
        if not value:
            return "US"
        value = value.strip()
        if len(value) == 2 and value.isalpha():
            return value.upper()
        return COUNTRY_CODE_MAP.get(value, "US")

    @staticmethod
    def _digits(value: Optional[str]) -> str:
        """Extract the first 6+ digit numeric id from a string like 'act_123456789'.

        Returns empty string if no match is found.
        """
        match = re.search(r"\d{6,}", value or "")
        return match.group(0) if match else ""
