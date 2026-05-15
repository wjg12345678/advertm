from typing import Any

from app.services.catalog.ad_service import MetaAdService
from app.services.catalog.payload import make_mock_result


def _detect_meta_sdk() -> bool:
    try:
        import facebook_business  # noqa: F401
        return True
    except ImportError:
        return False


def create_ads(payload: dict[str, Any]) -> dict[str, Any]:
    """Create catalog ads, falling back to mock if SDK or auth is unavailable."""
    meta_sdk_available = _detect_meta_sdk()
    use_mock = payload.get("mock_mode", False) or not meta_sdk_available

    if not use_mock:
        service = MetaAdService()
        try:
            return service.create_ads(payload)
        except (FileNotFoundError, KeyError):
            pass

    return make_mock_result(payload)
