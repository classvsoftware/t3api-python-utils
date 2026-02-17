"""Interactive getting started tutorial for t3api-python-utils."""

import sys
import threading
import time

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

_theme = Theme(
    {
        "primary": "#8B5CF6",
        "accent": "#A855F7",
        "muted": "#C4B5FD",
        "bright": "#DDD6FE",
        "success": "#10B981",
        "error": "#EF4444",
        "warning": "#F59E0B",
        "info": "#6366F1",
    }
)

console = Console(theme=_theme, highlight=False)


def _print_info(message: str) -> None:
    """Print an info message with blue info symbol."""
    console.print(f"[bold blue]ℹ[/bold blue] {message}")

DOCS_URL = "https://classvsoftware.github.io/t3api-python-utils/"
WIKI_URL = "https://www.trackandtrace.tools/wiki"

_TOTAL_STEPS = 5

_T3_BANNER = r"""
████████╗██████╗      █████╗ ██████╗ ██╗
╚══██╔══╝╚════██╗    ██╔══██╗██╔══██╗██║
   ██║    █████╔╝    ███████║██████╔╝██║
   ██║   ╚═══██╗    ██╔══██║██╔═══╝ ██║
   ██║   ██████╔╝   ██║  ██║██║     ██║
   ╚═╝   ╚═════╝    ╚═╝  ╚═╝╚═╝     ╚═╝
""".strip()

# Gradient: deep purple → light violet
_GRAD_START = (109, 40, 217)
_GRAD_END = (192, 180, 252)


# ---------------------------------------------------------------------------
# Visual helpers
# ---------------------------------------------------------------------------


def _interpolate_color(t: float) -> str:
    """Return a bold RGB style string interpolated between gradient endpoints."""
    r = int(_GRAD_START[0] + (_GRAD_END[0] - _GRAD_START[0]) * t)
    g = int(_GRAD_START[1] + (_GRAD_END[1] - _GRAD_START[1]) * t)
    b = int(_GRAD_START[2] + (_GRAD_END[2] - _GRAD_START[2]) * t)
    return f"bold rgb({r},{g},{b})"


def _gradient_banner(text: str) -> Text:
    """Apply a diagonal purple gradient to ASCII art text."""
    lines = text.split("\n")
    result = Text()
    total_lines = len(lines)
    max_width = max(len(line) for line in lines) if lines else 1

    for y, line in enumerate(lines):
        for x, char in enumerate(line):
            if char.strip():
                t = (x / max(max_width - 1, 1)) * 0.6 + (
                    y / max(total_lines - 1, 1)
                ) * 0.4
                result.append(char, style=_interpolate_color(min(t, 1.0)))
            else:
                result.append(char)
        if y < total_lines - 1:
            result.append("\n")

    return result


def _animate_banner() -> None:
    """Reveal the ASCII art banner line-by-line with gradient."""
    lines = _T3_BANNER.split("\n")
    revealed: list[str] = []

    with Live(Text(""), console=console, refresh_per_second=30) as live:
        for line in lines:
            revealed.append(line)
            banner = _gradient_banner("\n".join(revealed))
            live.update(Align.center(banner))
            time.sleep(0.1)
        time.sleep(0.3)


def _type_text(text: str, style: str = "bright_white", speed: float = 0.02) -> None:
    """Display text with a character-by-character typing animation."""
    result = Text(style=style)
    with Live(result, console=console, refresh_per_second=60) as live:
        for char in text:
            result.append(char)
            live.update(result)
            time.sleep(speed)


def _animate_code(code: str) -> None:
    """Reveal a syntax-highlighted code block line-by-line."""
    lines = code.strip().split("\n")
    with Live(
        Syntax("", "python", theme="monokai", padding=1),
        console=console,
        refresh_per_second=30,
    ) as live:
        for i in range(len(lines)):
            partial = "\n".join(lines[: i + 1])
            live.update(Syntax(partial, "python", theme="monokai", padding=1))
            time.sleep(0.05)


def _show_progress(step: int, title: str) -> None:
    """Render a progress bar with step counter and section title."""
    bar_filled = int(30 * step / _TOTAL_STEPS)
    bar_empty = 30 - bar_filled
    console.print(
        f"  [bold magenta]{'━' * bar_filled}[/bold magenta]"
        f"[dim]{'━' * bar_empty}[/dim]"
        f"  [bright_white]Step {step} of {_TOTAL_STEPS}[/bright_white]"
        f"  [dim]·[/dim]  [muted]{title}[/muted]"
    )
    console.print()


def _wait_for_next(last: bool = False) -> None:
    """Wait for Enter with an animated spinner prompt."""
    prompt = "Press Enter to finish..." if last else "Press Enter to continue..."
    console.print()

    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    stop = threading.Event()

    def animate() -> None:
        i = 0
        while not stop.is_set():
            frame = frames[i % len(frames)]
            sys.stdout.write(f"\r\033[2m  {frame} {prompt}\033[0m")
            sys.stdout.flush()
            i += 1
            stop.wait(0.08)

    thread = threading.Thread(target=animate, daemon=True)
    thread.start()

    try:
        input()
    finally:
        stop.set()
        thread.join(timeout=0.5)
        # input() added a newline — move up and clear the spinner line
        sys.stdout.write("\033[A\r\033[K")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Tutorial steps
# ---------------------------------------------------------------------------


def _step_welcome() -> None:
    console.clear()
    console.print()
    _animate_banner()
    console.print()

    _type_text("A Python toolkit for working with the T3 API (Metrc).")

    console.print()
    console.print(
        "[bright_white]This walkthrough will teach you how to authenticate, "
        "make API calls, and troubleshoot.[/bright_white]"
    )
    console.print()

    console.print(
        Panel(
            f"[magenta]Documentation:[/magenta]  [link={DOCS_URL}][cyan]{DOCS_URL}[/cyan][/link]\n"
            f"[magenta]T3 Wiki:[/magenta]         [link={WIKI_URL}][cyan]{WIKI_URL}[/cyan][/link]",
            title="[bold magenta]Resources[/bold magenta]",
            border_style="magenta",
            padding=(1, 2),
        )
    )

    _wait_for_next()


def _step_authentication() -> None:
    console.clear()
    _show_progress(1, "Authentication")
    console.print(Rule("[bold magenta]Authentication[/bold magenta]", style="magenta"))
    console.print()

    table = Table(
        border_style="magenta",
        header_style="bold magenta",
        padding=(0, 1),
        show_lines=True,
    )
    table.add_column("Method", style="bright_white", min_width=12)
    table.add_column("Best For", style="dim")
    table.add_column("How To Get It", style="cyan")
    table.add_row(
        "Credentials",
        "Automation & scheduled scripts",
        "Your Metrc username & password",
    )
    table.add_row(
        "JWT Token",
        "Quick testing & development",
        "T3 browser extension",
    )
    table.add_row(
        "API Key",
        "Long-lived integrations",
        "Request from T3 support",
    )
    console.print(table)
    console.print()

    console.print(
        Rule(
            "[bold bright_magenta]Easiest: Interactive Auth Picker[/bold bright_magenta]",
            style="bright_magenta",
            align="left",
        )
    )
    console.print()
    _print_info("Shows a menu and walks you through whichever method you choose:")
    console.print()

    _animate_code("""\
from t3api_utils.main.utils import get_authenticated_client_or_error

# Shows an interactive picker with all 3 auth options
client = get_authenticated_client_or_error()""")

    console.print()
    console.print(
        Rule(
            "[bold bright_magenta]Direct: JWT Token[/bold bright_magenta]",
            style="bright_magenta",
            align="left",
        )
    )
    console.print()

    _animate_code("""\
from t3api_utils.main.utils import get_jwt_authenticated_client_or_error_with_validation

# Authenticate with a JWT token (validates it automatically)
client = get_jwt_authenticated_client_or_error_with_validation(
    jwt_token="your_jwt_token_here"
)""")

    console.print()
    console.print(
        Rule(
            "[bold bright_magenta]Direct: Credentials[/bold bright_magenta]",
            style="bright_magenta",
            align="left",
        )
    )
    console.print()

    _animate_code("""\
from t3api_utils.auth.utils import create_credentials_authenticated_client_or_error

# Authenticate with Metrc credentials
client = create_credentials_authenticated_client_or_error(
    hostname="co.metrc.com",
    username="your_username",
    password="your_password",
)""")

    _wait_for_next()


def _step_env_file() -> None:
    console.clear()
    _show_progress(2, "Configuration")
    console.print(
        Rule("[bold magenta]The .t3.env File[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        "[bright_white]When you first import from [magenta]t3api_utils[/magenta], "
        "a [cyan].t3.env[/cyan] file is auto-generated in your working directory.[/bright_white]"
    )
    console.print()
    console.print(
        "[bright_white]This file stores your credentials and configuration "
        "so you don't have to re-enter them every time.[/bright_white]"
    )
    console.print()

    table = Table(
        title="[bold magenta]Key Variables[/bold magenta]",
        border_style="magenta",
        header_style="bold magenta",
        padding=(0, 1),
        show_lines=True,
    )
    table.add_column("Variable", style="magenta", min_width=16)
    table.add_column("Description", style="bright_white")
    table.add_row("METRC_HOSTNAME", "Metrc state domain (e.g. co.metrc.com)")
    table.add_row("METRC_USERNAME", "Your Metrc account username")
    table.add_row("METRC_PASSWORD", "Your Metrc account password")
    table.add_row("JWT_TOKEN", "JWT from the T3 browser extension")
    table.add_row("API_KEY", "Long-lived API key from T3")
    table.add_row("T3_LOG_HTTP", "Enable HTTP debug logging (true/false)")
    table.add_row("T3_LOG_FILE", "Log file path (default: t3_http.log)")
    console.print(table)

    console.print()
    _print_info(
        "The [cyan].t3.env[/cyan] file is gitignored by default — "
        "your credentials stay local."
    )
    _print_info(
        "After authenticating, you'll be prompted to save your credentials "
        "to this file for next time."
    )

    _wait_for_next()


def _step_api_calls() -> None:
    console.clear()
    _show_progress(3, "Making API Calls")
    console.print(
        Rule("[bold magenta]Making API Calls[/bold magenta]", style="magenta")
    )
    console.print()

    tree = Tree("[bold magenta]Script Workflow[/bold magenta]")
    auth_node = tree.add("[magenta]1.[/magenta] [bright_white]Authenticate[/bright_white]")
    auth_node.add("[dim]get_authenticated_client_or_error()[/dim]")
    lic_node = tree.add("[magenta]2.[/magenta] [bright_white]Pick License[/bright_white]")
    lic_node.add("[dim]pick_license(api_client=client)[/dim]")
    col_node = tree.add("[magenta]3.[/magenta] [bright_white]Pick Collection[/bright_white]")
    col_node.add("[dim]pick_collection()[/dim]")
    data_node = tree.add("[magenta]4.[/magenta] [bright_white]Load Data[/bright_white]")
    data_node.add("[dim]load_all_data_sync(client, path, license_number)[/dim]")
    out_node = tree.add("[magenta]5.[/magenta] [bright_white]Process & Export[/bright_white]")
    out_node.add("[dim]save_dicts_to_csv() / save_dicts_to_json()[/dim]")
    console.print(tree)

    console.print()
    console.print(
        Rule(
            "[bold bright_magenta]Full Workflow Example[/bold bright_magenta]",
            style="bright_magenta",
            align="left",
        )
    )
    console.print()

    _animate_code("""\
from t3api_utils.api.parallel import load_all_data_sync
from t3api_utils.main.utils import (
    get_authenticated_client_or_error,
    pick_license,
)
from t3api_utils.openapi import pick_collection

# 1. Authenticate
client = get_authenticated_client_or_error()

# 2. Pick a Metrc license from your account
license = pick_license(api_client=client)

# 3. Pick a data collection (packages, plants, etc.)
collection = pick_collection()

# 4. Load all data for that collection and license
data = load_all_data_sync(
    client=client,
    path=collection["path"],
    license_number=license["licenseNumber"],
)

print(f"Loaded {len(data)} records!")""")

    console.print()
    _print_info(
        "[magenta]pick_license()[/magenta] and [magenta]pick_collection()[/magenta] "
        "show interactive Rich tables for selection."
    )
    _print_info(
        "[magenta]load_all_data_sync()[/magenta] handles pagination and "
        "parallel fetching automatically."
    )

    _wait_for_next()


def _step_troubleshooting() -> None:
    console.clear()
    _show_progress(4, "Troubleshooting")
    console.print(
        Rule("[bold magenta]Troubleshooting[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        "[bright_white]If something isn't working, enable HTTP debug logging "
        "to see exactly what's happening.[/bright_white]"
    )
    console.print()

    console.print(
        Rule(
            "[bold bright_magenta]Enable HTTP Logging[/bold bright_magenta]",
            style="bright_magenta",
            align="left",
        )
    )
    console.print()
    console.print(
        "[bright_white]In your [cyan].t3.env[/cyan] file, set:[/bright_white]"
    )
    console.print()

    console.print(
        Panel(
            "[magenta]T3_LOG_HTTP[/magenta] = [bright_white]true[/bright_white]",
            border_style="magenta",
            padding=(0, 2),
        )
    )

    console.print()
    console.print(
        "[bright_white]This writes all HTTP requests and responses to "
        "[cyan]t3_http.log[/cyan] in your working directory.[/bright_white]"
    )
    console.print()

    _print_info(
        "The log shows request methods, URLs, headers, and response status codes."
    )
    _print_info(
        "The log file is overwritten each run, so it always shows the latest session."
    )

    console.print()
    console.print(
        Rule(
            "[bold bright_magenta]Common Issues[/bold bright_magenta]",
            style="bright_magenta",
            align="left",
        )
    )
    console.print()

    table = Table(
        border_style="magenta",
        header_style="bold magenta",
        padding=(0, 1),
        show_lines=True,
    )
    table.add_column("Issue", style="bold yellow", min_width=20)
    table.add_column("Solution", style="bright_white")
    table.add_row(
        "Authentication failed",
        "Check credentials in .t3.env. JWT tokens expire — "
        "get a fresh one from the T3 extension.",
    )
    table.add_row(
        "No licenses found",
        "Make sure your account has access to at least one Metrc license.",
    )
    table.add_row(
        "Empty data returned",
        "Check t3_http.log for API responses. "
        "Verify license and collection are correct.",
    )
    console.print(table)

    _wait_for_next()


def _step_next() -> None:
    console.clear()
    _show_progress(5, "Next Steps")
    console.print(Rule("[bold magenta]Next Steps[/bold magenta]", style="magenta"))
    console.print()

    console.print(
        "[bright_white]You're ready to start writing scripts![/bright_white]"
    )
    console.print()

    console.print(
        Panel(
            "[magenta]Full example script:[/magenta]\n"
            "  [cyan]uv run scripts/example.py[/cyan]\n"
            "\n"
            "[magenta]Documentation:[/magenta]\n"
            f"  [link={DOCS_URL}][cyan]{DOCS_URL}[/cyan][/link]\n"
            "\n"
            "[magenta]T3 Wiki:[/magenta]\n"
            f"  [link={WIKI_URL}][cyan]{WIKI_URL}[/cyan][/link]",
            title="[bold magenta]What's Next[/bold magenta]",
            border_style="magenta",
            padding=(1, 2),
        )
    )

    console.print()
    _type_text("Happy scripting!", style="bold magenta", speed=0.04)

    _wait_for_next(last=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_intro() -> None:
    """Run the interactive getting started tutorial.

    Call this from any script to launch the step-by-step walkthrough::

        from t3api_utils.intro import run_intro
        run_intro()
    """
    try:
        _step_welcome()
        _step_authentication()
        _step_env_file()
        _step_api_calls()
        _step_troubleshooting()
        _step_next()
    except KeyboardInterrupt:
        console.print()
        console.print("[dim]Tutorial exited.[/dim]")
