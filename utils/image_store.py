"""Helper for persisting base64-encoded images from ad payloads."""

import base64
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List


# Matches data URLs like "data:image/png;base64,iVBORw0..."
DATA_URL_PATTERN = re.compile(
    r"^data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$"
)


def persist_payload_images(
    payload: Dict[str, Any],
    image_dir: Path,
) -> List[Dict[str, Any]]:
    """Walk every ad in the payload and persist base64 images to disk.

    Ads with image_url (but no image_base64) are recorded as-is without
    downloading the URL.

    Returns a list of image records with keys: ad_name, source ("base64" or
    "url"), and path.
    """
    image_dir.mkdir(parents=True, exist_ok=True)
    records: List[Dict[str, Any]] = []

    for ad_set_index, ad_set in enumerate(payload.get("ad_sets", [])):
        for ad_index, ad in enumerate(ad_set.get("ads", [])):
            base64_value = ad.get("image_base64")
            if not base64_value:
                if ad.get("image_url"):
                    records.append(
                        {
                            "ad_name": ad.get("name"),
                            "source": "url",
                            "path": ad.get("image_url"),
                        }
                    )
                continue

            saved_path = _save_base64_image(
                base64_value,
                image_dir,
                ad_set_index,
                ad_index,
            )
            ad["image_file"] = str(saved_path)
            records.append(
                {
                    "ad_name": ad.get("name"),
                    "source": "base64",
                    "path": str(saved_path),
                }
            )

    return records


def _save_base64_image(
    base64_value: str,
    image_dir: Path,
    ad_set_index: int,
    ad_index: int,
) -> Path:
    """Decode a base64 string (or data URL) and write it to a file.

    The filename includes ad set index, ad index, and a content hash
    for uniqueness.
    """
    match = DATA_URL_PATTERN.match(base64_value)
    if match:
        mime_type = match.group("mime")
        encoded = match.group("data")
    else:
        mime_type = "image/png"
        encoded = base64_value

    extension = _extension_for_mime(mime_type)
    image_bytes = base64.b64decode(encoded)
    digest = hashlib.sha256(image_bytes).hexdigest()[:12]
    filename = f"adset_{ad_set_index + 1}_ad_{ad_index + 1}_{digest}{extension}"
    path = image_dir / filename
    path.write_bytes(image_bytes)
    return path


def _extension_for_mime(mime_type: str) -> str:
    """Map a MIME type string to a file extension (e.g. "image/jpeg" → ".jpg")."""
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get(mime_type.lower(), ".png")
