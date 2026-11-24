"""Secret key management: list, create, rotate and delete.

A secret key's ID is the key value itself, so rotate and delete take the key.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx2

from t3api_utils import _api
from t3api_utils.auth.credentials import normalize_otp_seed

if TYPE_CHECKING:
    from t3api_utils.client import T3Client

SECRET_KEY_PATH = "/v2/auth/secretkey"


def _payload(
    *,
    hostname: str,
    username: str,
    password: str,
    email: str | None,
    otp_seed: str | None,
) -> dict[str, str]:
    body = {"hostname": hostname, "username": username, "password": password}
    if email:
        body["email"] = email
    if otp_seed:
        body["otpSeed"] = normalize_otp_seed(otp_seed)
    return body


def create_secret_key(
    http: httpx2.Client,
    *,
    hostname: str,
    username: str,
    password: str,
    email: str | None = None,
    otp_seed: str | None = None,
) -> str:
    """Create a secret key from Metrc credentials. Needs no prior auth.

    In states that need a one-time password, pass the OTP *seed* (the base32
    secret behind the authenticator app), not a 6-digit code: T3 signs in to
    Metrc on your behalf later.
    """
    data = _api.call(
        http,
        "POST",
        SECRET_KEY_PATH,
        json=_payload(
            hostname=hostname, username=username, password=password, email=email, otp_seed=otp_seed
        ),
    )
    return _api.require_field(data, "secretKey", f"POST {SECRET_KEY_PATH}")


class SecretKeys:
    """``client.secret_keys``: manage the account's secret keys."""

    def __init__(self, client: T3Client) -> None:
        self._client = client

    def list(self) -> list[dict[str, Any]]:
        """Every secret key on the account, with ``isEnabled``, ``isManaged`` and ``lastUsedAt``."""
        data = self._client._call("GET", SECRET_KEY_PATH)
        rows: list[dict[str, Any]] = data.get("data", []) if isinstance(data, dict) else []
        return rows

    def create(
        self,
        hostname: str,
        username: str,
        password: str,
        email: str | None = None,
        otp_seed: str | None = None,
    ) -> str:
        """Create a secret key and return it. See :func:`create_secret_key`."""
        return create_secret_key(
            self._client.http,
            hostname=hostname,
            username=username,
            password=password,
            email=email,
            otp_seed=otp_seed,
        )

    def rotate(
        self,
        key: str,
        *,
        password: str,
        username: str | None = None,
        hostname: str | None = None,
        email: str | None = None,
        otp_seed: str | None = None,
    ) -> dict[str, Any]:
        """Update the Metrc credentials behind a key after a password, email or OTP change.

        The key value doesn't change. ``username`` and ``hostname`` default to
        the profile's, then to ``whoami``.
        """
        profile = self._client.profile
        username = username or (profile.username if profile else None)
        hostname = hostname or (profile.metrc_hostname if profile else None)
        if not username or not hostname:
            who = self._client.whoami()
            username = username or who.get("username")
            hostname = hostname or who.get("hostname")
        if not username or not hostname:
            raise ValueError("rotate() needs username= and hostname=.")
        data = self._client._call(
            "PUT",
            f"{SECRET_KEY_PATH}/{quote(key.strip(), safe='')}",
            json=_payload(
                hostname=hostname, username=username, password=password, email=email, otp_seed=otp_seed
            ),
        )
        result: dict[str, Any] = data if isinstance(data, dict) else {}
        return result

    def delete(self, key: str) -> dict[str, Any]:
        """Delete a key. Managed keys can't be deleted (the server answers 403)."""
        data = self._client._call("DELETE", f"{SECRET_KEY_PATH}/{quote(key.strip(), safe='')}")
        result: dict[str, Any] = data if isinstance(data, dict) else {}
        return result
