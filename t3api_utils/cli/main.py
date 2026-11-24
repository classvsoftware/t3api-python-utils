"""The ``t3api`` command."""

from __future__ import annotations

import functools
import logging
import os
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, ParamSpec, TypeVar

import typer
from rich.logging import RichHandler

import t3api_utils as t3
from t3api_utils import _console
from t3api_utils._console import console, out
from t3api_utils._http import DEFAULT_HOST, build_client
from t3api_utils.auth.login import run_login
from t3api_utils.auth.states import fetch_states, requirements
from t3api_utils.auth.store import Profile, Store
from t3api_utils.errors import T3Error, TagListResolveError
from t3api_utils.spec.loader import SpecMode, load_spec
from t3api_utils.spec.registry import KINDS, Registry

P = ParamSpec("P")
R = TypeVar("R")

app = typer.Typer(
    name="t3api",
    help="T3 API tools: log in, manage secret keys, pull collections, download reports, build tag lists.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
profiles_app = typer.Typer(help="Manage saved profiles.", no_args_is_help=True)
keys_app = typer.Typer(help="Manage secret keys.", no_args_is_help=True)
license_app = typer.Typer(help="Show or set the profile's default license.")
tag_lists_app = typer.Typer(help="Create and resolve tag lists.", no_args_is_help=True)
spec_app = typer.Typer(help="The OpenAPI spec copy in use.", no_args_is_help=True)
app.add_typer(profiles_app, name="profiles")
app.add_typer(keys_app, name="keys")
app.add_typer(license_app, name="license")
app.add_typer(tag_lists_app, name="tag-lists")
app.add_typer(spec_app, name="spec")

ProfileOpt = Annotated[
    str | None, typer.Option("--profile", "-p", help="Profile to use.", envvar="T3_PROFILE")
]
LicensesOpt = Annotated[
    list[str] | None, typer.Option("--license", "-l", help="License number. Repeat for several.")
]
OutputOpt = Annotated[
    Path | None, typer.Option("--output", "-o", help="File to write (.csv, .json or .jsonl).")
]


def handle_errors(fn: Callable[P, R]) -> Callable[P, R]:
    """Turn library errors into a red message and exit code 1."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except TagListResolveError as exc:
            _show_resolve_errors(exc)
            raise typer.Exit(1) from exc
        except (T3Error, ValueError, KeyError, FileNotFoundError, ImportError) as exc:
            message = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
            _console.error(str(message))
            raise typer.Exit(1) from exc
        except (KeyboardInterrupt, EOFError) as exc:
            _console.error("Cancelled.")
            raise typer.Exit(130) from exc

    return wrapper


def _version(value: bool) -> None:
    if value:
        out.print(f"t3api-utils {t3.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show progress logs.")] = False,
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show the version.")
    ] = False,
) -> None:
    logger = logging.getLogger("t3api_utils")
    if not any(isinstance(h, RichHandler) for h in logger.handlers):
        handler = RichHandler(console=console, show_time=False, show_path=False, markup=False)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO if verbose else logging.WARNING)
    logger.propagate = False


# --------------------------------------------------------------------------- helpers


def _store() -> Store:
    return Store()


def _profile_name(store: Store, profile: str | None) -> str:
    return profile or store.default_profile_name() or "default"


def _api_host(store: Store, profile: str | None) -> str:
    saved = store.get_profile(_profile_name(store, profile))
    return os.environ.get("T3_API_HOST") or (saved.api_host if saved else None) or DEFAULT_HOST


def _connect(profile: str | None, license: str | None = None) -> t3.T3Client:
    return t3.connect(profile, license=license, validate=False)


def _registry(profile: str | None) -> Registry:
    store = _store()
    host = _api_host(store, profile)
    mode: SpecMode = "bundled" if os.environ.get("T3_SPEC", "").lower() == "bundled" else "auto"
    with build_client(base_url=host) as http:
        raw, source = load_spec(http, host, mode)
    return Registry(raw, source)


def _group_profile(ctx: typer.Context) -> str | None:
    """A --profile given on a command group, before the subcommand."""
    obj = ctx.obj
    value = obj.get("profile") if isinstance(obj, dict) else None
    return value if isinstance(value, str) else None


def _require_profile(store: Store, profile: str | None) -> Profile:
    name = _profile_name(store, profile)
    saved = store.get_profile(name)
    if saved is None:
        raise T3Error(f"No profile named {name!r}. Run `t3api login --profile {name}`.")
    return saved


def _show_resolve_errors(exc: TagListResolveError) -> None:
    _console.error(exc.detail or str(exc))
    table = _console.table("Handles that didn't resolve")
    table.add_column("Handle", style="bright_white")
    table.add_column("Reason", style="cyan")
    table.add_column("Matches", style="cyan", justify="right")
    for item in exc.errors[:50]:
        if isinstance(item, dict):
            table.add_row(str(item.get("handle", "")), str(item.get("reason", "")), str(item.get("matchCount", "")))
    console.print(table)


def _write_rows(rows: list[dict[str, Any]], output: Path | None) -> Path:
    if output is not None and output.suffix.lower() == ".json":
        return t3.to_json(rows, output)
    if output is not None and output.suffix.lower() == ".jsonl":
        return t3.to_json(rows, output, lines=True)
    return t3.to_csv(rows, output)


# --------------------------------------------------------------------------- auth


@app.command()
@handle_errors
def login(
    profile: ProfileOpt = None,
    host: Annotated[str | None, typer.Option("--host", help="T3 API base URL.")] = None,
) -> None:
    """Log in and save a credential (a secret key, unless you decline)."""
    store = _store()
    name = _profile_name(store, profile)
    api_host = host or _api_host(store, profile)
    result = run_login(store=store, profile_name=name, api_host=api_host)
    default = store.default_profile_name()
    use = "t3.connect()" if default == name else f't3.connect(profile="{name}")'
    _console.info(f"Scripts can now call {use}.")
    if result.profile.credential == "jwt":
        _console.info("Run `t3api login` again any time to switch to a secret key.")


@app.command()
@handle_errors
def logout(
    profile: ProfileOpt = None,
    everywhere: Annotated[
        bool, typer.Option("--everywhere", help="Also log out all Metrc sessions (POST /v2/auth/logout).")
    ] = False,
) -> None:
    """Remove the profile's saved credential."""
    store = _store()
    saved = _require_profile(store, profile)
    if everywhere:
        with _connect(saved.name) as client:
            client._call("POST", "/v2/auth/logout")
        _console.success("Logged out of all Metrc sessions.")
    was_key = saved.credential == "secret_key"
    store.delete_secret(saved.name, "secret_key")
    store.delete_secret(saved.name, "jwt")
    saved.credential = None
    store.save_profile(saved, make_default=False)
    _console.success(f"Removed the saved credential from profile {saved.name}.")
    if was_key:
        _console.info("The secret key itself still works. Delete it with `t3api keys revoke` if it's no longer needed.")


@app.command()
@handle_errors
def whoami(profile: ProfileOpt = None) -> None:
    """Show the current user, profile and credential type."""
    with _connect(profile) as client:
        who = client.whoami()
        table = _console.table("Who am I")
        table.add_column("Field", style="bright_white")
        table.add_column("Value", style="cyan")
        if client.profile:
            table.add_row("profile", client.profile.name)
        table.add_row("credential", client.credential_kind or "none")
        table.add_row("api host", client.base_url)
        table.add_row("default license", client.license or "")
        for key in ("username", "hostname", "authMode", "hasT3plus", "t3plusSubscriptionTier", "subscriptionStatus"):
            if key in who:
                table.add_row(key, str(who[key]))
        out.print(table)


# --------------------------------------------------------------------------- profiles


@profiles_app.command("list")
@handle_errors
def profiles_list() -> None:
    """List saved profiles."""
    store = _store()
    profiles = store.profiles()
    if not profiles:
        _console.info("No profiles yet. Run `t3api login`.")
        return
    default = store.default_profile_name()
    table = _console.table("Profiles")
    table.add_column("Profile", style="bright_white")
    for column in ("Default", "Credential", "Metrc host", "Username", "License", "API host"):
        table.add_column(column, style="cyan")
    for p in sorted(profiles, key=lambda p: p.name):
        table.add_row(
            p.name,
            "✓" if p.name == default else "",
            p.credential or "none",
            p.metrc_hostname or "",
            p.username or "",
            p.license or "",
            p.api_host,
        )
    out.print(table)


@profiles_app.command("use")
@handle_errors
def profiles_use(name: str) -> None:
    """Make a profile the default."""
    _store().set_default(name)
    _console.success(f"Default profile: {name}")


@profiles_app.command("remove")
@handle_errors
def profiles_remove(name: str) -> None:
    """Delete a profile and its saved credential."""
    if not _store().remove_profile(name):
        raise T3Error(f"No profile named {name!r}.")
    _console.success(f"Removed profile {name}.")


# --------------------------------------------------------------------------- license


@license_app.callback(invoke_without_command=True)
@handle_errors
def license_show(ctx: typer.Context, profile: ProfileOpt = None) -> None:
    """Show the profile's default license."""
    if ctx.invoked_subcommand is not None:
        # `t3api license -p work pick` passes the profile on to the subcommand.
        ctx.obj = {"profile": profile}
        return
    saved = _require_profile(_store(), profile)
    if saved.license:
        out.print(saved.license, markup=False)
    else:
        _console.info(f"Profile {saved.name} has no default license. Set one with `t3api license pick`.")


@license_app.command("pick")
@handle_errors
def license_pick(ctx: typer.Context, profile: ProfileOpt = None) -> None:
    """Pick the profile's default license from the account's licenses."""
    profile = profile or _group_profile(ctx)
    store = _store()
    saved = _require_profile(store, profile)
    with _connect(saved.name) as client:
        saved.license = client.pick_license()
    store.save_profile(saved, make_default=False)
    _console.success(f"Default license for {saved.name}: {saved.license}")


@license_app.command("set")
@handle_errors
def license_set(ctx: typer.Context, license: str, profile: ProfileOpt = None) -> None:
    """Set the profile's default license."""
    profile = profile or _group_profile(ctx)
    store = _store()
    saved = _require_profile(store, profile)
    saved.license = license.strip()
    store.save_profile(saved, make_default=False)
    _console.success(f"Default license for {saved.name}: {saved.license}")


# --------------------------------------------------------------------------- keys


@keys_app.command("list")
@handle_errors
def keys_list(profile: ProfileOpt = None) -> None:
    """List the account's secret keys (masked)."""
    with _connect(profile) as client:
        keys = client.secret_keys.list()
        current = client.secret_key
    table = _console.table("Secret keys")
    table.add_column("Key", style="bright_white")
    for column in ("Enabled", "Managed", "Created", "Last used", "In use"):
        table.add_column(column, style="cyan")
    for k in keys:
        value = str(k.get("secretKey", ""))
        table.add_row(
            _console.mask_secret(value),
            "yes" if k.get("isEnabled") else "no",
            "yes" if k.get("isManaged") else "no",
            str(k.get("createdAt") or ""),
            str(k.get("lastUsedAt") or "never"),
            "✓" if value and value == current else "",
        )
    out.print(table)


def _ask_metrc(store: Store, saved: Profile | None, host: str) -> tuple[str, str, bool, bool]:
    with build_client(base_url=host) as http:
        states = fetch_states(http, host)
    from t3api_utils.auth.states import normalize_hostname

    hostname = normalize_hostname(
        _console.ask("Metrc hostname", default=saved.metrc_hostname if saved else None), states
    )
    username = _console.ask("Metrc username", default=saved.username if saved else None)
    needs = requirements(hostname, states)
    return hostname, username, needs.requires_email, needs.requires_otp


@keys_app.command("create")
@handle_errors
def keys_create(profile: ProfileOpt = None) -> None:
    """Create a secret key from Metrc credentials, and offer to save it."""
    from t3api_utils.auth.secret_keys import create_secret_key

    store = _store()
    name = _profile_name(store, profile)
    saved = store.get_profile(name)
    host = _api_host(store, profile)
    hostname, username, needs_email, needs_otp = _ask_metrc(store, saved, host)
    password = _console.ask("Metrc password", password=True)
    email = _console.ask("Metrc login email") if needs_email else None
    otp_seed = _console.ask("OTP seed (base32, not a 6-digit code)", password=True) if needs_otp else None
    with build_client(base_url=host) as http:
        key = create_secret_key(
            http, hostname=hostname, username=username, password=password, email=email, otp_seed=otp_seed
        )
    _console.success("Created a secret key. It is shown once here:")
    out.print(key, markup=False)
    if _console.confirm(f"Save it to profile {name}?", default=True):
        target = saved or Profile(name=name, api_host=host)
        target.metrc_hostname, target.username = hostname, username
        store.set_secret(name, "secret_key", key)
        store.delete_secret(name, "jwt")
        target.credential = "secret_key"
        store.save_profile(target)
        _console.success(f"Saved to profile {name}.")


@keys_app.command("rotate")
@handle_errors
def keys_rotate(
    key: Annotated[str | None, typer.Argument(help="The key to update. Defaults to the profile's.")] = None,
    profile: ProfileOpt = None,
) -> None:
    """Update the Metrc credentials behind a key (after a password, email or OTP change)."""
    store = _store()
    saved = store.get_profile(_profile_name(store, profile))
    target = (key or "").strip() or (store.get_secret(saved.name, "secret_key") if saved else None)
    if not target:
        raise T3Error("No secret key given and none saved in the profile.")
    host = _api_host(store, profile)
    hostname, username, needs_email, needs_otp = _ask_metrc(store, saved, host)
    password = _console.ask("New Metrc password", password=True)
    email = _console.ask("Metrc login email") if needs_email else None
    otp_seed = _console.ask("OTP seed (base32)", password=True) if needs_otp else None
    client = t3.T3Client(auth=t3.SecretKeyAuth(target), base_url=host, profile=saved)
    with client:
        client.secret_keys.rotate(
            target, password=password, username=username, hostname=hostname, email=email, otp_seed=otp_seed
        )
    _console.success(f"Updated the credentials behind {_console.mask_secret(target)}. The key value is unchanged.")


@keys_app.command("revoke")
@handle_errors
def keys_revoke(
    key: Annotated[str, typer.Argument(help="The secret key to delete.")],
    profile: ProfileOpt = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Don't ask for confirmation.")] = False,
) -> None:
    """Delete a secret key. Anything using it stops working."""
    key = key.strip()
    if not yes and not _console.confirm(
        f"Delete secret key {_console.mask_secret(key)}? Anything using it stops working.", default=False
    ):
        raise typer.Exit(1)
    store = _store()
    with _connect(profile) as client:
        client.secret_keys.delete(key)
    _console.success(f"Deleted {_console.mask_secret(key)}.")
    for p in store.profiles():
        if store.get_secret(p.name, "secret_key") == key:
            store.delete_secret(p.name, "secret_key")
            p.credential = None
            store.save_profile(p, make_default=False)
            _console.info(f"Removed it from profile {p.name}.")


# --------------------------------------------------------------------------- data


@app.command()
@handle_errors
def endpoints(
    query: Annotated[str, typer.Argument(help="Words to search for in IDs, paths and summaries.")] = "",
    kind: Annotated[str | None, typer.Option("--kind", "-k", help=f"One of: {', '.join(KINDS)}.")] = None,
    profile: ProfileOpt = None,
) -> None:
    """Search the endpoints in the T3 spec."""
    if kind is not None and kind not in KINDS:
        raise ValueError(f"--kind must be one of {', '.join(KINDS)}.")
    found = _registry(profile).find(query, kind)  # type: ignore[arg-type]
    table = _console.table(f"{len(found)} endpoint(s)")
    table.add_column("Endpoint", style="bright_white", no_wrap=True)
    table.add_column("Route", style="cyan", no_wrap=True)
    table.add_column("Kind", style="cyan", no_wrap=True)
    table.add_column("Summary", style="cyan", ratio=1)
    for ep in found:
        table.add_row(ep.id or "", f"{ep.method} {ep.path}", ep.kind, ep.summary)
    out.print(table)


@app.command()
@handle_errors
def pull(
    endpoint: Annotated[str | None, typer.Argument(help="Collection endpoint ID or path.")] = None,
    license: LicensesOpt = None,
    filter: Annotated[list[str] | None, typer.Option("--filter", "-f", help="field__op:value. Repeatable.")] = None,
    sort: Annotated[str | None, typer.Option("--sort", help="field:asc or field:desc.")] = None,
    mask: Annotated[str | None, typer.Option("--mask", help="Comma-separated fields to return.")] = None,
    output: OutputOpt = None,
    inspect: Annotated[bool, typer.Option("--inspect", help="Open the rows in the inspector.")] = False,
    profile: ProfileOpt = None,
) -> None:
    """Load a whole collection to CSV or JSON, or open it in the inspector."""
    with _connect(profile) as client:
        if endpoint is None:
            chosen = client.pick_endpoint("collection")
            endpoint = chosen.id or chosen.path
        licenses: list[str] | None = list(license) if license else None
        if licenses is None and client.license is None:
            ep = client.spec.endpoint(endpoint, method="GET", kind="collection")
            param = ep.param("licenseNumber")
            if param is not None and param.required and _console.is_interactive():
                licenses = [client.pick_license()]
        rows = client.collect(endpoint, license=licenses, filter=filter, sort=sort, mask=mask)
    if inspect:
        t3.inspect(rows, title=endpoint)
        return
    path = _write_rows(rows, output)
    _console.success(f"Wrote {len(rows):,} rows to {path}")


@app.command()
@handle_errors
def report(
    endpoint: Annotated[str, typer.Argument(help="Report endpoint ID or path, e.g. ITEMS_REPORT.")],
    license: LicensesOpt = None,
    format: Annotated[str | None, typer.Option("--format", help="csv, xlsx, json or googleSheets.")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="File to write.")] = None,
    columns: Annotated[str | None, typer.Option("--columns", help="Comma-separated columns.")] = None,
    filter: Annotated[list[str] | None, typer.Option("--filter", "-f", help="field__op:value. Repeatable.")] = None,
    sort: Annotated[str | None, typer.Option("--sort")] = None,
    url: Annotated[bool, typer.Option("--url", help="Print a URL with the secret key instead.")] = False,
    profile: ProfileOpt = None,
) -> None:
    """Download a server-side report, or print its secret-key URL with --url."""
    with _connect(profile) as client:
        licenses = list(license) if license else None
        if url:
            out.print(
                client.report_url(
                    endpoint, licenses=licenses, format=format or "csv", columns=columns, filter=filter, sort=sort
                ),
                soft_wrap=True,
                markup=False,
            )
            _console.warning("Anyone with this URL can use your secret key. Delete the key to cut it off.")
            return
        if format == "googleSheets":
            sheet = client.report(endpoint, licenses=licenses, format=format, columns=columns, filter=filter, sort=sort)
            out.print(str(sheet), soft_wrap=True, markup=False)
            return
        fmt = format or (output.suffix.lstrip(".").lower() if output else "csv") or "csv"
        target = output or Path(f"{endpoint.strip('/').replace('/', '_')}__{datetime.now():%Y-%m-%dT%H-%M-%S}.{fmt}")
        path = client.report(
            endpoint, licenses=licenses, format=fmt, to=target, columns=columns, filter=filter, sort=sort
        )
    _console.success(f"Saved the report to {path}")


@app.command("inspect")
@handle_errors
def inspect_file(path: Annotated[Path, typer.Argument(help="A JSON, JSONL or CSV file.")]) -> None:
    """Open a JSON or CSV file in the inspector."""
    t3.inspect(t3.read_rows(path), title=path.name)


# --------------------------------------------------------------------------- tag lists


@tag_lists_app.command("list")
@handle_errors
def tag_lists_list(
    license: Annotated[str | None, typer.Option("--license", "-l")] = None,
    profile: ProfileOpt = None,
) -> None:
    """List your tag lists."""
    with _connect(profile) as client:
        lists = client.tag_lists.list(license=license)
    table = _console.table("Tag lists")
    table.add_column("ID", style="bright_white")
    for column in ("Name", "License", "Endpoint", "Entries", "Scanned"):
        table.add_column(column, style="cyan")
    for tl in lists:
        table.add_row(
            str(tl.get("id", "")),
            str(tl.get("name", "")),
            str(tl.get("licenseNumber", "")),
            str(tl.get("t3EndpointId") or ""),
            str(tl.get("entryCount", "")),
            str(tl.get("scannedCount", "")),
        )
    out.print(table)


@tag_lists_app.command("create")
@handle_errors
def tag_lists_create(
    file: Annotated[Path, typer.Argument(help="CSV or TSV file.")],
    column: Annotated[str, typer.Option("--column", "-c", help="Column holding the handles.")],
    name: Annotated[str | None, typer.Option("--name", help="List name. Defaults to the file name.")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint", "-e", help="Default endpoint ID to resolve against.")] = None,
    license: Annotated[str | None, typer.Option("--license", "-l")] = None,
    shared: Annotated[bool, typer.Option("--shared", help="Visible to everyone with access to the license.")] = False,
    profile: ProfileOpt = None,
) -> None:
    """Create a tag list from one column of a CSV file."""
    with _connect(profile, license) as client:
        tl = client.tag_lists.from_csv(
            file, column, name=name, license=license, endpoint=endpoint, visibility="LICENSE" if shared else "USER"
        )
    _console.success(f"Created tag list {tl.name!r} with {tl.data.get('entryCount', '?')} entries.")
    out.print(tl.id, markup=False)


@tag_lists_app.command("resolve")
@handle_errors
def tag_lists_resolve(
    list_id: Annotated[str, typer.Argument(help="Tag list ID.")],
    endpoint: Annotated[str | None, typer.Option("--endpoint", "-e", help="Endpoint ID to resolve against.")] = None,
    output: OutputOpt = None,
    profile: ProfileOpt = None,
) -> None:
    """Resolve a tag list to its objects and save them."""
    with _connect(profile) as client:
        rows = client.tag_lists.resolve(list_id, endpoint)
    path = _write_rows(rows, output)
    _console.success(f"Resolved {len(rows):,} objects to {path}")


# --------------------------------------------------------------------------- spec


@spec_app.command("info")
@handle_errors
def spec_info(profile: ProfileOpt = None) -> None:
    """Show which copy of the spec is in use and how old it is."""
    registry = _registry(profile)
    source = registry.source
    out.print(f"Spec: {source.describe() if source else 'unknown'}")
    if registry.version:
        out.print(f"Version: {registry.version}")
    counts: Counter[str] = Counter(str(ep.kind) for ep in registry.endpoints)
    table = _console.table(f"{len(registry.endpoints)} operations")
    table.add_column("Kind", style="bright_white")
    table.add_column("Count", style="cyan", justify="right")
    for kind in KINDS:
        table.add_row(kind, str(counts.get(kind, 0)))
    out.print(table)


@spec_app.command("refresh")
@handle_errors
def spec_refresh(profile: ProfileOpt = None) -> None:
    """Fetch the live spec now and cache it."""
    store = _store()
    host = _api_host(store, profile)
    with build_client(base_url=host) as http:
        raw, source = load_spec(http, host, "refresh")
    _console.success(f"Fetched the spec from {host}: {len(Registry(raw, source).endpoints)} operations.")
