from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from typer import Exit

from t3api_utils.exceptions import AuthenticationError
from t3api_utils.main.utils import (
    _discover_data_files, _format_file_size, _format_file_time,
    _load_file_content, _pick_authentication_method,
    get_api_key_authenticated_client_or_error,
    get_authenticated_client_or_error, get_jwt_authenticated_client_or_error,
    get_jwt_authenticated_client_or_error_with_validation, load_collection,
    match_collection_from_csv, pick_file, pick_license, save_collection_to_csv,
    save_collection_to_json)


@patch("t3api_utils.main.utils._authenticate_with_credentials")
@patch("t3api_utils.main.utils._pick_authentication_method")
def test_get_authenticated_client_or_error(mock_pick, mock_auth_creds):
    """Test get_authenticated_client_or_error with credentials selection."""
    mock_pick.return_value = "credentials"
    mock_client = MagicMock(name="authenticated_client")
    mock_auth_creds.return_value = mock_client

    result = get_authenticated_client_or_error()

    assert result == mock_client
    mock_pick.assert_called_once()
    mock_auth_creds.assert_called_once()


@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_success(mock_create_jwt_client):
    """Test successful JWT authentication."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
    mock_client = MagicMock(name="jwt_authenticated_client")
    mock_create_jwt_client.return_value = mock_client

    result = get_jwt_authenticated_client_or_error(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(jwt_token=test_token)
    assert result == mock_client


@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_invalid_token(mock_create_jwt_client):
    """Test JWT authentication with invalid token."""
    test_token = ""
    mock_create_jwt_client.side_effect = ValueError("JWT token cannot be empty or None")

    with pytest.raises(AuthenticationError, match="Invalid JWT token"):
        get_jwt_authenticated_client_or_error(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(jwt_token=test_token)


@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_unexpected_error(mock_create_jwt_client):
    """Test JWT authentication with unexpected error."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
    mock_create_jwt_client.side_effect = RuntimeError("Unexpected error")

    with pytest.raises(RuntimeError, match="Unexpected error"):
        get_jwt_authenticated_client_or_error(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(jwt_token=test_token)


@patch("t3api_utils.main.utils.send_api_request")
@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_with_validation_success(mock_create_jwt_client, mock_get_data):
    """Test successful JWT authentication with validation."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
    mock_client = MagicMock(name="jwt_authenticated_client")
    mock_create_jwt_client.return_value = mock_client
    mock_get_data.return_value = {"username": "testuser", "id": "123"}

    result = get_jwt_authenticated_client_or_error_with_validation(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(jwt_token=test_token)
    mock_get_data.assert_called_once_with(mock_client, "/v2/auth/whoami")
    assert result == mock_client


@patch("t3api_utils.main.utils.send_api_request")
@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_with_validation_invalid_token(mock_create_jwt_client, mock_get_data):
    """Test JWT authentication with validation when token is invalid."""
    test_token = ""
    mock_create_jwt_client.side_effect = ValueError("JWT token cannot be empty or None")

    with pytest.raises(AuthenticationError, match="Invalid JWT token"):
        get_jwt_authenticated_client_or_error_with_validation(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(jwt_token=test_token)
    mock_get_data.assert_not_called()


@patch("asyncio.run")
@patch("t3api_utils.main.utils.send_api_request")
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

    mock_create_jwt_client.assert_called_once_with(jwt_token=test_token)
    mock_get_data.assert_called_once_with(mock_client, "/v2/auth/whoami")
    # Verify client was closed on validation failure
    mock_asyncio_run.assert_called_once()


@patch("asyncio.run")
@patch("t3api_utils.main.utils.send_api_request")
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

    mock_create_jwt_client.assert_called_once_with(jwt_token=test_token)
    mock_get_data.assert_called_once_with(mock_client, "/v2/auth/whoami")
    # Verify client was closed on validation failure
    mock_asyncio_run.assert_called_once()


@patch("asyncio.run")
@patch("t3api_utils.main.utils.send_api_request")
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

    mock_create_jwt_client.assert_called_once_with(jwt_token=test_token)
    mock_get_data.assert_called_once_with(mock_client, "/v2/auth/whoami")
    # Verify client was closed on validation failure
    mock_asyncio_run.assert_called_once()


@patch("t3api_utils.main.utils.send_api_request")
@patch("t3api_utils.main.utils.create_jwt_authenticated_client")
def test_get_jwt_authenticated_client_or_error_with_validation_unexpected_error(mock_create_jwt_client, mock_get_data):
    """Test JWT authentication with validation when unexpected error occurs."""
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature"
    mock_create_jwt_client.side_effect = RuntimeError("Unexpected system error")

    with pytest.raises(AuthenticationError, match="Unexpected authentication error: Unexpected system error"):
        get_jwt_authenticated_client_or_error_with_validation(jwt_token=test_token)

    mock_create_jwt_client.assert_called_once_with(jwt_token=test_token)
    mock_get_data.assert_not_called()


@patch("t3api_utils.main.utils.create_api_key_authenticated_client_or_error")
def test_get_api_key_authenticated_client_or_error_success(mock_create_api_key_client):
    """Test successful API key authentication."""
    test_api_key = "test-api-key-123"
    test_state_code = "CA"
    mock_client = MagicMock(name="api_key_authenticated_client")
    mock_create_api_key_client.return_value = mock_client

    result = get_api_key_authenticated_client_or_error(
        api_key=test_api_key,
        state_code=test_state_code
    )

    assert result == mock_client
    mock_create_api_key_client.assert_called_once_with(
        api_key=test_api_key,
        state_code=test_state_code
    )


@patch("t3api_utils.main.utils.create_api_key_authenticated_client_or_error")
def test_get_api_key_authenticated_client_or_error_invalid_key(mock_create_api_key_client):
    """Test API key authentication with invalid key."""
    test_api_key = ""
    test_state_code = "CA"
    mock_create_api_key_client.side_effect = ValueError("API key cannot be empty or None")

    with pytest.raises(AuthenticationError, match="Invalid API key or state code"):
        get_api_key_authenticated_client_or_error(
            api_key=test_api_key,
            state_code=test_state_code
        )

    mock_create_api_key_client.assert_called_once_with(
        api_key=test_api_key,
        state_code=test_state_code
    )


@patch("typer.prompt")
@patch("t3api_utils.main.utils.print_error")
@patch("t3api_utils.main.utils.console.print")
def test_pick_authentication_method_credentials(mock_console, mock_print_error, mock_prompt):
    """Test authentication picker returns credentials."""
    mock_prompt.return_value = 1
    result = _pick_authentication_method()
    assert result == "credentials"
    mock_prompt.assert_called_once()


@patch("typer.prompt")
@patch("t3api_utils.main.utils.print_error")
@patch("t3api_utils.main.utils.console.print")
def test_pick_authentication_method_jwt(mock_console, mock_print_error, mock_prompt):
    """Test authentication picker returns jwt."""
    mock_prompt.return_value = 2
    result = _pick_authentication_method()
    assert result == "jwt"
    mock_prompt.assert_called_once()


@patch("typer.prompt")
@patch("t3api_utils.main.utils.print_error")
@patch("t3api_utils.main.utils.console.print")
def test_pick_authentication_method_api_key(mock_console, mock_print_error, mock_prompt):
    """Test authentication picker returns api_key."""
    mock_prompt.return_value = 3
    result = _pick_authentication_method()
    assert result == "api_key"
    mock_prompt.assert_called_once()


@patch("typer.prompt")
@patch("t3api_utils.main.utils.print_error")
@patch("t3api_utils.main.utils.console.print")
def test_pick_authentication_method_invalid_choice(mock_console, mock_print_error, mock_prompt):
    """Test authentication picker handles invalid choice."""
    mock_prompt.side_effect = [4, 1]  # Invalid choice first, then valid
    result = _pick_authentication_method()
    assert result == "credentials"
    assert mock_prompt.call_count == 2
    mock_print_error.assert_called_once_with("Invalid selection. Please choose 1-3.")


@patch("typer.prompt")
@patch("t3api_utils.main.utils.print_error")
@patch("t3api_utils.main.utils.console.print")
def test_pick_authentication_method_keyboard_interrupt(mock_console, mock_print_error, mock_prompt):
    """Test authentication picker handles keyboard interrupt."""
    mock_prompt.side_effect = KeyboardInterrupt()
    with pytest.raises(Exit):
        _pick_authentication_method()
    mock_print_error.assert_called_once_with("Invalid input or operation cancelled.")


@patch("t3api_utils.main.utils._authenticate_with_credentials")
@patch("t3api_utils.main.utils._pick_authentication_method")
def test_get_authenticated_client_or_error_routes_to_credentials(mock_pick, mock_auth_creds):
    """Test main auth function routes to credentials authentication."""
    mock_pick.return_value = "credentials"
    mock_client = MagicMock()
    mock_auth_creds.return_value = mock_client

    result = get_authenticated_client_or_error()

    assert result == mock_client
    mock_pick.assert_called_once()
    mock_auth_creds.assert_called_once()


@patch("t3api_utils.main.utils._authenticate_with_jwt")
@patch("t3api_utils.main.utils._pick_authentication_method")
def test_get_authenticated_client_or_error_routes_to_jwt(mock_pick, mock_auth_jwt):
    """Test main auth function routes to JWT authentication."""
    mock_pick.return_value = "jwt"
    mock_client = MagicMock()
    mock_auth_jwt.return_value = mock_client

    result = get_authenticated_client_or_error()

    assert result == mock_client
    mock_pick.assert_called_once()
    mock_auth_jwt.assert_called_once()


@patch("t3api_utils.main.utils._authenticate_with_api_key")
@patch("t3api_utils.main.utils._pick_authentication_method")
def test_get_authenticated_client_or_error_routes_to_api_key(mock_pick, mock_auth_api_key):
    """Test main auth function routes to API key authentication."""
    mock_pick.return_value = "api_key"
    mock_client = MagicMock()
    mock_auth_api_key.return_value = mock_client

    result = get_authenticated_client_or_error()

    assert result == mock_client
    mock_pick.assert_called_once()
    mock_auth_api_key.assert_called_once()


@patch("t3api_utils.main.utils._pick_authentication_method")
def test_get_authenticated_client_or_error_unknown_method(mock_pick):
    """Test main auth function handles unknown authentication method."""
    mock_pick.return_value = "unknown"

    with pytest.raises(AuthenticationError, match="Unknown authentication method: unknown"):
        get_authenticated_client_or_error()

    mock_pick.assert_called_once()


@patch("t3api_utils.main.utils.console.print")
@patch("t3api_utils.main.utils.typer.prompt")
@patch("t3api_utils.main.utils.send_api_request")
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
@patch("t3api_utils.main.utils.send_api_request")
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
    mock_extract.return_value = [
        {"id": 1, "hostname": "test.com", "licenseNumber": "LIC-1", "dataModel": "TEST", "retrievedAt": "2023-01-01T00:00:00Z"},
        {"id": 2, "hostname": "test.com", "licenseNumber": "LIC-2", "dataModel": "TEST", "retrievedAt": "2023-01-01T00:00:00Z"}
    ]

    def fake_method(*args, **kwargs):
        pass

    result = load_collection(fake_method)
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2
    mock_parallel.assert_called_once()
    mock_extract.assert_called_once_with(responses=mock_response)


@patch("t3api_utils.main.utils.open_file")
@patch("t3api_utils.main.utils.save_dicts_to_json")
def test_save_collection_to_json_success(mock_save, mock_open):
    fake_obj = {"index": "my_model", "licenseNumber": "XYZ", "other": "data"}
    mock_save.return_value = Path("/tmp/output.json")

    result = save_collection_to_json(objects=[fake_obj], output_dir=".", open_after=True)

    assert result == Path("/tmp/output.json")
    mock_open.assert_called_once_with(path=Path("/tmp/output.json"))


@patch("t3api_utils.main.utils.open_file")
@patch("t3api_utils.main.utils.save_dicts_to_csv")
def test_save_collection_to_csv_success(mock_save, mock_open):
    fake_obj = {"index": "test", "licenseNumber": "LIC123", "other": "data"}
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


# File Picker Tests
class TestFilePickerUtilities:
    """Test file picker utility functions."""

    def test_format_file_size_bytes(self):
        """Test file size formatting for byte values."""
        assert _format_file_size(0) == "0 B"
        assert _format_file_size(512) == "512 B"
        assert _format_file_size(1023) == "1023 B"

    def test_format_file_size_kilobytes(self):
        """Test file size formatting for kilobyte values."""
        assert _format_file_size(1024) == "1.0 KB"
        assert _format_file_size(1536) == "1.5 KB"
        assert _format_file_size(1048575) == "1024.0 KB"

    def test_format_file_size_megabytes(self):
        """Test file size formatting for megabyte values."""
        assert _format_file_size(1048576) == "1.0 MB"
        assert _format_file_size(1572864) == "1.5 MB"

    def test_format_file_size_gigabytes(self):
        """Test file size formatting for gigabyte values."""
        assert _format_file_size(1073741824) == "1.0 GB"
        assert _format_file_size(2147483648) == "2.0 GB"

    @patch('t3api_utils.main.utils.datetime')
    def test_format_file_time_today(self, mock_datetime):
        """Test file time formatting for today's files."""
        from datetime import datetime
        now = datetime(2023, 12, 15, 14, 30, 0)
        mock_datetime.now.return_value = now
        mock_datetime.fromtimestamp.return_value = datetime(2023, 12, 15, 10, 15, 0)

        result = _format_file_time(1702638900.0)  # Mock timestamp
        assert result == "10:15"

    @patch('t3api_utils.main.utils.datetime')
    def test_format_file_time_this_year(self, mock_datetime):
        """Test file time formatting for files from this year."""
        from datetime import datetime
        now = datetime(2023, 12, 15, 14, 30, 0)
        mock_datetime.now.return_value = now
        mock_datetime.fromtimestamp.return_value = datetime(2023, 11, 10, 10, 15, 0)

        result = _format_file_time(1699610100.0)  # Mock timestamp
        assert result == "11-10"

    @patch('t3api_utils.main.utils.datetime')
    def test_format_file_time_previous_year(self, mock_datetime):
        """Test file time formatting for files from previous years."""
        from datetime import datetime
        now = datetime(2023, 12, 15, 14, 30, 0)
        mock_datetime.now.return_value = now
        mock_datetime.fromtimestamp.return_value = datetime(2022, 11, 10, 10, 15, 0)

        result = _format_file_time(1668074100.0)  # Mock timestamp
        assert result == "2022"

    @patch('t3api_utils.main.utils.datetime')
    def test_format_file_time_invalid_timestamp(self, mock_datetime):
        """Test file time formatting with invalid timestamp."""
        mock_datetime.fromtimestamp.side_effect = OSError("Invalid timestamp")
        result = _format_file_time(1234567890.0)
        assert result == "Unknown"

    @patch('t3api_utils.main.utils.Path')
    def test_discover_data_files_directory_not_exists(self, mock_path):
        """Test file discovery when directory doesn't exist."""
        mock_search_path = MagicMock()
        mock_search_path.exists.return_value = False
        mock_path.return_value.resolve.return_value = mock_search_path

        result = _discover_data_files(
            search_directory="/nonexistent",
            file_extensions=[".csv", ".json"]
        )

        assert result == []

    @patch('t3api_utils.main.utils.Path')
    def test_discover_data_files_with_files(self, mock_path):
        """Test file discovery with existing files."""
        # Setup mock files
        mock_file1 = MagicMock()
        mock_file1.parts = ("data", "file1.csv")
        mock_file1.stat.return_value.st_mtime = 1609459200.0  # 2021-01-01

        mock_file2 = MagicMock()
        mock_file2.parts = ("data", "file2.json")
        mock_file2.stat.return_value.st_mtime = 1609545600.0  # 2021-01-02

        mock_search_path = MagicMock()
        mock_search_path.exists.return_value = True
        mock_search_path.glob.side_effect = [
            [mock_file1],  # *.csv files
            [mock_file2]   # *.json files
        ]

        mock_path.return_value.resolve.return_value = mock_search_path

        result = _discover_data_files(
            search_directory="/data",
            file_extensions=[".csv", ".json"]
        )

        # Should return files sorted by modification time (newest first)
        assert len(result) == 2
        assert result[0] == mock_file2  # Newer file first
        assert result[1] == mock_file1

    @patch('t3api_utils.main.utils.Path')
    def test_discover_data_files_filters_hidden(self, mock_path):
        """Test that hidden files are filtered out."""
        mock_visible_file = MagicMock()
        mock_visible_file.parts = ("data", "file.csv")
        mock_visible_file.stat.return_value.st_mtime = 1609459200.0

        mock_hidden_file = MagicMock()
        mock_hidden_file.parts = ("data", ".hidden.csv")

        mock_search_path = MagicMock()
        mock_search_path.exists.return_value = True
        mock_search_path.glob.return_value = [mock_visible_file, mock_hidden_file]

        mock_path.return_value.resolve.return_value = mock_search_path

        result = _discover_data_files(
            search_directory="/data",
            file_extensions=[".csv"]
        )

        assert len(result) == 1
        assert result[0] == mock_visible_file

    def test_load_file_content_file_not_found(self):
        """Test loading content from non-existent file."""
        from pathlib import Path
        non_existent_path = Path("/nonexistent/file.csv")

        with pytest.raises(FileNotFoundError, match="File not found"):
            _load_file_content(non_existent_path)

    @patch('builtins.open')
    @patch('t3api_utils.main.utils.json.load')
    def test_load_file_content_json(self, mock_json_load, mock_open):
        """Test loading JSON file content."""
        from pathlib import Path

        mock_data = {"key": "value", "numbers": [1, 2, 3]}
        mock_json_load.return_value = mock_data

        # Mock Path methods
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        mock_path.suffix = ".json"
        mock_path.stat.return_value.st_size = 100

        result = _load_file_content(mock_path)

        assert result["content"] == mock_data
        assert result["format"] == "json"
        assert result["size"] == 100
        assert result["path"] == mock_path

    @patch('builtins.open')
    @patch('t3api_utils.main.utils.csv.DictReader')
    def test_load_file_content_csv(self, mock_csv_reader, mock_open):
        """Test loading CSV file content."""
        from pathlib import Path

        mock_data = [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]
        mock_csv_reader.return_value = iter(mock_data)

        # Mock Path methods
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        mock_path.suffix = ".csv"
        mock_path.stat.return_value.st_size = 50

        result = _load_file_content(mock_path)

        assert result["content"] == mock_data
        assert result["format"] == "csv"
        assert result["size"] == 50

    @patch('builtins.open')
    def test_load_file_content_txt(self, mock_open):
        """Test loading plain text file content."""
        from pathlib import Path

        mock_file = MagicMock()
        mock_file.read.return_value = "This is plain text content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock Path methods
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        mock_path.suffix = ".txt"
        mock_path.stat.return_value.st_size = 25

        result = _load_file_content(mock_path)

        assert result["content"] == "This is plain text content"
        assert result["format"] == "txt"

    @patch('builtins.open')
    @patch('t3api_utils.main.utils.json.loads')
    def test_load_file_content_jsonl(self, mock_json_loads, mock_open):
        """Test loading JSONL file content."""
        from pathlib import Path

        # Mock file content with JSON lines
        mock_file = MagicMock()
        mock_file.__iter__.return_value = ['{"id": 1}\n', '{"id": 2}\n', '\n']
        mock_open.return_value.__enter__.return_value = mock_file

        mock_json_loads.side_effect = [{"id": 1}, {"id": 2}]

        # Mock Path methods
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        mock_path.suffix = ".jsonl"
        mock_path.stat.return_value.st_size = 20

        result = _load_file_content(mock_path)

        assert result["content"] == [{"id": 1}, {"id": 2}]
        assert result["format"] == "jsonl"

    @patch('builtins.open')
    @patch('t3api_utils.main.utils.json.load')
    def test_load_file_content_invalid_json(self, mock_json_load, mock_open):
        """Test loading invalid JSON file."""
        import json
        from pathlib import Path

        mock_json_load.side_effect = json.JSONDecodeError("Invalid JSON", "doc", 0)

        # Mock Path methods
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        mock_path.suffix = ".json"

        with pytest.raises(ValueError, match="Invalid JSON in file"):
            _load_file_content(mock_path)


class TestPickFile:
    """Test the main pick_file function."""

    @patch('t3api_utils.main.utils.typer.prompt')
    @patch('t3api_utils.main.utils.console.print')
    @patch('t3api_utils.main.utils._discover_data_files')
    def test_pick_file_single_file_selection(self, mock_discover, mock_console, mock_prompt):
        """Test selecting a single file from the picker."""
        from pathlib import Path

        # Mock discovered file
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test.csv"
        mock_file.suffix = ".csv"
        mock_file.stat.return_value.st_size = 1024
        mock_file.stat.return_value.st_mtime = 1609459200.0
        mock_file.relative_to.return_value = Path("test.csv")

        mock_discover.return_value = [mock_file]
        mock_prompt.return_value = 1

        result = pick_file(load_content=False)

        assert result == mock_file
        mock_discover.assert_called_once()
        mock_prompt.assert_called_once_with("Select file (number)", type=int)

    @patch('t3api_utils.main.utils.typer.prompt')
    @patch('t3api_utils.main.utils.console.print')
    @patch('t3api_utils.main.utils._discover_data_files')
    @patch('t3api_utils.main.utils._load_file_content')
    def test_pick_file_with_content_loading(self, mock_load_content, mock_discover, mock_console, mock_prompt):
        """Test selecting a file and loading its content."""
        from pathlib import Path

        # Mock discovered file
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test.json"
        mock_file.suffix = ".json"
        mock_file.stat.return_value.st_size = 512
        mock_file.stat.return_value.st_mtime = 1609459200.0
        mock_file.relative_to.return_value = Path("test.json")

        mock_discover.return_value = [mock_file]
        mock_prompt.return_value = 1

        mock_file_data = {
            "path": mock_file,
            "content": {"key": "value"},
            "format": "json",
            "size": 512
        }
        mock_load_content.return_value = mock_file_data

        result = pick_file(load_content=True)

        assert result == mock_file_data
        mock_load_content.assert_called_once_with(mock_file)

    @patch('t3api_utils.main.utils._handle_custom_path_input')
    @patch('t3api_utils.main.utils.typer.prompt')
    @patch('t3api_utils.main.utils.console.print')
    @patch('t3api_utils.main.utils._discover_data_files')
    def test_pick_file_custom_path_selection(self, mock_discover, mock_console, mock_prompt, mock_custom_path):
        """Test selecting the custom path option."""
        from pathlib import Path

        # Mock one regular file plus custom option
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test.csv"
        mock_file.suffix = ".csv"
        mock_file.stat.return_value.st_size = 1024
        mock_file.stat.return_value.st_mtime = 1609459200.0
        mock_file.relative_to.return_value = Path("test.csv")

        mock_discover.return_value = [mock_file]
        mock_prompt.return_value = 2  # Select custom path option

        mock_custom_file = Path("/custom/path/file.json")
        mock_custom_path.return_value = mock_custom_file

        result = pick_file(allow_custom_path=True, load_content=False)

        assert result == mock_custom_file
        mock_custom_path.assert_called_once_with(load_content=False)

    @patch('t3api_utils.main.utils.print_error')
    @patch('t3api_utils.main.utils._discover_data_files')
    def test_pick_file_no_files_no_custom_path(self, mock_discover, mock_print_error):
        """Test behavior when no files found and custom path disabled."""
        mock_discover.return_value = []

        with pytest.raises(Exit):
            pick_file(allow_custom_path=False)

        mock_print_error.assert_called_once_with("No data files found in the specified directory.")

    @patch('t3api_utils.main.utils.typer.prompt')
    @patch('t3api_utils.main.utils._handle_custom_path_input')
    @patch('t3api_utils.main.utils.console.print')
    @patch('t3api_utils.main.utils._discover_data_files')
    def test_pick_file_no_files_with_custom_path(self, mock_discover, mock_console, mock_custom_path, mock_prompt):
        """Test behavior when no files found but custom path enabled."""
        from pathlib import Path

        mock_discover.return_value = []
        mock_custom_file = Path("/custom/file.csv")
        mock_custom_path.return_value = mock_custom_file
        mock_prompt.return_value = 1  # Select the only option (custom path)

        result = pick_file(allow_custom_path=True)

        assert result == mock_custom_file
        mock_custom_path.assert_called_once_with(load_content=False)

    @patch('t3api_utils.main.utils.typer.prompt')
    @patch('t3api_utils.main.utils.console.print')
    @patch('t3api_utils.main.utils._discover_data_files')
    def test_pick_file_invalid_selection(self, mock_discover, mock_console, mock_prompt):
        """Test handling invalid file selection."""
        from pathlib import Path

        mock_file = MagicMock(spec=Path)
        mock_file.name = "test.csv"
        mock_file.suffix = ".csv"
        mock_file.stat.return_value.st_size = 1024
        mock_file.stat.return_value.st_mtime = 1609459200.0
        mock_file.relative_to.return_value = Path("test.csv")

        mock_discover.return_value = [mock_file]
        mock_prompt.side_effect = [99, 1]  # Invalid selection first, then valid

        result = pick_file(load_content=False)

        assert result == mock_file
        assert mock_prompt.call_count == 2

    @patch('t3api_utils.main.utils.typer.prompt')
    @patch('t3api_utils.main.utils._discover_data_files')
    def test_pick_file_keyboard_interrupt(self, mock_discover, mock_prompt):
        """Test handling keyboard interrupt."""
        from pathlib import Path

        # Mock file with proper string returns for rendering
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test.csv"
        mock_file.suffix = ".csv"
        mock_file.stat.return_value.st_size = 1024
        mock_file.stat.return_value.st_mtime = 1609459200.0
        mock_file.relative_to.return_value = Path("test.csv")

        mock_discover.return_value = [mock_file]
        mock_prompt.side_effect = KeyboardInterrupt()

        with pytest.raises(Exit):
            pick_file()

    def test_pick_file_with_custom_extensions(self):
        """Test pick_file with custom file extensions."""
        with patch('t3api_utils.main.utils._discover_data_files') as mock_discover:
            mock_discover.return_value = []

            with pytest.raises(Exit):
                pick_file(
                    file_extensions=[".xml", ".yaml"],
                    allow_custom_path=False
                )

            mock_discover.assert_called_once_with(
                search_directory=".",
                file_extensions=[".xml", ".yaml"],
                include_subdirectories=False
            )

    def test_pick_file_include_subdirectories(self):
        """Test pick_file with subdirectory search enabled."""
        with patch('t3api_utils.main.utils._discover_data_files') as mock_discover:
            mock_discover.return_value = []

            with pytest.raises(Exit):
                pick_file(
                    search_directory="/data",
                    include_subdirectories=True,
                    allow_custom_path=False
                )

            mock_discover.assert_called_once_with(
                search_directory="/data",
                file_extensions=[".csv", ".json", ".txt", ".tsv", ".jsonl"],
                include_subdirectories=True
            )


class TestMatchCollectionFromCSV:
    """Test the collection matching functionality."""

    def setup_method(self):
        """Set up test data for each test."""
        self.sample_collection = [
            {"id": 123, "name": "ProductA", "status": "Active", "category": "Electronics",
             "hostname": "ca.metrc.com", "licenseNumber": "CUL00001", "dataModel": "PACKAGE", "retrievedAt": "2025-09-23T13:19:22.734Z"},
            {"id": 456, "name": "ProductB", "status": "Inactive", "category": "Clothing",
             "hostname": "ca.metrc.com", "licenseNumber": "CUL00001", "dataModel": "PACKAGE", "retrievedAt": "2025-09-23T13:19:22.734Z"},
            {"id": 789, "name": "ProductC", "status": "Active", "category": "Electronics",
             "hostname": "ca.metrc.com", "licenseNumber": "CUL00001", "dataModel": "PACKAGE", "retrievedAt": "2025-09-23T13:19:22.734Z"},
            {"id": 101, "name": "ProductD", "status": "Active", "category": "Books",
             "hostname": "ca.metrc.com", "licenseNumber": "CUL00001", "dataModel": "PACKAGE", "retrievedAt": "2025-09-23T13:19:22.734Z"}
        ]

        self.valid_csv_content = [
            {"id": "123", "status": "Active"},
            {"id": "789", "status": "Active"}
        ]

        self.invalid_csv_content = [
            {"unknown_field": "123", "status": "Active"}
        ]

    @patch('t3api_utils.main.utils.pick_file')
    def test_successful_matching(self, mock_pick_file):
        """Test successful CSV matching with valid data."""
        mock_pick_file.return_value = {
            "content": self.valid_csv_content,
            "format": "csv",
            "path": Path("/test/file.csv")
        }

        result = match_collection_from_csv(
            data=self.sample_collection
        )

        # Should return 2 matching items
        assert len(result) == 2
        assert result[0]["id"] == 123
        assert result[1]["id"] == 789
        mock_pick_file.assert_called_once()

    @patch('t3api_utils.main.utils.pick_file')
    def test_column_validation_error(self, mock_pick_file):
        """Test error when CSV columns don't match collection fields."""
        mock_pick_file.return_value = {
            "content": self.invalid_csv_content,
            "format": "csv",
            "path": Path("/test/file.csv")
        }

        with pytest.raises(ValueError, match="CSV columns not found in collection"):
            match_collection_from_csv(
                data=self.sample_collection
            )

    @patch('t3api_utils.main.utils.pick_file')
    def test_no_matches_warn_behavior(self, mock_pick_file):
        """Test behavior when no matches found with warn setting."""
        no_match_csv = [{"id": "999", "status": "Unknown"}]
        mock_pick_file.return_value = {
            "content": no_match_csv,
            "format": "csv",
            "path": Path("/test/file.csv")
        }

        result = match_collection_from_csv(
            data=self.sample_collection,
            on_no_match="warn"
        )

        # Should return empty list
        assert result == []

    @patch('t3api_utils.main.utils.pick_file')
    def test_no_matches_error_behavior(self, mock_pick_file):
        """Test error behavior when no matches found with error setting."""
        no_match_csv = [{"id": "999", "status": "Unknown"}]
        mock_pick_file.return_value = {
            "content": no_match_csv,
            "format": "csv",
            "path": Path("/test/file.csv")
        }

        with pytest.raises(ValueError, match="No match found for CSV row"):
            match_collection_from_csv(
                data=self.sample_collection,
                on_no_match="error"
            )

    @patch('t3api_utils.main.utils.pick_file')
    def test_no_matches_skip_behavior(self, mock_pick_file):
        """Test skip behavior when no matches found."""
        mixed_csv = [
            {"id": "123", "status": "Active"},  # This will match
            {"id": "999", "status": "Unknown"}  # This won't match
        ]
        mock_pick_file.return_value = {
            "content": mixed_csv,
            "format": "csv",
            "path": Path("/test/file.csv")
        }

        result = match_collection_from_csv(
            data=self.sample_collection,
            on_no_match="skip"
        )

        # Should return only the matching item
        assert len(result) == 1
        assert result[0]["id"] == 123

    @patch('t3api_utils.main.utils.pick_file')
    def test_multiple_field_matching(self, mock_pick_file):
        """Test matching on multiple CSV fields."""
        multi_field_csv = [
            {"id": "123", "name": "ProductA", "status": "Active"},
            {"id": "456", "name": "ProductB", "status": "Active"}  # Wrong status, won't match
        ]
        mock_pick_file.return_value = {
            "content": multi_field_csv,
            "format": "csv",
            "path": Path("/test/file.csv")
        }

        result = match_collection_from_csv(
            data=self.sample_collection
        )

        # Only first row should match (ProductB has wrong status)
        assert len(result) == 1
        assert result[0]["id"] == 123

    @patch('t3api_utils.main.utils.pick_file')
    def test_duplicate_removal(self, mock_pick_file):
        """Test that duplicate matches are removed."""
        duplicate_csv = [
            {"status": "Active"},  # This will match multiple items
            {"category": "Electronics"}  # This will also match multiple items
        ]
        mock_pick_file.return_value = {
            "content": duplicate_csv,
            "format": "csv",
            "path": Path("/test/file.csv")
        }

        result = match_collection_from_csv(
            data=self.sample_collection
        )

        # Should have unique items only (no duplicates)
        ids = [item["id"] for item in result]
        assert len(ids) == len(set(ids))  # No duplicates

    def test_empty_collection_error(self):
        """Test error when collection is empty."""
        with pytest.raises(ValueError, match="Collection data cannot be empty"):
            match_collection_from_csv(
                data=[]
            )

    @patch('t3api_utils.main.utils.pick_file')
    def test_empty_csv_error(self, mock_pick_file):
        """Test error when CSV is empty."""
        mock_pick_file.return_value = {
            "content": [],
            "format": "csv",
            "path": Path("/test/file.csv")
        }

        with pytest.raises(ValueError, match="CSV file contains no data"):
            match_collection_from_csv(
                data=self.sample_collection
            )

    @patch('t3api_utils.main.utils.pick_file')
    def test_invalid_csv_format_error(self, mock_pick_file):
        """Test error when CSV format is invalid."""
        mock_pick_file.return_value = {
            "content": "invalid_format",
            "format": "csv",
            "path": Path("/test/file.csv")
        }

        with pytest.raises(ValueError, match="CSV must contain headers and data rows"):
            match_collection_from_csv(
                data=self.sample_collection
            )

    @patch('t3api_utils.main.utils.pick_file')
    def test_file_selection_cancelled(self, mock_pick_file):
        """Test behavior when file selection is cancelled."""
        mock_pick_file.side_effect = Exit(code=1)

        with pytest.raises(Exit):
            match_collection_from_csv(
                data=self.sample_collection
            )

    @patch('t3api_utils.main.utils.pick_file')
    def test_string_conversion_matching(self, mock_pick_file):
        """Test that values are converted to strings for comparison."""
        # Collection with mixed types
        mixed_collection = [
            {"id": 123, "name": "Product", "active": True,
             "hostname": "ca.metrc.com", "licenseNumber": "CUL00001", "dataModel": "PACKAGE", "retrievedAt": "2025-09-23T13:19:22.734Z"},
            {"id": 456, "name": "Service", "active": False,
             "hostname": "ca.metrc.com", "licenseNumber": "CUL00001", "dataModel": "PACKAGE", "retrievedAt": "2025-09-23T13:19:22.734Z"}
        ]

        # CSV with string values
        string_csv = [
            {"id": "123", "active": "True"}
        ]

        mock_pick_file.return_value = {
            "content": string_csv,
            "format": "csv",
            "path": Path("/test/file.csv")
        }

        result = match_collection_from_csv(
            data=mixed_collection
        )

        # Should match due to string conversion
        assert len(result) == 1
        assert result[0]["id"] == 123
