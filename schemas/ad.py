"""Pydantic schemas for Facebook ad creation requests."""

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CampaignPayload(BaseModel):
    """
    Campaign-level parameters for ad creation.

    Fields:
        name: Campaign name displayed in Meta Ads Manager.
        site: Target website domain or identifier.
        ad_account: Meta ad account ID (numeric string or act_XXX format).
        date: Campaign schedule date string.
        page_id: Facebook page ID used for ad creatives.
    """

    name: str = Field(..., min_length=1)
    site: str = Field(..., min_length=1)
    ad_account: str = Field(..., min_length=1)
    date: str = Field(..., min_length=1)
    page_id: str = Field(..., min_length=1)


class AdPayload(BaseModel):
    """
    Individual ad creative within an ad set.

    Fields:
        name: Ad name shown in Meta Ads Manager.
        link: Destination URL the ad clicks through to.
        ad_copy: Primary text / body copy of the ad (API alias: "copy").
        title: Headline text of the ad.
        description: Optional description text below the headline.
        image_url: Public URL of the ad image (mutually exclusive with image_base64).
        image_base64: Base64-encoded image data (mutually exclusive with image_url).
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1)
    link: str = Field(..., min_length=1)
    ad_copy: str = Field(..., alias="copy", min_length=1)
    title: str = Field(..., min_length=1)
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    image_base64: Optional[str] = None


class AdSetPayload(BaseModel):
    """
    Ad set grouping one or more ads under shared targeting and budget.

    Fields:
        name: Ad set name displayed in Meta Ads Manager.
        pixel_id: Meta Pixel ID for conversion tracking.
        budget: Daily budget amount in the configured currency unit.
        country: Target country name or ISO code.
        audience: Targeting audience specification (JSON string or structured dict).
        schedule: Ad set schedule description.
        ads: List of ads belonging to this ad set (at least one required).
    """

    name: str = Field(..., min_length=1)
    pixel_id: str = Field(..., min_length=1)
    budget: float = Field(..., gt=0)
    country: str = Field(..., min_length=1)
    audience: Optional[Any] = ""
    schedule: str = Field(..., min_length=1)
    ads: List[AdPayload] = Field(..., min_length=1)


class FacebookAdCreatePayload(BaseModel):
    """
    Top-level request payload for creating Facebook ads.

    Fields:
        campaign: Campaign configuration.
        ad_sets: List of ad sets (at least one required), each containing ads.
    """

    campaign: CampaignPayload
    ad_sets: List[AdSetPayload] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Catalog ad schemas (DPA / product catalog ads)
# ---------------------------------------------------------------------------


class CatalogAdPayload(BaseModel):
    """Ad creative within a catalog ad set."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., examples=["Fabric Ambient Wall Lamps"])
    product_group_ids: list[str] = Field(
        ..., examples=[["1594231", "1594856", "1595142"]]
    )
    message: str = Field(
        ..., examples=["Transform your home with soft, calming illumination."]
    )
    description: str = Field(
        "", examples=["Layered ambient lighting for bedrooms, lounges, and reading corners."]
    )


class CatalogAdSetPayload(BaseModel):
    """Ad set grouping catalog ads under shared targeting and budget."""

    model_config = ConfigDict(extra="ignore")

    adset_name: str = Field(..., examples=["0415-US-25-室内设计"])
    pixel_id: str = Field(..., examples=["1258150169543224"])
    daily_budget_cents: int = Field(..., gt=0, examples=[100])
    countries: list[str] = Field(..., examples=[["US"]])
    ads: list[CatalogAdPayload] = Field(..., min_length=1)
    age_min: int | None = Field(None, ge=13, examples=[25])
    age_max: int | None = Field(None, ge=13, examples=[45])
    custom_audience_ids: list[str] = Field(default_factory=list)
    interest_ids: list[str] = Field(default_factory=list, examples=[["6003139266461", "6003349442621"]])


class CatalogAdCreatePayload(BaseModel):
    """Top-level request payload for creating catalog ads."""

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "ad_account_id": "act_1356925565754293",
                "instagram_user_id": "",
                "link": "https://www.ezerliving.com/",
                "campaign_name": "260415-TC2603-DPA",
                "page_id": "106727735072213",
                "catalog_fid": "980108417921945",
                "adsets": [
                    {
                        "adset_name": "0415-US-25-室内设计",
                        "pixel_id": "1258150169543224",
                        "daily_budget_cents": 100,
                        "countries": ["US"],
                        "age_min": 25,
                        "age_max": 45,
                        "custom_audience_ids": [],
                        "interest_ids": ["6003139266461", "6003349442621"],
                        "ads": [
                            {
                                "name": "Fabric Ambient Wall Lamps",
                                "product_group_ids": ["1594231", "1594856", "1595142"],
                                "message": "Transform your home with soft, calming illumination.",
                                "description": "Layered ambient lighting for bedrooms, lounges, and reading corners.",
                            }
                        ],
                    }
                ],
            }
        },
    )

    ad_account_id: str = Field(..., examples=["act_1356925565754293"])
    link: str = Field(..., examples=["https://www.ezerliving.com/"])
    campaign_name: str = Field(..., examples=["260415-TC2603-DPA"])
    page_id: str = Field(..., examples=["106727735072213"])
    catalog_fid: str = Field(..., examples=["980108417921945"])
    adsets: list[CatalogAdSetPayload] = Field(..., min_length=1)
    instagram_user_id: str = Field("", description="留空时只投 Facebook")
    mock_mode: bool = Field(False, description="true 时不调用 Meta API，返回 mock 结果")
