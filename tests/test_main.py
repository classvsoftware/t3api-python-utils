from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from typer import Exit

from t3api_utils.exceptions import AuthenticationError
from t3api_utils.interfaces import SerializableObject
from t3api_utils.main.utils import (get_authenticated_client_or_error,
                                    get_jwt_authenticated_client_or_error,
                                    get_jwt_authenticated_client_or_error_with_validation,
                                    load_collection, pick_license,
                                    save_collection_to_csv,
                                    save_collection_to_json)


@patch("t3api_utils.main.utils.get_authenticated_client_or_error_async")
def test_get_authenticated_client_or_error(mock_get_client_async):
    mock_client = MagicMock(name="authenticated_client")
    mock_get_client_async.return_value = mock_client

    result = get_authenticated_client_or_error()

    mock_get_client_async.assert_called_once()
    assert result == mock_client


@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_success(mock_create_jwt_client):
    """Test successful JWT authentication."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
    mock_client = MagicMock(name="jwt_authenticated_client")
    mock_create_jwt_client.return_value = mock_client

    result = get_jwt_authenticated_client_or_error(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(test_token)
    assert result == mock_client


@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_invalid_token(mock_create_jwt_client):
    """Test JWT authentication with invalid token."""
    test_token = ""
    mock_create_jwt_client.side_effect = ValueError("JWT token cannot be empty or None")

    with pytest.raises(AuthenticationError, match="Invalid JWT token"):
        get_jwt_authenticated_client_or_error(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(test_token)


@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_unexpected_error(mock_create_jwt_client):
    """Test JWT authentication with unexpected error."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
    mock_create_jwt_client.side_effect = RuntimeError("Unexpected error")

    with pytest.raises(RuntimeError, match="Unexpected error"):
        get_jwt_authenticated_client_or_error(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(test_token)


@patch("t3api_utils.main.utils.get_data")
@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_with_validation_success(mock_create_jwt_client, mock_get_data):
    """Test successful JWT authentication with validation."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
    mock_client = MagicMock(name="jwt_authenticated_client")
    mock_create_jwt_client.return_value = mock_client
    mock_get_data.return_value = {"username": "testuser", "id": "123"}

    result = get_jwt_authenticated_client_or_error_with_validation(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(test_token)
    mock_get_data.assert_called_once_with(mock_client, "/v2/auth/whoami")
    assert result == mock_client


@patch("t3api_utils.main.utils.get_data")
@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_with_validation_invalid_token(mock_create_jwt_client, mock_get_data):
    """Test JWT authentication with validation when token is invalid."""
    test_token = ""
    mock_create_jwt_client.side_effect = ValueError("JWT token cannot be empty or None")

    with pytest.raises(AuthenticationError, match="Invalid JWT token"):
        get_jwt_authenticated_client_or_error_with_validation(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(test_token)
    mock_get_data.assert_not_called()


@patch("asyncio.run")
@patch("t3api_utils.main.utils.get_data")
@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_with_validation_unauthorized(mock_create_jwt_client, mock_get_data, mock_asyncio_run):
    """Test JWT authentication with validation when token is unauthorized."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.expired.signature"
    mock_client = MagicMock(name="jwt_authenticated_client")
    mock_create_jwt_client.return_value = mock_client

    # Simulate 401 Unauthorized response
    from t3api_utils.http.utils import T3HTTPError
    mock_get_data.side_effect = T3HTTPError("401 Unauthorized")

    with pytest.raises(AuthenticationError, match="JWT token is invalid or expired"):
        get_jwt_authenticated_client_or_error_with_validation(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(test_token)
    mock_get_data.assert_called_once_with(mock_client, "/v2/auth/whoami")
    # Verify client was closed on validation failure
    mock_asyncio_run.assert_called_once()


@patch("asyncio.run")
@patch("t3api_utils.main.utils.get_data")
@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_with_validation_forbidden(mock_create_jwt_client, mock_get_data, mock_asyncio_run):
    """Test JWT authentication with validation when token has insufficient permissions."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.limited.signature"
    mock_client = MagicMock(name="jwt_authenticated_client")
    mock_create_jwt_client.return_value = mock_client

    # Simulate 403 Forbidden response
    from t3api_utils.http.utils import T3HTTPError
    mock_get_data.side_effect = T3HTTPError("403 Forbidden")

    with pytest.raises(AuthenticationError, match="JWT token does not have sufficient permissions"):
        get_jwt_authenticated_client_or_error_with_validation(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(test_token)
    mock_get_data.assert_called_once_with(mock_client, "/v2/auth/whoami")
    # Verify client was closed on validation failure
    mock_asyncio_run.assert_called_once()


@patch("asyncio.run")
@patch("t3api_utils.main.utils.get_data")
@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_with_validation_generic_error(mock_create_jwt_client, mock_get_data, mock_asyncio_run):
    """Test JWT authentication with validation for generic validation errors."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
    mock_client = MagicMock(name="jwt_authenticated_client")
    mock_create_jwt_client.return_value = mock_client

    # Simulate generic network error
    mock_get_data.side_effect = RuntimeError("Network connection failed")

    with pytest.raises(AuthenticationError, match="JWT token validation failed: Network connection failed"):
        get_jwt_authenticated_client_or_error_with_validation(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(test_token)
    mock_get_data.assert_called_once_with(mock_client, "/v2/auth/whoami")
    # Verify client was closed on validation failure
    mock_asyncio_run.assert_called_once()


@patch("t3api_utils.main.utils.get_data")
@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_with_validation_unexpected_error(mock_create_jwt_client, mock_get_data):
    """Test JWT authentication with validation when unexpected error occurs."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
    mock_create_jwt_client.side_effect = RuntimeError("Unexpected system error")

    with pytest.raises(AuthenticationError, match="Unexpected authentication error: Unexpected system error"):
        get_jwt_authenticated_client_or_error_with_validation(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(test_token)
    mock_get_data.assert_not_called()


@patch("t3api_utils.main.utils.console.print")
@patch("t3api_utils.main.utils.typer.prompt")
@patch("t3api_utils.main.utils.get_data")
def test_pick_license_valid_choice(mock_get_data, mock_prompt, mock_console):
    mock_client = MagicMock()
    license1 = {"id": "1", "licenseNumber": "123", "licenseName": "Alpha"}
    license2 = {"id": "2", "licenseNumber": "456", "licenseName": "Beta"}
    mock_licenses: List[Dict[str, Any]] = [license1, license2]
    mock_get_data.return_value = mock_licenses
    mock_prompt.return_value = 2

    result = pick_license(api_client=mock_client)
    assert result == license2


@patch("t3api_utils.main.utils.print_error")
@patch("t3api_utils.main.utils.get_data")
def test_pick_license_empty_list(mock_get_data, mock_print_error):
    mock_client = MagicMock()
    mock_licenses: List[Dict[str, Any]] = []
    mock_get_data.return_value = mock_licenses

    with pytest.raises(Exit):
        pick_license(api_client=mock_client)

    mock_print_error.assert_called_once_with("No licenses found.")


@patch("t3api_utils.main.utils.extract_data")
@patch("t3api_utils.main.utils.parallel_load_collection")
def test_load_collection_flattens_data(mock_parallel, mock_extract):
    mock_response = [MagicMock()]
    mock_parallel.return_value = mock_response
    mock_extract.return_value = ["a", "b"]

    def fake_method(*args, **kwargs):
        pass

    result = load_collection(fake_method)
    assert result == ["a", "b"]
    mock_parallel.assert_called_once()
    mock_extract.assert_called_once_with(responses=mock_response)


@patch("t3api_utils.main.utils.open_file")
@patch("t3api_utils.main.utils.save_dicts_to_json")
@patch("t3api_utils.main.utils.collection_to_dicts")
def test_save_collection_to_json_success(mock_convert, mock_save, mock_open):
    fake_obj = MagicMock(spec=SerializableObject)
    fake_obj.index = "my_model"
    fake_obj.license_number = "XYZ"
    mock_convert.return_value = [{"some": "dict"}]
    mock_save.return_value = Path("/tmp/output.json")

    result = save_collection_to_json(objects=[fake_obj], output_dir=".", open_after=True)

    assert result == Path("/tmp/output.json")
    mock_open.assert_called_once_with(path=Path("/tmp/output.json"))


@patch("t3api_utils.main.utils.open_file")
@patch("t3api_utils.main.utils.save_dicts_to_csv")
@patch("t3api_utils.main.utils.collection_to_dicts")
def test_save_collection_to_csv_success(mock_convert, mock_save, mock_open):
    fake_obj = MagicMock(spec=SerializableObject)
    fake_obj.index = "test"
    fake_obj.license_number = "LIC123"
    mock_convert.return_value = [{"some": "dict"}]
    mock_save.return_value = Path("/tmp/output.csv")

    result = save_collection_to_csv(objects=[fake_obj], output_dir=".", open_after=True, strip_empty_columns=True)

    assert result == Path("/tmp/output.csv")
    mock_open.assert_called_once_with(path=Path("/tmp/output.csv"))


def test_save_collection_to_json_raises_on_empty():
    with pytest.raises(ValueError, match="Cannot serialize an empty list of objects"):
        save_collection_to_json(objects=[], output_dir=".")


def test_save_collection_to_csv_raises_on_empty():
    with pytest.raises(ValueError, match="Cannot serialize an empty list of objects"):
        save_collection_to_csv(objects=[], output_dir=".")
