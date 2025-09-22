"""Pre-defined Rich styles for consistent purple-themed CLI output."""

from rich.style import Style

# Message type styles
success_style = Style(color="green", bold=True)
error_style = Style(color="red", bold=True)
warning_style = Style(color="yellow", bold=True)
info_style = Style(color="blue", bold=True)
progress_style = Style(color="magenta", bold=True)

# Header and structure styles
header_style = Style(color="magenta", bold=True)
subheader_style = Style(color="bright_magenta", bold=True)
menu_style = Style(color="magenta")

# Content styles
file_path_style = Style(color="cyan")
technical_style = Style(color="white", dim=True)
data_style = Style(color="bright_white")

# Theme colors
primary_style = Style(color="magenta")
accent_style = Style(color="bright_magenta")
muted_style = Style(color="magenta", dim=True)

# Common style patterns as formatted strings
SUCCESS_SYMBOL = "[bold green]✓[/bold green]"
ERROR_SYMBOL = "[bold red]✗[/bold red]"
WARNING_SYMBOL = "[bold yellow]⚠[/bold yellow]"
INFO_SYMBOL = "[bold blue]ℹ[/bold blue]"
PROGRESS_SYMBOL = "[bold magenta]⋯[/bold magenta]"

# Header patterns
MAIN_HEADER_PREFIX = "[bold magenta]═══[/bold magenta]"
MAIN_HEADER_SUFFIX = "[bold magenta]═══[/bold magenta]"
SUB_HEADER_PREFIX = "[bold bright_magenta]──[/bold bright_magenta]"
SUB_HEADER_SUFFIX = "[bold bright_magenta]──[/bold bright_magenta]"

# Menu patterns
MENU_BULLET = "[magenta]•[/magenta]"
MENU_NUMBER = "[magenta]{number}.[/magenta]"