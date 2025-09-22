"""Tests for style utilities including messages and styles."""

from unittest.mock import MagicMock, patch
import pytest

from t3api_utils.style.messages import (
    print_success, print_error, print_warning, print_info, print_progress,
    print_header, print_subheader, print_menu_item, print_file_path,
    print_technical, print_data, print_labeled_info, print_state_info
)
from t3api_utils.style.styles import (
    SUCCESS_SYMBOL, ERROR_SYMBOL, WARNING_SYMBOL, INFO_SYMBOL, PROGRESS_SYMBOL,
    MAIN_HEADER_PREFIX, MAIN_HEADER_SUFFIX, SUB_HEADER_PREFIX, SUB_HEADER_SUFFIX,
    MENU_NUMBER
)


class TestStyleMessages:
    """Test style message functions."""

    @patch('t3api_utils.style.messages.console')
    def test_print_success(self, mock_console):
        """Test success message printing."""
        print_success("Operation completed")
        mock_console.print.assert_called_once_with(f"{SUCCESS_SYMBOL} Operation completed")

    @patch('t3api_utils.style.messages.console')
    def test_print_error(self, mock_console):
        """Test error message printing."""
        print_error("Something went wrong")
        mock_console.print.assert_called_once_with(f"{ERROR_SYMBOL} Something went wrong")

    @patch('t3api_utils.style.messages.console')
    def test_print_warning(self, mock_console):
        """Test warning message printing."""
        print_warning("This is a warning")
        mock_console.print.assert_called_once_with(f"{WARNING_SYMBOL} This is a warning")

    @patch('t3api_utils.style.messages.console')
    def test_print_info(self, mock_console):
        """Test info message printing."""
        print_info("Here's some info")
        mock_console.print.assert_called_once_with(f"{INFO_SYMBOL} Here's some info")

    @patch('t3api_utils.style.messages.console')
    def test_print_progress(self, mock_console):
        """Test progress message printing."""
        print_progress("Processing...")
        mock_console.print.assert_called_once_with(f"{PROGRESS_SYMBOL} Processing...")

    @patch('t3api_utils.style.messages.console')
    def test_print_header(self, mock_console):
        """Test main header printing."""
        print_header("Main Title")
        expected = f"{MAIN_HEADER_PREFIX} Main Title {MAIN_HEADER_SUFFIX}"
        mock_console.print.assert_called_once_with(expected)

    @patch('t3api_utils.style.messages.console')
    def test_print_subheader(self, mock_console):
        """Test subheader printing."""
        print_subheader("Section Title")
        expected = f"{SUB_HEADER_PREFIX} Section Title {SUB_HEADER_SUFFIX}"
        mock_console.print.assert_called_once_with(expected)

    @patch('t3api_utils.style.messages.console')
    def test_print_menu_item(self, mock_console):
        """Test menu item printing."""
        print_menu_item(1, "First Option")
        formatted_number = MENU_NUMBER.format(number=1)
        expected = f"  {formatted_number} First Option"
        mock_console.print.assert_called_once_with(expected)

    @patch('t3api_utils.style.messages.console')
    def test_print_file_path(self, mock_console):
        """Test file path printing."""
        print_file_path("/path/to/file.txt")
        mock_console.print.assert_called_once_with("[cyan]/path/to/file.txt[/cyan]")

    @patch('t3api_utils.style.messages.console')
    def test_print_file_path_with_pathlib(self, mock_console):
        """Test file path printing with pathlib Path object."""
        from pathlib import Path
        path = Path("/path/to/file.txt")
        print_file_path(path)
        mock_console.print.assert_called_once_with(f"[cyan]{path}[/cyan]")

    @patch('t3api_utils.style.messages.console')
    def test_print_technical(self, mock_console):
        """Test technical info printing."""
        print_technical("Debug information")
        mock_console.print.assert_called_once_with("[dim]Debug information[/dim]")

    @patch('t3api_utils.style.messages.console')
    def test_print_data(self, mock_console):
        """Test data printing."""
        print_data("{'key': 'value'}")
        mock_console.print.assert_called_once_with("[bright_white]{'key': 'value'}[/bright_white]")

    @patch('t3api_utils.style.messages.console')
    def test_print_labeled_info(self, mock_console):
        """Test labeled info printing."""
        print_labeled_info("Status", "Active")
        expected = "[magenta]Status:[/magenta] [bright_white]Active[/bright_white]"
        mock_console.print.assert_called_once_with(expected)

    @patch('t3api_utils.style.messages.console')
    def test_print_labeled_info_with_number(self, mock_console):
        """Test labeled info printing with numeric value."""
        print_labeled_info("Count", 42)
        expected = "[magenta]Count:[/magenta] [bright_white]42[/bright_white]"
        mock_console.print.assert_called_once_with(expected)

    @patch('t3api_utils.style.messages.console')
    def test_print_state_info_with_items(self, mock_console):
        """Test state info printing with items."""
        state_items = ["Database: Connected", "Cache: Enabled", "Debug: On"]
        print_state_info(state_items)
        state_text = " | ".join(state_items)
        expected = f"[dim]Current state:[/dim] [magenta]{state_text}[/magenta]"
        mock_console.print.assert_called_once_with(expected)

    @patch('t3api_utils.style.messages.console')
    def test_print_state_info_empty_list(self, mock_console):
        """Test state info printing with empty list."""
        print_state_info([])
        mock_console.print.assert_not_called()

    @patch('t3api_utils.style.messages.console')
    def test_print_state_info_single_item(self, mock_console):
        """Test state info printing with single item."""
        state_items = ["Ready"]
        print_state_info(state_items)
        expected = "[dim]Current state:[/dim] [magenta]Ready[/magenta]"
        mock_console.print.assert_called_once_with(expected)


class TestStyleConstants:
    """Test style constants are properly defined."""

    def test_symbol_constants_exist(self):
        """Test that all symbol constants are defined and non-empty."""
        symbols = [SUCCESS_SYMBOL, ERROR_SYMBOL, WARNING_SYMBOL, INFO_SYMBOL, PROGRESS_SYMBOL]
        for symbol in symbols:
            assert symbol is not None
            assert len(symbol) > 0
            assert isinstance(symbol, str)

    def test_header_constants_exist(self):
        """Test that header format constants are defined."""
        headers = [MAIN_HEADER_PREFIX, MAIN_HEADER_SUFFIX, SUB_HEADER_PREFIX, SUB_HEADER_SUFFIX]
        for header in headers:
            assert header is not None
            assert isinstance(header, str)

    def test_menu_number_format(self):
        """Test that menu number format works correctly."""
        assert MENU_NUMBER is not None
        assert isinstance(MENU_NUMBER, str)

        # Should contain format placeholder
        assert "{number}" in MENU_NUMBER or "{" in MENU_NUMBER

        # Should format correctly
        formatted = MENU_NUMBER.format(number=1)
        assert "1" in formatted

    def test_symbols_contain_colors(self):
        """Test that symbols contain Rich markup."""
        # Most symbols should contain color markup (brackets)
        symbols = [SUCCESS_SYMBOL, ERROR_SYMBOL, WARNING_SYMBOL, INFO_SYMBOL, PROGRESS_SYMBOL]
        for symbol in symbols:
            # Should contain at least one bracket for Rich markup
            assert "[" in symbol and "]" in symbol, f"Symbol {symbol} should contain Rich markup"


class TestStyleIntegration:
    """Test integration between styles and console."""

    def test_console_import(self):
        """Test that console can be imported successfully."""
        from t3api_utils.style.console import console
        assert console is not None

    def test_console_has_print_method(self):
        """Test that console has required methods."""
        from t3api_utils.style.console import console
        assert hasattr(console, 'print')
        assert callable(console.print)

    @patch('t3api_utils.style.messages.console.print')
    def test_all_message_functions_use_console(self, mock_print):
        """Test that all message functions use the console."""
        # Call all message functions
        print_success("test")
        print_error("test")
        print_warning("test")
        print_info("test")
        print_progress("test")
        print_header("test")
        print_subheader("test")
        print_menu_item(1, "test")
        print_file_path("test")
        print_technical("test")
        print_data("test")
        print_labeled_info("label", "value")
        print_state_info(["test"])

        # Should have called console.print multiple times
        assert mock_print.call_count == 13