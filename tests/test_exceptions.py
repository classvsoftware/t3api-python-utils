"""Tests for custom exceptions."""

import pytest

from t3api_utils.exceptions import AuthenticationError


class TestAuthenticationError:
    """Test AuthenticationError exception."""

    def test_authentication_error_creation(self):
        """Test creating an AuthenticationError."""
        error = AuthenticationError("Authentication failed")

        assert isinstance(error, Exception)
        assert isinstance(error, AuthenticationError)
        assert str(error) == "Authentication failed"

    def test_authentication_error_empty_message(self):
        """Test creating an AuthenticationError with empty message."""
        error = AuthenticationError("")

        assert isinstance(error, AuthenticationError)
        assert str(error) == ""

    def test_authentication_error_no_message(self):
        """Test creating an AuthenticationError with no message."""
        error = AuthenticationError()

        assert isinstance(error, AuthenticationError)
        assert str(error) == ""

    def test_authentication_error_with_args(self):
        """Test creating an AuthenticationError with multiple arguments."""
        error = AuthenticationError("Authentication failed", "Invalid credentials", 401)

        assert isinstance(error, AuthenticationError)
        assert error.args == ("Authentication failed", "Invalid credentials", 401)

    def test_authentication_error_inheritance(self):
        """Test that AuthenticationError inherits from Exception."""
        error = AuthenticationError("Test error")

        assert isinstance(error, Exception)
        assert issubclass(AuthenticationError, Exception)

    def test_authentication_error_can_be_raised(self):
        """Test that AuthenticationError can be raised and caught."""
        with pytest.raises(AuthenticationError) as exc_info:
            raise AuthenticationError("Test authentication failure")

        assert str(exc_info.value) == "Test authentication failure"
        assert exc_info.type == AuthenticationError

    def test_authentication_error_caught_as_exception(self):
        """Test that AuthenticationError can be caught as generic Exception."""
        with pytest.raises(Exception) as exc_info:
            raise AuthenticationError("Generic exception test")

        assert isinstance(exc_info.value, AuthenticationError)
        assert str(exc_info.value) == "Generic exception test"

    def test_authentication_error_with_complex_message(self):
        """Test AuthenticationError with complex error message."""
        complex_message = (
            "Authentication failed: Invalid JWT token. "
            "Token may be expired or malformed. "
            "Please re-authenticate and try again."
        )
        error = AuthenticationError(complex_message)

        assert str(error) == complex_message

    def test_authentication_error_repr(self):
        """Test AuthenticationError string representation."""
        error = AuthenticationError("Test message")

        # Should have a valid repr
        repr_str = repr(error)
        assert "AuthenticationError" in repr_str
        assert "Test message" in repr_str

    def test_authentication_error_with_numeric_message(self):
        """Test AuthenticationError with numeric arguments."""
        error = AuthenticationError(401)

        assert isinstance(error, AuthenticationError)
        assert error.args == (401,)

    def test_authentication_error_equality(self):
        """Test AuthenticationError equality comparison."""
        error1 = AuthenticationError("Same message")
        error2 = AuthenticationError("Same message")
        error3 = AuthenticationError("Different message")

        # Exception instances are compared by identity, not content
        assert error1 != error2  # Different instances
        assert error1 != error3  # Different instances and messages

    def test_authentication_error_with_dict_message(self):
        """Test AuthenticationError with dictionary as message."""
        error_dict = {"code": 401, "message": "Unauthorized", "details": "Invalid token"}
        error = AuthenticationError(error_dict)

        assert isinstance(error, AuthenticationError)
        assert error.args == (error_dict,)

    def test_authentication_error_chaining(self):
        """Test AuthenticationError with exception chaining."""
        original_error = ValueError("Original error")

        try:
            raise original_error
        except ValueError as e:
            with pytest.raises(AuthenticationError) as exc_info:
                raise AuthenticationError("Authentication failed") from e

            assert exc_info.value.__cause__ == original_error

    def test_authentication_error_context_manager(self):
        """Test AuthenticationError within context manager."""
        caught_exception = None

        try:
            with pytest.raises(AuthenticationError):
                raise AuthenticationError("Context test")
        except Exception as e:
            caught_exception = e

        # Should not reach here since pytest.raises handles it
        assert caught_exception is None


class TestExceptionsModule:
    """Test exceptions module structure."""

    def test_module_exports(self):
        """Test that exceptions module exports expected classes."""
        import t3api_utils.exceptions as exceptions_module

        assert hasattr(exceptions_module, 'AuthenticationError')
        assert exceptions_module.AuthenticationError is AuthenticationError

    def test_module_imports(self):
        """Test that we can import exceptions directly."""
        from t3api_utils.exceptions import AuthenticationError as ImportedAuth

        assert ImportedAuth is AuthenticationError

    def test_module_structure(self):
        """Test exceptions module structure."""
        import t3api_utils.exceptions as exceptions_module

        # Should be a module
        assert hasattr(exceptions_module, '__name__')
        assert exceptions_module.__name__ == 't3api_utils.exceptions'

        # Should have the AuthenticationError class
        assert hasattr(exceptions_module, 'AuthenticationError')
        assert callable(exceptions_module.AuthenticationError)


class TestAuthenticationErrorUsagePatterns:
    """Test common usage patterns for AuthenticationError."""

    def test_http_401_pattern(self):
        """Test typical HTTP 401 error pattern."""
        def authenticate_user(token):
            if not token or token == "invalid":
                raise AuthenticationError("Invalid or missing authentication token")
            return {"user": "test_user"}

        # Valid authentication
        result = authenticate_user("valid_token")
        assert result["user"] == "test_user"

        # Invalid authentication
        with pytest.raises(AuthenticationError):
            authenticate_user("invalid")

        with pytest.raises(AuthenticationError):
            authenticate_user(None)

    def test_jwt_validation_pattern(self):
        """Test JWT validation error pattern."""
        def validate_jwt(jwt_token):
            if not jwt_token:
                raise AuthenticationError("JWT token is required")
            if jwt_token == "expired":
                raise AuthenticationError("JWT token has expired")
            if jwt_token == "malformed":
                raise AuthenticationError("JWT token is malformed")
            return {"sub": "user123", "exp": 1234567890}

        # Valid token
        result = validate_jwt("valid.jwt.token")
        assert result["sub"] == "user123"

        # Various error conditions
        with pytest.raises(AuthenticationError, match="is required"):
            validate_jwt("")

        with pytest.raises(AuthenticationError, match="has expired"):
            validate_jwt("expired")

        with pytest.raises(AuthenticationError, match="is malformed"):
            validate_jwt("malformed")

    def test_api_client_pattern(self):
        """Test API client authentication error pattern."""
        class MockAPIClient:
            def __init__(self, api_key):
                if not api_key:
                    raise AuthenticationError("API key is required for authentication")
                self.api_key = api_key

            def make_request(self):
                if self.api_key == "invalid":
                    raise AuthenticationError("API key is invalid or has been revoked")
                return {"status": "success"}

        # Valid client
        client = MockAPIClient("valid_key")
        result = client.make_request()
        assert result["status"] == "success"

        # Missing API key
        with pytest.raises(AuthenticationError, match="is required"):
            MockAPIClient("")

        # Invalid API key
        client = MockAPIClient("invalid")
        with pytest.raises(AuthenticationError, match="is invalid"):
            client.make_request()

    def test_credentials_validation_pattern(self):
        """Test credentials validation error pattern."""
        def validate_credentials(username, password):
            if not username or not password:
                raise AuthenticationError("Both username and password are required")
            if username == "admin" and password == "wrong":
                raise AuthenticationError("Invalid credentials for user 'admin'")
            return {"user_id": 123, "username": username}

        # Valid credentials
        result = validate_credentials("testuser", "testpass")
        assert result["username"] == "testuser"

        # Missing credentials
        with pytest.raises(AuthenticationError, match="are required"):
            validate_credentials("", "password")

        with pytest.raises(AuthenticationError, match="are required"):
            validate_credentials("username", "")

        # Wrong credentials
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            validate_credentials("admin", "wrong")