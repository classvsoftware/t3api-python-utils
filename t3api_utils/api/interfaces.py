"""API response type definitions for T3 API endpoints.

These TypedDict definitions provide type safety while keeping data
in its raw dict/list format for maximum flexibility.
"""
from __future__ import annotations

from typing import Any, Dict, List, NotRequired, TypedDict, TypeVar, Union


class AuthResponseData(TypedDict):
    """Authentication response returned by ``/v2/auth/credentials`` and ``/v2/auth/apikey``.

    May contain additional fields beyond ``accessToken`` depending on the
    authentication method used.
    """

    accessToken: str
    """JWT bearer token used to authorize subsequent API requests."""


class LicenseData(TypedDict):
    """A Metrc license associated with an authenticated user."""

    licenseNumber: str
    """Unique license identifier (e.g. ``"CUL00001"``)."""

    licenseName: str
    """Human-readable display name for the license."""


class MetrcObject(TypedDict):
    """Base Metrc object containing fields common to all collection data responses.

    All Metrc API collection endpoints return objects that extend this base structure
    with additional fields specific to the resource type (packages, plants, etc.).
    """

    id: int
    """Unique numeric identifier for the Metrc object (e.g., 123456)"""

    hostname: str
    """Metrc instance hostname where the data originated (e.g., 'ca.metrc.com')"""

    licenseNumber: str
    """License number associated with this object (e.g., 'CUL00001')"""

    dataModel: str
    """Metrc data model type identifier (e.g., 'ACTIVE_PACKAGE', 'PLANT', 'TRANSFER')"""

    retrievedAt: str
    """ISO 8601 timestamp when this object was retrieved from the API (e.g., '2025-09-23T13:19:22.734Z')"""

    index: NotRequired[str]
    """Optional index that differentiates objects of the same dataModel type"""
    


class MetrcCollectionResponse(TypedDict):
    """Generic paginated collection response from Metrc API endpoints.

    This is the standard response format for all collection endpoints
    like licenses, packages, plants, transfers, etc.
    """

    data: List[MetrcObject]
    """List of Metrc objects for the current page."""

    total: int
    """Total number of records across all pages."""

    page: int
    """Current page number (1-based)."""

    pageSize: int
    """Number of items per page."""

