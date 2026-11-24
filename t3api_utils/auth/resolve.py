"""``connect()``: find a credential and return a ready T3Client.

Order: ``secret_key=``/``jwt=`` arguments, then ``T3_SECRET_KEY``/``T3_JWT``,
then the profile's saved secret key or unexpired JWT, then the login flow (only
in a terminal), else :class:`~t3api_utils.errors.AuthRequired`.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

import httpx2

from t3api_utils import _console
from t3api_utils._http import DEFAULT_HOST, DEFAULT_TIMEOUT, env_flag
from t3api_utils.auth.credentials import BearerAuth, SecretKeyAuth, jwt_expired
from t3api_utils.auth.login import StartAt, run_login
from t3api_utils.auth.store import Profile, Store
from t3api_utils.client import T3Client
from t3api_utils.errors import AuthRequired

logger = logging.getLogger("t3api_utils")

SETUP_HELP = (
    "No T3 credential found. Do one of these:\n"
    "  • Run `t3api login` in a terminal. It saves a secret key to a profile.\n"
    "  • Set T3_SECRET_KEY (best for scheduled jobs and CI).\n"
    "  • Pass connect(secret_key=...).\n"
    "Secret keys can also be created at https://api.trackandtrace.tools/v2/pages/secret-key"
)


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def connect(
    profile: str | None = None,
    *,
    secret_key: str | None = None,
    jwt: str | None = None,
    api_host: str | None = None,
    license: str | None = None,
    interactive: bool | None = None,
    validate: bool = True,
    sandbox: bool | None = None,
    spec: Literal["auto", "bundled"] | None = None,
    rate_limit: float | None = 10.0,
    concurrency: int = 10,
    timeout: float = DEFAULT_TIMEOUT,
    log_http: bool | None = None,
    transport: httpx2.BaseTransport | None = None,
    verify: bool | str = True,
    proxy: str | None = None,
) -> T3Client:
    """Find a credential and return a validated :class:`T3Client`.

    Args:
        profile: Saved profile to use. Defaults to ``T3_PROFILE``, then the
            config's default profile.
        secret_key: Use this secret key. Wins over everything else.
        jwt: Use this JWT.
        api_host: T3 API base URL. Defaults to ``T3_API_HOST``, then the
            profile's, then ``https://api.trackandtrace.tools``.
        license: Default license for calls that need one. Defaults to
            ``T3_LICENSE``, then the profile's, except in the sandbox, where
            only this argument counts.
        interactive: ``False`` never prompts; ``True`` always may. By default
            it prompts only in a terminal or Jupyter.
        validate: Check the credential with ``GET /v2/auth/whoami``.
        sandbox: Exchange the credential for a Metrc sandbox JWT. Defaults to
            ``T3_SANDBOX`` (``1``, ``true``, ``yes`` or ``on``). In the sandbox,
            ``T3_LICENSE`` and the profile's license are ignored, since a
            production license there returns no rows rather than an error.
        spec: ``"bundled"`` pins the spec that ships with the package.
            Defaults to ``T3_SPEC``, then ``"auto"``.
        rate_limit: Requests per second across all threads. ``None`` disables it.
        concurrency: Threads used to fetch collection pages.
        timeout: Request timeout in seconds.
        log_http: Log every request and response at DEBUG, with secrets
            masked. Defaults to ``T3_LOG_HTTP``.
        transport: An ``httpx2`` transport to use instead of the network.
        verify: TLS verification, as in httpx2.
        proxy: Proxy URL, as in httpx2.

    Raises:
        AuthRequired: no credential and no terminal to ask in.
        AuthError: the credential was rejected.
    """
    store = Store()
    named = profile or _env("T3_PROFILE")
    profile_name = named or store.default_profile_name()
    saved: Profile | None = store.get_profile(profile_name) if profile_name else None

    auth: SecretKeyAuth | BearerAuth | None = None
    from_profile = False
    expired = False
    if secret_key:
        auth = SecretKeyAuth(secret_key)
    elif jwt:
        auth = BearerAuth(jwt)
    elif env_key := _env("T3_SECRET_KEY"):
        auth = SecretKeyAuth(env_key)
    elif env_jwt := _env("T3_JWT"):
        auth = BearerAuth(env_jwt)
    elif saved is not None:
        if saved.credential == "secret_key":
            stored = store.get_secret(saved.name, "secret_key")
            if stored:
                auth, from_profile = SecretKeyAuth(stored), True
        elif saved.credential == "jwt":
            token = store.get_secret(saved.name, "jwt")
            if token and not jwt_expired(token):
                auth, from_profile = BearerAuth(token), True
            elif token:
                expired = True

    # A profile's settings apply when its credential is used, when it was asked
    # for by name, or when the login flow is about to save into it.
    use_profile = saved if (from_profile or named or auth is None) else None
    base_url = api_host or _env("T3_API_HOST") or (use_profile.api_host if use_profile else None)
    base_url = base_url or DEFAULT_HOST

    http_options: dict[str, Any] = {"transport": transport, "verify": verify, "proxy": proxy}
    if auth is None:
        can_prompt = _console.is_interactive() if interactive is None else interactive
        if not can_prompt:
            message = SETUP_HELP
            if named and saved is None:
                message = f"There is no saved profile named {named!r}.\n" + message
            if expired:
                message = f"The JWT saved in profile {profile_name!r} has expired.\n" + message
            raise AuthRequired(message)
        start_at: StartAt = "offer" if expired else "start"
        result = run_login(
            store=store,
            profile_name=profile_name or "default",
            api_host=base_url,
            start_at=start_at,
            http_options=http_options,
        )
        auth, use_profile = result.auth, result.profile

    use_sandbox = env_flag("T3_SANDBOX") if sandbox is None else sandbox
    saved_license = _env("T3_LICENSE") or (use_profile.license if use_profile else None)
    default_license = license if use_sandbox else (license or saved_license)
    if use_sandbox and not license and saved_license:
        logger.info(
            "Not using default license %s in the sandbox. Pass license= with a sandbox license.",
            saved_license,
        )
    spec_mode = spec or ("bundled" if (_env("T3_SPEC") or "").lower() == "bundled" else "auto")
    client = T3Client(
        auth=auth,
        base_url=base_url,
        license=default_license,
        profile=use_profile,
        spec=spec_mode,
        rate_limit=rate_limit,
        concurrency=concurrency,
        timeout=timeout,
        log_http=env_flag("T3_LOG_HTTP") if log_http is None else log_http,
        **http_options,
    )
    try:
        if use_sandbox:
            # Clears the default license and calls whoami, which validates.
            client.enter_sandbox()
            client.license = license
        elif validate:
            client.whoami()
    except BaseException:
        client.close()
        raise
    return client
