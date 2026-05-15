"""Unified API response model and factory functions."""

from typing import Any, Optional

from pydantic import BaseModel


class ApiResponse(BaseModel):
    """
    Standard API response envelope.

    Fields:
        code: HTTP-style status code (200 for success).
        message: Human-readable status description.
        data: Optional response payload.
    """

    code: int = 200
    message: str = "success"
    data: Optional[Any] = None


def success(data: Any = None, message: str = "success") -> ApiResponse:
    """Build a success response (code=200)."""
    return ApiResponse(code=200, message=message, data=data)


def failure(message: str, code: int = 500, data: Any = None) -> ApiResponse:
    """Build an error response with the given status code and message."""
    return ApiResponse(code=code, message=message, data=data)
