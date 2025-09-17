from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
from typer import Exit

from t3api_utils.main.utils import (
    get_authenticated_client_or_error,
    pick_license,
    load_collection,
    save_collection_to_json,
    save_collection_to_csv,
)
from t3api_utils.interfaces import SerializableObject


@patch("t3api_utils.main.utils.create_credentials_authenticated_client_or_error")
@patch("t3api_utils.main.utils.resolve_auth_inputs_or_error")
def test_get_authenticated_client_or_error(mock_resolve, mock_create_client):
    fake_inputs = {
        "hostname": "mo.metrc.com",
        "username": "user",
        "password": "pass",
    }
    mock_client = MagicMock(name="authenticated_client")
    mock_resolve.return_value = fake_inputs
    mock_create_client.return_value = mock_client

    result = get_authenticated_client_or_error()

    mock_resolve.assert_called_once()
    mock_create_client.assert_called_once_with(**fake_inputs)
    assert result == mock_client


@patch("t3api_utils.main.utils.console.print")
@patch("t3api_utils.main.utils.typer.prompt")
def test_pick_license_valid_choice(mock_prompt, mock_console):
    from t3api_utils.api.models import License, LicensesResponse

    mock_client = MagicMock()
    license1 = License(id="1", license_number="123", legal_name="Alpha")
    license2 = License(id="2", license_number="456", legal_name="Beta")
    mock_response = LicensesResponse(data=[license1, license2], total=2, page=1, page_size=100)
    mock_client.get_licenses.return_value = mock_response
    mock_prompt.return_value = 2

    result = pick_license(api_client=mock_client)
    assert result == license2


@patch("t3api_utils.main.utils.typer.echo")
def test_pick_license_empty_list(mock_echo):
    from t3api_utils.api.models import LicensesResponse

    mock_client = MagicMock()
    mock_response = LicensesResponse(data=[], total=0, page=1, page_size=100)
    mock_client.get_licenses.return_value = mock_response

    with pytest.raises(Exit):
        pick_license(api_client=mock_client)

    mock_echo.assert_called_once_with("No licenses found.")


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
    mock_extract.assert_called_once_with(mock_response)


@patch("t3api_utils.main.utils.open_file")
@patch("t3api_utils.main.utils.save_dicts_to_json")
@patch("t3api_utils.main.utils.collection_to_dicts")
def test_save_collection_to_json_success(mock_convert, mock_save, mock_open):
    fake_obj = MagicMock(spec=SerializableObject)
    fake_obj.index = "my_model"
    fake_obj.license_number = "XYZ"
    mock_convert.return_value = [{"some": "dict"}]
    mock_save.return_value = Path("/tmp/output.json")

    result = save_collection_to_json([fake_obj], open_after=True)

    assert result == Path("/tmp/output.json")
    mock_open.assert_called_once_with(Path("/tmp/output.json"))


@patch("t3api_utils.main.utils.open_file")
@patch("t3api_utils.main.utils.save_dicts_to_csv")
@patch("t3api_utils.main.utils.collection_to_dicts")
def test_save_collection_to_csv_success(mock_convert, mock_save, mock_open):
    fake_obj = MagicMock(spec=SerializableObject)
    fake_obj.index = "test"
    fake_obj.license_number = "LIC123"
    mock_convert.return_value = [{"some": "dict"}]
    mock_save.return_value = Path("/tmp/output.csv")

    result = save_collection_to_csv([fake_obj], open_after=True, strip_empty_columns=True)

    assert result == Path("/tmp/output.csv")
    mock_open.assert_called_once_with(Path("/tmp/output.csv"))


def test_save_collection_to_json_raises_on_empty():
    with pytest.raises(ValueError, match="Cannot serialize an empty list of objects"):
        save_collection_to_json([])


def test_save_collection_to_csv_raises_on_empty():
    with pytest.raises(ValueError, match="Cannot serialize an empty list of objects"):
        save_collection_to_csv([])
