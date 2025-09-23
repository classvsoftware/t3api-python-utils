"""API response type definitions for T3 API endpoints.

These TypedDict definitions provide type safety while keeping data
in its raw dict/list format for maximum flexibility.
"""
from __future__ import annotations

from typing import Any, Dict, List, NotRequired, TypedDict, TypeVar, Union


class AuthResponseData(TypedDict):
    """Authentication response data structure."""

    accessToken: str


class LicenseData(TypedDict):
    licenseNumber: str
    licenseName: str


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
    total: int
    page: int
    pageSize: int

