"""Tests for API models."""
import pytest
from typing import Dict, Any

from t3api_utils.api.models import (
    AuthResponse,
    License,
    Package,
    LicensesResponse,
    PackagesResponse,
    PaginatedResponse,
)


class TestAuthResponse:
    """Test AuthResponse model."""

    def test_basic_creation(self):
        """Test basic AuthResponse creation."""
        response = AuthResponse(access_token="test_token")
        assert response.access_token == "test_token"
        assert response.refresh_token is None
        assert response.expires_in is None
        assert response.token_type == "Bearer"

    def test_full_creation(self):
        """Test AuthResponse with all fields."""
        response = AuthResponse(
            access_token="test_token",
            refresh_token="refresh_token",
            expires_in=3600,
            token_type="Custom"
        )
        assert response.access_token == "test_token"
        assert response.refresh_token == "refresh_token"
        assert response.expires_in == 3600
        assert response.token_type == "Custom"


class TestLicense:
    """Test License model."""

    def test_basic_creation(self):
        """Test basic License creation."""
        license_obj = License(
            id="123",
            license_number="LIC-001",
            legal_name="Test Company"
        )
        assert license_obj.id == "123"
        assert license_obj.license_number == "LIC-001"
        assert license_obj.legal_name == "Test Company"
        assert license_obj.is_active is True

    def test_serializable_object_interface(self):
        """Test License implements SerializableObject interface."""
        license_obj = License(
            id="123",
            license_number="LIC-001",
            legal_name="Test Company"
        )

        # Test index property
        assert license_obj.index == "123"

        # Test to_dict method
        result = license_obj.to_dict()
        expected = {
            "id": "123",
            "license_number": "LIC-001",
            "legal_name": "Test Company",
            "dba_name": None,
            "facility_name": None,
            "is_active": True,
            "license_type": None,
        }
        assert result == expected

    def test_full_license(self):
        """Test License with all optional fields."""
        license_obj = License(
            id="123",
            license_number="LIC-001",
            legal_name="Test Company",
            dba_name="Test DBA",
            facility_name="Test Facility",
            is_active=False,
            license_type="Cultivation"
        )

        result = license_obj.to_dict()
        assert result["dba_name"] == "Test DBA"
        assert result["facility_name"] == "Test Facility"
        assert result["is_active"] is False
        assert result["license_type"] == "Cultivation"


class TestPackage:
    """Test Package model."""

    def test_basic_creation(self):
        """Test basic Package creation."""
        package = Package(
            id="pkg-123",
            license_number="LIC-001",
            tag="TAG-001"
        )
        assert package.id == "pkg-123"
        assert package.license_number == "LIC-001"
        assert package.tag == "TAG-001"

    def test_serializable_object_interface(self):
        """Test Package implements SerializableObject interface."""
        package = Package(
            id="pkg-123",
            license_number="LIC-001",
            tag="TAG-001"
        )

        # Test index property
        assert package.index == "pkg-123"

        # Test to_dict method
        result = package.to_dict()
        expected = {
            "id": "pkg-123",
            "license_number": "LIC-001",
            "tag": "TAG-001",
            "package_type": None,
            "product_name": None,
            "quantity": None,
            "unit_of_measure": None,
            "package_state": None,
        }
        assert result == expected

    def test_full_package(self):
        """Test Package with all optional fields."""
        package = Package(
            id="pkg-123",
            license_number="LIC-001",
            tag="TAG-001",
            package_type="Product",
            product_name="Test Product",
            quantity=10.5,
            unit_of_measure="grams",
            package_state="Active"
        )

        result = package.to_dict()
        assert result["package_type"] == "Product"
        assert result["product_name"] == "Test Product"
        assert result["quantity"] == 10.5
        assert result["unit_of_measure"] == "grams"
        assert result["package_state"] == "Active"


class TestLicensesResponse:
    """Test LicensesResponse model."""

    def test_basic_creation(self):
        """Test basic LicensesResponse creation."""
        licenses = [
            License(id="1", license_number="LIC-001", legal_name="Company 1"),
            License(id="2", license_number="LIC-002", legal_name="Company 2"),
        ]
        response = LicensesResponse(data=licenses, total=2)

        assert len(response) == 2
        assert response.total == 2
        assert response.page == 1
        assert response.page_size == 100

    def test_from_dict_conversion(self):
        """Test creating LicensesResponse from API dict."""
        api_data = {
            "data": [
                {
                    "id": "123",
                    "licenseNumber": "LIC-001",
                    "legalName": "Test Company",
                    "dbaName": "Test DBA",
                    "facilityName": "Test Facility",
                    "isActive": True,
                    "licenseType": "Cultivation"
                },
                {
                    "id": "456",
                    "licenseNumber": "LIC-002",
                    "legalName": "Another Company",
                    "isActive": False
                }
            ],
            "total": 2,
            "page": 1,
            "pageSize": 100
        }

        response = LicensesResponse.from_dict(api_data)

        assert len(response) == 2
        assert response.total == 2
        assert response.page == 1
        assert response.page_size == 100

        # Check first license
        license1 = response.data[0]
        assert license1.id == "123"
        assert license1.license_number == "LIC-001"
        assert license1.legal_name == "Test Company"
        assert license1.dba_name == "Test DBA"
        assert license1.facility_name == "Test Facility"
        assert license1.is_active is True
        assert license1.license_type == "Cultivation"

        # Check second license
        license2 = response.data[1]
        assert license2.id == "456"
        assert license2.license_number == "LIC-002"
        assert license2.legal_name == "Another Company"
        assert license2.dba_name is None
        assert license2.is_active is False

    def test_from_dict_minimal_data(self):
        """Test from_dict with minimal API response."""
        api_data = {
            "data": [
                {
                    "id": "123",
                    "licenseNumber": "LIC-001",
                    "legalName": "Test Company"
                }
            ]
        }

        response = LicensesResponse.from_dict(api_data)

        assert len(response) == 1
        assert response.total == 1  # Should default to data length
        assert response.page == 1
        assert response.page_size == 1

        license = response.data[0]
        assert license.id == "123"
        assert license.license_number == "LIC-001"
        assert license.legal_name == "Test Company"

    def test_implements_paginated_response_protocol(self):
        """Test that LicensesResponse implements PaginatedResponse protocol."""
        licenses = [License(id="1", license_number="LIC-001", legal_name="Company")]
        response = LicensesResponse(data=licenses, total=1)

        # Should pass isinstance check for protocol
        assert isinstance(response, PaginatedResponse)


class TestPackagesResponse:
    """Test PackagesResponse model."""

    def test_basic_creation(self):
        """Test basic PackagesResponse creation."""
        packages = [
            Package(id="1", license_number="LIC-001", tag="TAG-001"),
            Package(id="2", license_number="LIC-001", tag="TAG-002"),
        ]
        response = PackagesResponse(data=packages, total=2)

        assert len(response) == 2
        assert response.total == 2
        assert response.page == 1
        assert response.page_size == 100

    def test_from_dict_conversion(self):
        """Test creating PackagesResponse from API dict."""
        api_data = {
            "data": [
                {
                    "id": "pkg-123",
                    "licenseNumber": "LIC-001",
                    "tag": "TAG-001",
                    "packageType": "Product",
                    "productName": "Test Product",
                    "quantity": 10.5,
                    "unitOfMeasure": "grams",
                    "packageState": "Active"
                },
                {
                    "id": "pkg-456",
                    "licenseNumber": "LIC-001",
                    "tag": "TAG-002"
                }
            ],
            "total": 2,
            "page": 2,
            "pageSize": 50
        }

        response = PackagesResponse.from_dict(api_data)

        assert len(response) == 2
        assert response.total == 2
        assert response.page == 2
        assert response.page_size == 50

        # Check first package
        package1 = response.data[0]
        assert package1.id == "pkg-123"
        assert package1.license_number == "LIC-001"
        assert package1.tag == "TAG-001"
        assert package1.package_type == "Product"
        assert package1.product_name == "Test Product"
        assert package1.quantity == 10.5
        assert package1.unit_of_measure == "grams"
        assert package1.package_state == "Active"

        # Check second package
        package2 = response.data[1]
        assert package2.id == "pkg-456"
        assert package2.package_type is None

    def test_implements_paginated_response_protocol(self):
        """Test that PackagesResponse implements PaginatedResponse protocol."""
        packages = [Package(id="1", license_number="LIC-001", tag="TAG-001")]
        response = PackagesResponse(data=packages, total=1)

        # Should pass isinstance check for protocol
        assert isinstance(response, PaginatedResponse)