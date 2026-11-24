"""Credentials as httpx2.Auth classes, plus JWT and OTP helpers."""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx2
import pyotp

from t3api_utils._console import mask_secret

CredentialKind = Literal["secret_key", "jwt"]

SECRET_KEY_HEADER = "X-T3-API-Key"


class SecretKeyAuth(httpx2.Auth):
    """Sends a T3 secret key in the ``X-T3-API-Key`` header."""

    kind: CredentialKind = "secret_key"

    def __init__(self, key: str) -> None:
        key = key.strip()
        if not key:
            raise ValueError("The secret key is empty.")
        self.key = key

    def auth_flow(self, request: httpx2.Request) -> Generator[httpx2.Request, httpx2.Response, None]:
        request.headers[SECRET_KEY_HEADER] = self.key
        yield request

    def __repr__(self) -> str:
        return f"SecretKeyAuth({mask_secret(self.key)!r})"


class BearerAuth(httpx2.Auth):
    """Sends a JWT in the ``Authorization: Bearer`` header."""

    kind: CredentialKind = "jwt"

    def __init__(self, token: str) -> None:
        token = re.sub(r"^bearer(?:\s+|$)", "", token.strip(), flags=re.IGNORECASE)
        if not token:
            raise ValueError("The JWT is empty.")
        self.token = token

    @property
    def expires_at(self) -> datetime | None:
        return jwt_expiry(self.token)

    def auth_flow(self, request: httpx2.Request) -> Generator[httpx2.Request, httpx2.Response, None]:
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request

    def __repr__(self) -> str:
        return f"BearerAuth({mask_secret(self.token)!r})"


def credential_kind(auth: httpx2.Auth | None) -> CredentialKind | None:
    if isinstance(auth, SecretKeyAuth):
        return "secret_key"
    if isinstance(auth, BearerAuth):
        return "jwt"
    return None


def jwt_expiry(token: str) -> datetime | None:
    """The ``exp`` claim of a JWT, without verifying it. ``None`` if unreadable."""
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return datetime.fromtimestamp(float(claims["exp"]), tz=UTC)
    except (binascii.Error, ValueError, KeyError, TypeError, OverflowError, OSError):
        return None


def jwt_expired(token: str, *, leeway: timedelta = timedelta(minutes=1), now: datetime | None = None) -> bool:
    """True if the JWT's ``exp`` has passed. A JWT without a readable ``exp`` counts as live."""
    expiry = jwt_expiry(token)
    if expiry is None:
        return False
    return (now or datetime.now(UTC)) >= expiry - leeway


_OTP_CODE = re.compile(r"^\d{6}$")


def is_otp_code(value: str) -> bool:
    return bool(_OTP_CODE.match(value.strip()))


def normalize_otp_seed(seed: str) -> str:
    """Strip spaces and dashes and uppercase a base32 OTP seed; raise ValueError if invalid."""
    cleaned = re.sub(r"[\s-]", "", seed).upper()
    if not cleaned:
        raise ValueError("The OTP seed is empty.")
    try:
        base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            "That isn't a valid OTP seed. It's the base32 secret behind your "
            "authenticator app (letters A-Z and digits 2-7), not a 6-digit code."
        ) from exc
    return cleaned


class _TOTP(pyotp.TOTP):
    """``pyotp.TOTP`` without its 112-bit seed minimum (pyotp >= 2.12).

    The seed is whatever Metrc issued, and authenticator apps accept the common
    80-bit (16-character) seeds, so a code must be computable for them too.
    """

    min_secret_length_bits = 0


def otp_code(seed: str) -> str:
    """The current 6-digit code for an OTP seed."""
    return str(_TOTP(normalize_otp_seed(seed)).now())
