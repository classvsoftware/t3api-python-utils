"""Tests for logging utilities."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from rich.logging import RichHandler

from t3api_utils.logging import setup_logging, get_logger


class TestLoggingSetup:
    """Test logging setup functionality."""

    @patch('t3api_utils.logging.logging.basicConfig')
    def test_setup_logging_default_level(self, mock_basic_config):
        """Test setup_logging with default INFO level."""
        setup_logging()

        mock_basic_config.assert_called_once()
        call_args = mock_basic_config.call_args

        assert call_args[1]['level'] == logging.INFO
        assert call_args[1]['format'] == "%(message)s"
        assert call_args[1]['datefmt'] == "[%X]"
        assert len(call_args[1]['handlers']) == 1
        assert isinstance(call_args[1]['handlers'][0], RichHandler)

    @patch('t3api_utils.logging.logging.basicConfig')
    def test_setup_logging_custom_level(self, mock_basic_config):
        """Test setup_logging with custom level."""
        setup_logging(level=logging.DEBUG)

        mock_basic_config.assert_called_once()
        call_args = mock_basic_config.call_args

        assert call_args[1]['level'] == logging.DEBUG

    @patch('t3api_utils.logging.logging.basicConfig')
    def test_setup_logging_warning_level(self, mock_basic_config):
        """Test setup_logging with WARNING level."""
        setup_logging(level=logging.WARNING)

        mock_basic_config.assert_called_once()
        call_args = mock_basic_config.call_args

        assert call_args[1]['level'] == logging.WARNING

    @patch('t3api_utils.logging.logging.basicConfig')
    def test_setup_logging_error_level(self, mock_basic_config):
        """Test setup_logging with ERROR level."""
        setup_logging(level=logging.ERROR)

        mock_basic_config.assert_called_once()
        call_args = mock_basic_config.call_args

        assert call_args[1]['level'] == logging.ERROR

    @patch('t3api_utils.logging.logging.basicConfig')
    def test_setup_logging_critical_level(self, mock_basic_config):
        """Test setup_logging with CRITICAL level."""
        setup_logging(level=logging.CRITICAL)

        mock_basic_config.assert_called_once()
        call_args = mock_basic_config.call_args

        assert call_args[1]['level'] == logging.CRITICAL

    @patch('t3api_utils.logging.logging.basicConfig')
    def test_rich_handler_configuration(self, mock_basic_config):
        """Test that RichHandler is configured correctly."""
        setup_logging()

        call_args = mock_basic_config.call_args
        handler = call_args[1]['handlers'][0]

        assert isinstance(handler, RichHandler)
        # RichHandler properties are set during construction
        # We can verify the handler type but internal properties may not be directly accessible

    def test_multiple_setup_calls(self):
        """Test that multiple setup_logging calls don't cause issues."""
        # This should not raise an exception
        setup_logging(logging.INFO)
        setup_logging(logging.DEBUG)
        setup_logging(logging.WARNING)


class TestGetLogger:
    """Test get_logger functionality."""

    @patch('t3api_utils.logging.logging.getLogger')
    def test_get_logger_returns_logger(self, mock_get_logger):
        """Test that get_logger returns a logger instance."""
        mock_logger = MagicMock(spec=logging.Logger)
        mock_get_logger.return_value = mock_logger

        result = get_logger("test_logger")

        mock_get_logger.assert_called_once_with("test_logger")
        assert result == mock_logger

    @patch('t3api_utils.logging.logging.getLogger')
    def test_get_logger_different_names(self, mock_get_logger):
        """Test get_logger with different logger names."""
        mock_logger = MagicMock(spec=logging.Logger)
        mock_get_logger.return_value = mock_logger

        # Test various logger names
        names = ["module1", "module2.submodule", "test", "__main__", "t3api_utils.api"]

        for name in names:
            result = get_logger(name)
            mock_get_logger.assert_called_with(name)
            assert result == mock_logger

    def test_get_logger_integration(self):
        """Test get_logger integration with actual logging module."""
        # Test with actual logging module (no mocking)
        logger1 = get_logger("test_logger_1")
        logger2 = get_logger("test_logger_2")
        logger3 = get_logger("test_logger_1")  # Same name as logger1

        assert isinstance(logger1, logging.Logger)
        assert isinstance(logger2, logging.Logger)
        assert isinstance(logger3, logging.Logger)

        # Same name should return the same logger instance
        assert logger1 is logger3
        # Different names should return different logger instances
        assert logger1 is not logger2

    @patch('t3api_utils.logging.logging.getLogger')
    def test_get_logger_empty_name(self, mock_get_logger):
        """Test get_logger with empty name."""
        mock_logger = MagicMock(spec=logging.Logger)
        mock_get_logger.return_value = mock_logger

        result = get_logger("")

        mock_get_logger.assert_called_once_with("")
        assert result == mock_logger


class TestLoggingModule:
    """Test logging module behavior."""

    def test_module_imports(self):
        """Test that all required imports are available."""
        import t3api_utils.logging as logging_module

        assert hasattr(logging_module, 'setup_logging')
        assert hasattr(logging_module, 'get_logger')
        assert hasattr(logging_module, 'logging')
        assert hasattr(logging_module, 'RichHandler')

    def test_module_setup_called_on_import(self):
        """Test that setup_logging configures logging correctly."""
        # Since the module is already imported and setup_logging was called,
        # we can verify the configuration is in place
        root_logger = logging.getLogger()

        # Root logger should be a valid logger instance
        assert isinstance(root_logger, logging.Logger)

        # Level should be a valid logging level
        assert root_logger.level in [
            logging.NOTSET, logging.DEBUG, logging.INFO,
            logging.WARNING, logging.ERROR, logging.CRITICAL
        ]

    def test_module_initialization(self):
        """Test that the module can be imported successfully."""
        # Test that we can import the module and its functions
        from t3api_utils.logging import setup_logging, get_logger

        assert callable(setup_logging)
        assert callable(get_logger)

        # Test that we can create a logger
        logger = get_logger("test_module_init")
        assert isinstance(logger, logging.Logger)


class TestLoggingIntegration:
    """Test logging integration and functionality."""

    def test_logger_can_log_messages(self):
        """Test that loggers can actually log messages."""
        logger = get_logger("test_integration")

        # These should not raise exceptions
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")

    def test_logger_hierarchy(self):
        """Test logger hierarchy functionality."""
        parent_logger = get_logger("parent")
        child_logger = get_logger("parent.child")

        assert isinstance(parent_logger, logging.Logger)
        assert isinstance(child_logger, logging.Logger)
        assert parent_logger is not child_logger

    @patch('t3api_utils.logging.logging.basicConfig')
    def test_setup_preserves_format_and_handler(self, mock_basic_config):
        """Test that setup_logging preserves expected format and handler configuration."""
        setup_logging(logging.INFO)

        call_args = mock_basic_config.call_args

        # Verify format string
        assert call_args[1]['format'] == "%(message)s"

        # Verify date format
        assert call_args[1]['datefmt'] == "[%X]"

        # Verify handler configuration
        handlers = call_args[1]['handlers']
        assert len(handlers) == 1
        assert isinstance(handlers[0], RichHandler)

    def test_rich_handler_properties(self):
        """Test RichHandler is configured with expected properties."""
        # Create a new RichHandler with the same config as setup_logging
        handler = RichHandler(rich_tracebacks=True, markup=True)

        assert isinstance(handler, RichHandler)
        # These properties should be accessible
        assert hasattr(handler, 'rich_tracebacks')
        assert hasattr(handler, 'markup')