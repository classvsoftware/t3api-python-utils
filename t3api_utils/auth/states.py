"""Which Metrc states need an email or a one-time password to log in.

``GET /v2/states`` is public and reports ``requiresEmail`` and ``requiresOtp``
for every state. The result is cached next to the spec. If the API can't be
reached, the 1.x lists are the fallback.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx2

from t3api_utils import _paths
from t3api_utils.spec.loader import _atomic_write, host_key

logger = logging.getLogger("t3api_utils")

STATES_PATH = "/v2/states"
STATES_TTL = 7 * 24 * 3600.0
FETCH_TIMEOUT = 5.0

FALLBACK_OTP = frozenset({"mi.metrc.com"})
FALLBACK_EMAIL = frozenset({"co.metrc.com"})


@dataclass(frozen=True)
class LoginRequirements:
    hostname: str
    requires_email: bool
    requires_otp: bool
    state_name: str | None = None
    source: Literal["api", "fallback"] = "api"


def _cache_file(base_url: str) -> Path:
    return _paths.cache_dir() / "states" / f"{host_key(base_url)}.json"


def fetch_states(
    http: httpx2.Client,
    base_url: str,
    *,
    now: Callable[[], float] = time.time,
    refresh: bool = False,
) -> list[dict[str, Any]] | None:
    """Every Metrc state from ``GET /v2/states``, cached for a week. ``None`` if unavailable."""
    cache = _cache_file(base_url)
    cached: dict[str, Any] | None = None
    try:
        loaded = json.loads(cache.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("states"), list):
            cached = loaded
    except (OSError, ValueError):
        cached = None
    if cached is not None and not refresh and now() - float(cached.get("fetched_at", 0)) < STATES_TTL:
        states: list[dict[str, Any]] = cached["states"]
        return states

    try:
        response = http.get(base_url.rstrip("/") + STATES_PATH, timeout=FETCH_TIMEOUT)
        response.raise_for_status()
        fresh = response.json()
        if not isinstance(fresh, list):
            raise ValueError("expected a list of states")
    except (httpx2.HTTPError, ValueError) as exc:
        logger.info("Couldn't load %s (%s).", STATES_PATH, exc)
        if cached is not None:
            stale: list[dict[str, Any]] = cached["states"]
            return stale
        return None

    rows = [s for s in fresh if isinstance(s, dict)]
    try:
        _atomic_write(cache, json.dumps({"fetched_at": now(), "states": rows}).encode())
    except OSError as exc:
        logger.debug("Couldn't cache %s: %s", STATES_PATH, exc)
    return rows


def normalize_hostname(value: str, states: list[dict[str, Any]] | None = None) -> str:
    """Turn ``CA``, ``ca``, ``https://ca.metrc.com/`` or ``ca.metrc.com`` into ``ca.metrc.com``."""
    text = value.strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    text = text.split("/", 1)[0]
    for state in states or []:
        abbreviation = str(state.get("abbreviation", "")).lower()
        name = str(state.get("name", "")).lower()
        if text and text in (abbreviation, name):
            return str(state.get("hostname", text)).lower()
    if text and "." not in text and len(text) == 2:
        return f"{text}.metrc.com"
    return text


def requirements(hostname: str, states: list[dict[str, Any]] | None) -> LoginRequirements:
    """What a login to ``hostname`` needs besides username and password."""
    hostname = hostname.lower()
    for state in states or []:
        if str(state.get("hostname", "")).lower() == hostname:
            return LoginRequirements(
                hostname=hostname,
                requires_email=bool(state.get("requiresEmail")),
                requires_otp=bool(state.get("requiresOtp")),
                state_name=state.get("name"),
                source="api",
            )
    return LoginRequirements(
        hostname=hostname,
        requires_email=hostname in FALLBACK_EMAIL,
        requires_otp=hostname in FALLBACK_OTP,
        source="fallback",
    )
