from unittest.mock import MagicMock, patch

from t3api_utils.main import utils


@patch("t3api_utils.auth.utils.create_credentials_authenticated_client")
@patch("t3api_utils.cli.utils.resolve_auth_inputs_or_error")
def test_get_authenticated_client(mock_resolve, mock_create_client):
    fake_inputs = {
        "hostname": "mo.metrc.com",
        "username": "user",
        "password": "pass",
    }
    mock_client = MagicMock(name="ApiClient")
    mock_resolve.return_value = fake_inputs
    mock_create_client.return_value = mock_client

    # Act
    result = utils.get_authenticated_client()

    # Assert
    mock_resolve.assert_called_once()
    mock_create_client.assert_called_once_with(**fake_inputs)
    assert result == mock_client
