"""API response type definitions for T3 API endpoints.

These TypedDict definitions provide type safety while keeping data
in its raw dict/list format for maximum flexibility.
"""
from __future__ import annotations

from typing import Any, Dict, List, NotRequired, TypedDict, TypeVar

T = TypeVar("T")


class AuthResponseData(TypedDict):
    """Authentication response data structure."""

    access_token: str
    refresh_token: NotRequired[str]
    expires_in: NotRequired[int]
    token_type: NotRequired[str]


class MetrcObject(TypedDict):
    """Generic Metrc object with common fields."""

    id: NotRequired[str]
    licenseNumber: NotRequired[str]


class MetrcCollectionResponse(TypedDict):
    """Generic paginated collection response from Metrc API endpoints.

    This is the standard response format for all collection endpoints
    like licenses, packages, plants, transfers, etc.
    """

    data: List[Dict[str, Any]]
    total: int
    page: int
    pageSize: int