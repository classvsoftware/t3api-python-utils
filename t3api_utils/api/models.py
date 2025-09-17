"""API response models for T3 API endpoints.

These models replace the t3api package's generated models with lightweight
dataclasses that work with our httpx-based implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class PaginatedResponse(Protocol[T]):
    """Protocol for paginated API responses."""

    data: List[T]
    total: int
    page: int
    page_size: int

    def __len__(self) -> int:
        return len(self.data)


@dataclass
class AuthResponse:
    """Response from /v2/auth/credentials endpoint."""

    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_type: str = "Bearer"


@dataclass
class License:
    """License information from /v2/licenses endpoint."""

    id: str
    license_number: str
    legal_name: str
    dba_name: Optional[str] = None
    facility_name: Optional[str] = None
    is_active: bool = True
    license_type: Optional[str] = None

    @property
    def index(self) -> str:
        """Compatibility property for existing SerializableObject interface."""
        return self.id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "id": self.id,
            "license_number": self.license_number,
            "legal_name": self.legal_name,
            "dba_name": self.dba_name,
            "facility_name": self.facility_name,
            "is_active": self.is_active,
            "license_type": self.license_type,
        }


@dataclass
class Package:
    """Package information from packages endpoints."""

    id: str
    license_number: str
    tag: str
    package_type: Optional[str] = None
    product_name: Optional[str] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    package_state: Optional[str] = None

    @property
    def index(self) -> str:
        """Compatibility property for existing SerializableObject interface."""
        return self.id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "id": self.id,
            "license_number": self.license_number,
            "tag": self.tag,
            "package_type": self.package_type,
            "product_name": self.product_name,
            "quantity": self.quantity,
            "unit_of_measure": self.unit_of_measure,
            "package_state": self.package_state,
        }


@dataclass
class LicensesResponse:
    """Paginated response for licenses endpoint."""

    data: List[License]
    total: int
    page: int = 1
    page_size: int = 100

    def __len__(self) -> int:
        return len(self.data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LicensesResponse:
        """Create from API response dict."""
        licenses = [
            License(
                id=item.get("id", ""),
                license_number=item.get("licenseNumber", ""),
                legal_name=item.get("legalName", ""),
                dba_name=item.get("dbaName"),
                facility_name=item.get("facilityName"),
                is_active=item.get("isActive", True),
                license_type=item.get("licenseType"),
            )
            for item in data.get("data", [])
        ]

        return cls(
            data=licenses,
            total=data.get("total", len(licenses)),
            page=data.get("page", 1),
            page_size=data.get("pageSize", len(licenses)),
        )


@dataclass
class PackagesResponse:
    """Paginated response for packages endpoint."""

    data: List[Package]
    total: int
    page: int = 1
    page_size: int = 100

    def __len__(self) -> int:
        return len(self.data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PackagesResponse:
        """Create from API response dict."""
        packages = [
            Package(
                id=item.get("id", ""),
                license_number=item.get("licenseNumber", ""),
                tag=item.get("tag", ""),
                package_type=item.get("packageType"),
                product_name=item.get("productName"),
                quantity=item.get("quantity"),
                unit_of_measure=item.get("unitOfMeasure"),
                package_state=item.get("packageState"),
            )
            for item in data.get("data", [])
        ]

        return cls(
            data=packages,
            total=data.get("total", len(packages)),
            page=data.get("page", 1),
            page_size=data.get("pageSize", len(packages)),
        )