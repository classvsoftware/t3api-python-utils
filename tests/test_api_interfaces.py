"""Tests for API interfaces."""
from typing import Any, Dict

import pytest

from t3api_utils.api.interfaces import (AuthResponseData,
                                        MetrcCollectionResponse, MetrcObject)


class TestAuthResponseData:
    """Test AuthResponseData TypedDict."""

    def test_basic_structure(self):
        """Test basic AuthResponseData structure."""
        response: AuthResponseData = {
            "accessToken": "test_token"
        }
        assert response["accessToken"] == "test_token"

    def test_full_structure(self):
        """Test AuthResponseData with all fields."""
        response: AuthResponseData = {
            "accessToken": "test_token",
        }
        assert response["accessToken"] == "test_token"


class TestMetrcObject:
    """Test MetrcObject TypedDict."""

    def test_basic_structure(self):
        """Test basic MetrcObject structure."""
        metrc_obj: MetrcObject = {
            "id": 1,
            "hostname": "ca.metrc.com",
            "licenseNumber": "LIC-001",
            "dataModel": "PACKAGE",
            "retrievedAt": "2025-09-23T13:19:22.734Z"
        }

    def test_with_fields(self):
        """Test MetrcObject with fields."""
        metrc_obj: MetrcObject = {
            "id": 123,
            "hostname": "ca.metrc.com",
            "licenseNumber": "LIC-001",
            "dataModel": "PACKAGE",
            "retrievedAt": "2025-09-23T13:19:22.734Z"
        }
        assert metrc_obj["id"] == 123
        assert metrc_obj["licenseNumber"] == "LIC-001"


class TestMetrcCollectionResponse:
    """Test MetrcCollectionResponse TypedDict."""

    def test_basic_structure(self):
        """Test basic MetrcCollectionResponse structure."""
        response: MetrcCollectionResponse = {
            "data": [
                {
                    "id": 1,
                    "hostname": "ca.metrc.com",
                    "licenseNumber": "LIC-001",
                    "dataModel": "LICENSE",
                    "retrievedAt": "2025-09-23T13:19:22.734Z"
                },
                {
                    "id": 2,
                    "hostname": "ca.metrc.com",
                    "licenseNumber": "LIC-002",
                    "dataModel": "LICENSE",
                    "retrievedAt": "2025-09-23T13:19:22.734Z"
                }
            ],
            "total": 2,
            "page": 1,
            "pageSize": 100
        }

        assert len(response["data"]) == 2
        assert response["total"] == 2
        assert response["page"] == 1
        assert response["pageSize"] == 100

    def test_license_collection_response(self):
        """Test MetrcCollectionResponse with license data."""
        license_response: MetrcCollectionResponse = {
            "data": [
                {
                    "id": 123,
                    "hostname": "ca.metrc.com",
                    "licenseNumber": "LIC-001",
                    "dataModel": "LICENSE",
                    "retrievedAt": "2025-09-23T13:19:22.734Z"
                },
                {
                    "id": 456,
                    "hostname": "ca.metrc.com",
                    "licenseNumber": "LIC-002",
                    "dataModel": "LICENSE",
                    "retrievedAt": "2025-09-23T13:19:22.734Z"
                }
            ],
            "total": 2,
            "page": 1,
            "pageSize": 100
        }

        assert len(license_response["data"]) == 2
        assert license_response["total"] == 2

        # Check first license
        license1 = license_response["data"][0]
        assert license1["id"] == 123
        assert license1["licenseNumber"] == "LIC-001"
        assert license1["hostname"] == "ca.metrc.com"
        assert license1["dataModel"] == "LICENSE"

        # Check second license
        license2 = license_response["data"][1]
        assert license2["id"] == 456
        assert license2["licenseNumber"] == "LIC-002"
        assert license2["hostname"] == "ca.metrc.com"

    def test_package_collection_response(self):
        """Test MetrcCollectionResponse with package data."""
        package_response: MetrcCollectionResponse = {
            "data": [
                {
                    "id": 123,
                    "hostname": "ca.metrc.com",
                    "licenseNumber": "LIC-001",
                    "dataModel": "PACKAGE",
                    "retrievedAt": "2025-09-23T13:19:22.734Z"
                },
                {
                    "id": 456,
                    "hostname": "ca.metrc.com",
                    "licenseNumber": "LIC-001",
                    "dataModel": "PACKAGE",
                    "retrievedAt": "2025-09-23T13:19:22.734Z"
                }
            ],
            "total": 2,
            "page": 2,
            "pageSize": 50
        }

        assert len(package_response["data"]) == 2
        assert package_response["total"] == 2
        assert package_response["page"] == 2
        assert package_response["pageSize"] == 50

        # Check first package
        package1 = package_response["data"][0]
        assert package1["id"] == 123
        assert package1["licenseNumber"] == "LIC-001"
        assert package1["hostname"] == "ca.metrc.com"
        assert package1["dataModel"] == "PACKAGE"

        # Check second package
        package2 = package_response["data"][1]
        assert package2["id"] == 456

    def test_empty_collection_response(self):
        """Test MetrcCollectionResponse with no data."""
        empty_response: MetrcCollectionResponse = {
            "data": [],
            "total": 0,
            "page": 1,
            "pageSize": 100
        }

        assert len(empty_response["data"]) == 0
        assert empty_response["total"] == 0
        assert empty_response["page"] == 1
        assert empty_response["pageSize"] == 100