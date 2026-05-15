from typing import Any


def validate_ads_list(ads: Any, prefix: str) -> list[str]:
    errors: list[str] = []
    if ads is not None and not isinstance(ads, list):
        errors.append(f"{prefix} must be a list")
    if isinstance(ads, list):
        for index, ad in enumerate(ads, start=1):
            if not isinstance(ad, dict):
                errors.append(f"{prefix}[{index}] must be an object")
                continue
            if _is_blank_ad(ad):
                continue
            for field in ("name", "product_group_ids", "message"):
                if field not in ad or ad[field] in (None, "", []):
                    errors.append(f"{prefix}[{index}] missing field: {field}")
            if "product_group_ids" in ad and not isinstance(ad["product_group_ids"], list):
                errors.append(f"{prefix}[{index}].product_group_ids must be a list")
    return errors


def _is_blank_ad(ad: dict[str, Any]) -> bool:
    return (
        not str(ad.get("name", "")).strip()
        and not str(ad.get("message", "")).strip()
        and not str(ad.get("description", "")).strip()
        and not [
            str(product_id).strip()
            for product_id in ad.get("product_group_ids", [])
            if str(product_id).strip()
        ]
    )


def _is_blank_adset(adset: dict[str, Any]) -> bool:
    ads = adset.get("ads")
    non_blank_ads = []
    if isinstance(ads, list):
        non_blank_ads = [ad for ad in ads if isinstance(ad, dict) and not _is_blank_ad(ad)]
    return (
        not str(adset.get("adset_name", "")).strip()
        and not str(adset.get("pixel_id", "")).strip()
        and adset.get("daily_budget_cents") in (None, "", 0, "0")
        and not [str(country).strip() for country in adset.get("countries", []) if str(country).strip()]
        and adset.get("age_min") in (None, "", 0, "0")
        and adset.get("age_max") in (None, "", 0, "0")
        and not [str(audience_id).strip() for audience_id in adset.get("custom_audience_ids", []) if str(audience_id).strip()]
        and not [str(interest_id).strip() for interest_id in adset.get("interest_ids", []) if str(interest_id).strip()]
        and not non_blank_ads
    )


def validate_payload(payload: dict[str, Any]) -> list[str]:
    required_fields = [
        "ad_account_id",
        "link",
        "campaign_name",
        "page_id",
        "catalog_fid",
        "adsets",
    ]
    errors: list[str] = []
    for field in required_fields:
        if field not in payload or payload[field] in (None, "", []):
            errors.append(f"missing field: {field}")

    adsets = payload.get("adsets")
    if adsets is not None and not isinstance(adsets, list):
        errors.append("adsets must be a list")
    if isinstance(adsets, list):
        for index, adset in enumerate(adsets, start=1):
            if not isinstance(adset, dict):
                errors.append(f"adsets[{index}] must be an object")
                continue
            if _is_blank_adset(adset):
                continue
            for field in ("adset_name", "pixel_id", "daily_budget_cents", "countries", "ads"):
                if field not in adset or adset[field] in (None, "", []):
                    errors.append(f"adsets[{index}] missing field: {field}")

            if "daily_budget_cents" in adset:
                try:
                    budget = int(adset["daily_budget_cents"])
                    if budget <= 0:
                        errors.append(f"adsets[{index}].daily_budget_cents must be greater than 0")
                except (TypeError, ValueError):
                    errors.append(f"adsets[{index}].daily_budget_cents must be an integer")

            age_min: int | None = None
            age_max: int | None = None
            if adset.get("age_min") not in (None, ""):
                try:
                    age_min = int(adset["age_min"])
                    if age_min < 13:
                        errors.append(f"adsets[{index}].age_min must be >= 13")
                except (TypeError, ValueError):
                    errors.append(f"adsets[{index}].age_min must be an integer")

            if adset.get("age_max") not in (None, ""):
                try:
                    age_max = int(adset["age_max"])
                    if age_max < 13:
                        errors.append(f"adsets[{index}].age_max must be >= 13")
                except (TypeError, ValueError):
                    errors.append(f"adsets[{index}].age_max must be an integer")

            if age_min is not None and age_max is not None and age_min > age_max:
                errors.append(f"adsets[{index}].age_min must be <= age_max")

            countries = adset.get("countries")
            if countries is not None:
                if not isinstance(countries, list) or not all(isinstance(code, str) and code for code in countries):
                    errors.append(f"adsets[{index}].countries must be a list of non-empty strings")

            custom_audience_ids = adset.get("custom_audience_ids")
            if custom_audience_ids is not None:
                if not isinstance(custom_audience_ids, list) or not all(
                    isinstance(audience_id, str) and audience_id.strip() for audience_id in custom_audience_ids
                ):
                    errors.append(f"adsets[{index}].custom_audience_ids must be a list of non-empty strings")

            interest_ids = adset.get("interest_ids")
            if interest_ids is not None:
                if not isinstance(interest_ids, list) or not all(
                    isinstance(interest_id, str) and interest_id.strip() for interest_id in interest_ids
                ):
                    errors.append(f"adsets[{index}].interest_ids must be a list of non-empty strings")

            errors.extend(validate_ads_list(adset.get("ads"), f"adsets[{index}].ads"))

    link = payload.get("link")
    if link and not str(link).startswith(("http://", "https://")):
        errors.append("link must start with http:// or https://")

    return errors


def _normalize_id_value(value: Any) -> str:
    normalized = str(value).strip()
    while len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in ("'", '"'):
        normalized = normalized[1:-1].strip()
    return normalized


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["instagram_user_id"] = _normalize_id_value(payload.get("instagram_user_id", ""))
    normalized["adsets"] = []
    for adset in payload["adsets"]:
        if _is_blank_adset(adset):
            continue
        normalized_ads = [
            {
                "name": str(ad["name"]).strip(),
                "message": str(ad["message"]).strip(),
                "description": str(ad.get("description", "")).strip(),
                "product_group_ids": [
                    normalized_id
                    for product_id in ad["product_group_ids"]
                    if (normalized_id := _normalize_id_value(product_id))
                ],
            }
            for ad in adset["ads"]
            if not _is_blank_ad(ad)
        ]
        normalized["adsets"].append(
            {
                "adset_name": str(adset["adset_name"]).strip(),
                "pixel_id": str(adset["pixel_id"]).strip(),
                "daily_budget_cents": int(adset["daily_budget_cents"]),
                "countries": [str(country).upper() for country in adset["countries"]],
                "age_min": int(adset["age_min"]) if adset.get("age_min") not in (None, "") else None,
                "age_max": int(adset["age_max"]) if adset.get("age_max") not in (None, "") else None,
                "custom_audience_ids": [
                    normalized_id
                    for audience_id in adset.get("custom_audience_ids", [])
                    if (normalized_id := _normalize_id_value(audience_id))
                ],
                "interest_ids": [
                    normalized_id
                    for interest_id in adset.get("interest_ids", [])
                    if (normalized_id := _normalize_id_value(interest_id))
                ],
                "ads": normalized_ads,
            }
        )
    return normalized


def make_mock_result(payload: dict[str, Any]) -> dict[str, Any]:
    campaign_id = "mock_campaign_10001"
    adsets_result = []
    ad_index = 1

    for adset_index, adset in enumerate(payload["adsets"], start=1):
        ads_result = []
        for ad in adset["ads"]:
            ads_result.append(
                {
                    "name": ad["name"],
                    "product_set_id": f"mock_product_set_{ad_index:04d}",
                    "creative_id": f"mock_creative_{ad_index:04d}",
                    "ad_id": f"mock_ad_{ad_index:04d}",
                    "description": ad.get("description", ""),
                    "product_group_ids": ad["product_group_ids"],
                }
            )
            ad_index += 1
        adsets_result.append(
            {
                "adset_name": adset["adset_name"],
                "adset_id": f"mock_adset_{adset_index:04d}",
                "countries": adset["countries"],
                "daily_budget_cents": adset["daily_budget_cents"],
                "age_min": adset.get("age_min"),
                "age_max": adset.get("age_max"),
                "custom_audience_ids": adset.get("custom_audience_ids", []),
                "interest_ids": adset.get("interest_ids", []),
                "ads": ads_result,
            }
        )

    return {
        "mode": "mock",
        "message": "Meta SDK or token map not available, returned mock creation result.",
        "campaign_id": campaign_id,
        "adsets": adsets_result,
    }
