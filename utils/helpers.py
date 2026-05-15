"""Shared utility functions used across the service layer."""

import json
from typing import Any


def to_dict(obj: Any) -> Any:
    """Convert a Pydantic model or dict-like object to a plain dict.

    Handles Pydantic v2 (model_dump) and v1 (dict) interfaces.
    Returns the object unchanged if it is already a plain dict.
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True)
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "dict"):
        return obj.dict(by_alias=True)
    return obj


def json_dumps(value: Any) -> str:
    """Serialize a Python value to a JSON string with ensure_ascii=False."""
    return json.dumps(value, ensure_ascii=False)
