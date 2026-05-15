import json
from pathlib import Path
from typing import Any

from app.core.config import settings


class MetaAdService:
    """Catalog ad creation via the facebook-business SDK."""

    def __init__(
        self,
        token_map_path: str = "",
        site_data: dict[str, Any] | None = None,
        app_id: str = "",
        app_secret: str = "",
        access_token: str = "",
    ) -> None:
        self.token_map_path = token_map_path or settings.fb_token_map_path
        self.app_id = app_id or settings.meta_app_id
        self.app_secret = app_secret or settings.meta_app_secret
        self.access_token = access_token or settings.meta_access_token
        if site_data is not None:
            self.site_data = site_data
        elif self.access_token:
            self.site_data = {}
        else:
            self.site_data = self._load_site_data()

    def _load_site_data(self) -> dict[str, Any]:
        path = Path(self.token_map_path)
        if not path.exists():
            raise FileNotFoundError(f"token map not found: {self.token_map_path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _init_account(self, ad_account_id: str):
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adaccount import AdAccount

        site_info = self.site_data.get(ad_account_id)
        if not site_info and self.access_token:
            site_info = {
                "app_id": self.app_id or None,
                "app_secret": self.app_secret or None,
                "access_token": self.access_token,
            }
        if not site_info:
            raise KeyError(
                f"account not found in token map and META_ACCESS_TOKEN is not configured: {ad_account_id}"
            )

        FacebookAdsApi.init(
            app_id=site_info["app_id"],
            app_secret=site_info["app_secret"],
            access_token=site_info["access_token"],
        )
        return AdAccount(ad_account_id)

    def create_product_catalog(
        self, catalog_fid: str, product_catalog_name: str, product_group_ids: list[str]
    ) -> str:
        from facebook_business.exceptions import FacebookRequestError
        from facebook_business.adobjects.productcatalog import ProductCatalog
        from facebook_business.adobjects.productset import ProductSet

        catalog = ProductCatalog(fbid=catalog_fid)
        group_filters = [
            {"retailer_product_group_id": {"eq": product_id}} for product_id in product_group_ids
        ]
        try:
            product_set = catalog.create_product_set(
                fields=[ProductSet.Field.id, ProductSet.Field.name],
                params={"name": product_catalog_name, "filter": {"or": group_filters}},
            )
        except FacebookRequestError as exc:
            body = exc.body()
            error = body.get("error", {}) if isinstance(body, dict) else {}
            error_data = error.get("error_data", {})
            if not isinstance(error_data, dict):
                try:
                    error_data = json.loads(error_data)
                except (TypeError, ValueError):
                    error_data = {}
            existing_product_set_id = error_data.get("product_set_id")
            if exc.api_error_code() == 10803 and existing_product_set_id:
                return str(existing_product_set_id)
            raise
        return product_set[ProductSet.Field.id]

    def create_catalog_campaign(self, ad_account: Any, campaign_name: str) -> str:
        from facebook_business.adobjects.campaign import Campaign

        campaign = ad_account.create_campaign(
            fields=[],
            params={
                "name": campaign_name,
                "status": Campaign.Status.paused,
                "objective": Campaign.Objective.outcome_sales,
                "special_ad_categories": [Campaign.SpecialAdCategories.none],
                "is_adset_budget_sharing_enabled": False,
            },
        )
        return campaign["id"]

    def create_catalog_adset(
        self,
        ad_account: Any,
        campaign_id: str,
        pixel_id: str,
        adset_name: str,
        daily_budget_cents: int,
        countries: list[str],
        age_min: int | None,
        age_max: int | None,
        custom_audience_ids: list[str],
        interest_ids: list[str],
        publisher_platforms: list[str],
    ) -> str:
        from facebook_business.adobjects.adset import AdSet

        targeting: dict[str, Any] = {
            "geo_locations": {"countries": countries},
            "genders": [1, 2],
            "publisher_platforms": publisher_platforms,
            "targeting_automation": {"advantage_audience": 0},
        }
        if age_min is not None:
            targeting["age_min"] = age_min
        if age_max is not None:
            targeting["age_max"] = age_max
        if custom_audience_ids:
            targeting["custom_audiences"] = [
                {"id": audience_id} for audience_id in custom_audience_ids
            ]
        if interest_ids:
            targeting["flexible_spec"] = [
                {"interests": [{"id": interest_id} for interest_id in interest_ids]}
            ]
        params = {
            "campaign_id": campaign_id,
            "name": adset_name,
            "status": AdSet.Status.paused,
            "targeting": targeting,
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "OFFSITE_CONVERSIONS",
            "promoted_object": {"pixel_id": pixel_id, "custom_event_type": "PURCHASE"},
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            AdSet.Field.daily_budget: str(daily_budget_cents),
        }
        adset = ad_account.create_ad_set(params=params)
        return adset["id"]

    def create_catalog_ad(
        self,
        ad_account: Any,
        link: str,
        adset_id: str,
        product_set_id: str,
        instagram_user_id: str | None,
        page_id: str,
        ad_name: str,
        message: str,
        description: str,
    ) -> dict[str, str]:
        from facebook_business.adobjects.ad import Ad
        from facebook_business.adobjects.adcreative import AdCreative

        object_story_spec: dict[str, Any] = {
            "page_id": page_id,
            "template_data": {
                "link": link,
                "message": message,
                "description": description,
                "name": "{{product.name}}",
                "call_to_action": {"type": "SHOP_NOW"},
                "multi_share_end_card": False,
                "show_multiple_images": False,
            },
        }
        if instagram_user_id:
            object_story_spec["instagram_user_id"] = instagram_user_id

        creative = ad_account.create_ad_creative(
            params={
                "name": f"{ad_name}-创意",
                "object_story_spec": object_story_spec,
                "product_set_id": product_set_id,
                "recommender_settings": {"product_sales_channel": "ONLINE"},
                "object_type": "SHARE",
                AdCreative.Field.degrees_of_freedom_spec: {
                    "creative_features_spec": {
                        "adapt_to_placement": {
                            "enroll_status": "OPT_IN",
                            "customizations": {
                                "aspect_ratio_config": {
                                    "ar_4_5": {"adapt": {"enroll_status": "OPT_IN"}},
                                    "ar_9_16": {"adapt": {"enroll_status": "OPT_IN"}},
                                },
                                "showcase_card_display": "AUTO",
                                "image_crop_style": "AUTO",
                            },
                        },
                        "add_text_overlay": {"enroll_status": "OPT_IN"},
                        "advantage_plus_creative": {"enroll_status": "OPT_IN"},
                        "description_automation": {"enroll_status": "OPT_IN"},
                        "enhance_cta": {"enroll_status": "OPT_IN"},
                        "hide_price": {"enroll_status": "OPT_IN"},
                        "image_animation": {"enroll_status": "OPT_IN"},
                        "image_background_gen": {"enroll_status": "OPT_IN"},
                        "image_uncrop": {"enroll_status": "OPT_IN"},
                        "inline_comment": {"enroll_status": "OPT_IN"},
                        "media_type_automation": {"enroll_status": "OPT_IN"},
                        "product_metadata_automation": {"enroll_status": "OPT_IN"},
                        "standard_enhancements_catalog": {"enroll_status": "OPT_IN"},
                    }
                },
            },
        )
        creative_id = creative["id"]
        ad = ad_account.create_ad(
            params={
                Ad.Field.name: ad_name,
                Ad.Field.adset_id: adset_id,
                Ad.Field.creative: {"creative_id": creative_id},
                Ad.Field.status: Ad.Status.paused,
            }
        )
        return {"creative_id": creative_id, "ad_id": ad["id"]}

    def create_ads(self, payload: dict[str, Any]) -> dict[str, Any]:
        ad_account = self._init_account(payload["ad_account_id"])
        campaign_id = self.create_catalog_campaign(ad_account, payload["campaign_name"])
        adsets_result = []
        instagram_user_id = payload.get("instagram_user_id")
        publisher_platforms = ["facebook", "instagram"] if instagram_user_id else ["facebook"]
        for adset in payload["adsets"]:
            adset_id = self.create_catalog_adset(
                ad_account=ad_account,
                campaign_id=campaign_id,
                pixel_id=adset["pixel_id"],
                adset_name=adset["adset_name"],
                daily_budget_cents=adset["daily_budget_cents"],
                countries=adset["countries"],
                age_min=adset.get("age_min"),
                age_max=adset.get("age_max"),
                custom_audience_ids=adset.get("custom_audience_ids", []),
                interest_ids=adset.get("interest_ids", []),
                publisher_platforms=publisher_platforms,
            )

            ads_result = []
            for ad in adset["ads"]:
                product_set_id = self.create_product_catalog(
                    catalog_fid=payload["catalog_fid"],
                    product_catalog_name=ad["name"],
                    product_group_ids=ad["product_group_ids"],
                )
                ad_result = self.create_catalog_ad(
                    ad_account=ad_account,
                    link=payload["link"],
                    adset_id=adset_id,
                    product_set_id=product_set_id,
                    instagram_user_id=instagram_user_id,
                    page_id=payload["page_id"],
                    ad_name=ad["name"],
                    message=ad["message"],
                    description=ad.get("description", ""),
                )
                ads_result.append(
                    {
                        "name": ad["name"],
                        "product_set_id": product_set_id,
                        "creative_id": ad_result["creative_id"],
                        "ad_id": ad_result["ad_id"],
                        "description": ad.get("description", ""),
                        "product_group_ids": ad["product_group_ids"],
                    }
                )
            adsets_result.append(
                {
                    "adset_name": adset["adset_name"],
                    "adset_id": adset_id,
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
            "mode": "meta",
            "campaign_id": campaign_id,
            "adsets": adsets_result,
        }
