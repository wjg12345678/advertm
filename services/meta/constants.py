"""Static constants shared by Meta Marketing API services."""

from typing import Any, Dict

# Maps Chinese interest names to their English equivalents for Meta API search.
INTEREST_NAME_MAP = {
    "室内设计": "Interior design",
    "Interior design": "Interior design",
    "家居装饰": "Home decor",
    "Home decor": "Home decor",
    "Home improvement": "Home improvement",
    "家居改善": "Home improvement",
    "Light fixture": "Light fixture",
    "灯具": "Light fixture",
    "房间": "Room",
    "卧室": "Bedroom",
    "客厅": "Living room",
    "餐厅": "Dining room",
    "厨房": "Kitchen",
    "浴室": "Bathroom",
    "室内建筑": "Interior architecture",
    "现代主义建筑": "Modern architecture",
    "建筑风格": "Architectural style",
    "家具": "Furniture",
    "卧室家具": "Bedroom furniture",
    "现代风家具": "Modern furniture",
    "沙发": "Sofa",
    "装饰艺术": "Decorative arts",
    "视觉艺术": "Visual arts",
}

# Default interest keywords used when no audience query is provided.
DEFAULT_INTEREST_KEYWORDS = [
    "Light fixture",
    "Interior design",
    "Home decor",
    "Home improvement",
]

# Maps Chinese country names to ISO 3166-1 alpha-2 country codes.
COUNTRY_CODE_MAP = {
    "美国": "US",
    "法国": "FR",
    "德国": "DE",
    "香港": "HK",
    "中国香港": "HK",
    "英国": "GB",
    "加拿大": "CA",
    "澳大利亚": "AU",
}


class MetaAdCreationError(RuntimeError):
    """Raised when the Meta API ad creation flow fails part-way through.

    Fields:
        partial_result: The partial result data captured before the failure,
            including campaign/adset/creative IDs that were already created.
    """

    def __init__(self, message: str, partial_result: Dict[str, Any]) -> None:
        super().__init__(message)
        self.partial_result = partial_result


