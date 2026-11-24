# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Strategy

- The data returned from Metrc collection API endpoints may slightly change over time. Extra fields may be added. Don't write python classes that assume an exact data shape, they should fall back gracefully. In 2.0, rows are plain dicts exactly as the API returns them; never rename, drop or validate fields.
- What the library knows about endpoints comes from the T3 OpenAPI spec at runtime. Don't hardcode endpoint lists, ID parameters or per-endpoint behaviour; derive it from the spec (see `t3api_utils/spec/registry.py`) so new endpoints work without a release.
- `V2_DESIGN.md` is the design. Where the code and the design differ in small ways, the code wins; keep the docs in `docs/` matching the code.

## Development Setup

This project uses `uv`. Python 3.12 or later.

```bash
uv sync                                   # create .venv with the dev group (includes textual)

uv run pytest                             # all tests; coverage must stay at 100%
uv run pytest --cov --cov-branch --cov-report=term-missing
uv run pytest tests/test_collect.py       # one file
uv run mypy                               # strict; checks t3api_utils, tests and scripts (see pyproject)

uv run mkdocs serve                       # docs preview at http://127.0.0.1:8000
uv run mkdocs build --strict              # what CI runs; must pass with no warnings

T3_SPEC=bundled uv run t3api endpoints harvest   # try the CLI offline against the bundled spec
```

Before each release:

```bash
uv run python scripts/update_spec.py      # refresh t3api_utils/spec/openapi.json.gz from the live spec
T3_SMOKE_SECRET_KEY=... uv run pytest -m sandbox
```

`update_spec.py` prints how the endpoint-kind counts changed; mention notable changes in `CHANGELOG.md`. CI (`.github/workflows/ci.yml`) runs mypy and pytest on Linux, macOS and Windows with Python 3.12 and 3.13, plus a strict docs build. `.github/workflows/release.yml` runs when a `vX.Y.Z` tag is pushed: it uploads to PyPI through trusted publishing, then creates the GitHub release from that version's `CHANGELOG.md` section.

### Releasing

For this repository (t3api-python-utils) only, Claude may merge to `master`, push, tag and publish a release without asking first, as long as the tests fully pass:

- `uv run pytest --cov` passes at 100% coverage;
- `uv run mypy` is clean;
- `uv run mkdocs build --strict` passes;
- CI is green on every OS for the commit being released.

If any of these fail, stop and report instead of releasing.

Steps:

1. Bump `version` in `pyproject.toml` and add a `## X.Y.Z` section to `CHANGELOG.md`.
2. Run the checklist above.
3. Push the branch and wait for CI.
4. Fast-forward `master` to the release commit and push it.
5. `git tag -a vX.Y.Z -m "t3api-utils X.Y.Z"` on that commit, then `git push origin vX.Y.Z`.
6. Check that every `release.yml` job succeeds. The jobs publish to PyPI, create the GitHub release and deploy the docs site. If only the docs job fails, deploy from the tagged commit with `uv run mkdocs gh-deploy --strict`.

A release isn't finished until the docs site at <https://classvsoftware.github.io/t3api-python-utils/> shows the released version.

## Architecture

### Package layout

```
t3api_utils/
  __init__.py          public API: connect, T3Client, inspect, filter_rows, to_csv, to_json, read_rows,
                       pick_file, confirm, ask, choose, errors, WriteResult/BulkResult/RowResult, TagList,
                       Endpoint, auth classes
  client.py            T3Client: request(), get/post/put/patch/delete(), download(), collect(), iter_rows(),
                       bulk(), report(), report_url(), whoami(), licenses(), sandbox state, pickers, namespaces
  errors.py            exception hierarchy; error_from_response() maps status codes to classes
  writes.py            WriteResult, BulkResult, RowResult, bulk()
  reports.py           report(), report_url()
  tag_lists.py         TagLists (client.tag_lists) and TagList
  local.py             filter_rows(), to_csv(), to_json(), read_rows(), flatten()
  pickers.py           choose(), pick_license(), pick_endpoint(), pick_file() as Rich tables
  prompts.py           public confirm() (default no) and ask(parse=...)
  _http.py             httpx2 client builder, RetryTransport, HTTP log redaction
  _ratelimit.py        thread-safe token bucket
  _api.py              send/parse helpers that raise APIError subclasses; atomic streaming download()
  _console.py          Rich consoles, purple theme, message/prompt/progress helpers (internal)
  _paths.py            platformdirs config and cache folders (tests patch these)
  spec/
    loader.py          cached live spec -> live fetch -> stale cache -> bundled copy
    registry.py        Endpoint, Param, Registry: classification, lookup, parameter checks
    openapi.json.gz    bundled spec
  auth/
    credentials.py     SecretKeyAuth, BearerAuth (httpx2.Auth), JWT expiry and OTP helpers
    resolve.py         connect(): argument -> env var -> profile -> login flow -> AuthRequired
    login.py           interactive login flow and secret-key offer
    store.py           Profile, Store: config.toml plus OS keyring (secrets.toml fallback)
    secret_keys.py     SecretKeys (client.secret_keys): list/create/rotate/delete
    states.py          GET /v2/states (requiresEmail/requiresOtp), cached, with 1.x fallback lists
  tui/inspector.py     Textual inspector, imported lazily by t3.inspect()
  cli/main.py          Typer app behind the `t3api` command
scripts/               example.py, discontinue-items.py (user-facing examples), update_spec.py
docs/                  mkdocs-material site; reference pages are mkdocstrings
```

### Rules

- Importing the package has no side effects: no files written, no logging configured, no network calls. The spec loads the first time something needs it.
- Library code never calls `sys.exit()` or `typer.Exit`. Only `cli/` does.
- Modules whose names start with `_` are private. Anything a user needs is re-exported from `t3api_utils/__init__.py`.
- Every exception raised on purpose derives from `T3Error` (`errors.py`). Every `APIError` keeps its `response`.
- The library logs to `logging.getLogger("t3api_utils")` and never adds handlers or touches the root logger, except `enable_http_logging()` when HTTP logging is explicitly requested.
- Prompts and pickers work only when `_console.is_interactive()` (a terminal or Jupyter); otherwise they raise `NotInteractive`. Every interactive helper must have a non-interactive form. `connect()` must never hang waiting for input.
- Sync only. Parallel collection paging uses a thread pool behind the client's one shared rate limiter.
- Optional dependencies (Textual) are imported inside the function that needs them, with an `ImportError` that names the extra.
- No DuckDB, pyarrow, `.t3.env` or `python-dotenv`. Export is CSV/JSON only.

### Key behaviours to preserve

- **Endpoint kinds** come from spec structure alone (`registry.classify`): collection, report, metrc_write, immediate_write, file, object, other. Tests check named endpoints' kinds, not counts.
- **Writes**: `metrc_write` routes are a dry run unless `submit=True`; `immediate_write` routes reject `submit=` entirely. A dry run is static validation only (format, required fields, types), never call it more than that. `bulk()` validates every row before submitting; row statuses are valid/invalid/submitted/failed/not_sent. `submit="ask"` raises `NotInteractive` without a terminal before sending anything.
- **Body shape**: `Endpoint.body_type` comes from the spec. Most Metrc write routes take a JSON list; `bulk()` wraps each row in a list for them, and single writes warn when the `json=` shape doesn't match.
- **Retries** (`_http.RetryTransport`): GET/HEAD/OPTIONS retry on connection errors and 429/502/503/504; writes retry only on 429 and pre-send connection failures. Never retry a write on 5xx or a post-send timeout. Max 3 attempts.
- **Credentials**: secret keys go in the `X-T3-API-Key` header, never the query string, except `report_url()`. The Metrc password is never stored.
- **Redaction**: HTTP debug logs mask auth headers, `/v2/auth/secretkey/{key}` paths, `secretKey=` queries, and `password`/`otp`/`otpSeed`/`secretKey`/`accessToken`/`refreshToken` body fields.
- **Default license** (`client.license`) is applied only to endpoints whose `licenseNumber` is required. An explicit `license=` always wins.
- **Sandbox**: `connect(sandbox=True)` / `T3_SANDBOX` ignores `T3_LICENSE` and the profile's license, `enter_sandbox()` clears `client.license`, and explicit licenses are checked against the session's (the sandbox returns an empty 200 for other licenses). The CLI's `--sandbox` applies to data commands only, never to `login`, `logout`, `keys` or `license`.

### Docs

- Docstrings are Google style. They're rendered by mkdocstrings on the `docs/reference/` pages; `docs/_ext/griffe_roles.py` turns Sphinx roles like `:func:` into inline code at build time.
- The documentation pages must stay up to date. Any change to public behaviour, the CLI, configuration or install steps updates, in the same commit:
  - the matching `docs/guide/` page;
  - the docstrings that feed `docs/reference/`;
  - `README.md` and `CHANGELOG.md` where they cover it.

  `uv run mkdocs build --strict` must pass.
- The published site is redeployed by `release.yml` on every release (see Releasing). A docs-only fix between releases is deployed with `uv run mkdocs gh-deploy --strict`, but only if the docs still describe the released version.

## Testing

- **Coverage is 100%, line and branch**, enforced: `fail_under = 100` and `branch = true` are set in `pyproject.toml`, so `uv run pytest --cov` fails below that. Use `# pragma: no cover` only for code that can't run in tests (and say why).
- **HTTP is mocked with `httpx2.MockTransport`** through the `Router` fixture in `tests/conftest.py`: `router.add("GET", "/v2/licenses", json=[...])` answers a route (paths may contain `{placeholders}`; later routes win; unmatched requests get 404), and `router.calls` / `router.requests(...)` record what was sent. `paginated(rows)` serves rows as a T3 paginated collection. The `client` fixture is a `T3Client` with a secret key, the bundled spec, no rate limit and the router's transport.
- **Autouse fixtures** isolate every test: config and cache folders in a temp dir, no `T3_*` environment variables, an in-memory keyring, a temp working directory, no terminal (`_console.is_interactive()` is False unless a test patches it), and `time.sleep` replaced with a recorder so retries don't wait.
- `filterwarnings = ["error"]`: a warning fails the test.
- **Spec tests** use the bundled spec and assert the kind of specific named endpoints, not totals.
- **Retry tests** must check that a POST answered with 400 or 500 is sent exactly once.
- **Sandbox smoke tests** (`tests/test_sandbox.py`, marker `sandbox`) run against the real T3 API and the Metrc sandbox. They're skipped unless `T3_SMOKE_SECRET_KEY` is set (`T3_SMOKE_API_HOST` optionally points at another host): `T3_SMOKE_SECRET_KEY=... uv run pytest -m sandbox`. Run them before each release.
- mypy is strict for `t3api_utils`, `tests` and `scripts`.

## CLI Standards

### Color Palette

**Primary Purple Theme:**
- `primary` - `#8B5CF6` (Violet-500) - Headers, titles, primary actions
- `accent` - `#A855F7` (Purple-500) - Highlights, emphasis, interactive elements
- `muted` - `#C4B5FD` (Violet-300) - Secondary text, subdued information
- `bright` - `#DDD6FE` (Violet-200) - Backgrounds, subtle highlights

**Status Colors:**
- `success` - `#10B981` (Emerald-500) - Success messages, completed actions
- `error` - `#EF4444` (Red-500) - Error messages, failures
- `warning` - `#F59E0B` (Amber-500) - Warnings, cautions
- `info` - `#6366F1` (Indigo-500) - Information, help text

These are defined as the Rich theme in `t3api_utils/_console.py` (`THEME`).

### Style Conventions

**Message Types** (use the helpers in `t3api_utils/_console.py`, which print exactly these):
```python
from t3api_utils import _console

_console.success("Operation completed successfully")   # [bold green]✓[/bold green] ...
_console.error(f"Operation failed: {error_message}")   # [bold red]✗[/bold red] ...
_console.warning(f"Warning: {warning_message}")        # [bold yellow]⚠[/bold yellow] ...
_console.info(info_message)                            # [bold blue]ℹ[/bold blue] ...
_console.progress(status_message)                      # [bold magenta]⋯[/bold magenta] ...
```

**Headers and Structure:**
```python
# Main headers, section headers, sub-headers
_console.header(title)   # [bold magenta]═══ {title} ═══[/bold magenta]
console.print("[bold bright_magenta]── {section_name} ──[/bold bright_magenta]")
console.print("[magenta]{sub_header}:[/magenta]")
```

**Interactive Elements:**
```python
# Tables, prompts, file paths
table = _console.table("Title")        # Table(border_style="magenta", header_style="bold magenta")
value = _console.ask("Enter your choice")          # Rich prompt, raises NotInteractive without a terminal
ok = _console.confirm("Continue?", default=False)
console.print(f"[cyan]{file_path}[/cyan]")
```

### Implementation Guidelines

**Centralized Styling:**
- Use `t3api_utils/_console.py` for all styling, prompts and progress bars: `from t3api_utils._console import console, out`.
- `console` writes to **stderr** (messages, prompts, tables meant for a person). `out` writes to **stdout** and is only for data a user might pipe or capture (e.g. `t3api whoami` tables, printed IDs and URLs).
- Never use plain `print()` in library or CLI code - always use the Rich consoles. (The user-facing example scripts in `scripts/` may use `print()`.)
- Progress bars go through `_console.progress_bar(label, total, enabled)`, which is transient and disabled when stderr isn't a terminal.

**Consistency Rules:**
- All success messages use green with checkmark: `[bold green]✓[/bold green]`
- All error messages use red with X mark: `[bold red]✗[/bold red]`
- All progress/status use purple with dots: `[bold magenta]⋯[/bold magenta]`
- All headers use magenta with decorative borders

**Accessibility:**
- Always include symbols (✓, ✗, ⚠, ℹ, ⋯) alongside colors
- Use `bold` for important messages to improve readability
- Maintain good contrast ratios

### CLI Picker Standards

All selection interfaces use consistent Rich Table formatting. Build new pickers on `choose()` in `t3api_utils/pickers.py` rather than writing the loop again.

**Standard Implementation:**
```python
from t3api_utils.pickers import choose

def pick_something(items: Sequence[SomeType]) -> SomeType:
    """Standard picker implementation."""
    return choose(
        "Available Items",
        items,
        ["Name", "Details"],                      # columns after the "#" column
        lambda item: [item.name, item.details],   # one string per column
        filterable=None,                          # default: typing text narrows lists of more than 10
    )
```

`choose()` produces:
- A Rich Table from `_console.table()` (magenta border, bold magenta header)
- A numbered selection column with `style="magenta", justify="right"`
- The primary content column with `style="bright_white"`
- Further detail columns with `style="cyan"`

**Requirements:**
- Always validate the user's input range (re-prompt on a bad number).
- Call `_console.require_interactive()` first, so a picker without a terminal raises `NotInteractive` instead of hanging.
- Let `KeyboardInterrupt` propagate to the caller. Library code never exits; the CLI's `handle_errors` turns Ctrl-C into "Cancelled." and exit code 130.

**Examples in Codebase:**
- `choose()`, `pick_license()`, `pick_endpoint()` and `pick_file()` in `t3api_utils/pickers.py`
- The public `t3.confirm()` and `t3.ask()` in `t3api_utils/prompts.py`
- `T3Client.pick_license()` and `T3Client.pick_endpoint()` in `t3api_utils/client.py`
- The failed-rows table in `writes._show_invalid()` and the CLI tables in `t3api_utils/cli/main.py`
