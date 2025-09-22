"""Convenient message printing functions with consistent purple styling."""

from typing import Any

from t3api_utils.style.console import console
from t3api_utils.style.styles import (
    ERROR_SYMBOL,
    INFO_SYMBOL,
    MAIN_HEADER_PREFIX,
    MAIN_HEADER_SUFFIX,
    MENU_NUMBER,
    PROGRESS_SYMBOL,
    SUB_HEADER_PREFIX,
    SUB_HEADER_SUFFIX,
    SUCCESS_SYMBOL,
    WARNING_SYMBOL,
)


def print_success(message: str) -> None:
    """Print a success message with green checkmark."""
    console.print(f"{SUCCESS_SYMBOL} {message}")


def print_error(message: str) -> None:
    """Print an error message with red X mark."""
    console.print(f"{ERROR_SYMBOL} {message}")


def print_warning(message: str) -> None:
    """Print a warning message with yellow warning symbol."""
    console.print(f"{WARNING_SYMBOL} {message}")


def print_info(message: str) -> None:
    """Print an info message with blue info symbol."""
    console.print(f"{INFO_SYMBOL} {message}")


def print_progress(message: str) -> None:
    """Print a progress/status message with purple dots."""
    console.print(f"{PROGRESS_SYMBOL} {message}")


def print_header(title: str) -> None:
    """Print a main header with decorative purple borders."""
    console.print(f"{MAIN_HEADER_PREFIX} {title} {MAIN_HEADER_SUFFIX}")


def print_subheader(title: str) -> None:
    """Print a section subheader with decorative purple borders."""
    console.print(f"{SUB_HEADER_PREFIX} {title} {SUB_HEADER_SUFFIX}")


def print_menu_item(number: int, text: str) -> None:
    """Print a numbered menu item with purple styling."""
    formatted_number = MENU_NUMBER.format(number=number)
    console.print(f"  {formatted_number} {text}")


def print_file_path(path: Any) -> None:
    """Print a file path with cyan highlighting."""
    console.print(f"[cyan]{path}[/cyan]")


def print_technical(info: str) -> None:
    """Print technical information in dim text."""
    console.print(f"[dim]{info}[/dim]")


def print_data(data: str) -> None:
    """Print data/code in bright white."""
    console.print(f"[bright_white]{data}[/bright_white]")


def print_labeled_info(label: str, value: Any) -> None:
    """Print labeled information with purple label and white value."""
    console.print(f"[magenta]{label}:[/magenta] [bright_white]{value}[/bright_white]")


def print_state_info(state_items: list[str]) -> None:
    """Print current state information with purple styling."""
    if state_items:
        state_text = " | ".join(state_items)
        console.print(f"[dim]Current state:[/dim] [magenta]{state_text}[/magenta]")