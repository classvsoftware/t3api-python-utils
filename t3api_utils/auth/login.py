"""The interactive login flow, and its secret-key offer.

Runs from ``t3api login``, or from ``connect()`` in a terminal when no saved
credential is found.

1. Ask whether the user already has a secret key. If so, validate and save it.
2. Ask for the Metrc hostname, username and password, plus email or OTP only
   in states that need them (from ``GET /v2/states``).
3. Offer to create a secret key (default yes). Otherwise log in for a JWT,
   which lasts 24 hours. The Metrc password is never stored.
4. Optionally pick a default license for the profile.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import httpx2

from t3api_utils import _api, _console
from t3api_utils._http import build_client
from t3api_utils.auth.credentials import (
    BearerAuth,
    CredentialKind,
    SecretKeyAuth,
    is_otp_code,
    normalize_otp_seed,
    otp_code,
)
from t3api_utils.auth.secret_keys import create_secret_key
from t3api_utils.auth.states import fetch_states, normalize_hostname, requirements
from t3api_utils.auth.store import Profile, Store
from t3api_utils.errors import APIError, AuthError

CREDENTIALS_PATH = "/v2/auth/credentials"
WHOAMI_PATH = "/v2/auth/whoami"
LICENSES_PATH = "/v2/licenses"

StartAt = Literal["start", "offer"]


@dataclass
class LoginResult:
    auth: SecretKeyAuth | BearerAuth
    profile: Profile
    secret_location: str


def credentials_login(
    http: httpx2.Client,
    *,
    hostname: str,
    username: str,
    password: str,
    email: str | None = None,
    otp: str | None = None,
) -> str:
    """Log in with Metrc credentials and return a JWT (valid for 24 hours).

    ``otp`` is a 6-digit code, or an OTP seed that is turned into a code.
    """
    body: dict[str, str] = {"hostname": hostname, "username": username, "password": password}
    if email:
        body["email"] = email
    if otp:
        body["otp"] = otp.strip() if is_otp_code(otp) else otp_code(otp)
    data = _api.call(http, "POST", CREDENTIALS_PATH, json=body)
    return _api.require_field(data, "accessToken", f"POST {CREDENTIALS_PATH}")


def _whoami(http: httpx2.Client, auth: httpx2.Auth, kind: CredentialKind) -> dict[str, Any]:
    data = _api.call(http, "GET", WHOAMI_PATH, auth=auth, credential_kind=kind)
    return data if isinstance(data, dict) else {}


def _ask_hostname(states: list[dict[str, Any]] | None, default: str | None) -> str:
    if states:
        _console.info("Enter a state abbreviation (e.g. CA) or a Metrc hostname (e.g. ca.metrc.com).")
    while True:
        hostname = normalize_hostname(_console.ask("Metrc hostname", default=default), states)
        known = {str(s.get("hostname", "")).lower() for s in states or []}
        if not known or hostname in known:
            return hostname
        if _console.confirm(f"{hostname} isn't in T3's list of Metrc hostnames. Use it anyway?", default=False):
            return hostname


def _ask_otp_seed() -> str:
    _console.info(
        "This state needs a one-time password. A secret key needs your OTP seed: the "
        "base32 secret behind your authenticator app, not a 6-digit code. T3 uses it "
        "to sign in to Metrc for you later."
    )
    while True:
        try:
            return normalize_otp_seed(_console.ask("OTP seed", password=True))
        except ValueError as exc:
            _console.error(str(exc))


def _ask_otp() -> str:
    while True:
        value = _console.ask("6-digit code from your authenticator app (or your OTP seed)", password=True)
        if is_otp_code(value):
            return value
        try:
            return otp_code(value)
        except ValueError as exc:
            _console.error(str(exc))


def _pick_default_license(http: httpx2.Client, auth: httpx2.Auth, kind: CredentialKind) -> str | None:
    from t3api_utils.pickers import pick_license

    licenses = _api.call(http, "GET", LICENSES_PATH, auth=auth, credential_kind=kind)
    if not isinstance(licenses, list) or not licenses:
        _console.warning("No licenses are available to this account.")
        return None
    return pick_license(licenses)


def run_login(
    *,
    store: Store,
    profile_name: str,
    api_host: str,
    start_at: StartAt = "start",
    http_options: Mapping[str, Any] | None = None,
) -> LoginResult:
    """Run the login flow and save the result to ``profile_name``."""
    http = build_client(base_url=api_host, **dict(http_options or {}))
    try:
        return _run(http, store=store, profile_name=profile_name, api_host=api_host, start_at=start_at)
    finally:
        http.close()


def _save(
    store: Store, profile: Profile, kind: CredentialKind, secret: str
) -> str:
    location = store.set_secret(profile.name, kind, secret)
    other: CredentialKind = "jwt" if kind == "secret_key" else "secret_key"
    store.delete_secret(profile.name, other)
    profile.credential = kind
    store.save_profile(profile)
    if location == "file":
        _console.warning(
            f"No OS keyring is available, so the credential was saved to {store.secrets_path} "
            "(readable only by you)."
        )
    return location


def _run(
    http: httpx2.Client,
    *,
    store: Store,
    profile_name: str,
    api_host: str,
    start_at: StartAt,
) -> LoginResult:
    profile = store.get_profile(profile_name) or Profile(name=profile_name, api_host=api_host)
    profile.api_host = api_host
    _console.header(f"T3 login · profile {profile_name}")

    auth: SecretKeyAuth | BearerAuth
    kind: CredentialKind
    if start_at == "start" and _console.confirm("Do you already have a T3 secret key?", default=False):
        while True:
            auth = SecretKeyAuth(_console.ask("Paste your secret key", password=True))
            try:
                who = _whoami(http, auth, "secret_key")
                break
            except AuthError:
                _console.error("T3 rejected that secret key. Try again, or press Ctrl-C to stop.")
        profile.username = who.get("username") or profile.username
        profile.metrc_hostname = who.get("hostname") or profile.metrc_hostname
        location = _save(store, profile, "secret_key", auth.key)
        _console.success(f"Saved your secret key to profile {profile.name}.")
        kind = "secret_key"
    else:
        if start_at == "offer":
            _console.warning("Your saved login has expired. Log in again to continue.")
        states = fetch_states(http, api_host)
        hostname = _ask_hostname(states, profile.metrc_hostname)
        needs = requirements(hostname, states)
        username = _console.ask("Metrc username", default=profile.username)
        password = _console.ask("Metrc password", password=True)
        email = _console.ask("Metrc login email") if needs.requires_email else None

        if _console.confirm(
            "Create a secret key so you don't have to log in again?", default=True
        ):
            otp_seed = _ask_otp_seed() if needs.requires_otp else None
            key = create_secret_key(
                http, hostname=hostname, username=username, password=password, email=email, otp_seed=otp_seed
            )
            auth, kind = SecretKeyAuth(key), "secret_key"
            secret = key
        else:
            otp = _ask_otp() if needs.requires_otp else None
            token = credentials_login(
                http, hostname=hostname, username=username, password=password, email=email, otp=otp
            )
            auth, kind = BearerAuth(token), "jwt"
            secret = token
        profile.metrc_hostname = hostname
        profile.username = username
        location = _save(store, profile, kind, secret)
        if kind == "secret_key":
            _console.success(
                f"Created a secret key ({_console.mask_secret(secret)}) and saved it to profile "
                f"{profile.name}. Your Metrc password was not stored."
            )
        else:
            _console.success(f"Logged in. Saved the JWT to profile {profile.name}.")
            _console.warning(
                "JWTs expire after 24 hours, and you'll be asked to log in again. A secret key "
                "avoids this: run `t3api login` again and accept the offer."
            )

    if profile.license is None and _console.confirm(
        "Pick a default license for this profile?", default=True
    ):
        try:
            profile.license = _pick_default_license(http, auth, kind)
        except APIError as exc:
            _console.warning(f"Couldn't load licenses: {exc}")
        if profile.license:
            store.save_profile(profile)
            _console.success(f"Default license: {profile.license}")
    return LoginResult(auth=auth, profile=profile, secret_location=location)
