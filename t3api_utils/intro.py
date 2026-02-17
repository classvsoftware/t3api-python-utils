"""Interactive getting started tutorial for t3api-python-utils."""

import sys
import threading

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

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
YOUTUBE_URL = "https://www.youtube.com/watch?v=GjHhyuLTh20"

EXAMPLES_URL = "https://github.com/classvsoftware/t3-api-examples"
WEBSITE_URL = "https://www.trackandtrace.tools"

_TOTAL_STEPS = 12

_T3_BANNER = r"""
████████╗██████╗  █████╗ ██████╗ ██╗    ██╗   ██╗████████╗██╗██╗     ███████╗
╚══██╔══╝╚════██╗██╔══██╗██╔══██╗██║    ██║   ██║╚══██╔══╝██║██║     ██╔════╝
   ██║    █████╔╝███████║██████╔╝██║    ██║   ██║   ██║   ██║██║     ███████╗
   ██║    ╚═══██╗██╔══██║██╔═══╝ ██║    ██║   ██║   ██║   ██║██║     ╚════██║
   ██║   ██████╔╝██║  ██║██║     ██║    ╚██████╔╝   ██║   ██║███████╗███████║
   ╚═╝   ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝     ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝
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


def _show_banner() -> None:
    """Display the ASCII art banner with gradient."""
    console.print(Align.center(_gradient_banner(_T3_BANNER)))


def _type_text(text: str, style: str = "bright_white") -> None:
    """Display styled text."""
    console.print(Text(text, style=style))


def _show_code(code: str) -> None:
    """Display a syntax-highlighted code block."""
    console.print(Syntax(code.strip(), "python", theme="monokai", padding=1))


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
    _show_banner()
    console.print()

    console.print(Align.center(Text("Python utilities for the T3 API", style="bright_white")))

    console.print()
    console.print(
        Align.center(
            Text.from_markup(
                f"[dim]Built by[/dim] [bold bright_white]Matt Frisbie[/bold bright_white] "
                f"[dim]at[/dim] [bold magenta]Track and Trace Tools[/bold magenta]"
            )
        )
    )
    console.print(
        Align.center(
            Text.from_markup(
                f"[link={WEBSITE_URL}][cyan]{WEBSITE_URL}[/cyan][/link]"
            )
        )
    )
    console.print()

    console.print(
        Panel(
            f"[magenta]Documentation:[/magenta]  [link={DOCS_URL}][cyan]{DOCS_URL}[/cyan][/link]\n"
            f"[magenta]T3 Wiki:[/magenta]         [link={WIKI_URL}][cyan]{WIKI_URL}[/cyan][/link]\n"
            f"[magenta]YouTube Demo:[/magenta]    [link={YOUTUBE_URL}][cyan]{YOUTUBE_URL}[/cyan][/link]",
            title="[bold magenta]Resources[/bold magenta]",
            border_style="magenta",
            padding=(1, 2),
        )
    )

    _wait_for_next()


def _step_running_with_uv() -> None:
    console.clear()
    _show_progress(1, "Running with UV")
    console.print(
        Rule("[bold magenta]Running with UV[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        "[bright_white]Add this header so [cyan]uv[/cyan] "
        "handles dependencies for you:[/bright_white]"
    )
    console.print()

    _show_code("""\
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "t3api_utils",
# ]
# ///

from t3api_utils.main.utils import get_authenticated_client_or_error

client = get_authenticated_client_or_error()""")

    console.print()
    _print_info("Run with: [cyan]uv run your_script.py[/cyan]")

    _wait_for_next()


def _step_authentication() -> None:
    console.clear()
    _show_progress(2, "Authentication")
    console.print(
        Rule("[bold magenta]Authentication[/bold magenta]", style="magenta")
    )
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
    _print_info("The interactive picker walks you through any method:")
    console.print()

    _show_code("""\
from t3api_utils.main.utils import get_authenticated_client_or_error

client = get_authenticated_client_or_error()""")

    _wait_for_next()


def _step_jwt() -> None:
    console.clear()
    _show_progress(3, "JWT Authentication")
    console.print(
        Rule("[bold magenta]JWT Authentication[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        "[bright_white]The T3 browser extension provides a JWT for your "
        "current Metrc session:[/bright_white]"
    )
    console.print()

    _show_code("""\
from t3api_utils.main.utils import get_jwt_authenticated_client_or_error_with_validation

client = get_jwt_authenticated_client_or_error_with_validation(
    jwt_token="your_jwt_token_here"
)""")

    console.print()
    _print_info("Tokens expire — grab a fresh one from the extension when needed.")

    _wait_for_next()


def _step_env_file() -> None:
    console.clear()
    _show_progress(4, "The .t3.env File")
    console.print(
        Rule("[bold magenta]The .t3.env File[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        "[bright_white]Auto-generated on first import. "
        "Stores credentials, performance, logging, and output settings:[/bright_white]"
    )
    console.print()

    console.print(
        Syntax(
            """\
# T3 API UTILS CONFIGURATION FILE
# Auto-generated by t3api-utils - edit values as needed.

# AUTHENTICATION
METRC_HOSTNAME=co.metrc.com
METRC_USERNAME=
METRC_PASSWORD=
JWT_TOKEN=
API_KEY=

# PERFORMANCE
MAX_WORKERS=
RATE_LIMIT_RPS=

# HTTP LOGGING
T3_LOG_HTTP=
T3_LOG_FILE=

# OUTPUT
OUTPUT_DIR=
DEFAULT_FILE_FORMAT=
# ... and more""",
            "ini",
            theme="monokai",
            padding=1,
        )
    )

    console.print()
    _print_info("Gitignored by default — your credentials stay local.")

    _wait_for_next()


def _step_loading_data() -> None:
    console.clear()
    _show_progress(5, "Loading Data")
    console.print(
        Rule("[bold magenta]Loading Data[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        "[bright_white]Load all records from a collection with "
        "automatic parallel pagination:[/bright_white]"
    )
    console.print()

    _show_code("""\
from t3api_utils.api.parallel import load_all_data_sync
from t3api_utils.main.utils import get_authenticated_client_or_error, pick_license
from t3api_utils.openapi import pick_collection

client = get_authenticated_client_or_error()
license = pick_license(api_client=client)
collection = pick_collection()

data = load_all_data_sync(
    client=client,
    path=collection["path"],
    license_number=license["licenseNumber"],
)
print(f"Loaded {len(data)} records!")""")

    console.print()
    _print_info("Handles rate limiting and retries automatically.")

    _wait_for_next()


def _step_inspecting_data() -> None:
    console.clear()
    _show_progress(6, "Inspecting Data")
    console.print(
        Rule("[bold magenta]Inspecting Data[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        "[bright_white]Browse data in a full-screen terminal UI:[/bright_white]"
    )
    console.print()

    _show_code("""\
from t3api_utils.main.utils import inspect_collection

inspect_collection(data=data)""")

    console.print()
    _print_info(
        "Arrow keys to navigate, [cyan]/[/cyan] to search, "
        "[cyan]q[/cyan] to quit."
    )
    console.print()
    console.print(
        "[bright_white]Or use the all-in-one interactive menu:[/bright_white]"
    )
    console.print()

    _show_code("""\
from t3api_utils.main.utils import interactive_collection_handler

interactive_collection_handler(data=data)""")

    _wait_for_next()


def _step_export_file() -> None:
    console.clear()
    _show_progress(7, "Exporting to File")
    console.print(
        Rule("[bold magenta]Exporting to File[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        "[bright_white]Save data to CSV or JSON:[/bright_white]"
    )
    console.print()

    _show_code("""\
from t3api_utils.file.utils import save_dicts_to_csv, save_dicts_to_json

csv_path = save_dicts_to_csv(
    dicts=data,
    model_name="packages",
    license_number="CUL00001",
)

json_path = save_dicts_to_json(
    dicts=data,
    model_name="packages",
    license_number="CUL00001",
)""")

    console.print()
    _print_info("Nested dicts are auto-flattened in CSV. Saved to [cyan]output/[/cyan] by default.")

    _wait_for_next()


def _step_export_db() -> None:
    console.clear()
    _show_progress(8, "Exporting to Database")
    console.print(
        Rule(
            "[bold magenta]Exporting to Database[/bold magenta]", style="magenta"
        )
    )
    console.print()

    console.print(
        "[bright_white]Load data into DuckDB for SQL queries:[/bright_white]"
    )
    console.print()

    _show_code("""\
from t3api_utils.db.utils import create_duckdb_connection
from t3api_utils.main.utils import load_db

con = create_duckdb_connection()
load_db(con=con, data=data)

results = con.execute("SELECT * FROM main LIMIT 5").fetchall()""")

    console.print()
    _print_info("In-memory by default. Pass a file path to persist to disk.")

    _wait_for_next()


def _step_writing_to_metrc() -> None:
    console.clear()
    _show_progress(9, "Writing to Metrc")
    console.print(
        Rule("[bold magenta]Writing to Metrc[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        "[bright_white]POST, PUT, or PATCH data back to Metrc:[/bright_white]"
    )
    console.print()

    _show_code("""\
from t3api_utils.api.operations import send_api_request

# Discontinue an item
send_api_request(
    client=api_client,
    path="/v2/items/discontinue",
    method="POST",
    params={
        "licenseNumber": license["licenseNumber"],
        "submit": True,
    },
    json_body={"id": item["id"]},
)""")

    console.print()
    _print_info(
        f"More examples: [link={EXAMPLES_URL}][cyan]{EXAMPLES_URL}[/cyan][/link]"
    )

    _wait_for_next()


def _step_http_logging() -> None:
    console.clear()
    _show_progress(10, "HTTP Logging")
    console.print(
        Rule("[bold magenta]HTTP Logging[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        "[bright_white]Log all network requests. Enable in [cyan].t3.env[/cyan]:[/bright_white]"
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
    _print_info("Written to [cyan]t3_http.log[/cyan]. Overwritten each run.")

    _wait_for_next()


def _step_troubleshooting() -> None:
    console.clear()
    _show_progress(11, "Troubleshooting")
    console.print(
        Rule("[bold magenta]Troubleshooting[/bold magenta]", style="magenta")
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
    _show_progress(12, "Next Steps")
    console.print(
        Rule("[bold magenta]Next Steps[/bold magenta]", style="magenta")
    )
    console.print()

    console.print(
        Panel(
            "[magenta]Example scripts:[/magenta]\n"
            f"  [link={EXAMPLES_URL}][cyan]{EXAMPLES_URL}[/cyan][/link]\n"
            "\n"
            "[magenta]Documentation:[/magenta]\n"
            f"  [link={DOCS_URL}][cyan]{DOCS_URL}[/cyan][/link]\n"
            "\n"
            "[magenta]T3 Wiki:[/magenta]\n"
            f"  [link={WIKI_URL}][cyan]{WIKI_URL}[/cyan][/link]\n"
            "\n"
            "[magenta]YouTube Demo:[/magenta]\n"
            f"  [link={YOUTUBE_URL}][cyan]{YOUTUBE_URL}[/cyan][/link]",
            title="[bold magenta]What's Next[/bold magenta]",
            border_style="magenta",
            padding=(1, 2),
        )
    )

    console.print()
    _type_text("Happy scripting!", style="bold magenta")

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
        _step_running_with_uv()
        _step_authentication()
        _step_jwt()
        _step_env_file()
        _step_loading_data()
        _step_inspecting_data()
        _step_export_file()
        _step_export_db()
        _step_writing_to_metrc()
        _step_http_logging()
        _step_troubleshooting()
        _step_next()
    except KeyboardInterrupt:
        console.print()
        console.print("[dim]Tutorial exited.[/dim]")
