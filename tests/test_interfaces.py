"""Tests for TypedDict interfaces."""


from t3api_utils.auth.interfaces import T3Credentials
from t3api_utils.api.interfaces import AuthResponseData, MetrcObject, MetrcCollectionResponse


class TestT3Credentials:
    """Test T3Credentials TypedDict."""

    def test_t3_credentials_complete(self):
        """Test T3Credentials with all fields."""
        credentials: T3Credentials = {
            "hostname": "api.metrc.com",
            "username": "testuser",
            "password": "testpass",
            "otp": "123456",
            "email": "test@example.com"
        }

        assert credentials["hostname"] == "api.metrc.com"
        assert credentials["username"] == "testuser"
        assert credentials["password"] == "testpass"
        assert credentials["otp"] == "123456"
        assert credentials["email"] == "test@example.com"

    def test_t3_credentials_minimal(self):
        """Test T3Credentials with minimal required fields."""
        credentials: T3Credentials = {
            "hostname": "api.metrc.com",
            "username": "testuser",
            "password": "testpass",
            "otp": None,
            "email": None
        }

        assert credentials["hostname"] == "api.metrc.com"
        assert credentials["username"] == "testuser"
        assert credentials["password"] == "testpass"
        assert credentials["otp"] is None
        assert credentials["email"] is None

    def test_t3_credentials_partial_optional(self):
        """Test T3Credentials with some optional fields."""
        credentials: T3Credentials = {
            "hostname": "sandbox.metrc.com",
            "username": "sandboxuser",
            "password": "sandboxpass",
            "otp": "654321",
            "email": None
        }

        assert credentials["otp"] == "654321"
        assert credentials["email"] is None

    def test_t3_credentials_is_dict(self):
        """Test that T3Credentials behaves like a dictionary."""
        credentials: T3Credentials = {
            "hostname": "test.com",
            "username": "user",
            "password": "pass",
            "otp": None,
            "email": None
        }

        # Should support dict operations
        assert "hostname" in credentials
        assert len(credentials) == 5
        assert list(credentials.keys()) == ["hostname", "username", "password", "otp", "email"]


class TestAuthResponseData:
    """Test AuthResponseData TypedDict."""

    def test_auth_response_data_basic(self):
        """Test basic AuthResponseData structure."""
        auth_data: AuthResponseData = {
            "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        }

        assert auth_data["accessToken"].startswith("eyJ")
        assert isinstance(auth_data["accessToken"], str)

    def test_auth_response_data_is_dict(self):
        """Test that AuthResponseData behaves like a dictionary."""
        auth_data: AuthResponseData = {
            "accessToken": "test_token_123"
        }

        assert "accessToken" in auth_data
        assert len(auth_data) == 1
        assert list(auth_data.keys()) == ["accessToken"]

    def test_auth_response_data_token_types(self):
        """Test AuthResponseData with different token formats."""
        # JWT token
        jwt_data: AuthResponseData = {
            "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        }

        # Simple token
        simple_data: AuthResponseData = {
            "accessToken": "simple_access_token_123"
        }

        assert "eyJ" in jwt_data["accessToken"]
        assert jwt_data["accessToken"].count(".") == 2  # JWT has 3 parts
        assert simple_data["accessToken"] == "simple_access_token_123"


class TestMetrcObject:
    """Test MetrcObject TypedDict."""

    def test_metrc_object_complete(self):
        """Test MetrcObject with all fields."""
        metrc_obj: MetrcObject = {
            "id": 12345,
            "hostname": "ca.metrc.com",
            "licenseNumber": "LIC-123-456",
            "dataModel": "ACTIVE_PACKAGE",
            "retrievedAt": "2025-09-23T13:19:22.734Z"
        }

        assert metrc_obj["id"] == 12345
        assert metrc_obj["licenseNumber"] == "LIC-123-456"

    def test_metrc_object_minimal(self):
        """Test MetrcObject with minimal required fields."""
        metrc_obj: MetrcObject = {
            "id": 1,
            "hostname": "ca.metrc.com",
            "licenseNumber": "LIC-001",
            "dataModel": "PLANT",
            "retrievedAt": "2025-09-23T13:19:22.734Z"
        }

        assert len(metrc_obj) == 5

    def test_metrc_object_partial(self):
        """Test MetrcObject with different field values."""
        obj_with_id: MetrcObject = {
            "id": 67890,
            "hostname": "co.metrc.com",
            "licenseNumber": "LIC-789-012",
            "dataModel": "TRANSFER",
            "retrievedAt": "2025-09-23T13:19:22.734Z"
        }
        obj_with_license: MetrcObject = {
            "id": 99999,
            "hostname": "wa.metrc.com",
            "licenseNumber": "LIC-789-012",
            "dataModel": "SALE",
            "retrievedAt": "2025-09-23T13:19:22.734Z"
        }

        assert obj_with_id["id"] == 67890
        assert obj_with_id["licenseNumber"] == "LIC-789-012"

        assert obj_with_license["licenseNumber"] == "LIC-789-012"
        assert obj_with_license["id"] == 99999

    def test_metrc_object_is_dict(self):
        """Test that MetrcObject behaves like a dictionary."""
        metrc_obj: MetrcObject = {
            "id": 123,
            "hostname": "or.metrc.com",
            "licenseNumber": "LIC-TEST",
            "dataModel": "PACKAGE",
            "retrievedAt": "2025-09-23T13:19:22.734Z"
        }

        assert isinstance(metrc_obj, dict)
        assert "id" in metrc_obj
        assert metrc_obj.get("id") == 123


class TestMetrcCollectionResponse:
    """Test MetrcCollectionResponse TypedDict."""

    def test_metrc_collection_response_complete(self):
        """Test complete MetrcCollectionResponse."""
        response: MetrcCollectionResponse = {
            "data": [
                {
                    "id": 1,
                    "hostname": "ca.metrc.com",
                    "licenseNumber": "LIC-001",
                    "dataModel": "PACKAGE",
                    "retrievedAt": "2025-09-23T13:19:22.734Z"
                },
                {
                    "id": 2,
                    "hostname": "ca.metrc.com",
                    "licenseNumber": "LIC-002",
                    "dataModel": "PACKAGE",
                    "retrievedAt": "2025-09-23T13:19:22.734Z"
                }
            ],
            "total": 100,
            "page": 1,
            "pageSize": 20
        }

        assert len(response["data"]) == 2
        assert response["total"] == 100
        assert response["page"] == 1
        assert response["pageSize"] == 20

    def test_metrc_collection_response_empty_data(self):
        """Test MetrcCollectionResponse with empty data."""
        response: MetrcCollectionResponse = {
            "data": [],
            "total": 0,
            "page": 1,
            "pageSize": 20
        }

        assert response["data"] == []
        assert response["total"] == 0

    def test_metrc_collection_response_pagination(self):
        """Test MetrcCollectionResponse pagination fields."""
        # First page
        first_page: MetrcCollectionResponse = {
            "data": [{
                "id": i,
                "hostname": "ca.metrc.com",
                "licenseNumber": f"LIC-{i:03d}",
                "dataModel": "PACKAGE",
                "retrievedAt": "2025-09-23T13:19:22.734Z"
            } for i in range(1, 21)],
            "total": 100,
            "page": 1,
            "pageSize": 20
        }

        # Last page
        last_page: MetrcCollectionResponse = {
            "data": [{
                "id": i,
                "hostname": "ca.metrc.com",
                "licenseNumber": f"LIC-{i:03d}",
                "dataModel": "PACKAGE",
                "retrievedAt": "2025-09-23T13:19:22.734Z"
            } for i in range(81, 101)],
            "total": 100,
            "page": 5,
            "pageSize": 20
        }

        assert len(first_page["data"]) == 20
        assert first_page["page"] == 1

        assert len(last_page["data"]) == 20
        assert last_page["page"] == 5

    def test_metrc_collection_response_complex_data(self):
        """Test MetrcCollectionResponse with complex data objects."""
        response: MetrcCollectionResponse = {
            "data": [
                {
                    "id": 123,
                    "hostname": "ca.metrc.com",
                    "licenseNumber": "LIC-123",
                    "dataModel": "PACKAGE",
                    "retrievedAt": "2025-09-23T13:19:22.734Z"
                }
            ],
            "total": 1,
            "page": 1,
            "pageSize": 50
        }

        item = response["data"][0]
        assert item["id"] == 123
        assert item["licenseNumber"] == "LIC-123"

    def test_metrc_collection_response_is_dict(self):
        """Test that MetrcCollectionResponse behaves like a dictionary."""
        response: MetrcCollectionResponse = {
            "data": [],
            "total": 0,
            "page": 1,
            "pageSize": 10
        }

        assert isinstance(response, dict)
        assert "data" in response
        assert len(response) == 4
        expected_keys = ["data", "total", "page", "pageSize"]
        assert all(key in response for key in expected_keys)


class TestInterfacesModules:
    """Test interfaces module imports and structure."""

    def test_main_interfaces_module(self):
        """Test main interfaces module exports."""
        import t3api_utils.interfaces as interfaces

        assert hasattr(interfaces, 'P')

    def test_auth_interfaces_module(self):
        """Test auth interfaces module exports."""
        import t3api_utils.auth.interfaces as auth_interfaces

        assert hasattr(auth_interfaces, 'T3Credentials')

    def test_api_interfaces_module(self):
        """Test API interfaces module exports."""
        import t3api_utils.api.interfaces as api_interfaces

        assert hasattr(api_interfaces, 'AuthResponseData')
        assert hasattr(api_interfaces, 'MetrcObject')
        assert hasattr(api_interfaces, 'MetrcCollectionResponse')

    def test_cross_module_imports(self):
        """Test importing interfaces from different modules."""
        from t3api_utils.auth.interfaces import T3Credentials
        from t3api_utils.api.interfaces import AuthResponseData, MetrcCollectionResponse

        # Should be able to use all interfaces together
        assert T3Credentials is not None
        assert AuthResponseData is not None
        assert MetrcCollectionResponse is not None