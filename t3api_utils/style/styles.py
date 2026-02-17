"""Pre-defined Rich styles for consistent purple-themed CLI output."""

from rich.style import Style

# Message type styles
success_style = Style(color="green", bold=True)
"""Bold green style for success messages and completed actions."""
error_style = Style(color="red", bold=True)
"""Bold red style for error messages and failures."""
warning_style = Style(color="yellow", bold=True)
"""Bold yellow style for warning messages and cautions."""
info_style = Style(color="blue", bold=True)
"""Bold blue style for informational messages and help text."""
progress_style = Style(color="magenta", bold=True)
"""Bold magenta style for progress indicators and status updates."""

# Header and structure styles
header_style = Style(color="magenta", bold=True)
"""Bold magenta style for main section headers and titles."""
subheader_style = Style(color="bright_magenta", bold=True)
"""Bold bright magenta style for subsection headers."""
menu_style = Style(color="magenta")
"""Magenta style for menu items and interactive selection elements."""

# Content styles
file_path_style = Style(color="cyan")
"""Cyan style for file and directory paths."""
technical_style = Style(color="white", dim=True)
"""Dim white style for technical details and secondary information."""
data_style = Style(color="bright_white")
"""Bright white style for data values and code output."""

# Theme colors
primary_style = Style(color="magenta")
"""Primary magenta theme style for general branded elements."""
accent_style = Style(color="bright_magenta")
"""Bright magenta accent style for highlights and emphasis."""
muted_style = Style(color="magenta", dim=True)
"""Dim magenta style for subdued or secondary themed text."""

# Common style patterns as formatted strings
SUCCESS_SYMBOL = "[bold green]✓[/bold green]"
"""Rich markup string for a bold green checkmark, used to prefix success messages."""
ERROR_SYMBOL = "[bold red]✗[/bold red]"
"""Rich markup string for a bold red X mark, used to prefix error messages."""
WARNING_SYMBOL = "[bold yellow]⚠[/bold yellow]"
"""Rich markup string for a bold yellow warning sign, used to prefix warnings."""
INFO_SYMBOL = "[bold blue]ℹ[/bold blue]"
"""Rich markup string for a bold blue info symbol, used to prefix informational messages."""
PROGRESS_SYMBOL = "[bold magenta]⋯[/bold magenta]"
"""Rich markup string for bold magenta ellipsis dots, used to prefix progress/status messages."""

# Header patterns
MAIN_HEADER_PREFIX = "[bold magenta]═══[/bold magenta]"
"""Rich markup string for the leading triple-bar decoration before main header text."""
MAIN_HEADER_SUFFIX = "[bold magenta]═══[/bold magenta]"
"""Rich markup string for the trailing triple-bar decoration after main header text."""
SUB_HEADER_PREFIX = "[bold bright_magenta]──[/bold bright_magenta]"
"""Rich markup string for the leading dash decoration before subheader text."""
SUB_HEADER_SUFFIX = "[bold bright_magenta]──[/bold bright_magenta]"
"""Rich markup string for the trailing dash decoration after subheader text."""

# Menu patterns
MENU_BULLET = "[magenta]•[/magenta]"
"""Rich markup string for a magenta bullet point in unordered menu lists."""
MENU_NUMBER = "[magenta]{number}.[/magenta]"
"""Rich markup template for a magenta numbered menu item. Format with ``number`` key."""